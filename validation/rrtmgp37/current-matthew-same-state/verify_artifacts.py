#!/usr/bin/env python3
"""Offline integrity and scientific-contract checks for this evidence package."""
from __future__ import annotations
import argparse, csv, gzip, hashlib, json, math
from pathlib import Path

FIELDS = ('phase','domain','step','source_seconds','metric')
NUMERIC = ('value37','value4','mean37','sd37','mean4','sd4','sd_delta')
CSV_COLUMNS = ('phase','domain','step','source_seconds','i','j','metric','value37','value4',
               'sample_count','mean37','sd37','mean4','sd4','sd_delta','radius_mode','scope')

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()

def require(ok: bool, msg: str):
    if not ok:
        raise ValueError(msg)

def jread(root: Path, rel: str):
    return json.loads((root / rel).read_text())

def close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=2e-13, abs_tol=2e-12)

def record_key(row):
    return (row['phase'].lower(), row['domain'], row['step'], float(row['source_seconds']), row['metric'])

def validate(root: Path):
    root = root.resolve()
    manifest = jread(root, 'artifact-manifest.json')
    require(manifest.get('schema') == 'current-same-state-artifact-manifest-v1', 'manifest schema')
    require(manifest.get('verifier_sha256') == digest(Path(__file__).resolve()), 'verifier hash')
    entries = manifest.get('files')
    require(isinstance(entries, list), 'manifest files list')
    listed = [e['path'] for e in entries]
    require(len(listed) == len(set(listed)), 'duplicate manifest path')
    require(all(not Path(p).is_absolute() and '..' not in Path(p).parts for p in listed), 'unsafe manifest path')
    all_paths = list(root.rglob('*'))
    require(not any(p.is_symlink() for p in all_paths), 'symlinks are not permitted in package')
    actual = sorted(str(p.relative_to(root)) for p in all_paths
                    if p.is_file() and p.name not in ('artifact-manifest.json','verify_artifacts.py'))
    require(sorted(listed) == actual, 'manifest does not exactly enumerate package files')
    for ent in entries:
        p = root / ent['path']
        require(p.is_file() and not p.is_symlink(), f"missing/nonregular {ent['path']}")
        require(p.stat().st_size == ent['size_bytes'], f"size mismatch {ent['path']}")
        require(digest(p) == ent['sha256'], f"SHA256 mismatch {ent['path']}")

    receipt = jread(root, 'provenance/execution-receipt.json')
    require(receipt.get('status') == 'PASS_SERIAL_AUDIT_OUTPUTS_AND_CAPTURE_PARITY', 'run status')
    require(receipt.get('model_invocations') == 3, 'three forecast invocations')
    require(receipt.get('counts', {}).get('REAL') == 0 and receipt.get('counts', {}).get('compile') == 0,
            'no REAL/build in campaign')
    for arm in ('OFF','ON_native4_0','ON_native4_1'):
        a = receipt['arms'][arm]
        require(a['returncode'] == 0 and a['timed_out'] is False and a['status'] == 'PASS_ARM'
                and a['process_status'] == 'PROCESS_COMPLETE', f'{arm} process outcome')

    terminal = jread(root, 'review/runtime-terminal-review.json')
    require(terminal['status'] == 'PASS_SCOPED_INDEPENDENT_TERMINAL_SERIAL_AUDIT', 'independent terminal review')
    require(terminal['original_receipt']['sha256'] == digest(root/'provenance/execution-receipt.json'),
            'review binds execution receipt')
    require(terminal['review_script']['sha256'] == digest(root/'review/review_terminal.py'), 'review script pin')
    require(terminal['counts']['original_model_invocations'] == 3, 'independent invocation count')

    # Actual calendar/step/time roster must agree across run and independent review.
    expected = [(x['phase'].lower(), int(x['radiation_step']), float(x['source_seconds']))
                for x in receipt['actual_call_roster']]
    observed = [(x['phase'].lower(), int(x['radiation_step']), float(x['source_seconds']))
                for x in terminal['observed_call_roster']]
    require(len(expected) == 12 and expected == observed, 'actual call roster/clock mismatch')
    require(sum(x[0] == 'lw' for x in expected) == 6 and sum(x[0] == 'sw' for x in expected) == 6,
            'LW/SW roster counts')
    require(receipt.get('all_sky_only') is True and receipt.get('clear_sky_csv_available') is False,
            'all-sky-only scope')

    # Validate all 36 canonical compressed OFF records and bind each to the actual receipt clock/hash.
    ci = jread(root, 'captures/off/capture-index.json')
    require(ci.get('schema') == 'canonical-off-capture-gzip-index-v1', 'capture index schema')
    require(len(ci['files']) == 36, '36 canonical OFF capture files')
    index_keys = set()
    per_phase_ordinal = {'lw':0,'sw':0}
    roster_by_phase = {phase:[x for x in expected if x[0] == phase] for phase in ('lw','sw')}
    hash_by_key_suffix = {}
    for entry in receipt['capture_comparisons']:
        key = (entry['key'][0].lower(), int(entry['key'][1]), float(entry['key'][2]), entry['suffix'])
        require(key not in hash_by_key_suffix, 'duplicate execution capture key')
        hash_by_key_suffix[key] = entry['sha256']
    require(len(hash_by_key_suffix) == 36, 'execution capture hash roster size')
    for ent in ci['files']:
        name = ent['name']
        stem, suffix = name.rsplit('.', 1)
        phase = 'lw' if stem.startswith('lw_') else 'sw' if stem.startswith('sw_') else None
        require(phase is not None, f'unrecognized capture filename {name}')
        ordinal = int(stem[-6:])
        require(1 <= ordinal <= 6, f'capture ordinal {name}')
        require(name not in index_keys, f'duplicate capture index name {name}')
        index_keys.add(name)
        step_key = roster_by_phase[phase][ordinal-1]
        key = (*step_key, suffix)
        require(hash_by_key_suffix.get(key) == ent['original_sha256'], f'capture-to-receipt identity {name}')
        p = root / ent['stored_path']
        require(digest(p) == ent['gzip_sha256'] and p.stat().st_size == ent['gzip_bytes'],
                f'compressed capture hash {name}')
        data = gzip.decompress(p.read_bytes())
        require(len(data) == ent['original_bytes'] and hashlib.sha256(data).hexdigest() == ent['original_sha256'],
                f'decompressed capture integrity {name}')
    require(len(index_keys) == 36, 'complete canonical capture name set')

    # Full history/restart gate and no-feedback exact capture parity.
    require(terminal['capture_parity']['all_group_bytes_equal'] is True
            and terminal['capture_parity']['complete_raw_input_result_roster_equal'] is True,
            'OFF/ON capture parity')
    require(terminal['capture_parity']['groups_per_arm'] == 12
            and terminal['capture_parity']['records_per_group'] == 3
            and terminal['capture_parity']['phases'] == {'LW':6,'SW':6}, 'capture grouping')
    checks = terminal['exact_output_comparisons']
    require(len(checks) == 6 and all(x['whole_file_equal'] and x['all_raw_schema_full_attributes_equal'] for x in checks),
            'six exact output comparisons')
    require(sum(x['fields'] == 231 for x in checks) == 4 and sum(x['fields'] == 667 for x in checks) == 2,
            'history/restart variable counts')
    require(all(x['status'] == 'PASS_EXACT' and not x['mismatches'] for x in receipt['output_comparisons']),
            'execution output comparison outcomes')

    comparison = jread(root, 'analysis/radius-arm-comparison.json')
    require(comparison['schema'] == 'matched_same_state_radius_arms_v1'
            and comparison['selected_column'] == [24,55], 'comparison schema/column')
    require(comparison['samples_per_engine_per_call'] == 128 and comparison['metric_record_count'] == 564,
            'comparison sample/record count')
    require(comparison['identical_37_reference_between_arms'] is True, 'identical RRTMG37 reference')
    require(receipt['radius_comparison']['sha256'] == digest(root/'analysis/radius-arm-comparison.json'),
            'execution receipt comparison pin')
    comparison_rows = {}
    for row in comparison['records']:
        key = (str(row['phase']).lower(), str(row['domain']), str(row['step']),
               float(row['source_seconds']), row['metric'])
        require(key not in comparison_rows, 'duplicate comparison metric key')
        comparison_rows[key] = row
    require(len(comparison_rows) == 564, 'complete comparison metric keys')
    actual_clock_keys = {(phase, str(step), seconds) for phase, step, seconds in expected}
    require(all((k[0], k[2], k[3]) in actual_clock_keys for k in comparison_rows),
            'comparison records outside actual radiation call roster')
    metrics_by_call = {}
    for key in comparison_rows:
        clock = (key[0], key[2], key[3])
        metrics_by_call.setdefault(clock, set()).add(key[4])
    require(set(metrics_by_call) == actual_clock_keys, 'missing comparison call clock')
    phase_metrics = {}
    for clock, metrics in metrics_by_call.items():
        phase = clock[0]
        if phase not in phase_metrics:
            phase_metrics[phase] = metrics
        require(metrics == phase_metrics[phase], f'incomplete metric set at {clock}')

    parsed = {}
    for arm, radius_mode in (('ON_native4_0','0'),('ON_native4_1','1')):
        rel = f'analysis/{arm}-same_state.csv'
        with (root/rel).open(newline='') as f:
            reader = csv.DictReader(f)
            require(tuple(reader.fieldnames or ()) == CSV_COLUMNS, f'{arm} CSV columns')
            rows = list(reader)
        require(len(rows) == 1128, f'{arm} CSV row count')
        selected = [r for r in rows if (r['i'],r['j']) == ('24','55')]
        aggregate = [r for r in rows if (r['i'],r['j']) == ('0','0')]
        require(len(selected) == 564 and len(aggregate) == 564, f'{arm} selected/aggregate counts')
        sel_map, agg_map = {}, {}
        for row, destination in [(x,sel_map) for x in selected] + [(x,agg_map) for x in aggregate]:
            key = record_key(row)
            require(key not in destination, f'{arm} duplicate CSV metric key')
            require(row['domain'] == '1' and row['radius_mode'] == radius_mode, f'{arm} domain/radius mode')
            require(row['scope'] == 'selected_column', f'{arm} row scope')
            require(int(row['sample_count']) == 128, f'{arm} sample count')
            for field in NUMERIC:
                value = float(row[field]); require(math.isfinite(value), f'{arm} nonfinite {field}')
            require(float(row['sd37']) >= 0 and float(row['sd4']) >= 0 and float(row['sd_delta']) >= 0,
                    f'{arm} negative SD')
            require(abs(float(row['sd37']) - float(row['sd4'])) <= float(row['sd_delta']) + 1e-10
                    and float(row['sd_delta']) <= float(row['sd37']) + float(row['sd4']) + 1e-10,
                    f'{arm} paired SD violates covariance bounds')
            destination[key] = row
        require(set(sel_map) == set(agg_map) == set(comparison_rows), f'{arm} incomplete metric roster')
        for key, row in sel_map.items():
            agg = agg_map[key]
            for field in NUMERIC + ('sample_count','radius_mode','domain','step','source_seconds','phase','metric'):
                require(row[field] == agg[field], f'{arm} selected/aggregate mismatch {field} {key}')
            ref = comparison_rows[key]
            contrast = ref['generic4_contrast'] if radius_mode == '0' else ref['native4_contrast']
            require(close(float(row['value37'])-float(row['value4']), contrast['operational_37_minus_4']),
                    f'{arm} operational contrast algebra {key}')
            require(close(float(row['mean37'])-float(row['mean4']), contrast['seed_mean_37_minus_4']),
                    f'{arm} seed mean contrast algebra {key}')
            require(close(float(row['sd_delta']), contrast['seed_set_paired_sd']),
                    f'{arm} paired SD comparison {key}')
        parsed[arm] = sel_map
    # 37-side shadow values and deterministic statistics are identical for both counterfactual modes.
    for key in parsed['ON_native4_0']:
        for field in ('value37','mean37','sd37'):
            require(float(parsed['ON_native4_0'][key][field]) == float(parsed['ON_native4_1'][key][field]),
                    f'RRTMG37 reference differs across native4 modes {key}/{field}')

    numerical = jread(root, 'analysis/numerical.json')
    require(numerical['status'] == 'PASS_DERIVED_FROM_TERMINAL_CAMPAIGN', 'numerical review status')
    require(numerical['campaign']['execution_receipt_sha256'] == digest(root/'provenance/execution-receipt.json'),
            'numerical review execution pin')
    require(numerical['campaign']['radius_arm_comparison_sha256'] == digest(root/'analysis/radius-arm-comparison.json'),
            'numerical review comparison pin')
    require(numerical['source_contract_sha256'] == digest(root/'provenance/source-contract.json'),
            'numerical source-contract pin')
    require(numerical['campaign']['samples_per_engine_call'] == 128
            and numerical['campaign']['capture_parity_count'] == 36, 'numerical review campaign counts')
    require(close(numerical['envelopes']['sw_profile_max_abs_rrtmgp37_minus_native4_seed_mean'],
                  max(abs(x['native4_contrast']['seed_mean_37_minus_4']) for x in comparison['records']
                      if x['phase'] == 'sw' and x['metric'].startswith('HEAT_'))), 'SW heating envelope')
    require(close(numerical['envelopes']['lw_profile_max_abs_rrtmgp37_minus_native4_seed_mean'],
                  max(abs(x['native4_contrast']['seed_mean_37_minus_4']) for x in comparison['records']
                      if x['phase'] == 'lw' and x['metric'].startswith('HEAT_'))), 'LW heating envelope')

    roster = jread(root,'evidence-roster.json')
    require(roster['status'] == 'PASS_SCOPED_SERIAL_SAME_STATE_AUDIT' and roster['campaign']['forecast_invocations'] == 3,
            'public roster status')
    require(roster['key_receipts']['execution_receipt_sha256'] == digest(root/'provenance/execution-receipt.json'),
            'roster execution pin')
    require(roster['key_receipts']['numerical_review_sha256'] == digest(root/'analysis/numerical.json'),
            'roster numerical review pin')
    require(numerical['envelopes']['sw_SW_DIRECT_seed_mean_max_abs_delta'] == 0.0
            and numerical['envelopes']['sw_SW_DIRECT_operational_max_abs_delta'] == 0.0,
            'SW direct diagnostics must remain explicitly zero')
    return 'PASS: exact package manifest, run/capture clocks and hashes, output parity, and CSV/comparison algebra'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent,
                        help='package root (defaults to this script directory)')
    args = parser.parse_args()
    try:
        print(validate(args.root))
    except Exception as exc:
        raise SystemExit(f'FAIL: {exc}')

if __name__ == '__main__':
    main()
