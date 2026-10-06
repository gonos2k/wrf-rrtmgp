#!/usr/bin/env python3
"""Reproduce a bounded, boundary-site SOLRAD comparison; never launch WRF."""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

import numpy as np

START = dt.datetime(2016, 10, 6)
END = dt.datetime(2016, 10, 8)
SITE = (38.97203, -77.48690, 85.0)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def load_observations(root):
    rows = {}
    headers = []
    for day in (280, 281, 282):
        p = root / 'raw' / f'ste16{day}.dat'
        lines = p.read_text().splitlines()
        head = lines[1].split()
        assert tuple(map(float, head[:3])) == SITE, 'station location changed'
        headers.append({'path': str(p.relative_to(root)), 'sha256': sha(p),
                        'station': lines[0].strip(), 'header': lines[1].strip()})
        a = np.loadtxt(p, skiprows=2)
        assert a.ndim == 2 and a.shape[1] == 22, 'non-Madison schema required'
        for v in a:
            assert np.isfinite(v).all()
            assert all(v[i] == int(v[i]) for i in (0, 1, 2, 3, 4, 5, 9, 11, 13))
            t = dt.datetime(*map(int, v[[0, 2, 3, 4, 5]]))
            assert t.timetuple().tm_yday == int(v[1]) == day
            assert t not in rows, 'duplicate UTC period end'
            assert 0 <= v[7] <= 180
            # Nonnegative solar projection; measured channel values stay signed.
            mu = max(0.0, math.cos(math.radians(float(v[7]))))
            good_components = (v[11] == 0 and v[13] == 0 and
                               v[10] != -9999.9 and v[12] != -9999.9)
            good_global = v[9] == 0 and v[8] != -9999.9
            rows[t] = {'component_wm2': float(v[10] * mu + v[12])
                       if good_components else None,
                       'global_psp_wm2': float(v[8]) if good_global else None,
                       'sun_above_horizon': bool(v[7] < 90)}
    return rows, headers


def hourly(rows, start, end):
    """Require every period-end minute in (start,end]; no fill or fallback."""
    assert (end - start).total_seconds() == 3600
    expected = [start + dt.timedelta(minutes=i) for i in range(1, 61)]
    selected = [rows.get(t) for t in expected]
    present = sum(v is not None for v in selected)
    out = {'present_minutes': present,
           'sun_above_horizon_minutes': sum(v['sun_above_horizon'] for v in selected if v)}
    for field in ('component_wm2', 'global_psp_wm2'):
        vals = [v[field] for v in selected if v is not None and v[field] is not None]
        out[field + '_good_minutes'] = len(vals)
        out[field] = float(sum(vals) / 60) if len(vals) == 60 else None
    # Fixed before evaluating errors: >=30 daylight minutes classifies a daylight hour.
    out['daylight_hour'] = out['sun_above_horizon_minutes'] >= 30
    return out


