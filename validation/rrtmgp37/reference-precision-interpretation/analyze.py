#!/usr/bin/env python3
"""Separate stored, mixed-precision and unknown publisher-prewrite comparisons.

Read existing pinned candidate captures only. Rounding cells are conditional
closed hulls for one IEEE binary32 nearest-even conversion without other packing.
No solver, compiler, data retrieval or published-reference replacement is used.
"""
import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import struct

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
OLD = 'validation/rrtmgp37/remaining-contract-resolution'
ATOL = Fraction(1, 100000)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path.relative_to(REPO)), 'sha256': hashlib.sha256(raw).hexdigest(),
            'bytes': len(raw)}


def f32(value):
    return struct.pack('<f', value)


def exact(value):
    require(math.isfinite(value), 'nonfinite value')
    return Fraction(value)


def positive_rounding_hull(reference):
    require(math.isfinite(reference) and reference > 0, 'expected finite positive flux reference')
    require(struct.unpack('<f', f32(reference))[0] == reference, 'reference is not exact binary32')
    word = struct.unpack('<I', f32(reference))[0]
    below = struct.unpack('<f', struct.pack('<I', word - 1))[0]
    above = struct.unpack('<f', struct.pack('<I', word + 1))[0]
    require(math.isfinite(above), 'rounding hull at overflow is outside this analysis')
    return (exact(below) + exact(reference))/2, (exact(reference) + exact(above))/2, word % 2 == 0


def metrics(candidate, stored, reference):
    x, r, y = map(exact, (candidate, reference, stored))
    require(f32(candidate) == f32(stored), 'candidate prewrite/cast join differs')
    lo, hi, ties_included = positive_rounding_hull(reference)
    lower = max(lo-x, x-hi, Fraction(0))
    upper = max(abs(x-lo), abs(x-hi))
    result = {
        'stored_error_W_m2': float(abs(y-r)),
        'mixed_error_W_m2': float(abs(x-r)),
        'stored_strict_fail': abs(y-r) > ATOL,
        'mixed_strict_fail': abs(x-r) > ATOL,
        'rounding_closed_hull_W_m2': [float(lo), float(hi)],
        'midpoint_ties_included_in_true_preimage': ties_included,
        'conditional_prewrite_error_lower_bound_W_m2': float(lower),
        'conditional_prewrite_error_upper_bound_W_m2': float(upper),
        'exact_lower_bound': [lower.numerator, lower.denominator],
        'exact_upper_bound': [upper.numerator, upper.denominator],
        'candidate_outside_closed_hull': not lo <= x <= hi,
        'conditional_error_bounds_straddle_tolerance': lower < ATOL < upper,
        'publisher_prewrite_strict_decision': 'UNKNOWN_PUBLISHER_PREWRITE_UNAVAILABLE',
    }
    if result['candidate_outside_closed_hull'] and lower < ATOL < upper:
        # These are per-cell mathematical witnesses, never publisher data.
        direction = 1 if x < lo else -1
        near = float(x + direction*(lower+ATOL)/2)
        far = float(x + direction*(ATOL+upper)/2)
        for value, should_fail in ((near, False), (far, True)):
            require(lo < exact(value) < hi and f32(value) == f32(reference), 'witness does not round to reference')
            require((abs(x-exact(value)) > ATOL) == should_fail, 'witness does not demonstrate ambiguity')
        result['hypothetical_per_cell_reference_prewrite_witnesses'] = {
            'under_tolerance': {'value': near, 'error_W_m2': float(abs(x-exact(near)))},
            'over_tolerance': {'value': far, 'error_W_m2': float(abs(x-exact(far)))},
            'actual_publisher_values': False,
            'jointly_realizable_publisher_run_established': False,
        }
    return result


def load_profiles(path):
    raw = path.read_bytes()
    step = 8 + 122*8
    require(raw and len(raw) % step == 0, 'candidate capture record length')
    profiles = {}
    for offset in range(0, len(raw), step):
        expt, site = struct.unpack_from('<ii', raw, offset)
        key = expt-1, site-1
        require(key not in profiles and 0 <= key[0] < 18 and 0 <= key[1] < 100, 'candidate capture profile identity')
        profiles[key] = struct.unpack_from('<122d', raw, offset+8)
    return profiles


