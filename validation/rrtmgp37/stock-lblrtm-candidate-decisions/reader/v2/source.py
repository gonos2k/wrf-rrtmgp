#!/usr/bin/env python3
"""One authorized saved-data read. Does not launch a solver or existing analyzer."""
import argparse
import collections
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
I = ('phase reason layer pass_id block_id slot_id batch_id outer_j buffer_i flag mol iso '
     'kpanel ipanel idata ilo ihi max1 jmin jmax j3shft overlap_lo overlap_hi').split()
F = 'vnu vft vbot vtop support sui sp sppsp alfl alfv recalf zeta speak threshold'.split()
TI = 'seq stage layer batch i j1 j3 molecule isotope flag izeta iz3 j3shft jmin1 jmax1'.split()
TF = ('vft dvr3 vnu sp sppsp recalf str f3 z before after zslope zint conf3 sui gi yi '
      'pavp0 pavp2 alfl zeta meta_vnu').split()
SENTINEL = -sys.float_info.max
ALLOWED = {1: {1, 2, 3, 4}, 2: {2, 3, 4, 5, 6, 7, 8, 9}, 3: {10, 11, 12, 13}}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def verify(pin):
    p = Path(pin['path']).resolve()
    n = pin['size_bytes']
    require(type(n) is int and n >= 0, 'invalid pin size')
    require(p.is_file() and p.stat().st_size == n, 'pin size/path: ' + str(p))
    require(digest(p) == pin['sha256'], 'pin digest: ' + str(p))
    return p


def atomic_new(path, obj):
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


def terminal(p, run):
    e = json.loads(p.read_text())
    require(e.get('status') in ('CHILD_RC0', 'TERMINAL'), 'not terminal child receipt')
    rc = e.get('actual_child_returncode', e.get('actual_child_RC'))
    require(type(rc) is int and rc == 0, 'child actual RC is not zero')
    require(e.get('timed_out', e.get('timeout')) is False, 'missing/nonfalse timeout')
    require(e.get('exception') is None, 'child exception')
    require(type(e.get('pid')) is int and e['pid'] > 0, 'missing child PID')
    require(Path(e['cwd']).resolve() == run, 'receipt cwd mismatch')
    return e


def records(p):
    with p.open('rb') as f:
        while True:
            marker = f.read(4)
            if not marker:
                return
            require(len(marker) == 4, 'partial record marker')
            n = struct.unpack('<i', marker)[0]
            require(0 <= n <= 64 * 1024 * 1024, 'invalid/subrecord marker')
            b = f.read(n)
            require(len(b) == n and f.read(4) == marker, 'truncated/mismatched record')
            yield b


