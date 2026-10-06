#!/usr/bin/env python3
"""Single authorized saved-artifact read for the v2 ancestry logger.

This program never launches a solver. It is deliberately unusable until a
one-use authorization binds terminal receipts and all 99 saved artifacts.
"""
import argparse
import collections
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLAN_PATH = HERE / 'plan.json'

INT_FIELDS = ('seq phase reason layer pass_id block_id slot_id batch_id buffer_i '
              'outer_j encoded_MOL isotope original_IFLAG JRAD ILNFLG').split()
REAL_FIELDS = ('VFT VBOT VTOP input_VNU adjusted_VNU input_line_strength '
               'prethermal_SUI corrected_SUI YI GI PAVP0 PAVP2 ALFL ALFV '
               'RECALF ZETA SP SPPSP EPP BETACR SCOR XKT TAVE PAVE TEMP0 P0').split()
IDENTITY_FIELDS = ('pass_id block_id slot_id batch_id buffer_i encoded_MOL isotope original_IFLAG').split()
SELECTED_VFT = 662.695395555556


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def verify(pin):
    p = Path(pin['path'])
    if not p.is_absolute():
        p = ROOT / p
    p = p.resolve(strict=True)
    require(p.is_file(), 'pin is not a regular file: ' + str(p))
    require(type(pin.get('size_bytes')) is int and p.stat().st_size == pin['size_bytes'],
            'pin size mismatch: ' + str(p))
    require(sha(p) == pin.get('sha256'), 'pin digest mismatch: ' + str(p))
    return p


