#!/usr/bin/env python3
"""Read-only linkage of the successful capture and two actual strict replay calls."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
HERE = Path(__file__).resolve().parent
FIRST = ROOT/'build/udm-stratified-captures-v3/cf0_rain_low_cloud_proxy'
sys.dont_write_bytecode = True


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_pin(path):
    return {'path': str(path), 'sha256': sha(path)}


def main():
    required = {
        FIRST/'receipt.json': '2bc9b28a9ac828372a8093541707383bc74d5dc117e8512f08196f1d5d9965a0',
        FIRST/'replay-recovery-v2/recovery-receipt.json': 'f8b19840a91b2c5df2cdccb2c46e4763bd3805ef58acfb488ebb01e96a86393a',
        FIRST/'replay-recovery-v3/recovery-receipt.json': 'b3ebad36b9ec4c541c4f669a18fe5365a0811c2c72467dd239262028e20de1b9',
    }
    for path, digest in required.items():
        assert sha(path) == digest
    original = json.loads((FIRST/'receipt.json').read_text())
    lw = json.loads((FIRST/'replay-recovery-v2/recovery-receipt.json').read_text())
    sw = json.loads((FIRST/'replay-recovery-v3/recovery-receipt.json').read_text())
    assert lw['status'] == 'RECOVERY_FAIL_PRESERVED'
    assert sw['status'] == 'STRICT_SW_REPLAY_RECOVERY_PASS_WITH_INHERITED_LW'
    assert len(lw['reference_invocations']) == len(sw['reference_invocations']) == 1
    assert lw['reference_invocations'][0]['phase'] == 'LW' and sw['reference_invocations'][0]['phase'] == 'SW'
    for directory, receipt in ((FIRST/'replay-recovery-v2', lw), (FIRST/'replay-recovery-v3', sw)):
        assert receipt['source_before'] == receipt['source_after']
        assert receipt['all_pins_original_failures_and_copied_captures_unchanged']
        for relative, digest in receipt['output_hashes'].items():
            assert sha(directory/relative) == digest
        for name, digest in receipt['all_input_pins'].items():
            assert sha(Path(name)) == digest
    sys.path.insert(0, str(Path(sw['explicit_validator_update']['path']).parent))
    import test_column_replay as replay
    import numpy as np
    assert sha(Path(replay.__file__)) == sw['explicit_validator_update']['sha256']
    phases = {}
    for phase, directory, receipt in (('LW', FIRST/'replay-recovery-v2', lw),
                                       ('SW', FIRST/'replay-recovery-v3', sw)):
        report = receipt['phase_reports'][0]
        assert report['phase'] == phase and report['reference_comparison']['passed']
        assert all(detail['passed'] for detail in report['reference_comparison']['max_differences'].values())
        _, i, j, raw = replay.read_raw(FIRST/'capture'/(phase.lower()+'.raw'))
        _, nc, nl, overlap, seed, iceflag, inp = replay.read_input(FIRST/'capture'/(phase.lower()+'.input'))
        assert (i, j, nc) == (136, 48, 1) and inp['FROZEN_MODE'].item() == inp['FROZEN_OCCURRENCE'].item() == 1.
        dry = raw['DRY_LAYER_MASS_KG_M2']
        cf0 = raw['CF'] == 0.
        profiles = {name: raw[name].tolist() for name in
                    ('QC', 'QI', 'QR', 'QS', 'QG', 'QH', 'CF', 'RAD_CF_SOURCE', 'REL', 'REI', 'RES',
                     'DRY_LAYER_MASS_KG_M2', 'SOURCE_P_PA', 'SOURCE_T', 'SOURCE_RE_CLOUD',
                     'SOURCE_RE_ICE', 'SOURCE_RE_SNOW', 'FROZEN_LAMBDA_G_M-1', 'FROZEN_LAMBDA_H_M-1')}
        mass = {}
        for q in ('QC', 'QI', 'QR', 'QS', 'QG', 'QH'):
            path = np.maximum(raw[q], 0.)*dry*1000.
            mass[q] = {'positive_native_layers': int(np.count_nonzero(raw[q] > 0.)),
                       'native_positive_grid_path_g_m2': float(path.sum()),
                       'cf0_positive_grid_path_g_m2': float(path[cf0].sum())}
        parser = receipt['independent_parser_proof'][phase]
        phases[phase] = {
            'strict_report': file_pin(directory/('strict-'+phase.lower()+'.json')),
            'reference_result': file_pin(directory/'capture'/(phase.lower()+'.reference.result')),
            'actual_invocation': receipt['reference_invocations'][0],
            'strict_sections_compared': report['reference_comparison']['sections_compared'],
            'native_layers': 39, 'adapter_layers': nl, 'overlap': overlap, 'seed': seed, 'iceflag': iceflag,
            'step': int(raw['RADIATION_STEP'].item()), 'source_time_seconds': raw['SOURCE_TIME_SECONDS'].item(),
            'input_version': (FIRST/'capture'/(phase.lower()+'.input')).read_text().splitlines()[0],
            'independent_parser': parser,
            'native_path_check_count': len(report['adapter_input_checks']['cloud_paths']['max_adapter_path_differences_g_m2']),
            'radius_check_count': len(report['adapter_input_checks']['radii']['max_difference_um']),
            'wrf_diagnostic_check_count': len(report['wrf_diagnostic_checks_max_abs']),
            'canonical_microphysics_mapping_checks': report['microphysics_mapping']['mapping_checks'],
            'exact_source_species_checks': ['QC', 'QI', 'QR', 'QS'],
            'actual_native_profiles': profiles, 'actual_native_grid_mass_summary': mass,
            'mask_exact_to_reference': parser['mask_binary_and_exact_to_reference'],
        }
    history = json.loads((FIRST/'history-comparison.json').read_text())
    assert original['returncode'] == 0 and history['status'] == 'BITWISE_PASS'
    summary = {
        'status': 'FIRST_POINT_CAPTURE_AND_TWO_STRICT_REPLAYS_PASS_LINKED_FAILURES_PRESERVED',
        'scope': 'One selected point (136,48), first radiation call from shared 12h checkpoint; no domain bound or physical policy decision.',
        'executed_summary_script_sha256': sha(Path(__file__)),
        'phases': phases, 'strict_sections_compared_total': 66,
        'actual_reference_calls_total': 2, 'wrf_reruns': 0, 'variants_run': 0,
        'remaining_five_cases_not_run': True,
        'validator_and_sibling_pins': sw['successful_imports_before_reference_calls'],
        'strict_reference': sw['all_input_pins'][str(ROOT/'build/udm-phase-path-sensitivity-work/reference-build/reference_column')],
        'all_source_table_helper_binary_checkpoint_capture_pins': sw['all_input_pins'],
        'sw_serialization_source_proof': file_pin(FIRST/'replay-recovery-v3/sw-serialization-source-proof.json'),
        'sw_serialization': sw['sw_raw_gas_serialization_proof'],
        'linked_receipts': [file_pin(path) for path in required],
        'failure_erratum': 'V2 completed LW then failed before SW on absent GAS_TAU_RAW lookup. V3 uses exact default REAL serialization of SW GAS_TAU; no optical tolerances changed. V2 receipt remains FAIL.',
        'existing_capture_history': {'original_receipt_remains_FAIL': True,
            'history_comparison': file_pin(FIRST/'history-comparison.json'), 'history_comparison_status': history['status'],
            'history_sha256': original['history_sha256'], 'numeric_variables': original['numeric_variables'],
            'geometry': original['history_geometry'], 'physics': original['history_physics'],
            'all_numeric_raw_finite_unmasked': original['all_numeric_raw_finite_unmasked'],
            'all_numeric_decoded_finite_unmasked': original['all_numeric_decoded_finite_unmasked']},
    }
    (HERE/'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True)+'\n')
    print(summary['status'])


if __name__ == '__main__':
    main()
