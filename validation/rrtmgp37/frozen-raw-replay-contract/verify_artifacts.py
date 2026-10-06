#!/usr/bin/env python3
"""Portable stdlib-only integrity and linked-result verification; launches no binaries."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = json.loads((HERE/'file-manifest.json').read_text())
    actual = {str(path.relative_to(HERE)) for path in HERE.rglob('*')
              if path.is_file() and path.name != 'file-manifest.json'}
    assert actual == set(manifest['files']), 'artifact inventory differs'
    for name, pin in manifest['files'].items():
        assert digest(HERE/name) == pin['sha256'], name
        assert (HERE/name).stat().st_size == pin['bytes'], name
    for name, pin in manifest['source_files_sha256'].items():
        assert digest(REPO/name) == pin, name
    load = lambda name: json.loads((HERE/name).read_text())
    lw, sw = load('recovery-v2/recovery-receipt.json'), load('recovery-v3/recovery-receipt.json')
    assert lw['status'] == 'RECOVERY_FAIL_PRESERVED' and lw['error'] == "KeyError('GAS_TAU_RAW')"
    assert sw['status'] == 'STRICT_SW_REPLAY_RECOVERY_PASS_WITH_INHERITED_LW'
    assert len(lw['reference_invocations']) == len(sw['reference_invocations']) == 1
    assert lw['reference_invocations'][0]['phase'] == 'LW' and sw['reference_invocations'][0]['phase'] == 'SW'
    for receipt, phase, sections in ((lw, 'LW', 20), (sw, 'SW', 46)):
        assert receipt['source_before'] == receipt['source_after']
        assert receipt['all_pins_original_failures_and_copied_captures_unchanged']
        report = receipt['phase_reports'][0]
        assert report['phase'] == phase and report['reference_comparison']['passed']
        assert report['reference_comparison']['sections_compared'] == sections
        assert all(detail['passed'] for detail in report['reference_comparison']['max_differences'].values())
        assert receipt['independent_parser_proof'][phase]['mask_binary_and_exact_to_reference']
    linked = sw['combined_two_call_strict_result']
    assert linked['actual_calls_across_linked_receipts'] == 2 and linked['no_lw_repeat']
    assert linked['LW']['sha256'] == digest(HERE/'recovery-v2/strict-lw.json')
    assert linked['SW']['sha256'] == digest(HERE/'recovery-v3/strict-sw.json')
    serial = load('recovery-v3/sw-serialization-source-proof.json')
    assert serial['numeric_values_checked'] == 4480 and serial['default_REAL_bytes'] == 4
    assert serial['all_values_exact_under_source_declared_serialization'] and serial['no_optical_tolerance_relaxation']
    assert load('python/test-receipt.json')['status'] == 'PYTHON_PROOF_PASS'
    assert load('capture/history-comparison.json')['status'] == 'BITWISE_PASS'
    assert load('linked/summary.json')['strict_sections_compared_total'] == 66
    assert load('linked/summary.json')['remaining_five_cases_not_run']
    root = load('root/root-linked-replay-readback.json')
    assert root['status'] == 'ROOT_ACTUAL_OUTPUT_READBACK_PASS'
    for phase, sections in (('LW', 20), ('SW', 46)):
        proof = root['phases'][phase]
        assert proof['exact_binary_mask'] and proof['all_production_numeric_values_finite']
        assert len(proof['independently_recomputed_max_abs']) == sections
    print(f"PASS: {len(actual)} retained artifacts, four source pins, linked LW20/SW46 and two total calls")


if __name__ == '__main__':
    main()
