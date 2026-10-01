#!/usr/bin/env python3
"""Inspect finite radiation tendencies and WRF surface/TOA diagnostics."""
import argparse
import json
from pathlib import Path
import netCDF4
import numpy as np

required = ['SWDOWN', 'GLW', 'SWDDIR', 'SWDDIF', 'SWDNT', 'LWUPT',
            'SWDNB', 'GSW', 'SWUPB', 'LWDNB', 'ACSWDNB', 'ACLWDNB', 'RTHRATEN', 'RTHRATLW', 'RTHRATSW']
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('cases', nargs='+', type=Path)
parser.add_argument('--expected-options', nargs='+', type=int, choices=(4, 37),
                    help='expected paired LW/SW option for each case, in order')
args = parser.parse_args()
if args.expected_options is not None and len(args.expected_options) != len(args.cases):
    parser.error('--expected-options requires one option per case')
results = {}
for index, folder in enumerate(args.cases):
    if 'SUCCESS COMPLETE WRF' not in (folder/'wrf.log').read_text():
        raise RuntimeError(f'{folder}: WRF success marker missing')
    paths = sorted(folder.glob('wrfout_d01_*'))
    if not paths:
        raise RuntimeError(f'{folder}: no history file')
    stats = {}
    with netCDF4.Dataset(paths[-1]) as ds:
        lw_option, sw_option = int(ds.RA_LW_PHYSICS), int(ds.RA_SW_PHYSICS)
        if args.expected_options is not None:
            expected = args.expected_options[index]
            if (lw_option, sw_option) != (expected, expected):
                raise RuntimeError(f'{folder}: expected {expected}/{expected}, got {lw_option}/{sw_option}')
        for name in required:
            if name not in ds.variables:
                raise RuntimeError(f'{folder}: missing {name}')
            values = ds[name][:]
            if np.ma.getmaskarray(values).any() or not np.isfinite(values).all():
                raise RuntimeError(f'{folder}: non-finite or missing {name}')
            stats[name] = {'min': float(values.min()), 'max': float(values.max())}
        if not stats['SWDOWN']['max'] > 0:
            raise RuntimeError(f'{folder}: daytime shortwave never calculated')
        if not stats['GLW']['max'] > 0:
            raise RuntimeError(f'{folder}: longwave never calculated')
        if not stats['ACSWDNB']['max'] > 0 or not stats['ACLWDNB']['max'] > 0:
            raise RuntimeError(f'{folder}: accumulated radiation never updated')
        sw = ds['SWDOWN'][:]; split = ds['SWDDIR'][:] + ds['SWDDIF'][:]
        if not np.allclose(sw, split, rtol=2e-5, atol=2e-3):
            raise RuntimeError(f'{folder}: surface direct/diffuse sum mismatch')
        if lw_option == 37 and sw_option == 37:
            if not np.allclose(sw, ds['SWDNB'][:], rtol=2e-5, atol=2e-3):
                raise RuntimeError(f'{folder}: SWDOWN/SWDNB mismatch')
            if not np.allclose(ds['GSW'][:], ds['SWDNB'][:] - ds['SWUPB'][:], rtol=2e-5, atol=2e-3):
                raise RuntimeError(f'{folder}: net absorbed shortwave mismatch')
        total = ds['RTHRATEN'][:]
        parts = ds['RTHRATLW'][:] + ds['RTHRATSW'][:]
        if not np.allclose(total, parts, rtol=1e-5, atol=1e-9):
            raise RuntimeError(f'{folder}: radiation tendency sum mismatch')
        if total.shape[0] < 2 or not np.any(np.abs(total[1:]) > 0):
            raise RuntimeError(f'{folder}: radiation tendencies never calculated after initialization')
        results[str(folder)] = {'time_count': total.shape[0], 'radiation_option_lw': int(ds.RA_LW_PHYSICS),
                                'radiation_option_sw': int(ds.RA_SW_PHYSICS), 'history_file': str(paths[-1]),
                                'checks': 'finite fields, daytime SW, LW, nonzero accumulation, flux/tendency sums',
                                'variables': stats}
print(json.dumps(results, indent=2))
