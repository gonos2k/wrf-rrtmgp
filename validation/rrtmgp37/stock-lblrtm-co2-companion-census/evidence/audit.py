#!/usr/bin/env python3
"""Bounded TAPE3 association census for already-observed target CO2 identities.

This reader is prepared for a reviewed one-use invocation. It does not inspect
CAND/R3 raw traces, scan AER, reconstruct coupling coefficients, or claim a
physical coupling-group closure.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import struct
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = ROOT / 'build/udm37-lblrtm-co2-target-companion-census-v1/plan.json'
EXPECTED = {
    'report_sha256': '3244591f8545ba8f91f9c0f9ce3a8e8717ba7ec21487b13a0360e9d60ef83c51',
    'tape3_sha256_historical': '56bd55fa256ed3b3a672bd4bcd88034cd7086d4fbef2a1def9480199dab2b388',
    'tape3_size': 122157832,
    'expected_targets': 801,
    'first_block': 484,
    'last_block': 496,
    'header_bytes': 1664,
    'first_panel_offset': 1672,
    'panel_stride': 39040,
    'panel_header_bytes': 24,
    'panel_data_bytes': 39000,
    'slots': 250,
    'nwords': 9750,
    'block487_data_offset': 18975144,
}
REPORT = ROOT / 'build/udm37-lblrtm-candidate-decision-reader-run-v2/report.json'
TAPE3 = ROOT / 'build/udm37-lblrtm-held-state-r3terms-cpl-od-run-v1/runs/od-v1/TAPE3'


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pin_stat(path: Path) -> dict:
    s = path.stat()
    return {'size_bytes': s.st_size, 'mtime_ns': s.st_mtime_ns, 'inode': s.st_ino}


def exact_read(f, n: int, label: str) -> bytes:
    b = f.read(n)
    if len(b) != n:
        raise ValueError(f'{label}: short read {len(b)} != {n}')
    return b


def read_record(f, expected_len: int, label: str) -> tuple[int, bytes, bytes]:
    start = f.tell()
    lead = exact_read(f, 4, label + ' leading marker')
    n = struct.unpack('<i', lead)[0]
    if n != expected_len:
        raise ValueError(f'{label}: record marker {n} != {expected_len}')
    body = exact_read(f, n, label + ' payload')
    tail = exact_read(f, 4, label + ' trailing marker')
    if struct.unpack('<i', tail)[0] != n:
        raise ValueError(f'{label}: mismatched trailing marker')
    return start, body, lead + body + tail


def target_roster(report_path: Path) -> list[dict]:
    raw = report_path.read_bytes()
    if sha_bytes(raw) != EXPECTED['report_sha256']:
        raise ValueError('derived candidate report hash mismatch')
    d = json.loads(raw)
    rows = d['join']['target_unique_identity_summary']
    out = []
    for r in rows:
        encoded = int(r['encoded_MOL'])
        if encoded % 100 == 2 and int(r['original_IFLAG']) == 1:
            out.append({
                'block': int(r['block_id']),
                'slot': int(r['slot_id']),
                'mol': encoded,
                'iflg': int(r['original_IFLAG']),
                'isotope': int(r['isotope']),
                'pass_id': int(r['pass_id']),
                'LNCOR_batch': int(r['LNCOR_batch']),
            })
    keys = [(r['block'], r['slot'], r['mol'], r['iflg']) for r in out]
    if len(out) != EXPECTED['expected_targets'] or len(set(keys)) != len(keys):
        raise ValueError(f'expected 801 unique CO2 flag-1 target identities; got {len(out)}')
    if any(not (EXPECTED['first_block'] <= r['block'] <= EXPECTED['last_block']) for r in out):
        raise ValueError('target identity outside bounded TAPE3 panel range')
    return out


def panel_start(block: int) -> int:
    return EXPECTED['first_panel_offset'] + (block - 1) * EXPECTED['panel_stride']


def scan_panels(tape_path: Path) -> tuple[list[dict], dict]:
    before = pin_stat(tape_path)
    if before['size_bytes'] != EXPECTED['tape3_size']:
        raise ValueError('TAPE3 size differs from historical full-file pin')
    ranges = []
    panels = []
    bytes_read = 0
    with tape_path.open('rb') as f:
        # Validate the sequential-unformatted file header, but do not hash the
        # rest of TAPE3. The previously recorded whole-file SHA is provenance.
        _, hdr, raw = read_record(f, EXPECTED['header_bytes'], 'TAPE3 file header')
        bytes_read += len(raw)
        ranges.append({'range': 'header', 'sha256': sha_bytes(raw), 'bytes': len(raw)})
        for block in range(EXPECTED['first_block'], EXPECTED['last_block'] + 1):
            start = panel_start(block)
            f.seek(start)
            _, hbody, hraw = read_record(f, EXPECTED['panel_header_bytes'], f'block {block} header')
            vlo, vhi, nlines, nwords = struct.unpack('<ddii', hbody)
            if not (math.isfinite(vlo) and math.isfinite(vhi) and vlo <= vhi):
                raise ValueError(f'block {block}: invalid VNU bounds')
            if not (0 < nlines <= EXPECTED['slots']) or nwords != EXPECTED['nwords']:
                raise ValueError(f'block {block}: invalid slot/word counts')
            _, data, draw = read_record(f, EXPECTED['panel_data_bytes'], f'block {block} data')
            if f.tell() != start + EXPECTED['panel_stride']:
                raise ValueError(f'block {block}: unexpected panel stride')
            bytes_read += len(hraw) + len(draw)
            ranges.append({'range': f'block-{block}', 'sha256': sha_bytes(hraw + draw), 'bytes': len(hraw) + len(draw)})
            recs = []
            for slot in range(nlines):
                mol = struct.unpack_from('<i', data, 5000 + 4 * slot)[0]
                iflg = struct.unpack_from('<i', data, 9000 + 4 * slot)[0]
                recs.append({'block': block, 'slot': slot + 1, 'mol': mol, 'iflg': iflg})
            panels.append({'block': block, 'vlo': vlo, 'vhi': vhi, 'nlines': nlines, 'records': recs})
    after = pin_stat(tape_path)
    if before != after:
        raise ValueError('TAPE3 stat identity changed during selected-range read')
    if panel_start(487) + 32 != EXPECTED['block487_data_offset']:
        raise ValueError('block-487 offset anchor formula mismatch')
    return [r for p in panels for r in p['records']], {
        'stat_before': before,
        'stat_after': after,
        'previously_authenticated_whole_file_sha256': EXPECTED['tape3_sha256_historical'],
        'whole_file_sha_recomputed': False,
        'blocks_read': [EXPECTED['first_block'], EXPECTED['last_block']],
        'bytes_read': bytes_read,
        'selected_range_hashes': ranges,
        'panel_metadata': [{'block': p['block'], 'vlo': p['vlo'], 'vhi': p['vhi'], 'nlines': p['nlines']} for p in panels],
    }


def audit(report_path: Path, tape_path: Path) -> dict:
    roster = target_roster(report_path)
    records, range_info = scan_panels(tape_path)
    bykey = {}
    all_slots = {(r['block'], r['slot']): i for i, r in enumerate(records)}
    for i, r in enumerate(records):
        if r['iflg'] >= 0 and r['mol'] % 100 == 2:
            bykey.setdefault((r['block'], r['slot'], r['mol'], r['iflg']), []).append(i)
    matches = []
    missing = []
    duplicated = []
    identity_mismatch = []
    cardinality = Counter()
    open_groups = []
    for t in roster:
        key = (t['block'], t['slot'], t['mol'], t['iflg'])
        indices = bykey.get(key, [])
        if not indices:
            missing.append({'block': t['block'], 'slot': t['slot'], 'mol': t['mol'], 'iflg': t['iflg']})
            continue
        if len(indices) != 1:
            duplicated.append({'block': t['block'], 'slot': t['slot'], 'mol': t['mol'], 'iflg': t['iflg'], 'occurrences': len(indices)})
            continue
        i = indices[0]
        m = records[i]
        if m['iflg'] != 1 or m['mol'] != t['mol'] or m['mol'] % 100 != 2:
            identity_mismatch.append({'block': t['block'], 'slot': t['slot'], 'expected_mol': t['mol'], 'actual_mol': m['mol'], 'actual_iflg': m['iflg']})
            continue
        j = i + 1
        group = []
        while j < len(records) and records[j]['iflg'] < 0:
            group.append(records[j])
            j += 1
        cardinality[str(len(group))] += 1
        if group and j == len(records):
            open_groups.append({'block': t['block'], 'slot': t['slot'], 'negative_slots': len(group), 'status': 'OPEN_AT_BLOCK_496_BOUNDARY'})
        matches.append({'block': t['block'], 'slot': t['slot'], 'mol': t['mol'], 'iflg': 1,
                        'isotope': t['isotope'], 'companion_count': len(group),
                        'companion_slots': [{'block': g['block'], 'slot': g['slot'], 'iflg': g['iflg']} for g in group]})
    counts_by_block = Counter(str(x['block']) for x in matches)
    status = 'PASS_SCOPED_801_OBSERVED_CO2_TARGET_MAIN_COMPANION_ASSOCIATIONS' if (
        len(matches) == 801 and not missing and not duplicated and not identity_mismatch
        and not open_groups and cardinality == Counter({'1': 801})
    ) else 'FAIL_OR_INCOMPLETE_SCOPED_ASSOCIATIONS'
    return {
        'schema': 'UDM37_LBLRTM_CO2_TARGET_COMPANION_CENSUS_RESULT_V1',
        'status': status,
        'scope': 'All 801 observed CO2 flag-1 phase-3 reason-12 identities in the prior derived report; this is not a census of all possible line candidates or a physical coupling-group closure.',
        'source_report_sha256': EXPECTED['report_sha256'],
        'observed_target_identity_count': len(roster),
        'matched_main_count': len(matches),
        'missing_identity_count': len(missing),
        'duplicate_identity_count': len(duplicated),
        'identity_mismatch_count': len(identity_mismatch),
        'companion_cardinality_counts': dict(cardinality),
        'open_group_count': len(open_groups),
        'matched_by_block': dict(counts_by_block),
        'missing_identities': missing,
        'duplicate_identities': duplicated,
        'identity_mismatches': identity_mismatch,
        'open_groups': open_groups,
        'record_matches': matches,
        'range_read': range_info,
        'interpretation_limits': [
            'The prior saved report already joins all 6,072 target R3 updates to 837 reason-12 identities; this reader does not repeat that join.',
            'A passing result proves TAPE3 main-slot identity and adjacent negative-slot cardinality for these 801 observed CO2 target contributors only.',
            'No coupling coefficients or R3 term values are reconstructed here.',
            'No named physical group ID or completeness outside the observed target contributor roster is established.',
            'The full TAPE3 file hash is inherited from the previously recorded postflight; only selected header/panel byte ranges are hashed in this reader.'
        ],
        'new_model_build_solver_invocations': 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', type=Path, default=ROOT / 'build/udm37-lblrtm-co2-target-companion-census-v1/result.json')
    ap.add_argument('--candidate-report', type=Path, default=REPORT)
    ap.add_argument('--tape3', type=Path, default=TAPE3)
    ap.add_argument('--run', action='store_true', help='Required explicit execution switch; use only after independent scope review.')
    args = ap.parse_args()
    if not args.run:
        ap.error('refusing execution without explicit --run after scope review')
    if args.report.exists():
        raise SystemExit(f'refusing to overwrite {args.report}')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    result = audit(args.candidate_report, args.tape3)
    with args.report.open('x', encoding='utf-8') as f:
        json.dump(result, f, sort_keys=True, separators=(',', ':'))
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    print(json.dumps({'status': result['status'], 'matched_main_count': result['matched_main_count'],
                      'missing_identity_count': result['missing_identity_count'],
                      'companion_cardinality_counts': result['companion_cardinality_counts'],
                      'report': str(args.report)}, sort_keys=True))
    return 0 if result['status'].startswith('PASS_') else 2

if __name__ == '__main__':
    raise SystemExit(main())
