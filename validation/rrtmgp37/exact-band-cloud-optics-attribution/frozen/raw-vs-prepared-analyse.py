#!/usr/bin/env python3
"""Read existing SW optics only; no radiation solver or model launches."""
import gzip
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
HERE = Path(__file__).resolve().parent
PUB = ROOT / 'build/udm37-cf0-cu-replay-pr-work'
CAP = PUB / 'validation/rrtmgp37/rrtmg4-same-call-attribution'
INP = CAP / 'traces/NEW_ON/sw_000001.input'
BASE = ROOT / 'build/udm37-cf0-retained-cu-runtime-v1/run-v1/outputs/baseline-sw.result'
EXP = CAP / 'exports/rrtmg4_d01_i24_j55_step2161_sw.txt.gz'
COEF = ROOT / 'build/udm-cu-optics-design-work/WRF/run/rrtmgp-gas-sw-g112.nc'


def pin(path):
    data = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data)}


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    output = HERE / 'raw-vs-prepared.json'
    if output.exists():
        raise RuntimeError('Refusing to overwrite existing analysis')
    donor = ROOT / 'build/udm37-cf0-retained-cu-runtime-v1/run_eight.py'
    reader = ROOT / 'build/cf0-cu-src-v1/WRF/test/rrtmgp/compare_column_replay.py'
    legacy_reader = CAP / 'parser/read_export.py'
    pins = {str(p): pin(p) for p in (INP, BASE, EXP, COEF, donor, reader, legacy_reader, Path(__file__))}
    phase, nc, nl, f = module('rawprep_input', donor).parse_input(INP)
    s = module('rawprep_result', reader).read_result(BASE)['sections']
    assert (phase, nc, nl) == ('SW', 1, 45)
    with tempfile.TemporaryDirectory() as td:
        plain = Path(td) / 'export.txt'
        plain.write_bytes(gzip.decompress(EXP.read_bytes()))
        legacy = module('rawprep_legacy', legacy_reader).read_export(plain, expected_phase='SW')
    lf = legacy['fields']
    edges = list(zip(lf['CLOUD', 'BAND_WAVENUM_LO'].values, lf['CLOUD', 'BAND_WAVENUM_HI'].values))
    codes = lf['CLOUD', 'BAND_INDEX'].values
    legacy_gpt_codes = np.array(lf['CLOUD', 'GPOINT_TO_BAND'].values)
    lt = np.array(lf['CLOUD', 'CLDPRMC_TAU'].values).reshape((112,45), order='F')
    lr = np.array(lf['CLOUD', 'CLDPRMC_TAUOR'].values).reshape((112,45), order='F')
    mask = np.array(lf['CLOUD', 'MCICA_MASK'].values).reshape((112,45), order='F')
    dims, vals = f['RAW_PRECIP_TAU']
    raw_precip = np.array(vals).reshape(dims, order='F')
    assert dims == (1,45,14)
    with Dataset(COEF) as ds:
        bands = np.asarray(ds.variables['bnd_limits_wavenumber'][:])
    rows = []
    for gb, pair in enumerate(bands):
        matches = [i for i, edge in enumerate(edges) if tuple(pair) == edge]
        if not matches:
            assert gb in (0,1)
            continue
        assert len(matches) == 1 and gb >= 2
        lb = matches[0]
        pts = legacy_gpt_codes == codes[lb]
        for layer in (30,31,32):
            k = layer - 1
            assert np.all(mask[:,k] == 1) and np.all(s['MASK'][0,k,:] == 1)
            assert np.all(lt[pts,k] == lt[pts,k][0]) and np.all(lr[pts,k] == lr[pts,k][0])
            legacy_raw, legacy_prepared = float(lr[pts,k][0]), float(lt[pts,k][0])
            native_raw = float(s['NATIVE_CLOUD_TAU'][0,k,gb])
            cu_raw = float(s['CU_CLOUD_TAU'][0,k,gb])
            precip_raw32 = float(raw_precip[0,k,gb])
            gp_raw = native_raw + cu_raw + precip_raw32
            gp_prepared = float(s['PREPARED_TAU'][0,k,gb])
            assert legacy_raw > 0 and gp_raw > 0 and gp_prepared > 0
            rows.append({'native_layer_1based': layer, 'bounds_cm-1': list(map(float,pair)),
                         'gp_band_1based':gb+1, 'legacy_band_code':int(codes[lb]),
                         'legacy_TAUOR_real32':legacy_raw, 'legacy_prepared_tau_real32':legacy_prepared,
                         'gp_native_raw_tau_wp':native_raw, 'gp_CU_raw_tau_wp':cu_raw,
                         'gp_precip_raw_tau_promoted_real32':precip_raw32,
                         'gp_raw_sum_mixed_precision':gp_raw, 'gp_prepared_tau_wp':gp_prepared,
                         'legacy_raw_over_gp_raw':legacy_raw/gp_raw,
                         'legacy_prepared_over_gp_prepared':legacy_prepared/gp_prepared,
                         'legacy_prepared_over_legacy_raw':legacy_prepared/legacy_raw,
                         'gp_prepared_over_gp_raw':gp_prepared/gp_raw})
    assert len(rows) == 36
    assert pins == {str(p): pin(p) for p in map(Path,pins)}
    report = {'schema':'same-call-raw-prepared-descriptive-v1', 'status':'PASS_SCOPED_READ_ONLY',
              'solver_invocations':0, 'wrf_invocations':0, 'pins':pins, 'rows':rows,
              'limits':['36 band/layer tuples only; no flux attribution or physical accuracy',
                        'GP raw sum mixes native/CU wp values and captured REAL32 raw precipitation',
                        'GP and legacy use different ice/snow models, path/size conventions and transforms',
                        'TAUOR/prepared ratios are descriptive; they do not isolate a common delta transform',
                        'No spectral weighting, g-point averaging or first-two-band approximation'],
              'layer_ranges':{str(k):{n:[min(r[n] for r in rows if r['native_layer_1based']==k),
                                         max(r[n] for r in rows if r['native_layer_1based']==k)]
                                      for n in ('legacy_raw_over_gp_raw','legacy_prepared_over_gp_prepared',
                                                'legacy_prepared_over_legacy_raw','gp_prepared_over_gp_raw')}
                              for k in (30,31,32)}}
    with output.open('x') as out:
        json.dump(report, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')
    print(json.dumps({'output':pin(output), 'layer_ranges':report['layer_ranges']}))


if __name__ == '__main__':
    main()
