#!/usr/bin/env python3
"""Verify interpolation-report scope, explicit numerical gate and rejection."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

import generate as gen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--table', type=Path, required=True)
    parser.add_argument('--direct', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error('Use a new output directory')
    args.output_dir.mkdir(parents=True)
    checker = gen.HERE/'validate_lookup.py'
    baseline = [sys.executable, str(checker), '--table', str(args.table), '--direct', str(args.direct)]
    report = args.output_dir/'report.json'
    subprocess.run(baseline+['--output', str(report)], check=True, capture_output=True, text=True)
    values = json.loads(report.read_text())
    assert values['requested_numerical_tolerance_pass'] is None
    assert values['status'] == 'SAMPLED_INTERPOLATION_DIFFERENCE_NOT_MODEL_VALIDATION'
    maximum = values['maximum_extinction_normalized_error']
    assert maximum > 0, 'Use genuine off-grid direct points for this test'
    cases = ['no_implicit_acceptance']
    for name, tolerance, expected_rc, expected_pass in [('explicit_fail', maximum/2, 1, False),
                                                     ('explicit_pass', maximum*2, 0, True)]:
        path = args.output_dir/(name+'.json')
        run = subprocess.run(baseline+['--output', str(path), '--max-extinction-normalized-error', str(tolerance)],
                             capture_output=True, text=True)
        assert run.returncode == expected_rc
        actual = json.loads(path.read_text())
        assert actual['requested_numerical_tolerance_pass'] is expected_pass
        cases.append(name)
    failures = []
    for name, extra in [('zero_tolerance', ['--max-extinction-normalized-error', '0']),
                        ('negative_tolerance', ['--max-extinction-normalized-error', '-1']),
                        ('nan_tolerance', ['--max-extinction-normalized-error', 'nan']),
                        ('infinite_tolerance', ['--max-extinction-normalized-error', 'inf'])]:
        path = args.output_dir/(name+'.json')
        run = subprocess.run(baseline+['--output', str(path), *extra], capture_output=True, text=True)
        assert run.returncode != 0 and not path.exists()
        failures.append(name)
    before = gen.sha(report)
    run = subprocess.run(baseline+['--output', str(report)], capture_output=True, text=True)
    assert run.returncode != 0 and gen.sha(report) == before
    failures.append('existing_output_not_overwritten')
    wrong = args.output_dir/'changed-controls'
    wrong.mkdir()
    shutil.copyfile(args.direct/'frozen-ice-psd-moments.nc', wrong/'frozen-ice-psd-moments.nc')
    receipt = json.loads((args.direct/'result.json').read_text())
    receipt['order'] = 64 if receipt['order'] != 64 else 32
    (wrong/'result.json').write_text(json.dumps(receipt)+'\n')
    output = args.output_dir/'changed-controls-report.json'
    run = subprocess.run([sys.executable, str(checker), '--table', str(args.table),
                          '--direct', str(wrong), '--output', str(output)], capture_output=True, text=True)
    assert run.returncode != 0 and not output.exists() and 'order differs' in run.stderr
    failures.append('numerical_controls_not_isolated')
    result = dict(status='PASS_NUMERICAL_REPORT_CONTRACT', valid_cases=cases, expected_rejections=failures,
                  table_receipt_sha256=gen.sha(args.table/'result.json'),
                  direct_receipt_sha256=gen.sha(args.direct/'result.json'),
                  test_sha256=gen.sha(Path(__file__).resolve()), validator_sha256=gen.sha(checker),
                  artifact_validator_sha256=gen.sha(gen.HERE/'compare.py'),
                  scope='Explicit caller numerical criterion, not a scientific or forecast acceptance threshold')
    (args.output_dir/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'status': result['status'], 'valid_cases': len(cases), 'expected_rejections': len(failures)}))


if __name__ == '__main__':
    main()
