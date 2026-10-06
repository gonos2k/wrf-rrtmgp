"""Experimental offline optical moment lookup; no WRF runtime activation.

Interpolate kappa*rho/lambda in log(lambda), then restore lambda. This makes
the constant-efficiency sphere limit exact. Interpolate LW source temperature
linearly. Convex interpolation of moments retains extinction/scattering/
absorption closure; ratios such as single-scattering albedo are derived last.
There is no axis extrapolation or optical coefficient clipping.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np

import compare

ALGORITHM = 'NORMALIZED_MOMENTS_LOG_LAMBDA_LINEAR_T_V1'


def _values(value, name):
    if np.any(np.ma.getmaskarray(value)):
        raise ValueError(f'Masked {name}')
    result = np.asarray(value, dtype=np.float64)
    if not np.all(np.isfinite(result)):
        raise ValueError(f'Nonfinite {name}')
    return result


def _bracket(axis, query, name):
    if np.any(query < axis[0]) or np.any(query > axis[-1]):
        raise ValueError(f'{name} outside table range [{axis[0]}, {axis[-1]}]; no extrapolation')
    if len(axis) == 1:
        return np.zeros(query.shape, dtype=int), np.zeros(query.shape, dtype=int), np.zeros(query.shape)
    upper = np.clip(np.searchsorted(axis, query, side='right'), 1, len(axis)-1)
    lower = upper-1
    fraction = (query-axis[lower])/(axis[upper]-axis[lower])
    return lower, upper, fraction


class FrozenTable:
    def __init__(self, generation: Path):
        self.axes, self.arrays, receipt, self.receipt_sha256 = compare.load(Path(generation))
        self.table_sha256 = receipt['table_sha256']
        self.artifact_verification = dict(receipt['_artifact_verification'])
        for array in list(self.axes.values()) + list(self.arrays.values()):
            array.setflags(write=False)

    def moments(self, phase, slope, temperature=None):
        """Return kappa*rho_bulk [m-1], shape query_shape+(band,).

        SW has no temperature argument. LW temperature must have the same
        shape as slope: implicit state broadcasting is deliberately rejected.
        Empty inputs return empty band arrays, but all supplied values must
        otherwise be positive finite and within the exact table axes.
        """
        if phase not in ('SW', 'LW'):
            raise ValueError('Phase must be SW or LW')
        slope = _values(slope, 'lambda')
        if np.any(slope <= 0):
            raise ValueError('Lambda must be positive')
        # Check range in the physical coordinate before its logarithm.
        _bracket(self.axes['lambda'], slope, 'Lambda')
        i0, i1, fs = _bracket(np.log(self.axes['lambda']), np.log(slope), 'Log lambda')
        if phase == 'LW':
            if temperature is None:
                raise ValueError('LW needs source-weighting temperature')
            temperature = _values(temperature, 'temperature')
            if temperature.shape != slope.shape:
                raise ValueError('Temperature/lambda shapes differ')
            j0, j1, ft = _bracket(self.axes['temperature'], temperature, 'Temperature')
        elif temperature is not None:
            raise ValueError('SW coefficients have no source temperature axis')
        answer = {}
        for moment in compare.MOMENTS:
            values = self.arrays[phase.lower()+'_'+moment+'_times_density']
            if phase == 'SW':
                lo = values[i0, :]/self.axes['lambda'][i0, None]
                hi = values[i1, :]/self.axes['lambda'][i1, None]
            else:
                lo = ((1-ft)[..., None]*values[i0, j0, :] + ft[..., None]*values[i0, j1, :]) / self.axes['lambda'][i0, None]
                hi = ((1-ft)[..., None]*values[i1, j0, :] + ft[..., None]*values[i1, j1, :]) / self.axes['lambda'][i1, None]
            answer[moment] = ((1-fs)[..., None]*lo+fs[..., None]*hi)*slope[..., None]
        return answer

    def optical_depth(self, phase, slope, water_path_g_m2, bulk_density, temperature=None):
        """Mass-normalized optical moments; caller supplies occurrence/path policy.

        No positive mass is discarded at the UDM process cutoff. This method
        does not choose a precipitation fraction or cloud mask, or apply delta
        scaling. The path may be grid mean or in-occurrence, explicitly chosen
        by the caller; density must use the same shape as slope or be scalar.
        """
        slope = _values(slope, 'lambda')
        path = _values(water_path_g_m2, 'water path')
        density = _values(bulk_density, 'bulk density')
        if path.shape != slope.shape or density.shape not in ((), slope.shape):
            raise ValueError('Path/density/lambda shapes differ')
        if np.any(path < 0) or np.any(density <= 0):
            raise ValueError('Path must be nonnegative and bulk density positive')
        factor = path*1e-3/density
        moments = self.moments(phase, slope, temperature)
        result = {name: values*factor[..., None] for name, values in moments.items()}
        if any(not np.all(np.isfinite(values)) for values in result.values()):
            raise ValueError('Optical depth overflow')
        return result


def reconstructed_udm_slope(q, rho_microphysics, species):
    """State diagnostic using UDM slope closure, not an exported process slope.

    q is the returned dry-air mixing ratio. rho_microphysics is the moist-air
    density supplied to UDM by WRF (not the native dry mass density). Returned
    q has already undergone sedimentation. Preserve that attribution; do not
    interpret this reconstructed slope as UDM's pre-sedimentation work array.
    """
    constants = {'graupel': (4e6, 500.), 'hail': (4e4, 912.)}
    if species not in constants:
        raise ValueError('Species must be graupel or hail')
    q = _values(q, 'mixing ratio')
    density = _values(rho_microphysics, 'UDM air density')
    if q.shape != density.shape or np.any(q < 0) or np.any(density <= 0):
        raise ValueError('UDM q/density shape or range')
    n0, bulk_density = constants[species]
    slope = np.full(q.shape, 20000.)
    active = q > 1e-9
    # Log form avoids overflow of an intermediate ratio for extreme inputs.
    slope[active] = np.exp(np.minimum(np.log(20000.),
        .25*(np.log(np.pi*bulk_density*n0)-np.log(q[active])-np.log(density[active]))))
    if not np.all(np.isfinite(slope)) or np.any(slope <= 0):
        raise ValueError('Invalid reconstructed UDM slope')
    return slope
