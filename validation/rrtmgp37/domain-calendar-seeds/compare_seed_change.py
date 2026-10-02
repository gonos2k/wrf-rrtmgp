#!/usr/bin/env python3
"""Compare first-call captures before/after a seed-only change."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--before-scm', type=Path, required=True)
    parser.add_argument('--after-scm', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.repo.resolve() / 'WRF/test/rrtmgp'))
    from compare_column_replay import read_result
    from test_domain_seed_capture import read_raw

    cases = {}
    for case in ('control', 'mixed'):
        cases[case] = {}
        for phase in ('lw', 'sw'):
            old = args.before_scm / case / 'ra37-call1/capture' / phase
            new = args.after_scm / case / 'ra37-call1/capture' / phase
            paths = [old.with_suffix('.input'), new.with_suffix('.input')]
            lines = [p.read_text().splitlines() for p in paths]
            headers = [x[1].split() for x in lines]
            seeds = [int(x[4]) for x in headers]
            for ls, header in zip(lines, headers):
                header[4] = 'SEED'
                ls[1] = ' '.join(header)
            if lines[0] != lines[1]:
                raise RuntimeError(f'{case}/{phase}: nonseed physical input changed')
            raw_before = read_raw(old.with_suffix('.raw'))[-1]
            raw_after = read_raw(new.with_suffix('.raw'))[-1]
            for name, values in raw_before.items():
                if name not in raw_after or not np.array_equal(values, raw_after[name]):
                    raise RuntimeError(f'{case}/{phase}: previous raw field changed: {name}')
            a = read_result(old.with_suffix('.result'))['sections']
            b = read_result(new.with_suffix('.result'))['sections']
            delta = {name: float(np.max(np.abs(b[name] - a[name])))
                     for name in ('DN', 'UP', 'HR', 'DNC', 'UPC', 'HRC')}
            cases[case][phase] = {
                'physical_input_bitwise_text_equal_excluding_seed': True,
                'previous_raw_fields_exactly_equal': len(raw_before),
                'old_seed': seeds[0], 'new_seed': seeds[1],
                'result_max_abs_difference_new_minus_old': delta,
                'old_input_sha256': hashlib.sha256(paths[0].read_bytes()).hexdigest(),
                'new_input_sha256': hashlib.sha256(paths[1].read_bytes()).hexdigest(),
            }
    report = {
        'scope': 'same initial-state captures; only seed changed in replay input; '
                 'flux/heating deltas are single-realization changes, not accuracy '
                 'or ensemble-mean changes',
        'units': {'DN_UP_DNC_UPC': 'W m-2', 'HR_HRC': 'K day-1'},
        'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'cases': cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('SEED_ONLY_INPUT_ISOLATION_PASS')


if __name__ == '__main__':
    main()
