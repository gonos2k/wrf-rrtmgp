#!/usr/bin/env python3
"""Offline lookup contracts, including exact limits and invalid state rejection."""
import argparse
import json
from pathlib import Path
import re
import numpy as np

import compare
import generate as gen
from lookup import FrozenTable, reconstructed_udm_slope


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error('Use a new output directory')
    table = FrozenTable(args.generation)
    cases = []
    maximum_node_error = 0.
    # Every table knot must be recovered. Arbitrary state-shaped queries do
    # not implicitly mix temperature/size indices or swap wavelength bands.
    for phase in ('SW', 'LW'):
        for i, slope in enumerate(table.axes['lambda']):
            temperatures = table.axes['temperature'] if phase == 'LW' else [None]
            for j, temperature in enumerate(temperatures):
                values = table.moments(phase, slope, temperature)
                for name in compare.MOMENTS:
                    source = table.arrays[phase.lower()+'_'+name+'_times_density']
                    expected = source[i, j, :] if phase == 'LW' else source[i, :]
                    error = np.max(np.abs(values[name]-expected))
                    maximum_node_error = max(maximum_node_error, float(error))
                    np.testing.assert_allclose(values[name], expected, rtol=2e-15, atol=1e-12)
    cases.append('all_table_knots')
    # Analytic constant-Q efficiencies: kappa*rho is exactly proportional to
    # lambda. The optional linear T dependence exercises both interpolation
    # directions and derived ratios without numerical Mie uncertainty.
    synthetic = FrozenTable.__new__(FrozenTable)
    synthetic.axes = {'lambda': np.array([100., 1000., 20000.]),
                      'temperature': np.array([180., 240., 300.])}
    synthetic.arrays = {}
    coefficients = {'extinction': 2., 'scattering': 1.5,
                    'scatter_times_g': .75, 'absorption': .5}
    for name, coefficient in coefficients.items():
        synthetic.arrays['sw_'+name+'_times_density'] = np.outer(synthetic.axes['lambda'], np.full(14, coefficient))
        synthetic.arrays['lw_'+name+'_times_density'] = (synthetic.axes['lambda'][:, None, None] *
            (synthetic.axes['temperature'][None, :, None]/240.) * np.full((1, 1, 16), coefficient))
    slope = np.array([[100., 316.22776601683796], [6324.555320336759, 20000.]])
    temperature = np.array([[180., 215.], [275., 300.]])
    for phase in ('SW', 'LW'):
        values = synthetic.moments(phase, slope, temperature if phase == 'LW' else None)
        expected_base = slope*(temperature/240. if phase == 'LW' else 1.)
        for name, coefficient in coefficients.items():
            np.testing.assert_allclose(values[name], np.broadcast_to((coefficient*expected_base)[..., None], values[name].shape), rtol=2e-15)
        np.testing.assert_allclose(values['extinction'], values['scattering']+values['absorption'], rtol=2e-15)
        np.testing.assert_allclose(values['scatter_times_g']/values['scattering'], .5, rtol=2e-15)
    cases += ['constant_Q_lambda_limit', 'linear_T_limit', 'closure_and_derived_asymmetry']
    # Units/density/path closure: species density scales opacity, while every
    # nonzero path, including mass below UDM's process cutoff, is consumed.
    path = np.array([[0., 1e-10], [50., 100.]])
    for density in (500., 912.):
        values = synthetic.optical_depth('SW', slope, path, density)
        for name, coefficient in coefficients.items():
            expected = coefficient*slope*path*1e-3/density
            np.testing.assert_allclose(values[name], np.broadcast_to(expected[..., None], values[name].shape), rtol=2e-15)
        assert np.all(values['extinction'][0, 1, :] > 0)
        assert np.all(values['extinction'][0, 0, :] == 0)
    cases.append('g_m2_to_kg_m2_density_and_tiny_path')
    q = np.array([0., 1e-15, 1e-9, 1.01e-9, 1e-5, .003])
    rho_air = np.array([1., .2, .4, 1., .6, 1.3])
    for species, n0, density in [('graupel', 4e6, 500.), ('hail', 4e4, 912.)]:
        actual = reconstructed_udm_slope(q, rho_air, species)
        expected = np.full(q.shape, 20000.)
        active = q > 1e-9
        expected[active] = np.minimum(20000., (np.pi*density*n0/(q[active]*rho_air[active]))**.25)
        np.testing.assert_allclose(actual, expected, rtol=2e-15)
    cases.append('UDM_reconstructed_slope_cutoff_cap_and_density')
    udm_source = gen.ROOT/'WRF/phys/module_mp_udm.F'
    text = udm_source.read_text()
    constants = {'n0g': 4e6, 'n0h': 4e4, 'deng': 500., 'denh': 912.,
                 'lamdagmax': 20000., 'lamdahmax': 20000., 'qrmin': 1e-9}
    for name, expected in constants.items():
        match = re.search(r'\b'+name+r'\s*=\s*([.0-9eE+-]+)', text)
        assert match is not None and float(match.group(1)) == expected, 'UDM source constant differs: '+name
    cases.append('current_UDM_source_constants')
    # A singleton axis supports its exact point; empty shapes remain empty.
    singleton = FrozenTable.__new__(FrozenTable)
    singleton.axes = {'lambda': np.array([1000.]), 'temperature': np.array([240.])}
    singleton.arrays = {name: values[1:2, 1:2, :] if name.startswith('lw') else values[1:2, :]
                       for name, values in synthetic.arrays.items()}
    assert singleton.moments('LW', 1000., 240.)['extinction'].shape == (16,)
    assert singleton.moments('LW', np.empty((0, 3)), np.empty((0, 3)))['extinction'].shape == (0, 3, 16)
    cases.append('singleton_and_empty_query')
    failures = {
        'lambda_low': lambda: synthetic.moments('SW', 99.),
        'lambda_high': lambda: synthetic.moments('SW', 20001.),
        'lambda_nan': lambda: synthetic.moments('SW', np.nan),
        'lambda_infinity': lambda: synthetic.moments('SW', np.inf),
        'lambda_zero': lambda: synthetic.moments('SW', 0.),
        'lambda_negative': lambda: synthetic.moments('SW', -1.),
        'lambda_masked': lambda: synthetic.moments('SW', np.ma.array([1000.], mask=[True])),
        'temperature_low': lambda: synthetic.moments('LW', 1000., 179.),
        'temperature_high': lambda: synthetic.moments('LW', 1000., 301.),
        'temperature_nan': lambda: synthetic.moments('LW', 1000., np.nan),
        'temperature_masked': lambda: synthetic.moments('LW', np.array([1000.]), np.ma.array([240.], mask=[True])),
        'temperature_shape': lambda: synthetic.moments('LW', np.array([1000.]), 240.),
        'temperature_missing': lambda: synthetic.moments('LW', 1000.),
        'temperature_SW': lambda: synthetic.moments('SW', 1000., 240.),
        'phase': lambda: synthetic.moments('sw', 1000.),
        'singleton_extrapolation': lambda: singleton.moments('LW', 1000., 241.),
        'path_negative': lambda: synthetic.optical_depth('SW', 1000., -1., 500.),
        'path_nan': lambda: synthetic.optical_depth('SW', 1000., np.nan, 500.),
        'path_shape': lambda: synthetic.optical_depth('SW', np.array([1000.]), 1., 500.),
        'density_zero': lambda: synthetic.optical_depth('SW', 1000., 1., 0.),
        'density_negative': lambda: synthetic.optical_depth('SW', 1000., 1., -1.),
        'density_nonfinite': lambda: synthetic.optical_depth('SW', 1000., 1., np.inf),
        'density_shape': lambda: synthetic.optical_depth('SW', 1000., 1., np.array([500.])),
        'q_negative': lambda: reconstructed_udm_slope(-1e-15, 1., 'hail'),
        'q_nonfinite': lambda: reconstructed_udm_slope(np.nan, 1., 'hail'),
        'air_density_zero': lambda: reconstructed_udm_slope(1e-5, 0., 'hail'),
        'air_density_nonfinite': lambda: reconstructed_udm_slope(1e-5, np.inf, 'hail'),
        'air_density_shape': lambda: reconstructed_udm_slope(np.array([1e-5]), 1., 'hail'),
        'unknown_species': lambda: reconstructed_udm_slope(1e-5, 1., 'snow'),
    }
    rejected = []
    for name, action in failures.items():
        try:
            action()
        except ValueError as exc:
            rejected.append({'name': name, 'reason': str(exc)})
        else:
            raise AssertionError('Accepted invalid state: '+name)
    result = dict(status='PASS_OFFLINE_LOOKUP_CONTRACT', valid_cases=cases,
                  expected_rejections=rejected, maximum_knot_absolute_error=maximum_node_error,
                  lookup_sha256=gen.sha(gen.HERE/'lookup.py'), test_sha256=gen.sha(Path(__file__).resolve()),
                  artifact_validator_sha256=gen.sha(gen.HERE/'compare.py'),
                  udm_source_sha256=gen.sha(udm_source), udm_constants=constants,
                  generation_receipt_sha256=table.receipt_sha256, table_sha256=table.table_sha256,
                  scope='Interpolation algebra, units and failure behavior; not interpolation accuracy or WRF activation')
    args.output_dir.mkdir(parents=True)
    (args.output_dir/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'status': result['status'], 'valid_cases': len(cases), 'expected_rejections': len(rejected)}))


if __name__ == '__main__':
    main()
