#!/usr/bin/env python3
"""Compare offline interpolation with direct Mie/PSD integration on held-out axes.

The direct calculation shares the material/PSD model and numerical controls;
this measures sampled interpolation error, not material or forecast accuracy.
"""
import argparse
import json
from pathlib import Path
import numpy as np

import compare
import generate as gen
from lookup import ALGORITHM, FrozenTable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--table', type=Path, required=True)
    parser.add_argument('--direct', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-extinction-normalized-error', type=float)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new output file')
    tolerance = args.max_extinction_normalized_error
    if tolerance is not None and (not np.isfinite(tolerance) or tolerance <= 0):
        parser.error('Requested numerical tolerance must be positive finite')
    table = FrozenTable(args.table)
    axes, arrays, direct, direct_hash = compare.load(args.direct)
    _, _, receipt, _ = compare.load(args.table)
    for name in ('input_sources', 'gas_data_sha256', 'generator_sha256', 'kernel_source_sha256',
                 'kernel_source_adaptation', 'numerical_packages', 'compiler', 'kernel_flags',
                 'quadrature_algorithm', 'order', 'max_spectral_step_cm_inv'):
        compare.require(receipt[name] == direct[name], name+' differs; interpolation is not isolated')
    slope, temperature = np.meshgrid(axes['lambda'], axes['temperature'], indexing='ij')
    metrics = {}
    for phase in ('SW', 'LW'):
        lam = axes['lambda'] if phase == 'SW' else slope
        values = table.moments(phase, lam, temperature if phase == 'LW' else None)
        extinction = arrays[phase.lower()+'_extinction_times_density']
        for name, interpolated in values.items():
            reference = arrays[phase.lower()+'_'+name+'_times_density']
            error = np.abs(interpolated-reference)
            scaled = error/extinction
            index = np.unravel_index(np.argmax(scaled), scaled.shape)
            metrics[phase+'_'+name] = {
                'max_absolute_times_density_m_inv': float(np.max(error)),
                'max_extinction_normalized_error': float(np.max(scaled)),
                'worst_index': list(map(int, index)),
                'worst_lambda_m_inv': float(axes['lambda'][index[0]]),
                'worst_temperature_K': None if phase == 'SW' else float(axes['temperature'][index[1]]),
                'worst_band_one_based': int(index[-1]+1),
            }
    maximum = max(metric['max_extinction_normalized_error'] for metric in metrics.values())
    passed = None if tolerance is None else maximum <= tolerance
    result = dict(status='SAMPLED_INTERPOLATION_DIFFERENCE_NOT_MODEL_VALIDATION',
                  algorithm=ALGORITHM, lookup_sha256=gen.sha(gen.HERE/'lookup.py'),
                  validator_sha256=gen.sha(Path(__file__).resolve()),
                  artifact_validator_sha256=gen.sha(gen.HERE/'compare.py'),
                  table_receipt_sha256=table.receipt_sha256, direct_receipt_sha256=direct_hash,
                  table_axes={name: table.axes[name].tolist() for name in ('lambda', 'temperature')},
                  direct_axes={name: axes[name].tolist() for name in ('lambda', 'temperature')},
                  maximum_extinction_normalized_error=maximum, metrics=metrics,
                  requested_numerical_tolerance=tolerance, requested_numerical_tolerance_pass=passed,
                  scope='Same controls/material/PSD, sampled size/temperature interpolation; no worst-case bound or forecast accuracy')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'status': result['status'], 'maximum_extinction_normalized_error': maximum,
                      'requested_numerical_tolerance_pass': passed}))
    if passed is False:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
