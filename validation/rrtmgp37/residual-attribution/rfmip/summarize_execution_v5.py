#!/usr/bin/env python3
"""Recompute concise read-only metrics from the frozen v5 execution receipt."""
from __future__ import annotations
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXEC = HERE.parent / 'execution.json'
EXPECTED_EXEC_SHA = '88d2975310338bbec6b72280592dd9c1fc70742fc389842c7d04385fb68bbe3d'
ATOL = 1.0e-5


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def summarize_arm(call):
    rows = call['residual_cells_vs_published']
    ulp_saved = collections.Counter(str(r['stored_to_published_ulp_distance']) for r in rows)
    ulp_pre = collections.Counter(str(r['prewrite_to_published_ulp_distance']) for r in rows)
    full_cast = call['cast_diagnostic']['full_profile_level_cast_checks']
    return {
        'selected_cells': len(rows),
        'by_variable': {v: sum(r['variable'] == v for r in rows) for v in ('rsd', 'rsu')},
        'selected_stored_values_over_1e-5': sum(bool(r['stored_over_atol']) for r in rows),
        'selected_prewrite_values_over_1e-5': sum(bool(r['prewrite_over_atol_vs_published_float']) for r in rows),
        'prewrite_outside_target_float32_rounding_interval': sum(not r['prewrite_inside_published_rounding_interval'] for r in rows),
        'stored_minus_published_float32_ulp_counts': dict(sorted(ulp_saved.items(), key=lambda kv: int(kv[0]))),
        'prewrite_cast_ulp_counts': dict(sorted(ulp_pre.items(), key=lambda kv: int(kv[0]))),
        'max_abs_prewrite_minus_published': max(abs(r['prewrite_minus_published']) for r in rows),
        'mean_abs_prewrite_minus_published': sum(abs(r['prewrite_minus_published']) for r in rows) / len(rows),
        'max_abs_stored_minus_published': max(abs(r['stored_minus_published']) for r in rows),
        'full_float32_cast_gate': {
            v: {'profiles': x['profiles'], 'levels_per_profile': x['levels_per_profile'],
                'values_compared': x['values_compared'], 'mismatch_count': x['mismatch_count'],
                'exact': x['exact_bitwise_cast_gate']}
            for v, x in full_cast.items()
        },
        'normalization': call['broadband_tsi_diagnostic'],
        'output_bitwise_gate': call['output_bitwise_gate'],
        'log_sha256': call['log_sha256'],
        'capture_sha256': call['capture_hashes'],
        'returncode': call['returncode'],
        'timed_out': call['timed_out'],
        'post_process_pins_match': call['post_process_pins_match'],
    }