def analyze():
    manifest_path = REPO/OLD/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    require(manifest['production_accepted'] is False, 'parent acceptance changed')
    by_name = {r['path']: r for r in manifest['files']}
    names = ['evidence/rfmip-previous/residual-details.json',
             'evidence/rfmip-eight/result.json',
             'evidence/rfmip-previous/diag_flux_written.bin',
             'evidence/rfmip-eight/diag_flux_written.bin']
    pins = [pin(manifest_path)]
    for name in names:
        path = REPO/OLD/name
        got = pin(path); expected = by_name[name]
        require(got['sha256'] == expected['sha256'] and got['bytes'] == expected['bytes'], 'parent evidence bytes changed: '+name)
        pins.append(got)
    prior = json.loads((REPO/OLD/names[0]).read_text())
    added = json.loads((REPO/OLD/names[1]).read_text())
    old_profiles = load_profiles(REPO/OLD/names[2])
    new_profiles = load_profiles(REPO/OLD/names[3])
    require(len(old_profiles) == 135 and len(new_profiles) == 8, 'capture profile count differs')
    old_rows = {(r['variable'], *r['index0_experiment_site_level']): r for r in prior['residual_cells']}
    new_rows = {(r['variable'], *r['index0_experiment_site_level']): r for r in added['rows']}
    require(len(old_rows) == 21 and len(new_rows) == 8 and
            set(new_rows) == {k for k,r in old_rows.items() if not r['profile_captured']}, 'strict cell coverage differs')
    rows = []
    for key, r in sorted(old_rows.items()):
        var, expt, site, level = key
        profiles = old_profiles if r['profile_captured'] else new_profiles
        candidate = profiles[(expt,site)][level+(61 if var == 'rsd' else 0)]
        expected = r['historical_rounding']['prewrite_W_m2'] if r['profile_captured'] else new_rows[key]['prewrite_W_m2']
        require(candidate == expected, 'candidate JSON/binary join differs')
        stored, reference = r['historical_stored_W_m2'], r['reference_stored_W_m2']
        rows.append({'variable': var, 'index0_experiment_site_level': [expt,site,level],
                     'candidate_prewrite_W_m2': candidate, 'candidate_stored_W_m2': stored,
                     'published_stored_reference_W_m2': reference, **metrics(candidate,stored,reference)})
    summary = {
        'stored_candidate_vs_stored_reference_strict_failures': sum(r['stored_strict_fail'] for r in rows),
        'candidate_prewrite_vs_stored_reference_mixed_strict_failures': sum(r['mixed_strict_fail'] for r in rows),
        'candidate_cast_threshold_crossings_with_stored_reference_fixed': sum(r['stored_strict_fail'] and not r['mixed_strict_fail'] for r in rows),
        'candidate_outside_reference_closed_hull': sum(r['candidate_outside_closed_hull'] for r in rows),
        'conditional_prewrite_error_bounds_straddling_tolerance': sum(r['conditional_error_bounds_straddle_tolerance'] for r in rows),
        'candidate_vs_original_publisher_prewrite_strict_failures': 'UNKNOWN',
        'lower_bound_range_W_m2': [min(r['conditional_prewrite_error_lower_bound_W_m2'] for r in rows),
                                 max(r['conditional_prewrite_error_lower_bound_W_m2'] for r in rows)],
    }
    require(list(summary.values())[:5] == [21,14,7,21,21], 'preserved stored/mixed classifications differ')
    return {
        'schema': 'UDM37_REFERENCE_PRECISION_INTERPRETATION_V1',
        'status': 'PASS_SCOPED_CONDITIONAL_PRECISION_ANALYSIS_STORED_FAIL_PRESERVED',
        'base_main': 'b1da3b9be540666d2fcb0b4b8d9abee02e712963',
        'base_tree': '484509499ee85d9a8312d114be0c1ff8cb7951b5',
        'script': pin(Path(__file__).resolve()), 'input_pins': pins,
        'strict_atol_W_m2': 1e-5, 'strict_rtol': 0,
        'strict_stored_reference_gate': 'FAIL_PRESERVED',
        'production_accepted': False, 'physical_reference_accepted': False,
        'publisher_prewrite_available': False, 'publisher_storage_model_authenticated': False,
        'rounding_model': 'Conditional single IEEE binary32 nearest-even cast, no additional packing or quantization.',
        'closed_hull_scope': 'Conservative infimum/supremum bounds; odd-significand midpoint ties are excluded from the actual preimage.',
        'witness_scope': 'Per-cell hypothetical binary64 witnesses. No actual publisher values or jointly realizable publisher run is inferred.',
        'legacy_metric_name': 'candidate_precast_strict_fail',
        'legacy_metric_meaning': 'candidate binary64 prewrite compared to published stored binary32 reference, not two original prewrites',
        'new_compiler_model_solver_capture_calls': 0,
        'rows': rows, 'summary': summary,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    result = analyze()
    if args.verify:
        require(json.loads((BASE/'result.json').read_text()) == result, 'sealed interpretation result differs')
    if args.output:
        with args.output.open('x') as stream:
            stream.write(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'status': result['status'], **result['summary']}))


if __name__ == '__main__':
    main()
