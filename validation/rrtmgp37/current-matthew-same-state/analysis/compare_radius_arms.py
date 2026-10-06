#!/usr/bin/env python3
"""Describe matched shadow-wrapper results; no physical accuracy decision."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

VALUES = ('value37', 'value4', 'mean37', 'mean4', 'sd37', 'sd4', 'sd_delta')
IDENTITY = ('phase', 'domain', 'step', 'source_seconds', 'metric')


def read(path, mode):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        required = set(VALUES + IDENTITY + ('i', 'j', 'sample_count', 'radius_mode', 'scope'))
        if reader.fieldnames is None or not required <= set(reader.fieldnames):
            raise ValueError(f'{path}: incomplete header')
        rows = list(reader)
    if not rows:
        raise ValueError(f'{path}: empty audit')
    selected, aggregate = {}, {}
    for r in rows:
        if r['scope'] != 'selected_column' or int(r['radius_mode']) != mode:
            raise ValueError(f'{path}: unexpected scope/radius mode')
        if int(r['sample_count']) != 128 or int(r['domain']) != 1:
            raise ValueError(f'{path}: unexpected sample count/domain')
        numbers = {k: float(r[k]) for k in VALUES}
        if not all(math.isfinite(v) for v in numbers.values()):
            raise ValueError(f'{path}: nonfinite statistic')
        if any(numbers[k] < 0 for k in ('sd37', 'sd4', 'sd_delta')):
            raise ValueError(f'{path}: negative spread')
        key = tuple(r[k] for k in IDENTITY)
        index = (int(r['i']), int(r['j']))
        if index == (24, 55):
            target = selected
        elif index == (0, 0):
            target = aggregate
        else:
            raise ValueError(f'{path}: unexpected column {index}')
        if key in target:
            raise ValueError(f'{path}: duplicate row {key}')
        target[key] = numbers
    if set(selected) != set(aggregate) or not selected:
        raise ValueError(f'{path}: incomplete cell/aggregate pair')
    groups = {}
    for key in selected:
        if selected[key] != aggregate[key]:
            raise ValueError(f'{path}: selected column differs from duplicate aggregate')
        if key[0] not in ('lw', 'sw') or not math.isfinite(float(key[3])):
            raise ValueError(f'{path}: invalid phase/time')
        groups.setdefault(key[:4], set()).add(key[4])
    for call, metrics in groups.items():
        expected = {'SURFACE_DOWN', 'TOA_UP'} | {f'HEAT_{k}' for k in range(1, 45)}
        if call[0] == 'sw':
            expected |= {'SW_NET', 'SW_DIRECT'}
        if metrics != expected:
            raise ValueError(f'{path}: incomplete/unexpected metrics for {call}')
    return selected


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--generic', required=True, type=Path)
    p.add_argument('--native', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    g, n = read(args.generic, 0), read(args.native, 1)
    if set(g) != set(n):
        raise ValueError('radius arms have different clocks/metrics')
    records = []
    for key in sorted(g, key=lambda k: (k[0], float(k[3]), k[4])):
        a, b = g[key], n[key]
        if any(a[k] != b[k] for k in ('value37', 'mean37', 'sd37')):
            raise ValueError(f'37 reference differs between radius arms: {key}')
        record = dict(zip(IDENTITY, key))
        record['units'] = 'K/day' if key[4].startswith('HEAT_') else 'W/m2'
        record['generic4'] = a
        record['native4'] = b
        for label, r in (('generic4', a), ('native4', b)):
            op = r['value37'] - r['value4']
            mean = r['mean37'] - r['mean4']
            record[label + '_contrast'] = {
                'operational_37_minus_4': op,
                'seed_mean_37_minus_4': mean,
                'operational_minus_seed_mean': op - mean,
                'seed_set_paired_sd': r['sd_delta'],
            }
        record['four_native_minus_generic'] = {
            'operational': b['value4'] - a['value4'],
            'seed_mean': b['mean4'] - a['mean4'],
        }
        records.append(record)
    calls = sorted({(r['phase'], r['domain'], r['step'], r['source_seconds']) for r in records})
    result = {
        'schema': 'matched_same_state_radius_arms_v1',
        'selected_column': [24, 55], 'samples_per_engine_per_call': 128,
        'inputs': {label: {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                   for label, path in (('generic', args.generic), ('native', args.native))},
        'call_keys': calls, 'metric_record_count': len(records),
        'duplicate_aggregate_rows_excluded': True, 'identical_37_reference_between_arms': True,
        'records': records,
        'interpretation': {
            'scope': 'One preselected column in a one-hour UDM27 restart; all-sky metrics only.',
            'sample_deviation': 'Operational difference minus deterministic seed-set mean is descriptive; not an IID confidence interval or estimator-bias test.',
            'radius_control': 'Native4 flag changes legacy radius, ice-optics and path mapping together; it does not impose identical optical inputs across engines.',
            'causality': 'States are shared at each shadow call; engine4 and engine37 retain their own gas/cloud/precipitation optics, CU policy and sampling algorithms. No pure engine-only attribution.',
            'gate': 'Forecast OFF/ON identity and trace/history provenance must be checked separately before interpretation.',
            'accuracy': 'No observational or independent physical accuracy verdict; no blanket normal-difference conclusion.',
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'metrics': len(records), 'calls': len(calls), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
