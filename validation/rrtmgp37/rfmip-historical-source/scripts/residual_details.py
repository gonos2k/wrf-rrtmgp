#!/usr/bin/env python3
"""Inspect saved historical failures and rounding intervals; never run a solver."""
from pathlib import Path
import csv
import hashlib
import json
import warnings

import numpy as np
from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CURRENT = ROOT / 'build/udm37-rfmip-residual-next-diagnostic-v5/execution-v5/old_solar'
REFERENCE = ROOT / 'build/official-rrtmgp-reference/data/examples/rfmip-clear-sky/reference'
SELECTOR = ROOT / 'build/udm37-rfmip-residual-next-diagnostic-v4/failed_points.csv'
ATOL = 1e-5


def pin(path):
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def read(path, name):
    with Dataset(path) as ds:
        var = ds.variables[name]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            masked = var[:]
        mask_count = int(np.count_nonzero(np.ma.getmaskarray(masked)))
        var.set_auto_mask(False)
        raw = np.asarray(var[:])
        if raw.shape != (18, 100, 61) or raw.dtype != np.dtype('float32'):
            raise ValueError('Unexpected output shape/dtype')
        check = {'masked_cells': mask_count, 'nonfinite_cells': int(np.count_nonzero(~np.isfinite(raw))),
                 'warning_messages': sorted({str(w.message) for w in caught}), 'sentinels': {}}
        for attr in ('_FillValue', 'missing_value'):
            if attr in var.ncattrs():
                values = np.atleast_1d(var.getncattr(attr))
                check['sentinels'][attr] = {'values': values.tolist(),
                    'exact_raw_matches': int(sum(np.count_nonzero(raw.astype(np.float64) == float(v)) for v in values))}
        if check['masked_cells'] or check['nonfinite_cells'] or any(v['exact_raw_matches'] for v in check['sentinels'].values()):
            raise ValueError('Masked/nonfinite/sentinel output detected')
        return raw, check


def capture(path):
    dtype = np.dtype([('ids', '<i4', (2,)), ('data', '<f8', (122,))])
    if path.stat().st_size != 135 * dtype.itemsize:
        raise ValueError('Unexpected saved flux stream length')
    result = np.fromfile(path, dtype=dtype)
    if not np.isfinite(result['data']).all():
        raise ValueError('Nonfinite saved flux')
    ids = [(int(a)-1, int(b)-1) for a, b in result['ids']]
    if len(set(ids)) != 135:
        raise ValueError('Duplicate saved profile ID')
    return {key: data for key, data in zip(ids, result['data'])}


def rounding_details(value, reference, stored):
    below = np.nextafter(reference, np.float32(-np.inf), dtype=np.float32)
    above = np.nextafter(reference, np.float32(np.inf), dtype=np.float32)
    lower = (float(below) + float(reference)) / 2
    upper = (float(above) + float(reference)) / 2
    cast = np.float32(value)
    if cast.tobytes() != stored.tobytes():
        raise ValueError('Saved working-precision flux does not cast to saved output')
    return {'prewrite_W_m2': float(value), 'prewrite_minus_reference_W_m2': float(value) - float(reference),
            'prewrite_strict_fail': bool(abs(float(value)-float(reference)) > ATOL),
            'reference_float32_rounding_interval_W_m2': [lower, upper],
            'prewrite_outside_closed_reference_rounding_interval': bool(value < lower or value > upper),
            'at_midpoint_tie': bool(value == lower or value == upper),
            'cast_equals_saved_output_bits': True}


def main():
    output = HERE / 'residual-details.json'
    if output.exists():
        raise FileExistsError('Refusing to replace saved residual analysis')
    selected = {(r['variable'], int(r['expt_index0']), int(r['site_index0']), int(r['level_index0']))
                for r in csv.DictReader(SELECTOR.open())}
    if len(selected) != 155:
        raise ValueError('Inherited 155-cell selector changed')
    hc = capture(HERE / 'run/diag_flux_written.bin')
    cc = capture(CURRENT / 'diag_flux_written.bin')
    if hc.keys() != cc.keys():
        raise ValueError('Saved profile selections differ')
    pins = {name: pin(path) for name, path in {
        'analyzer': HERE / 'residual_details.py', 'frozen_analysis': HERE / 'analysis.json',
        'selector': SELECTOR, 'historical_prewrite': HERE / 'run/diag_flux_written.bin',
        'current_prewrite': CURRENT / 'diag_flux_written.bin'}.items()}
    records, validation = [], {}
    for name, offset in (('rsd', 61), ('rsu', 0)):
        filename = f'{name}_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc'
        arrays = {}
        for label, directory in (('historical', HERE / 'run'), ('current', CURRENT), ('reference', REFERENCE)):
            path = directory / filename
            arrays[label], validation[f'{label}_{name}'] = read(path, name)
            pins[f'{label}_{name}'] = pin(path)
        h, c, r = (arrays[k] for k in ('historical', 'current', 'reference'))
        inds = np.argwhere(np.abs(h.astype(np.float64) - r.astype(np.float64)) > ATOL)
        for expt, site, level in inds:
            key = (int(expt), int(site), int(level))
            profile = key[:2]
            row = {'variable': name, 'index0_experiment_site_level': list(key),
                   'in_original_155_selector': (name, *key) in selected,
                   'profile_captured': profile in hc,
                   'historical_stored_W_m2': float(h[key]), 'current_stored_W_m2': float(c[key]),
                   'reference_stored_W_m2': float(r[key]),
                   'historical_stored_minus_reference_W_m2': float(h[key])-float(r[key]),
                   'current_stored_strict_fail': bool(abs(float(c[key])-float(r[key])) > ATOL)}
            if profile in hc:
                hv, cv = hc[profile][offset+key[2]], cc[profile][offset+key[2]]
                row['historical_rounding'] = rounding_details(hv, r[key], h[key])
                row['current_rounding'] = rounding_details(cv, r[key], c[key])
                row['historical_minus_current_prewrite_W_m2'] = float(hv-cv)
            records.append(row)
    counts = {'full_strict_failures': len(records),
              'selected_failures': sum(r['in_original_155_selector'] for r in records),
              'new_failures_outside_original_selector': sum(not r['in_original_155_selector'] for r in records),
              'captured_failure_cells': sum(r['profile_captured'] for r in records)}
    captured = [r for r in records if r['profile_captured']]
    counts.update({'uncaptured_failure_cells': len(records)-len(captured),
                   'captured_historical_prewrite_strict_failures': sum(r['historical_rounding']['prewrite_strict_fail'] for r in captured),
                   'captured_historical_outside_reference_rounding_interval': sum(r['historical_rounding']['prewrite_outside_closed_reference_rounding_interval'] for r in captured),
                   'captured_midpoint_ties': sum(r['historical_rounding']['at_midpoint_tie'] for r in captured)})
    if counts['full_strict_failures'] != 21 or counts['selected_failures'] != 13:
        raise ValueError('Saved failure accounting differs from frozen analysis')
    result = {'schema': 'udm37-historical-source-residual-details-v1', 'status': 'COMPLETE_SAVED_RESIDUAL_INSPECTION_STRICT_FAIL',
              'new_solver_build_model_retrieval_calls': 0, 'threshold': {'atol': ATOL, 'rtol': 0},
              'pins': pins, 'array_validation': validation, 'counts': counts, 'residual_cells': records,
              'scope': 'Saved SW g224 clear RFMIP candidate only. Midpoint intervals describe float32 representation, not relaxed tolerances or original-generator/physical-accuracy proof.'}
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps(counts, sort_keys=True))


if __name__ == '__main__':
    main()