def extract_models(pair, output):
    import netCDF4
    prior = json.loads((pair / 'paired-descriptive-differences.json').read_text())
    plan = json.loads((pair / 'plan.json').read_text())
    receipt = json.loads((pair / 'execution-receipt.json').read_text())
    assert receipt['status'] == 'PASS_BOTH_VALIDATED_DESCRIPTIVE'
    result = {'schema': 'solrad-model-extract-v1', 'site_lat_lon_height': SITE,
              'execution_receipt_sha256': sha(pair / 'execution-receipt.json'),
              'plan_sha256': sha(pair / 'plan.json'),
              'source_build_scope': plan['binary_source_build'],
              'executable': plan['executable'], 'frozen_table': plan['table'],
              'arms': {}}
    for arm, radiation in (('ra4', 4), ('ra37', 37)):
        file = pair / arm / 'wrfout_d01_2016-10-06_00:00:00'
        digest = sha(file)
        assert digest == prior[arm]['sha256'], 'completed history pin changed'
        nml = pair / arm / 'namelist.input'
        with netCDF4.Dataset(file) as ds:
            ds.set_auto_maskandscale(False)
            lat, lon = np.asarray(ds['XLAT'][0], float), np.asarray(ds['XLONG'][0], float)
            assert ds.MAP_PROJ == 3, 'Mercator-only actual-grid inclusion check'
            assert np.allclose(lat, lat[:, :1]) and np.allclose(lon, lon[:1, :])
            assert np.all(np.diff(lat[:, 0]) > 0) and np.all(np.diff(lon[0]) > 0)
            assert lat.min() < SITE[0] < lat.max() and lon.min() < SITE[1] < lon.max()
            p1, p2 = np.deg2rad(lat), math.radians(SITE[0])
            a = np.sin((p1-p2)/2)**2 + np.cos(p1)*math.cos(p2)*np.sin(np.deg2rad(lon-SITE[1])/2)**2
            distance = 2*6371.0*np.arcsin(np.sqrt(np.clip(a, 0, 1)))
            j, i = map(int, np.unravel_index(np.argmin(distance), lat.shape))
            assert ds.MP_PHYSICS == 27 and ds.RA_SW_PHYSICS == ds.RA_LW_PHYSICS == radiation
            times = netCDF4.chartostring(ds['Times'][:]).astype(str).tolist()
            parsed = [dt.datetime.strptime(t, '%Y-%m-%d_%H:%M:%S') for t in times]
            assert parsed == [START + dt.timedelta(hours=k) for k in range(49)]
            ac = np.asarray(ds['ACSWDNB'][:, j, i], dtype=float)
            assert ds['ACSWDNB'].units.strip() == 'J m-2'
            assert np.isfinite(ac).all() and np.all(np.diff(ac) >= 0)
            result['arms'][arm] = {
                'history_path': str(file.resolve()), 'history_sha256': digest,
                'history_size_bytes': file.stat().st_size,
                'namelist_sha256': sha(nml), 'namelist': nml.read_text(),
                'times_utc': times, 'ACSWDNB_J_m2': ac.tolist(),
                'SWDOWN_instantaneous_W_m2_not_scored': np.asarray(ds['SWDOWN'][:, j, i], float).tolist(),
                'COSZEN_instantaneous_not_hour_classifier': np.asarray(ds['COSZEN'][:, j, i], float).tolist(),
                'grid': {'j_zero_based': j, 'i_zero_based': i, 'shape_y_x': list(lat.shape),
                         'lat': float(lat[j, i]), 'lon': float(lon[j, i]),
                         'great_circle_distance_km': float(distance[j, i]),
                         'height_m': float(ds['HGT'][0, j, i]), 'landmask': float(ds['LANDMASK'][0, j, i]),
                         'cells_to_nearest_edge': min(j, i, lat.shape[0]-1-j, lat.shape[1]-1-i),
                         'spec_bdy_width': 5, 'inside_boundary_zone': True,
                         'DX_m': float(ds.DX), 'DY_m': float(ds.DY)},
                'attributes': {k: int(ds.getncattr(k)) for k in ('MP_PHYSICS', 'RA_SW_PHYSICS', 'RA_LW_PHYSICS')},
                'DT_seconds': float(ds.DT), 'ACSWDNB_storage_dtype': str(ds['ACSWDNB'].dtype)}
            assert 'spec_bdy_width                      = 5' in nml.read_text()
    assert result['arms']['ra4']['grid'] == result['arms']['ra37']['grid']
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')


