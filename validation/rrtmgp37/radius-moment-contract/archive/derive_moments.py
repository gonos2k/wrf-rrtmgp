#!/usr/bin/env python3
"""Independent spherical Gamma-moment audit; no radiation/model execution."""
from pathlib import Path
import hashlib
import json
import math

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TREE = ROOT / 'build/udm37-rfmip-historical-source-pr-work'


def pin(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    target = HERE / 'moment-result.json'
    if target.exists():
        raise FileExistsError('Refusing to replace a completed moment audit')
    # x = lambda*r. Laguerre weights integrate exp(-x) over [0,infinity).
    x, w = np.polynomial.laguerre.laggauss(64)
    rows = []
    for nu in range(2, 16):
        integrals = [float(np.dot(w, x ** (nu+k))) for k in range(4)]
        exact = [math.gamma(nu+k+1) for k in range(4)]
        errors = [abs(a-b)/b for a, b in zip(integrals, exact)]
        ratio = (nu+3) / ((nu+1)*(nu+2)*(nu+3))**(1/3)
        quad_ratio = (integrals[3]/integrals[2]) / (integrals[3]/integrals[0])**(1/3)
        if max(errors) > 5e-12 or abs(quad_ratio-ratio) > 5e-12:
            raise ValueError('Independent Gamma quadrature does not close analytic moments')
        rows.append({'nu': nu, 'gamma_moments_x_k0_to_k3': integrals,
                     'max_relative_quadrature_error': max(errors),
                     're_M3_M2_over_volume_mean_radius': ratio,
                     'independent_quadrature_radius_ratio': quad_ratio})
    # This comparison uses the effective-radius routine's stated L=rho*qc
    # and number argument as the volumetric Nc used by slope_cloud/UDM
    # constants. It does not infer units from generic Registry metadata.
    rho_water = 1000.
    pi_udm = float(np.float32(3.141592653589793))
    min_radius, max_radius = 2.51e-6, 50e-6
    samples = []
    for nc in (5e7, 1e8, 3e8, 1e9, 2.1e9):
        nc_autoconv = min(max(nc, 2.), 1e12)
        nu = min(math.floor(1e9/nc_autoconv + .5) + 2, 15)
        for lwc in (1e-5, 1e-4, 1e-3):
            r_volume = (3*lwc/(4*pi_udm*rho_water*nc))**(1/3)
            native_formula = .5/(pi_udm*rho_water/6*nc/lwc)**(1/3)
            gamma_lambda_r = (nc*(pi_udm*rho_water/6)*8*math.gamma(nu+4)/math.gamma(nu+1)/lwc)**(1/3)
            re_gamma = (nu+3)/gamma_lambda_r
            if abs(native_formula-r_volume) > 1e-18:
                raise ValueError('Native source formula is not the spherical volume-mean radius')
            samples.append({'number_concentration_m_minus3': nc, 'L_kg_m_minus3': lwc,
                            'nu_from_autoconversion_rule': nu,
                            'native_unclipped_formula_m': native_formula,
                            'native_after_stated_radius_bounds_m': min(max(native_formula,min_radius),max_radius),
                            'Gamma_effective_M3_M2_radius_m': re_gamma,
                            'unclipped_re_gamma_over_native': re_gamma/native_formula,
                            'native_would_clip': not min_radius <= native_formula <= max_radius})
    result = {
        'schema': 'udm37-liquid-radius-moment-audit-v1',
        'status': 'PASS_SCOPED_SPHERICAL_GAMMA_MOMENT_DERIVATION_NO_POLICY_CHANGE',
        'source_pins': {'UDM': pin(TREE/'WRF/phys/module_mp_udm.F'),
                        'adapter': pin(TREE/'WRF/phys/module_ra_rrtmgp.F'),
                        'calculator': pin(HERE/'derive_moments.py')},
        'definitions': {'radius_PSD': 'n(r)=n0*r**nu*exp(-lambda*r)',
                        'M_k': 'integral(r**k*n(r),r=0..infinity)',
                        'volume_mean_radius': '(M3/M0)**(1/3)',
                        'spherical_optical_effective_radius': 'M3/M2',
                        'native_unclipped_radius': '0.5*(L/(pidnc*Nc))**(1/3); pidnc=pi*rho_water/6',
                        'Gamma_re_over_r_volume': '((nu+3)**2/((nu+1)*(nu+2)))**(1/3)'},
        'quadrature': {'method': '64-node Gauss-Laguerre; x=lambda*r', 'shape_rows': rows},
        'samples': samples,
        'bounds': {'nu_range_in_autoconversion': [2,15],
                   'min_gamma_to_volume_radius_ratio': min(row['re_M3_M2_over_volume_mean_radius'] for row in rows),
                   'max_gamma_to_volume_radius_ratio': max(row['re_M3_M2_over_volume_mean_radius'] for row in rows)},
        'assumptions_and_limits': [
            'The native routine formula equals a volume-mean radius before clipping if its number argument is volumetric Nc. Source constants and slope_cloud support that convention; generic Registry labels alone do not.',
            'The Gamma PSD is directly used in the autoconversion closure. This calculation does not prove it is the prescribed radiation PSD.',
            'The core divides condensate by its cloud fraction without dividing Nc in that block; post-step native radius uses restored grid condensate. No same-occurrence moment identity is asserted.',
            'Clipped or placeholder radii are excluded from the analytic radius identity; sample clipping is explicitly marked.',
            'No optical coefficient table, atmospheric column, model tendency, forecast or observation is evaluated. No flux error percentage or production correction is inferred.'
        ],
        'new_WRF_REAL_RTE_solver_build_calls': 0,
        'production_changes': 0,
    }
    target.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({'status':result['status'], 'shape_rows':len(rows), 'sample_rows':len(samples),
                      'radius_ratio_range':result['bounds'], 'max_quadrature_relative_error':max(row['max_relative_quadrature_error'] for row in rows)},sort_keys=True))


if __name__ == '__main__':
    main()
