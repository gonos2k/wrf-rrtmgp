#!/usr/bin/env python3
"""Check index integrity; never promote it to physical acceptance."""
import argparse
import hashlib
import json
from pathlib import Path

CURRENT_IDS = {
    'P1_startup_snow', 'CI_Nc', 'CI_ice_fit', 'CI_activation',
    'Nc_PSD_physical', 'RFMIP_strict', 'LBL_negative_OD', 'P2_CMake',
    'latest_policy_forecast', 'single_identity_manifest', 'main_warm_OMP',
    'startup_historical_archive_source_pin',
}
ORIGINAL_IDS = {
    'background_N2_host_input_contract', 'BON_night_combined_remaining_residual',
    'CF0_precip_occurrence', 'native_CU_radius_occurrence_and_frozen_GH',
    'UDM_ice_effective_size_metric_compatibility', 'strict_RFMIP_and_reference_accuracy',
    'observational_and_domain_physical_accuracy', 'strict_restart_full_metadata_identity',
    'band12_upper_inactive_source_difference', 'independent_GP_Planck_fraction_interpolation',
    'PR93_CI', 'PR95_CI', 'PR8_original_CI', 'UDM_radius_generation_consumption_stage',
    'UDM_Nc_units_and_liquid_moment', 'UDM_warm_ice_native_sqrt_domain',
    'UDM_entry_density_and_DEND_compatibility',
    'UDM_inherited_rain_only_cloud_slope_uninitialized_read',
    'normal_positive_N2_actual_WRF_opacity',
}
STATUSES = {'TODO', 'IN_PROGRESS', 'PASS_SCOPED', 'FAIL', 'NOT_RUN'}
EVIDENCE_PATHS = {
    'validation/rrtmgp37/startup-snow-native/LOCAL_VALIDATION.json',
    'validation/rrtmgp37/native-radius-stage/manifest.json',
    'validation/rrtmgp37/native-radius-stage/evidence/nc-source-supplement.json',
    'validation/rrtmgp37/rfmip-reference-lineage/manifest.json',
    'validation/rrtmgp37/current-policy-audit/publication-manifest.json',
    'validation/rrtmgp37/solrad-boundary-site-48h/manifest.json',
    'validation/rrtmgp37/current-source-contracts/README.md',
}
RUNTIME_PATHS = {
    'WRF/dyn_em/module_first_rk_step_part1.F',
    'WRF/phys/module_radiation_driver.F', 'WRF/phys/module_mp_udm.F',
    'WRF/phys/module_ra_rrtmg_lw.F', 'WRF/phys/module_ra_rrtmg_sw.F',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contained(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root) or Path(name).is_absolute():
        raise ValueError(f'path outside repository: {name}')
    return path


def verify(root, index):
    root = root.resolve()
    if index['schema'] != 'UDM37_ACCEPTANCE_INDEX_V1':
        raise ValueError('unknown index schema')
    # V1 is an incomplete acceptance index. A real approval requires a new
    # reviewed decision/schema, not changing a boolean after green archive CI.
    if index['production_accepted'] is not False:
        raise ValueError('V1 cannot declare production acceptance')
    if index['current_execution_identity']['status'] != 'INCOMPLETE':
        raise ValueError('V1 has no complete scientific execution identity')
    for name, rows, expected in (
        ('current_items', index['current_items'], CURRENT_IDS),
        ('original19', index['original19'], ORIGINAL_IDS),
    ):
        ids = [row['id'] for row in rows]
        if len(ids) != len(expected) or set(ids) != expected:
            raise ValueError(f'{name}: missing, duplicate or unexpected gates')
    if set(index['original_gate_ids']) != ORIGINAL_IDS or len(index['original_gate_ids']) != 19:
        raise ValueError('original gate roster changed')
    for row in index['current_items']:
        if row['status'] not in STATUSES:
            raise ValueError(f"invalid status for {row['id']}")
        for field in ('owner', 'completion_condition', 'scope_limit'):
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError(f"missing {field} for {row['id']}")
    evidence = index['evidence']
    if (len(evidence) != len(EVIDENCE_PATHS)
            or {row['path'] for row in evidence} != EVIDENCE_PATHS):
        raise ValueError('missing, duplicate or unexpected evidence paths')
    if set(index['startup_runtime_source_sha256']) != RUNTIME_PATHS:
        raise ValueError('missing or unexpected startup runtime paths')
    for row in evidence:
        path = contained(root, row['path'])
        if path.stat().st_size != row['size_bytes'] or digest(path) != row['sha256']:
            raise ValueError(f"evidence changed: {row['path']}")
    comparisons = []
    for name, expected in index['startup_runtime_source_sha256'].items():
        actual = digest(contained(root, name))
        comparisons.append({'path': name, 'tested_sha256': expected,
                            'current_sha256': actual, 'matches_tested_source': actual == expected})
    return {
        'index_integrity': 'PASS', 'production_accepted': False,
        'scope': 'index and pinned documentary bytes only; no model/solver execution',
        'checked_evidence_files': len(evidence),
        'original_gates': 19, 'current_items': len(CURRENT_IDS),
        'runtime_source_comparison': comparisons,
        'startup_source_subset_matches': all(r['matches_tested_source'] for r in comparisons),
        'remaining': [{'id': row['id'], 'status': row['status']} for row in index['current_items']
                      if row['status'] != 'PASS_SCOPED'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--index', type=Path, default=Path(__file__).with_name('checklist.json'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--require-production-acceptance', action='store_true')
    args = parser.parse_args()
    try:
        result = verify(args.repo_root, json.loads(args.index.read_text()))
        rc = 2 if args.require_production_acceptance else 0
        if rc:
            result['acceptance_gate'] = 'NOT_ACCEPTED'
    except (KeyError, TypeError, ValueError, OSError) as error:
        result = {'index_integrity': 'FAIL', 'production_accepted': False, 'error': str(error)}
        rc = 1
    result['exit_code'] = rc
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized)
    print(serialized, end='')
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