def statistics(rows, ref, subset):
    picked = [r for r in rows if r[ref] is not None and (subset == 'all' or r['daylight_hour'])]
    out = {'n_hours': len(picked)}
    for arm in ('ra4', 'ra37'):
        if not picked:
            out[arm] = None
            continue
        y = np.asarray([r[ref] for r in picked]); x = np.asarray([r[arm+'_hourly_W_m2'] for r in picked])
        e = x-y
        out[arm] = {'mean_observation_W_m2': float(y.mean()), 'mean_model_W_m2': float(x.mean()),
                    'bias_W_m2': float(e.mean()), 'MAE_W_m2': float(np.abs(e).mean()),
                    'RMSE_W_m2': float(np.sqrt(np.mean(e**2))), 'max_abs_error_W_m2': float(np.abs(e).max()),
                    'observed_energy_MJ_m2': float(y.sum()*3600/1e6),
                    'model_energy_MJ_m2': float(x.sum()*3600/1e6)}
    if picked:
        delta = np.asarray([r['ra37_hourly_W_m2']-r['ra4_hourly_W_m2'] for r in picked])
        out['ra37_minus_ra4_mean_W_m2'] = float(delta.mean())
    return out


def analyze(root):
    obs, headers = load_observations(root)
    model = json.loads((root/'model-extract.json').read_text())
    assert tuple(model['site_lat_lon_height']) == SITE
    items = []
    for h in range(48):
        start = START + dt.timedelta(hours=h); end = start + dt.timedelta(hours=1)
        item = {'start_utc': start.isoformat(), 'end_utc': end.isoformat(), **hourly(obs, start, end)}
        for arm in ('ra4', 'ra37'):
            ac = model['arms'][arm]['ACSWDNB_J_m2']
            assert len(ac) == 49 and all(math.isfinite(x) for x in ac)
            item[arm+'_hourly_W_m2'] = (ac[h+1]-ac[h])/3600
        items.append(item)
    with (root/'hourly-comparison.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(items[0]), lineterminator='\n'); w.writeheader(); w.writerows(items)
    results = {
        'schema': 'solrad-boundary-site-comparison-v1', 'status': 'DESCRIPTIVE_BOUNDARY_SITE_ONLY',
        'new_model_build_solver_invocations': 0,
        'window_utc': {'start_exclusive': START.isoformat(), 'end_inclusive': END.isoformat()},
        'expected_minutes': 2880, 'observed_minutes': sum(START < t <= END for t in obs),
        'observation_headers': headers, 'model_extract_sha256': sha(root/'model-extract.json'),
        'grid': model['arms']['ra4']['grid'],
        'metric_units': 'W m-2 unless otherwise named',
        'primary': {s: statistics(items, 'component_wm2', s) for s in ('all', 'daylight')},
        'secondary_global_psp': {s: statistics(items, 'global_psp_wm2', s) for s in ('all', 'daylight')},
        'interpretation_limits': [
            'One preselected operating station, two days, coupled states; no same-state engine error attribution.',
            'Sterling nearest cell is in the specified lateral-boundary relaxation zone, not independent interior skill.',
            'RA37 frozen-optics mode 1 is experimental; PR65-era executable, not the latest production tree.',
            'No LW instrument at this station; no LW or TOA validation.',
            'No observed DNI comparison to delta-scaled RTE direct flux.',
            'QC0 is not absolute truth; point versus 27km cell, radiometer offset and spectral coverage differ.',
            'No confidence interval or significance claim from 48 temporally correlated hours.',
            'All raw signed QC0 irradiances preserved; only the solar-direction projection is truncated below the horizon.',
            'Global PSP reported separately; no channel fallback, interpolation, or winner-based station/grid selection.'
        ]}
    (root/'comparison-results.json').write_text(json.dumps(results, indent=2, allow_nan=False)+'\n')
    return results


def main():
    p = argparse.ArgumentParser(); p.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    p.add_argument('--extract-from-pair', type=Path)
    args = p.parse_args()
    if args.extract_from_pair:
        extract_models(args.extract_from_pair, args.root/'model-extract.json')
    r = analyze(args.root)
    print(json.dumps({'status': r['status'], 'primary': r['primary']}, indent=2))


if __name__ == '__main__':
    main()
