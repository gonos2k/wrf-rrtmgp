#!/usr/bin/env python3
"""Compare a frozen pre-policy binary with completed positive-input SCM cases."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import netCDF4
import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'WRF/test/rrtmgp'))
import test_column_replay


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before_binary', type=Path)
    parser.add_argument('after_cases', type=Path)
    parser.add_argument('new_output_directory', type=Path)
    args = parser.parse_args()
    before = args.before_binary.resolve()
    output = args.new_output_directory.resolve()
    if output.exists():
        parser.error('refusing an existing output directory')
    output.mkdir(parents=True)
    receipt = {'scope': 'positive-input SCM only; unchanged raw input and all history arrays',
               'before_binary': str(before), 'before_binary_sha256': sha(before), 'cases': {}}
    for tag in ('control', 'mixed'):
        after = args.after_cases.resolve() / tag / 'ra37-call1'
        case = output / tag
        shutil.copytree(after, case, symlinks=True,
                        ignore=shutil.ignore_patterns('wrfout*', 'wrfrst*', 'rsl.*', 'capture',
                                                     '*.log', 'namelist.output', '*.json'))
        executable = case / 'wrf.exe'
        if executable.exists() or executable.is_symlink():
            executable.unlink()
        executable.symlink_to(before)
        for name in ('wrfinput_d01', 'namelist.input'):
            assert sha(case / name) == sha(after / name), (tag, name)
        with (case / 'wrf.log').open('w') as log:
            run = subprocess.run([str(before)], cwd=case, stdout=log, stderr=subprocess.STDOUT, check=False)
        assert run.returncode == 0 and 'SUCCESS COMPLETE WRF' in (case / 'wrf.log').read_text(), tag
        left = sorted(case.glob('wrfout_d01_*'))
        right = sorted(after.glob('wrfout_d01_*'))
        assert len(left) == len(right) > 0
        compared = 0
        for a, b in zip(left, right):
            assert a.name == b.name
            with netCDF4.Dataset(a) as da, netCDF4.Dataset(b) as db:
                assert set(da.variables) == set(db.variables), tag
                for name in da.variables:
                    va, vb = np.asarray(da[name][:]), np.asarray(db[name][:])
                    assert va.shape == vb.shape and va.dtype == vb.dtype
                    if va.dtype.kind in 'fci':
                        assert np.isfinite(va).all() and np.isfinite(vb).all(), (tag, name)
                    assert va.tobytes() == vb.tobytes(), (tag, name)
                    compared += 1
        # Independently reconstruct all six negative-input phase records from
        # the completed WRF captures using the current validator.
        raw_checks = {}
        for call in (1, 2):
            capture = args.after_cases.resolve() / tag / f'ra37-call{call}' / 'capture'
            for phase in ('lw', 'sw'):
                ph, _, _, raw = test_column_replay.read_raw(capture / f'{phase}.raw')
                _, _, _, _, _, _, inp = test_column_replay.read_input(capture / f'{phase}.input')
                test_column_replay.compare_input_to_raw(ph, raw, inp, len(raw["DP_HPA"]))
                raw_checks[f'{phase}_call{call}'] = 'PASS_SIX_PHASE_RAW_RECONSTRUCTION'
        receipt['cases'][tag] = {'arrays_bitwise_identical': compared,
                                'wrfinput_sha256': sha(case / 'wrfinput_d01'),
                                'namelist_sha256': sha(case / 'namelist.input'),
                                'raw_checks': raw_checks,
                                'before_history_sha256': {p.name: sha(p) for p in left},
                                'after_history_sha256': {p.name: sha(p) for p in right}}
    receipt['status'] = 'PASS'
    (output / 'positive-scm-comparison.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