def candidate_rows(p):
    rows = []
    counts = collections.Counter()
    with p.open('r', encoding='ascii') as f:
        for number, line in enumerate(f, 1):
            t = line.split()
            require(len(t) == 38 and t[0] == 'UDM37CAND1', 'candidate token/tag line ' + str(number))
            require(all(re.fullmatch(r'[+-]?\d+', x) for x in t[1:24]), 'integer token')
            ints = [int(x) for x in t[1:24]]
            require(all(-(1 << 63) <= x < (1 << 63) for x in ints), 'integer8 range')
            vals = [float(x.replace('D', 'E').replace('d', 'e')) for x in t[24:]]
            require(all(math.isfinite(x) for x in vals), 'nonfinite candidate operand')
            d = dict(zip(I, ints))
            d.update(zip(F, vals))
            d['record_1based'] = number
            require(d['phase'] in ALLOWED and d['reason'] in ALLOWED[d['phase']], 'phase/reason')
            require(d['layer'] == 21 and abs(d['vft'] - 662.695395555556) < 1e-10, 'selector')
            require(all(d[k] != SENTINEL for k in F[:4]), 'unknown coordinate')
            require(d['pass_id'] >= 1 and d['block_id'] >= 1, 'pass/block')
            if (d['phase'], d['reason']) == (1, 2):
                require(all(d[k] == -1 for k in ('slot_id', 'batch_id', 'buffer_i', 'mol', 'flag', 'iso')), 'skipped-block identity')
            else:
                require(1 <= d['slot_id'] <= 250 and d['buffer_i'] == d['slot_id'], 'slot/buffer')
                require(d['mol'] >= 0 and d['iso'] == (d['mol'] % 1000) // 100, 'encoded isotope')
                require(d['batch_id'] == -1 if d['phase'] == 1 else d['batch_id'] >= 1, 'batch identity')
            counts[str(d['phase']) + ':' + str(d['reason'])] += 1
            rows.append(d)
    require(rows, 'empty candidate ledger')
    return rows, counts


def term_rows(p):
    seq = 0
    terms = []
    it = iter(records(p))
    for b in it:
        require(len(b) >= 8, 'R3 tag')
        if b[:8] == b'UDMR3S1 ':
            require(len(b) == 200, 'snapshot layout')
            si = struct.unpack_from('<19q', b, 8)
            rf = struct.unpack_from('<5d', b, 160)
            require(si[0] == seq + 1 and si[2] == 21 and 1 <= si[3] <= 1000000, 'snapshot identity')
            require(all(math.isfinite(x) for x in rf), 'snapshot real8 finite')
            a = next(it, None)
            require(a is not None and len(a) == 8 * si[3], 'snapshot array length')
            require(all(math.isfinite(x[0]) for x in struct.iter_unpack('<d', a)), 'snapshot array finite')
        else:
            require(b[:8] == b'UDMR3T1 ' and len(b) == 304, 'term layout')
            d = dict(zip(TI, struct.unpack_from('<15q', b, 8)))
            d.update(zip(TF, struct.unpack_from('<22d', b, 128)))
            require(d['seq'] == seq + 1 and d['layer'] == 21 and d['stage'] in (1, 2), 'term identity')
            require(all(math.isfinite(d[k]) for k in TF), 'term real8 finite')
            terms.append(d)
        seq += 1
    require(seq and terms, 'empty R3 trace')
    return terms, seq


def bit(x):
    return struct.pack('<d', x)


def join(rows, terms):
    computed = collections.defaultdict(list)
    entries = collections.defaultdict(list)
    earliest_phase2 = {}
    for d in rows:
        if d['phase'] == 2:
            p = d['pass_id']
            earliest_phase2[p] = min(earliest_phase2.get(p, d['batch_id']), d['batch_id'])
    censored = collections.defaultdict(list)
    observed_ancestry_entries = 0
    for d in rows:
        if d['phase'] == 1:
            continue
        key = (d['pass_id'], d['block_id'], d['slot_id'], d['batch_id'])
        if d['phase'] == 2 and d['reason'] == 9:
            computed[key].append(d)
        if d['phase'] == 3:
            entries[key].append(d)
            if d['reason'] != 10:
                prior = [x for x in computed[key] if x['record_1based'] < d['record_1based']]
                if not prior:
                    # HIRAC1 PANEL -> GO TO70 reuses earlier LNCOR state while
                    # phase2 logging is restricted to the selected VFT. This
                    # permits only a left-censored batch prefix, never a later
                    # missing ancestor. These entries are NOT ancestry-proven.
                    cutoff = earliest_phase2.get(d['pass_id'])
                    require(cutoff is not None and d['batch_id'] < cutoff,
                            'later/unbounded CNVFNV entry lacks observed reason9')
                    censored[key].append(d)
                    continue
                observed_ancestry_entries += 1
                a = prior[-1]
                require(all(a[k] == d[k] for k in ('mol', 'iso', 'flag')), 'entry identity changed')
                require(all(bit(a[k]) == bit(d[k]) for k in ('vnu', 'sp', 'sppsp', 'recalf')), 'computed-entry operands changed')
    matched = 0
    identities = set()
    for t in terms:
        if abs(t['vft'] - 662.695395555556) >= 1e-10 or t['j3'] not in (61, 62, 63, 64):
            continue
        candidates = [(key, d) for key, ds in entries.items() for d in ds
                      if d['reason'] == 12 and d['batch_id'] == t['batch'] and d['buffer_i'] == t['i']
                      and bit(d['vnu']) == bit(t['meta_vnu'])]
        unique = {key for key, d in candidates}
        require(len(unique) == 1, 'term full identity ambiguous/missing')
        require(any(d['overlap_lo'] <= t['j3'] <= d['overlap_hi'] and
                    d['mol'] % 100 == t['molecule'] and d['iso'] == t['isotope'] and d['flag'] == t['flag']
                    and all(bit(d[k]) == bit(t[k]) for k in ('sp', 'sppsp', 'recalf'))
                    for key, d in candidates), 'term-to-entry mismatch')
        matched += 1
        identities.update(unique)
    require(matched, 'no target term joins')
    def identity_summary(key, events):
        a = events[0]
        return {'pass_id': key[0], 'block_id': key[1], 'slot_id': key[2], 'LNCOR_batch': key[3],
                'encoded_MOL': a['mol'], 'isotope': a['iso'], 'original_IFLAG': a['flag'],
                'phase3_records': len(events),
                'phase3_reason_counts': dict(collections.Counter(str(x['reason']) for x in events)),
                'record_1based_first': min(x['record_1based'] for x in events),
                'record_1based_last': max(x['record_1based'] for x in events)}
    target_summaries = [identity_summary(key, entries[key]) for key in sorted(identities)]
    censored_summaries = [identity_summary(key, events) for key, events in sorted(censored.items())]
    routing = collections.defaultdict(list)
    for d in rows:
        if d['phase'] != 1:
            routing[(d['pass_id'], d['block_id'], d['slot_id'], d['batch_id'])].append(d)
    rejection_rows = []
    for key, events in sorted(routing.items()):
        rejected = [x for x in events if x['phase'] == 2 and x['reason'] in (2, 3, 4, 5, 6, 7, 8)]
        if rejected:
            a = events[0]
            rejection_rows.append({'pass_id': key[0], 'block_id': key[1], 'slot_id': key[2],
                                   'LNCOR_batch': key[3], 'encoded_MOL': a['mol'], 'isotope': a['iso'],
                                   'original_IFLAG': a['flag'],
                                   'observed_LNCOR_rejection_reason_counts': dict(collections.Counter(str(x['reason']) for x in rejected)),
                                   'phase3_entry_records': sum(x['phase'] == 3 for x in events)})
    return {'target_term_updates_joined': matched, 'target_full_invocation_identities': len(identities),
            'target_unique_identity_summary': target_summaries,
            'earliest_observed_phase2_batch_by_pass': earliest_phase2,
            'left_censored_prefix_nonzero_entry_records': sum(len(x) for x in censored.values()),
            'left_censored_prefix_unique_identities': len(censored),
            'left_censored_prefix_identity_summary': censored_summaries,
            'left_censored_ancestry_validated': False,
            'observed_reason9_to_nonzero_phase3_entries_bitwise_checked': observed_ancestry_entries,
            'observed_LNCOR_rejection_reason_counts': dict(collections.Counter(str(x['reason']) for x in rows if x['phase'] == 2 and x['reason'] in (2, 3, 4, 5, 6, 7, 8))),
            'observed_rejection_identity_summary': rejection_rows,
            'computed_reason9_invocations': len(computed), 'phase3_entry_invocations': len(entries),
            'reason9_without_phase3': len(set(computed) - set(entries)),
            'reason11_records': sum(d['reason'] == 11 and d['phase'] == 3 for d in rows)}


def spectra(new, old):
    count = 0
    rows = []
    clocks = {side: (run / 'TAPE6').read_bytes() for side, run in [('old', old), ('new', new)]}
    for layer in range(1, 46):
        ni = iter(records(new / f'ODdeflt_{layer:03}'))
        oi = iter(records(old / f'ODdeflt_{layer:03}'))
        nh = next(ni, None)
        oh = next(oi, None)
        require(nh is not None and oh is not None and len(nh) == len(oh) == 1416, 'OD file header')
        changed = [j for j in range(177) if nh[j*8:(j+1)*8] != oh[j*8:(j+1)*8]]
        require(changed in ([], [168]), 'OD header change outside HTIME')
        for side, b in [('new', nh), ('old', oh)]:
            clock = b[168*8:169*8]
            require(re.fullmatch(rb'\d\d:\d\d:\d\d', clock) and clock in clocks[side], 'OD HTIME provenance')
        samples = 0
        while True:
            ph = next(ni, None)
            qh = next(oi, None)
            require(ph is not None and ph == qh, 'OD panel header')
            if ph == struct.pack('<6q', *([-99] * 6)):
                break
            require(len(ph) == 32, 'OD panel shape')
            v1, v2, dv, n = struct.unpack('<3dq', ph)
            require(all(math.isfinite(x) for x in (v1, v2, dv)) and dv > 0 and n > 0, 'OD panel coordinates')
            a = next(ni, None)
            b = next(oi, None)
            require(a is not None and a == b and len(a) == n * 8, 'OD samples not exact')
            require(all(math.isfinite(x[0]) for x in struct.iter_unpack('<d', a)), 'nonfinite OD')
            samples += n
        require(next(ni, None) is None and next(oi, None) is None, 'OD trailing records')
        rows.append({'layer': layer, 'samples': samples, 'changed_header_words': changed})
        count += samples
    require(count == 63838065, 'all45 total sample count')
    return {'layers': rows, 'samples_bitwise_equal': count, 'negative_OD_acceptance': 'FAIL_RETAINED_NO_CLIPPING'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--authorization', type=Path, required=True)
    args = ap.parse_args()
    auth = json.loads(args.authorization.read_text())
    require(auth.get('status') == 'AUTHORIZED_ONE_SAVED_CANDIDATE_READER' and auth.get('max_reader_invocations') == 1, 'authorization')
    plan_path = verify(auth['plan'])
    require(plan_path == HERE / 'plan.json', 'plan path')
    verify(auth['reader'])
    require(Path(auth['reader']['path']).resolve() == Path(__file__).resolve(), 'reader path')
    plan = json.loads(plan_path.read_text())
    for pin in plan['source_and_prior_small_pins']:
        verify(pin)
    run = Path(auth['candidate_run_dir']).resolve()
    old = Path(plan['baseline_run_dir']).resolve()
    # This terminal gate precedes any candidate raw hash/parse or baseline numeric read.
    epath = verify(auth['candidate_execution'])
    e = terminal(epath, run)
    terminal(verify(plan['baseline_execution']), old)
    report = Path(auth['report']).resolve()
    require(not report.exists() and not report.parent.exists(), 'one-use fresh report directory')
    report.parent.mkdir(parents=True)
    atomic_new(report.parent / 'reader-claim.json', {'plan_sha256': digest(plan_path), 'reader_sha256': digest(Path(__file__)), 'solver_PID': e['pid'], 'solver_actual_RC': 0})
    try:
        artifact_pins = auth['saved_artifacts']
        expected = {str((run / x).resolve()) for x in ['UDM37_CANDIDATE_DECISIONS', 'UDM37_R3_TERM_TRACE', 'UDM37_PANEL_TRACE', 'TAPE6']}
        expected |= {str((run / f'ODdeflt_{i:03}').resolve()) for i in range(1, 46)}
        expected |= {str((old / x).resolve()) for x in ['UDM37_R3_TERM_TRACE', 'UDM37_PANEL_TRACE', 'TAPE6']}
        expected |= {str((old / f'ODdeflt_{i:03}').resolve()) for i in range(1, 46)}
        actual = [str(Path(p['path']).resolve()) for p in artifact_pins]
        require(len(actual) == len(set(actual)) and set(actual) == expected, 'exact saved artifact pin roster')
        for pin in artifact_pins:
            verify(pin)
        rows, counts = candidate_rows(run / 'UDM37_CANDIDATE_DECISIONS')
        require(digest(run / 'UDM37_R3_TERM_TRACE') == digest(old / 'UDM37_R3_TERM_TRACE'), 'inherited term trace changed')
        require(digest(run / 'UDM37_PANEL_TRACE') == digest(old / 'UDM37_PANEL_TRACE'), 'inherited PANEL trace changed')
        terms, n = term_rows(run / 'UDM37_R3_TERM_TRACE')
        joined = join(rows, terms)
        spectral = spectra(run, old)
        for pin in artifact_pins + plan['source_and_prior_small_pins']:
            verify(pin)
        out = {'status': 'PASS_SCOPED_SAVED_ROUTING_AND_NONINTERFERENCE', 'candidate_records': len(rows),
               'phase_reason_counts': dict(counts), 'R3_trace_records': n, 'join': joined, 'spectra': spectral,
               'solver_PID': e['pid'], 'solver_actual_RC': 0, 'raw_pins': artifact_pins,
               'source_pins': plan['source_and_prior_small_pins'], 'limits': plan['limits'],
               'interpretation': {'reason9': 'corrected strength computed before later filters',
                                  'phase3': 'actual CNVFNV entry', 'reason11': 'later-panel handoff, not a rejection/drop'},
               'new_model_build_or_solver_invocations': 0}
        atomic_new(report, out)
    except BaseException as exc:
        atomic_new(report.parent / 'reader-failure.json', {'status': 'SAVED_READER_FAILED', 'error_type': type(exc).__name__, 'error': str(exc), 'new_model_build_or_solver_invocations': 0})
        raise


if __name__ == '__main__':
    main()