def main():
    actual_sha = sha(EXEC)
    if actual_sha != EXPECTED_EXEC_SHA:
        raise SystemExit(f'execution receipt pin mismatch: {actual_sha}')
    d = json.loads(EXEC.read_text())
    if d['status'] != 'COMPLETE_DIAGNOSTIC_NOT_STRICT_PASS' or len(d['calls']) != 2:
        raise SystemExit('unexpected execution status or call count')
    calls = {c['arm']: c for c in d['calls']}
    if set(calls) != {'current', 'old_solar'}:
        raise SystemExit('expected exactly current and old_solar arms')
    for c in calls.values():
        if c['returncode'] != 0 or c['timed_out'] or not c['post_process_pins_match']:
            raise SystemExit(f"arm did not complete cleanly: {c['arm']}")
    cross = d['diagnostic_summary']['cross_arm']
    pinned = {Path(path).name: {'sha256': value['sha256'], 'size': value['size']}
              for path, value in d['pins_before'].items()}
    raw_inputs = {name: pinned[name] for name in ('multiple_input4MIPs_radiation_RFMIP_UColorado-RFMIP-1-2_none.nc',
                                                    'rrtmgp-gas-sw-g224.nc',
                                                    'rrtmgp-gas-sw-g224-old-solar-counterfactual.nc')
                  if name in pinned}
    summary = {
        'schema': 'rfmip-sw-residual-diagnostic-v5-analysis',
        'status': 'READ_ONLY_ANALYSIS_COMPLETE',
        'execution': {
            'path': EXEC.parent.relative_to(EXEC.parents[2]).as_posix() + '/execution.json',
            'sha256': actual_sha, 'status': d['status'], 'standalone_sw_solver_calls': d['model_invocations'],
            'wrf_or_real_forecasts': 0, 'compile_returncode': d['compile']['returncode'],
            'link_returncode': d['link']['returncode'],
            'diagnostic_executable_sha256': d['diagnostic_executable_sha256'],
            'source_sha256': d['source_sha256'], 'plan_sha256': d['plan_sha256'],
            'runtime_closure_matches_frozen_baseline': d['runtime_closure_exact_match_to_original'],
        },
        'pinned_inputs': raw_inputs,
        'pinned_stage_v7_references': {name: item['sha256'] for name, item in pinned.items()
                                       if name.endswith('_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc')},
        'strict_comparison': {'published_atol': ATOL, 'rtol': 0,
                              'original_selected_failures': {'rsd': 116, 'rsu': 39},
                              'threshold_was_not_changed': True},
        'arms': {name: summarize_arm(calls[name]) for name in ('current', 'old_solar')},
        'cross_arm': {
            'captured_gas_optics_bitwise_equal_all_profiles': cross['optics']['all_profiles_bitwise_equal'],
            'gas_optics_profiles_equal': cross['optics']['bitwise_equal_profiles'],
            'profiles': cross['optics']['profile_count'],
            'max_abs_optics_delta': cross['optics']['max_abs_delta'],
            'source_pre_all_profiles_bitwise_equal': cross['source_pre']['all_profiles_bitwise_equal'],
            'source_post_all_profiles_bitwise_equal': cross['source_post']['all_profiles_bitwise_equal'],
            'flux_solver_all_profiles_bitwise_equal': cross['flux_solver']['all_profiles_bitwise_equal'],
            'max_abs_flux_solver_delta': cross['flux_solver']['max_abs_delta'],
            'flux_written_all_profiles_bitwise_equal': cross['flux_written']['all_profiles_bitwise_equal'],
            'max_abs_flux_written_delta': cross['flux_written']['max_abs_delta'],
        },
        'interpretation': {
            'float32_conversion_is_not_the_sole_explanation': True,
            'basis': 'In the old-solar counterfactual, 99/155 selected prewrite values already differ from the published float32 target by more than 1e-5, and all 155 prewrite values lie outside that target’s float32 rounding interval. For the 56 remaining cells, the prewrite difference is within 1e-5 but the stored float32 output exceeds it. Every old-solar stored value is one float32 ULP from the published value.',
            'current_arm_selected_prewrite_over_threshold': sum(bool(r['prewrite_over_atol_vs_published_float']) for r in calls['current']['residual_cells_vs_published']),
            'current_arm_selected_stored_over_threshold': sum(bool(r['stored_over_atol']) for r in calls['current']['residual_cells_vs_published']),
            'solar_only_control': 'The two arms have bitwise-identical captured gas optical properties for all 135 selected profiles, while source arrays and fluxes differ. Both arms reproduce their respective retained stage-v7 full-output arrays bitwise and pass all captured float32 cast checks.',
            'limits': ['This is a targeted old-solar counterfactual, not an authenticated historical coefficient set or source revision.', 'The RFMIP label does not establish a precise historical generator SHA.', 'The result does not attribute any remaining residual to a WRF port defect or establish physical accuracy.', 'The published strict threshold remains failing; no tolerance or coefficient was changed.'],
        },
    }
    out = HERE / 'analysis-summary-v5.json'
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    print(out)
    print(sha(out))

if __name__ == '__main__':
    main()
