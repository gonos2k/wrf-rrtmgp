#!/usr/bin/env python3
"""Read-only hourly RA37-minus-RA4 descriptive plot and SW-active grouping."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import netCDF4
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def read_history(path: Path):
    with netCDF4.Dataset(path) as ds:
        ds.set_auto_maskandscale(False)
        times = netCDF4.chartostring(ds['Times'][:]).astype(str).tolist()
        arrays = {name: np.asarray(ds[name][:], dtype=np.float64)
                  for name in ('SWDOWN', 'GLW', 'OLR')}
    if any(not np.isfinite(v).all() for v in arrays.values()):
        raise ValueError(f'nonfinite values in selected variables: {path}')
    return times, arrays


def metrics(values: np.ndarray) -> dict:
    return {'sample_count': int(values.size),
            'mean_ra37_minus_ra4': float(np.mean(values)),
            'rmse': float(np.sqrt(np.mean(values * values))),
            'max_abs': float(np.max(np.abs(values)))}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--ra4-history', required=True, type=Path)
    p.add_argument('--ra37-history', required=True, type=Path)
    p.add_argument('--output-dir', required=True, type=Path)
    a = p.parse_args()
    a.output_dir.mkdir(parents=True, exist_ok=True)
    t4, x = read_history(a.ra4_history)
    t37, y = read_history(a.ra37_history)
    if t4 != t37 or len(t4) != 49:
        raise ValueError('expected matching 49-record hourly histories')
    if any(x[k].shape != y[k].shape for k in x):
        raise ValueError('paired array shape mismatch')

    # Classify whole records by actual saved shortwave activity in either arm.
    # This is a data-derived SW-active/SW-zero grouping, not a solar-geometry test.
    sw_active = np.any((x['SWDOWN'] > 0) | (y['SWDOWN'] > 0), axis=(1, 2))
    d_glw = y['GLW'] - x['GLW']
    d_olr = y['OLR'] - x['OLR']
    d_swdown = y['SWDOWN'] - x['SWDOWN']
    group = {}
    for key, mask in (('sw_active_records', sw_active), ('both_arms_sw_zero_records', ~sw_active)):
        group[key] = {
            'record_count': int(mask.sum()),
            'times': [t for t, keep in zip(t4, mask) if keep],
            'GLW_W_m2': metrics(d_glw[mask]),
            'OLR_W_m2': metrics(d_olr[mask]),
            'SWDOWN_W_m2': metrics(d_swdown[mask]),
        }
    means = {
        'times': t4,
        'domain_mean_SW_down_W_m2': {
            'ra4': x['SWDOWN'].mean(axis=(1, 2)).tolist(),
            'ra37': y['SWDOWN'].mean(axis=(1, 2)).tolist(),
        },
        'domain_mean_difference_RA37_minus_RA4_W_m2': {
            'GLW': d_glw.mean(axis=(1, 2)).tolist(),
            'OLR': d_olr.mean(axis=(1, 2)).tolist(),
            'SWDOWN': d_swdown.mean(axis=(1, 2)).tolist(),
        },
    }
    result = {
        'schema': 'matthew-dt60-48h-diurnal-descriptive-v1',
        'status': 'DESCRIPTIVE_ONLY',
        'classification': 'A time record is SW-active if any grid cell in either saved SWDOWN field is positive; otherwise both arms are SW-zero. This is not a solar-zenith classification.',
        'pair': {'ra4_history': str(a.ra4_history.resolve()), 'ra37_history': str(a.ra37_history.resolve()),
                 'record_count': len(t4), 'start': t4[0], 'end': t4[-1]},
        'grouped_metrics': group,
        'hourly_domain_means': means,
        'interpretation': 'Coupled-state RA37-minus-RA4 descriptive differences, not same-state radiation-operator error or forecast accuracy.'
    }
    (a.output_dir / 'paired-diurnal-summary.json').write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')

    hours = np.arange(len(t4))
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True, constrained_layout=True)
    for idx, active in enumerate(sw_active):
        if active:
            for ax in axes:
                ax.axvspan(idx - .5, idx + .5, color='#ffe08a', alpha=.35, linewidth=0)
    axes[0].plot(hours, d_glw.mean(axis=(1, 2)), label='GLW', color='#087e8b')
    axes[0].plot(hours, d_olr.mean(axis=(1, 2)), label='OLR', color='#d1495b')
    axes[0].axhline(0, color='black', linewidth=.6)
    axes[0].set_ylabel('RA37 − RA4 (W m$^{-2}$)')
    axes[0].set_title('Hourly domain-mean paired differences; shaded records have SWDOWN > 0')
    axes[0].legend(frameon=False, ncol=2)
    axes[1].plot(hours, d_swdown.mean(axis=(1, 2)), label='SWDOWN', color='#4c78a8')
    axes[1].axhline(0, color='black', linewidth=.6)
    axes[1].set_ylabel('RA37 − RA4 SWDOWN\n(W m$^{-2}$)')
    axes[1].legend(frameon=False)
    axes[2].plot(hours, x['SWDOWN'].mean(axis=(1, 2)), label='RA4 SWDOWN', color='#4c78a8')
    axes[2].plot(hours, y['SWDOWN'].mean(axis=(1, 2)), label='RA37 SWDOWN', color='#f58518')
    axes[2].set_ylabel('Domain mean SWDOWN\n(W m$^{-2}$)')
    axes[2].set_xlabel('UTC time')
    axes[2].set_xticks(hours[::4], [t[11:16] for t in t4[::4]], rotation=45, ha='right')
    axes[2].legend(frameon=False, ncol=2)
    fig.suptitle('48-hour coupled trajectories (descriptive only)')
    fig.savefig(a.output_dir / 'paired-diurnal-differences.png', dpi=150)
    plt.close(fig)

if __name__ == '__main__':
    main()