def pin_path(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': sha(path), 'size_bytes': path.stat().st_size}


def terminal(execution_pin, run_dir):
    p = verify(execution_pin)
    e = json.loads(p.read_text())
    require(e.get('status') in ('TERMINAL', 'CHILD_RC0', 'CHILDRC0'), 'execution is not terminal')
    rc = e.get('actual_child_returncode', e.get('actual_child_RC'))
    require(type(rc) is int and rc == 0, 'terminal actual child RC is not zero')
    require(e.get('timed_out', e.get('timeout')) is False, 'execution timeout is not explicitly false')
    require(e.get('exception') is None, 'execution exception is present')
    require(e.get('reaped') is True, 'child is not confirmed reaped')
    require(type(e.get('pid')) is int and e['pid'] > 0, 'execution PID missing')
    require(Path(e.get('cwd', '')).resolve() == Path(run_dir).resolve(), 'execution cwd differs from run directory')
    return e


def atomic_json(path, obj):
    path = Path(path)
    with path.open('x', encoding='utf-8') as f:
        json.dump(obj, f, sort_keys=True, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def load_helper(pin):
    p = verify(pin)
    spec = importlib.util.spec_from_file_location('pinned_candidate_reader', p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    for name in ('candidate_rows', 'term_rows', 'join', 'spectra', 'require'):
        require(callable(getattr(mod, name, None)), 'pinned helper API missing ' + name)
    return mod


def load_allowlist(pin):
    p = verify(pin)
    doc = json.loads(p.read_text())
    require(doc.get('schema') == 'UDM37_DERIVED_ANCESTRY_ID_ALLOWLIST_V2', 'allowlist schema')
    fields = doc.get('fields')
    require(fields == IDENTITY_FIELDS, 'allowlist identity schema mismatch')
    rows = doc.get('identities')
    require(type(rows) is list and len(rows) == 72, 'allowlist must have 72 identities')
    allowed = {}
    groups = collections.Counter()
    for row in rows:
        key = tuple(row[k] for k in IDENTITY_FIELDS)
        require(key not in allowed, 'duplicate allowlist identity')
        group = row.get('group')
        require(group in ('left_censored_prefix69', 'dominant_negative3'), 'unknown ancestry group')
        allowed[key] = group
        groups[group] += 1
    require(groups == {'left_censored_prefix69': 69, 'dominant_negative3': 3}, 'allowlist group counts')
    return allowed


def parse_ancestry(path, allowed):
    rows = []
    sequence = 0
    event_keys = collections.Counter()
    with Path(path).open('r', encoding='ascii') as f:
        for line_no, line in enumerate(f, 1):
            tok = line.split()
            require(len(tok) == 42 and tok[0] == 'UDM37ANC1', 'ancestry record schema at line ' + str(line_no))
            require(all(re.fullmatch(r'[+-]?\d+', x) for x in tok[1:16]), 'ancestry integer token')
            ints = [int(x) for x in tok[1:16]]
            require(all(-(1 << 63) <= x < (1 << 63) for x in ints), 'ancestry integer8 range')
            vals = [float(x.replace('D', 'E').replace('d', 'e')) for x in tok[16:]]
            require(all(math.isfinite(x) for x in vals), 'nonfinite ancestry operand')
            d = dict(zip(INT_FIELDS, ints))
            d.update(zip(REAL_FIELDS, vals))
            require(d['seq'] == sequence + 1, 'ancestry sequence is not contiguous/unique')
            sequence += 1
            require((d['phase'], d['reason'], d['layer']) == (2, 9, 21), 'unexpected ancestry source site')
            key = tuple(d[k] for k in IDENTITY_FIELDS)
            require(key in allowed, 'unallowlisted ancestry identity')
            require(d['pass_id'] == 21 and d['buffer_i'] == d['slot_id'], 'ancestry pass/buffer identity')
            require(d['isotope'] == (d['encoded_MOL'] % 1000) // 100, 'encoded isotope mismatch')
            d['group'] = allowed[key]
            d['line'] = line_no
            ek = key + (d['VFT'], d['outer_j'])
            event_keys[ek] += 1
            rows.append(d)
    require(rows, 'ancestry ledger empty')
    return rows, {'record_count': len(rows), 'unique_identity_count': len({tuple(r[k] for k in IDENTITY_FIELDS) for r in rows}),
                  'event_duplicate_keys': sum(n > 1 for n in event_keys.values()),
                  'duplicate_event_occurrences': sum(n - 1 for n in event_keys.values() if n > 1),
                  'group_record_counts': dict(collections.Counter(r['group'] for r in rows)),
                  'group_identity_coverage': {g: len({tuple(r[k] for k in IDENTITY_FIELDS) for r in rows if r['group'] == g})
                                              for g in ('left_censored_prefix69', 'dominant_negative3')}}


def identity(row):
    return tuple(row[k] for k in IDENTITY_FIELDS)


def f64bits(value):
    return struct.pack('<d', value)


def compare_candidate_ledgers(candidate_path, baseline_path):
    """Strict token comparison except undefined LNCOR IPANEL/IDATA metadata.

    In LNCOR the local COMMON declaration exposes only VBOT/VTOP/VFT plus
    DUM(7); IPANEL and IDATA are not initialized/bound there. The candidate
    observer has phase-2 hooks for reasons 2..9, so only those two token
    positions on those diagnostic rows are exempted. No physical field is.
    """
    new_lines = Path(candidate_path).read_text(encoding='ascii').splitlines()
    old_lines = Path(baseline_path).read_text(encoding='ascii').splitlines()
    require(len(new_lines) == len(old_lines), 'candidate trace record count changed')
    allowed_positions = {14, 15}  # full whitespace-token positions including tag at 0
    allowed_rows = differences = 0
    changed_values = []
    for line_no, (new_line, old_line) in enumerate(zip(new_lines, old_lines), 1):
        nt, ot = new_line.split(), old_line.split()
        require(len(nt) == len(ot) == 38 and nt[0] == ot[0] == 'UDM37CAND1',
                'candidate trace layout/tag changed at line ' + str(line_no))
        phase, reason = int(nt[1]), int(nt[2])
        delta = [i for i, (a, b) in enumerate(zip(nt, ot)) if a != b]
        if delta:
            require(phase == 2 and reason in {2, 3, 4, 5, 6, 7, 8, 9},
                    'candidate data changed outside LNCOR phase-2 diagnostics at line ' + str(line_no))
            require(set(delta) <= allowed_positions, 'candidate field changed beyond undefined IPANEL/IDATA at line ' + str(line_no))
            def masked_fixed_metadata_fields(raw):
                spans = list(re.finditer(r'\S+', raw))
                require(len(spans) == 38, 'candidate fixed-field layout at line ' + str(line_no))
                # IPANEL and IDATA occupy I21 fields 14 and 15. Their entire
                # field bytes, including sign/leading padding, are undefined
                # local metadata. Keep every byte before field 14 and after
                # field 15 exact; do not normalize general line whitespace.
                require(spans[13].end() <= spans[14].start() <= spans[14].end() <= spans[15].start() <= spans[15].end(),
                        'candidate metadata field spans at line ' + str(line_no))
                return raw[:spans[13].end()] + '<IPANEL_I21><IDATA_I21>' + raw[spans[15].end():]
            require(masked_fixed_metadata_fields(new_line) == masked_fixed_metadata_fields(old_line),
                    'candidate bytes differ outside complete undefined I21 fields at line ' + str(line_no))
            allowed_rows += 1
            differences += len(delta)
            changed_values.append({'line': line_no,
                                   'fields': [{'token_index': i, 'candidate': nt[i], 'baseline': ot[i]}
                                              for i in delta]})
        else:
            require(new_line == old_line, 'candidate line formatting changed without token difference at line ' + str(line_no))
    return {'byte_sha256_equal': sha(Path(candidate_path)) == sha(Path(baseline_path)),
            'strict_byte_identity_failure_preserved': sha(Path(candidate_path)) != sha(Path(baseline_path)),
            'record_counts_equal': True, 'token_fields_equal_except_undefined_LNCOR_metadata': True,
            'undefined_field_allowlist': ['IPANEL', 'IDATA'], 'allowed_token_positions': sorted(allowed_positions),
            'allowed_candidate_event_scope': 'phase=2 and reason in 2..9 only',
            'masked_byte_scope': 'complete I21 fields 14 and 15 including leading padding; all prefix/suffix bytes remain exact',
            'rows_with_allowed_metadata_difference': allowed_rows,
            'allowed_token_differences': differences, 'difference_samples': changed_values[:12]}


def ancestry_joins(anc, candidate_rows, terms, allowed):
    selected_entries = []
    for d in candidate_rows:
        if d['phase'] == 3 and d['reason'] == 12 and abs(d['vft'] - SELECTED_VFT) < 1e-10:
            selected_entries.append(d)
    by_entry_identity = collections.defaultdict(list)
    by_computed = collections.defaultdict(list)
    for d in selected_entries:
        k = (d['pass_id'], d['block_id'], d['slot_id'], d['batch_id'], d['buffer_i'],
             d['mol'], d['iso'], d['flag'], d['outer_j'])
        by_entry_identity[(d['pass_id'], d['block_id'], d['slot_id'], d['batch_id'],
                           d['buffer_i'], d['mol'], d['iso'], d['flag'])].append(d)
    for d in candidate_rows:
        if d['phase'] == 2 and d['reason'] == 9 and abs(d['vft'] - SELECTED_VFT) < 1e-10:
            k = (d['pass_id'], d['block_id'], d['slot_id'], d['batch_id'], d['buffer_i'],
                 d['mol'], d['iso'], d['flag'], d['outer_j'])
            by_computed[k].append(d)
    by_anc = collections.defaultdict(list)
    for d in anc:
        by_anc[identity(d)].append(d)

    def candidate_key(key, outer_j):
        p, b, s, batch, buf, mol, iso, flag = key
        return (p, b, s, batch, buf, mol, iso, flag, outer_j)

    report = {}
    thermal_abs = []
    thermal_rel = []
    thermal_counts = collections.Counter()
    dominant_summaries = []
    thermal_field_summary = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    term_matches_by_identity = collections.Counter()
    term_candidate_index = collections.defaultdict(list)
    for d in selected_entries:
        term_candidate_index[(d['batch_id'], d['buffer_i'], f64bits(d['vnu']))].append(d)
    for t in terms:
        if abs(t['vft'] - SELECTED_VFT) >= 1e-10 or t['j3'] not in (61, 62, 63, 64):
            continue
        matches = []
        for d in term_candidate_index.get((t['batch'], t['i'], f64bits(t['meta_vnu'])), []):
            if (d['overlap_lo'] <= t['j3'] <= d['overlap_hi'] and
                d['mol'] % 100 == t['molecule'] and d['iso'] == t['isotope'] and
                d['flag'] == t['flag'] and
                all(f64bits(d[x]) == f64bits(t[y]) for x, y in
                    [('sp', 'sp'), ('sppsp', 'sppsp'), ('recalf', 'recalf')])):
                matches.append(d)
        unique = {tuple(d[k] for k in ('pass_id','block_id','slot_id','batch_id','buffer_i','mol','iso','flag'))
                  for d in matches}
        require(len(unique) == 1, 'selected R3 target term does not map to one full candidate identity')
        term_matches_by_identity[next(iter(unique))] += 1
    for group in ('left_censored_prefix69', 'dominant_negative3'):
        ids = sorted(key for key, g in allowed.items() if g == group)
        prior_cases = selected_events = joined = transport_checks = 0
        missing_prior, missing_selected, missing_phase3, ambiguous, bit_diffs = [], [], [], [], []
        seen_transport_events = 0
        for key in ids:
            events = by_anc.get(key, [])
            earlier = [e for e in events if e['VFT'] < SELECTED_VFT - 1e-10]
            at_target = [e for e in events if abs(e['VFT'] - SELECTED_VFT) < 1e-10]
            if group == 'left_censored_prefix69' and not earlier:
                missing_prior.append(key)
            if group == 'dominant_negative3' and not at_target:
                missing_selected.append(key)
            selected = by_entry_identity.get(key, [])
            if len(selected) != 1:
                missing_phase3.append({'identity': key, 'phase3_reason12_matches': len(selected)})
                if len(selected) > 1:
                    ambiguous.append({'identity': key, 'phase3_reason12_matches': len(selected)})
                continue
            c3 = selected[0]
            join_events = at_target if group == 'dominant_negative3' else earlier
            event_matches = 0
            for e in join_events:
                joined += 1
                event_matches += 1
                # Across VFTs, compare only the four values transported into
                # the actual selected-window entry. outer_j is not stable
                # across VFT and is deliberately not part of this join.
                for lhs, rhs in [('adjusted_VNU', 'vnu'), ('SP', 'sp'),
                                 ('SPPSP', 'sppsp'), ('RECALF', 'recalf')]:
                    transport_checks += 1
                    seen_transport_events += 1
                    if f64bits(e[lhs]) != f64bits(c3[rhs]):
                        bit_diffs.append({'identity': key, 'source_vft': e['VFT'], 'fields': [lhs, rhs]})
                # Re-evaluate the declared thermal expression for descriptive
                # residuals only; libm/compiler last-bit equality is not a gate.
                if e['EPP'] > -0.999:
                    expected = (e['prethermal_SUI'] * e['SCOR'] *
                                math.exp(-e['EPP'] * e['BETACR']) *
                                (1.0 + math.exp(-e['adjusted_VNU'] / e['XKT'])))
                    thermal_counts['temperature_corrected'] += 1
                else:
                    expected = e['prethermal_SUI']
                    thermal_counts['sentinel_or_unmodified'] += 1
                group_values = thermal_field_summary[group]
                for name, value in [('input_line_strength', e['input_line_strength']),
                                    ('prethermal_SUI', e['prethermal_SUI']),
                                    ('corrected_SUI', e['corrected_SUI']), ('SP', e['SP']),
                                    ('strength_factor', 1.0 + e['GI'] * e['PAVP2'])]:
                    c = group_values[name]
                    c['finite'] += int(math.isfinite(value))
                    c['positive'] += int(value > 0.0)
                    c['negative'] += int(value < 0.0)
                    c['zero'] += int(value == 0.0)
                    if math.isfinite(value):
                        c['min'] = min(c.get('min', value), value)
                        c['max'] = max(c.get('max', value), value)
                delta = e['corrected_SUI'] - expected
                thermal_abs.append(abs(delta))
                if expected != 0.0:
                    thermal_rel.append(abs(delta) / abs(expected))
                # Independent source-order assembly checks, diagnostic only.
                sp_expected = e['corrected_SUI'] * (1.0 + e['GI'] * e['PAVP2'])
                sp_delta = e['SP'] - sp_expected
                thermal_abs.append(abs(sp_delta))
                if sp_expected != 0.0:
                    thermal_rel.append(abs(sp_delta) / abs(sp_expected))
                spp_expected = ((e['corrected_SUI'] * e['YI'] * e['PAVP0']) / e['SP']) if e['SP'] != 0 else math.nan
                if math.isfinite(spp_expected):
                    spp_delta = e['SPPSP'] - spp_expected
                    thermal_abs.append(abs(spp_delta))
                    if spp_expected != 0.0:
                        thermal_rel.append(abs(spp_delta) / abs(spp_expected))
            # Same-call phase-2 source values may be checked only for the
            # dominant selected-window records. Phase-3 reason12 SUI is a
            # sentinel and is never compared to corrected_SUI.
            if group == 'dominant_negative3' and at_target:
                for e in at_target:
                    matches = by_computed.get(candidate_key(key, e['outer_j']), [])
                    if len(matches) != 1:
                        ambiguous.append({'identity': key, 'outer_j': e['outer_j'], 'phase2_reason9_matches': len(matches)})
                        continue
                    c2 = matches[0]
                    for lhs, rhs in [('adjusted_VNU', 'vnu'), ('corrected_SUI', 'sui'),
                                     ('SP', 'sp'), ('SPPSP', 'sppsp'), ('RECALF', 'recalf')]:
                        transport_checks += 1
                        if f64bits(e[lhs]) != f64bits(c2[rhs]):
                            bit_diffs.append({'identity': key, 'outer_j': e['outer_j'],
                                              'same_call_fields': [lhs, rhs]})
                e = at_target[0]
                dominant_summaries.append({'identity': key, 'input_VNU': e['input_VNU'],
                    'adjusted_VNU': e['adjusted_VNU'], 'input_line_strength': e['input_line_strength'],
                    'prethermal_SUI': e['prethermal_SUI'], 'corrected_SUI': e['corrected_SUI'],
                    'YI': e['YI'], 'GI': e['GI'], 'SP': e['SP'], 'SPPSP': e['SPPSP'],
                    'RECALF': e['RECALF'], 'selected_window_event_count': len(at_target)})
            if earlier:
                prior_cases += 1
            if at_target:
                selected_events += len(at_target)
        report[group] = {'allowlist_identity_count': 69 if group == 'left_censored_prefix69' else 3,
                         'observed_identity_count': len(ids), 'identities_with_prior_vft_event': prior_cases,
                         'selected_vft_ancestry_events': selected_events, 'joined_ancestry_to_selected_candidate_events': joined,
                         'missing_prior_vft_identities': missing_prior, 'missing_selected_vft_identities': missing_selected,
                         'missing_selected_phase3_reason12_entries': missing_phase3,
                         'ambiguous_candidate_event_joins': ambiguous, 'dominant_same_call_bit_checks': transport_checks,
                         'transport_bit_checks': transport_checks, 'transport_bit_differences': bit_diffs,
                         'matched_event_count': seen_transport_events}
        report[group]['target_R3_term_matches_by_identity'] = {
            str(key): term_matches_by_identity.get(key, 0) for key in ids}
    # Dominant identities must map to saved target R3 terms; this remains a
    # held-case routing join, not a negative-OD acceptance criterion.
    require(all(term_matches_by_identity.get(key, 0) > 0 for key, g in allowed.items()
                if g == 'dominant_negative3'), 'dominant identity lacks selected target R3 terms')
    require(not any(report[g]['missing_selected_phase3_reason12_entries'] for g in report),
            'allowlisted identity missing or ambiguous selected-window phase3 reason12 entry')
    require(not any(report[g]['missing_prior_vft_identities'] for g in report),
            'left-censored identity lacks an earlier-VFT ancestry observation')
    require(not report['dominant_negative3']['missing_selected_vft_identities'],
            'dominant identity lacks selected-window ancestry observation')
    require(not any(report[g]['ambiguous_candidate_event_joins'] for g in report), 'ambiguous ancestry/candidate join')
    require(not any(report[g]['transport_bit_differences'] for g in report), 'transported source fields differ')
    return {'groups': report, 'thermal_source_residuals_diagnostic_only': {
        'equation': 'SUI = prethermal_SUI * SCOR * exp(-EPP*BETACR) * (1+exp(-adjusted_VNU/XKT)) for EPP > -0.999; otherwise unchanged',
        'count_corrected': thermal_counts['temperature_corrected'],
        'count_unmodified': thermal_counts['sentinel_or_unmodified'],
        'max_abs_residual_combined_SUI_SP_SPPSP': max(thermal_abs, default=0.0),
        'max_rel_residual_combined_SUI_SP_SPPSP': max(thermal_rel, default=0.0),
        'interpretation': 'Binary64 descriptive recomputation only; not a compiler/libm last-bit oracle and no fitted tolerance.'},
        'dominant_negative_selected_window_summaries': dominant_summaries,
        'thermal_and_strength_sign_finite_summaries_by_group': {
            g: {field: dict(counts) for field, counts in fields.items()}
            for g, fields in thermal_field_summary.items()},
        'selected_target_R3_term_identity_count': len(term_matches_by_identity),
        'selected_target_R3_term_rows': sum(term_matches_by_identity.values())}


def summarize_existing_r3_report(pin, allowed):
    """Compact join to the already-reviewed negative terms; no recomputation."""
    doc = json.loads(verify(pin).read_text())
    require(doc.get('status') == 'PASS_SCOPED_EXACT_UPDATE_ACCOUNTING_AND_NONINTERFERENCE',
            'pinned R3 accounting report status changed')
    dominant = {key for key, group in allowed.items() if group == 'dominant_negative3'}
    rows_by_identity = collections.defaultdict(list)
    for bucket in doc['target_R3_accounting']:
        for term in bucket['largest_negative_coupling_terms']:
            for key in dominant:
                _, _, _, batch, buffer_i, mol, isotope, flag = key
                if (batch == term['batch'] and buffer_i == term['i'] and
                    mol % 100 == term['molecule'] and isotope == term['isotope'] and flag == term['flag']):
                    rows_by_identity[key].append(term)
    summaries = []
    for key in sorted(dominant):
        rows = rows_by_identity[key]
        require(len(rows) == 4, 'dominant R3 contributor must have four saved target-grid rows')
        operands = [r['actual_operand'] for r in rows]
        strengths = [r['sp'] for r in rows]
        require(all(math.isfinite(x) for x in operands + strengths), 'nonfinite dominant R3 context')
        summaries.append({'identity': key, 'target_grid_rows': len(rows),
                          'negative_operand_rows': sum(x < 0.0 for x in operands),
                          'actual_operand_min': min(operands), 'actual_operand_max': max(operands),
                          'actual_operand_sum': sum(operands), 'positive_SP_rows': sum(x > 0.0 for x in strengths),
                          'SP_min': min(strengths), 'SP_max': max(strengths),
                          'basis': 'Pinned earlier R3 accounting report; this reader does not recalculate R3 terms.'})
    return summaries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--authorization', type=Path, required=True)
    args = ap.parse_args()
    auth = json.loads(args.authorization.read_text())
    plan_pin = auth.get('plan', {})
    plan_path = verify(plan_pin)
    require(plan_path == PLAN_PATH.resolve(), 'authorization plan path')
    require(auth.get('status') == 'AUTHORIZED_ONE_SAVED_ANCESTRY_READER' and auth.get('max_reader_invocations') == 1,
            'one-use reader authorization required')
    reader_pin = verify(auth.get('reader', {}))
    require(reader_pin == Path(__file__).resolve(), 'authorization reader path')
    plan = json.loads(plan_path.read_text())
    static_pins = [plan['source_v2'][x] for x in ('source', 'plan', 'allowlist', 'static_review')]
    static_pins += [plan['source_v2'][x] for x in ('undefined_cand_fields_source_review', 'candidate_first_difference_receipt')]
    static_pins += [plan['fixed_baseline'][x] for x in ('execution', 'baseline_reader_report', 'counter_correction')]
    static_pins += [plan['fresh_candidate_runtime'][x] for x in ('plan', 'stage_receipt', 'case_stage')]
    static_pins += [plan['reused_saved_reader'], plan['accounting_reference']]
    for p in static_pins:
        verify(p)
    allowed = load_allowlist(plan['source_v2']['allowlist'])
    helper = load_helper(plan['reused_saved_reader'])

    candidate_run = Path(auth['candidate_run_dir']).resolve()
    baseline_run = (ROOT / plan['fixed_baseline']['run_dir']).resolve()
    require(candidate_run == (ROOT / plan['fresh_candidate_runtime']['run_dir']).resolve(), 'candidate run path mismatch')
    candidate_exec = terminal(auth['candidate_execution'], candidate_run)
    baseline_exec = terminal(plan['fixed_baseline']['execution'], baseline_run)
    require(auth.get('outer_runner_rc') == 3, 'preserve the outer strict-runner RC3 failure')
    outer_failure_pin = verify(auth.get('outer_runner_failure_receipt', {}))

    report_path = Path(auth['report_path']).resolve()
    report_dir = report_path.parent
    require(not report_dir.exists() and not report_path.exists(), 'reader output directory must be new')
    saved = auth.get('saved_artifact_pins')
    require(type(saved) is list and len(saved) == 99, 'authorization must bind exactly99 artifacts')
    expected = {str((candidate_run / n).resolve()) for n in
                ['UDM37_ANCESTRY', 'UDM37_CANDIDATE_DECISIONS', 'UDM37_R3_TERM_TRACE', 'UDM37_PANEL_TRACE', 'TAPE6']}
    expected |= {str((candidate_run / f'ODdeflt_{i:03}').resolve()) for i in range(1, 46)}
    expected |= {str((baseline_run / n).resolve()) for n in
                 ['UDM37_CANDIDATE_DECISIONS', 'UDM37_R3_TERM_TRACE', 'UDM37_PANEL_TRACE', 'TAPE6']}
    expected |= {str((baseline_run / f'ODdeflt_{i:03}').resolve()) for i in range(1, 46)}
    actual = [str(Path(p['path']).resolve()) for p in saved]
    require(len(set(actual)) == 99 and set(actual) == expected, 'exact 99-artifact closed roster')
    # Terminal receipts were checked before the first artifact open.
    for p in saved:
        verify(p)

    report_dir.mkdir(parents=True)
    atomic_json(report_dir / 'reader-claim.json', {'plan_sha256': sha(plan_path), 'reader_sha256': sha(reader_pin),
                                                    'candidate_solver_pid': candidate_exec['pid'],
                                                    'candidate_solver_rc': 0, 'baseline_solver_pid': baseline_exec['pid'],
                                                    'baseline_solver_rc': 0, 'artifact_count': len(saved),
                                                    'outer_runner_rc': 3,
                                                    'outer_runner_failure_receipt': pin_path(outer_failure_pin)})
    try:
        candidate = helper.candidate_rows(candidate_run / 'UDM37_CANDIDATE_DECISIONS')[0]
        baseline = helper.candidate_rows(baseline_run / 'UDM37_CANDIDATE_DECISIONS')[0]
        terms, term_count = helper.term_rows(candidate_run / 'UDM37_R3_TERM_TRACE')
        ordinary = helper.join(candidate, terms)
        # The inherited reader-v2 defaultdict length included keys inserted by
        # lookups. Do not repeat that invalid 7500 aggregate as invocation count.
        ordinary.pop('computed_reason9_invocations', None)
        ordinary['observed_phase2_reason9_record_count'] = sum(
            d['phase'] == 2 and d['reason'] == 9 for d in candidate)
        ordinary['phase2_reason9_count_is_records_not_unique_invocations'] = True
        candidate_comparison = compare_candidate_ledgers(candidate_run / 'UDM37_CANDIDATE_DECISIONS',
                                                         baseline_run / 'UDM37_CANDIDATE_DECISIONS')
        require(candidate_comparison['strict_byte_identity_failure_preserved'] and
                candidate_comparison['allowed_token_differences'] > 0,
                'candidate byte-hash mismatch did not match the preserved runner failure')
        require(sha(candidate_run / 'UDM37_R3_TERM_TRACE') == sha(baseline_run / 'UDM37_R3_TERM_TRACE'),
                'R3 trace changed versus baseline')
        require(sha(candidate_run / 'UDM37_PANEL_TRACE') == sha(baseline_run / 'UDM37_PANEL_TRACE'),
                'PANEL trace changed versus baseline')
        spectral = helper.spectra(candidate_run, baseline_run)
        ancestry, ancestry_counts = parse_ancestry(candidate_run / 'UDM37_ANCESTRY', allowed)
        require(ancestry_counts['event_duplicate_keys'] == 0,
                'duplicate source event key(s) flagged; ancestry join is ambiguous')
        groups = ancestry_joins(ancestry, candidate, terms, allowed)
        accounting = json.loads(verify(plan['accounting_reference']).read_text())
        require(sha(candidate_run / 'UDM37_R3_TERM_TRACE') == accounting['raw_trace_sha256'],
                'candidate R3 trace differs from the pinned accounting input')
        dominant_r3_summary = summarize_existing_r3_report(plan['accounting_reference'], allowed)
        # Recheck all 99 immutable artifacts after parsing/comparison.
        for p in saved + static_pins + [auth['outer_runner_failure_receipt']]:
            verify(p)
        result = {
            'status': 'PASS_SCOPED_SAVED_ANCESTRY_DIAGNOSTIC_OUTER_STRICT_FAILURE_PRESERVED',
            'scope': 'One held solver run; source-operand observability and exact saved-artifact joins only. This is not absorption truth or physical acceptance.',
            'solver': {'candidate_pid': candidate_exec['pid'], 'candidate_rc': 0,
                       'baseline_pid': baseline_exec['pid'], 'baseline_rc': 0,
                       'new_solver_build_model_calls_by_reader': 0,
                       'outer_runner_rc': 3,
                       'outer_runner_failure_receipt': pin_path(outer_failure_pin),
                       'outer_runner_failure_preserved': 'STRICT_CANDIDATE_TRACE_DIGEST_MISMATCH'},
            'artifact_count': 99,
            'candidate_artifact_count': 50,
            'baseline_artifact_count': 49,
            'candidate_trace_counts': {'candidate_records': len(candidate), 'R3_trace_records': term_count},
            'ancestry': ancestry_counts,
            'group_joins': groups,
            'dominant_negative_R3_context': dominant_r3_summary,
            'existing_join': ordinary,
            'candidate_trace_comparison': candidate_comparison,
            'spectra': spectral,
            'outer_runner_RC3_failure_is_not_superseded': True,
            'negative_OD_acceptance': 'FAIL_RETAINED_NO_CLIPPING',
            'limitations': [
                'The ancestry record sees source-loaded LNCOR S, not original AER ASCII coefficients.',
                'WKL/WKI gas amounts are absent, so absolute initial SUI is not independently reconstructed.',
                'The 69 prefix group and 3 dominant-negative group answer different questions and are reported separately.',
                'No tolerance or physical-acceptance gate is introduced by this reader.'
            ],
            'raw_artifact_pins': saved,
            'static_source_pins': static_pins
        }
        atomic_json(report_path, result)
    except BaseException as exc:
        atomic_json(report_dir / 'reader-failure.json', {'status': 'SAVED_ANCESTRY_READER_FAILED',
                                                         'error_type': type(exc).__name__, 'error': str(exc),
                                                         'solver_calls_by_reader': 0})
        raise


if __name__ == '__main__':
    main()
