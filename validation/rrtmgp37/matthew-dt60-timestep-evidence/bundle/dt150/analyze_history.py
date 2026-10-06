#!/usr/bin/env python3
"""Read-only endpoint eta-Courant analysis for native WW history output.

No threshold is applied. Missing, masked/fill, zero-denominator, and nonfinite
values are reported as evidence rather than filtered into an acceptance result.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

DT_SECONDS = 150.0
VARS = ('WW', 'DNW', 'C1F', 'C2F', 'MU', 'MUB', 'Times')

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

def decode_time(row) -> str:
    if getattr(row, 'dtype', None) is not None and row.dtype.kind == 'S':
        return b''.join(row.tolist()).decode('ascii', errors='replace').rstrip('\x00 ')
    return ''.join(chr(int(x)) for x in row).rstrip('\x00 ')

def read_raw(var):
    var.set_auto_maskandscale(False)
    raw = np.asarray(var[:])
    fill = getattr(var, '_FillValue', None)
    missing = getattr(var, 'missing_value', None)
    fill_count = 0
    fill_mask = np.zeros(raw.shape, dtype=bool)
    for marker in (fill, missing):
        if marker is not None:
            try:
                if np.issubdtype(raw.dtype, np.floating) and np.isnan(marker):
                    this_mask = np.isnan(raw)
                else:
                    this_mask = raw == marker
                fill_mask |= this_mask
                fill_count = int(np.count_nonzero(fill_mask))
            except (TypeError, ValueError):
                pass
    return raw, fill_count, fill_mask

def analyze(path: Path) -> dict:
    path = Path(path).resolve(strict=True)
    result = {'path': str(path), 'size_bytes': path.stat().st_size, 'sha256': sha(path),
              'dt_seconds': DT_SECONDS, 'formula': 'abs(WW * dt / DNW / (C1F*(MU+MUB)+C2F))',
              'status': 'ANALYZED_NO_ACCEPTANCE_THRESHOLD', 'missing_variables': [], 'variables': {},
              'times': [], 'records': []}
    with Dataset(path, 'r') as ds:
        ds.set_auto_maskandscale(False)
        selected = {}
        for name in VARS:
            match = name if name in ds.variables else next((k for k in ds.variables if k.lower() == name.lower()), None)
            if match is None:
                result['missing_variables'].append(name)
            else:
                selected[name] = match
        if result['missing_variables']:
            result['status'] = 'INCOMPLETE_REQUIRED_FIELDS'
            return result
        loaded = {}
        fill_masks = {}
        for name in VARS:
            var = ds.variables[selected[name]]
            raw, fill_count, fill_mask = read_raw(var)
            result['variables'][name] = {
                'dimensions': list(var.dimensions), 'shape': list(raw.shape),
                'dtype': str(raw.dtype), 'netcdf_name': selected[name], 'units': getattr(var, 'units', None),
                'nonfinite_count': int(np.count_nonzero(~np.isfinite(raw))) if raw.dtype.kind == 'f' else 0,
                'fill_or_missing_count': fill_count,
            }
            loaded[name] = raw
            fill_masks[name] = fill_mask
        ww, dnw, c1f, c2f, mu, mub = (loaded[x].astype(np.float64, copy=False) for x in ('WW', 'DNW', 'C1F', 'C2F', 'MU', 'MUB'))
        times = [decode_time(row) for row in loaded['Times']]
        result['times'] = times
        expected = {
            'WW': ('Time', 'bottom_top_stag', 'south_north', 'west_east'),
            'DNW': ('Time', 'bottom_top'),
            'C1F': ('Time', 'bottom_top_stag'),
            'C2F': ('Time', 'bottom_top_stag'),
            'MU': ('Time', 'south_north', 'west_east'),
            'MUB': ('Time', 'south_north', 'west_east'),
        }
        result['dimension_contract'] = {n: list(ds.variables[selected[n]].dimensions) == list(d) for n, d in expected.items()}
        if not all(result['dimension_contract'].values()):
            result['status'] = 'UNEXPECTED_DIMENSION_CONTRACT'
            return result
        if (ww.ndim != 4 or c1f.shape != ww.shape[:2] or c2f.shape != ww.shape[:2]
                or dnw.shape[0] != ww.shape[0] or dnw.shape[1] != ww.shape[1] - 1
                or mu.shape != (ww.shape[0], ww.shape[2], ww.shape[3]) or mub.shape != mu.shape):
            result['status'] = 'UNEXPECTED_STAGGER_SHAPES'
            result['observed_shapes'] = {k: list(v.shape) for k, v in loaded.items()}
            return result
        # WRF module_ieva_em.F iterates interior full/w interfaces k=2..ktf-1.
        # NetCDF zero-based WW/C1F/C2F indices 1:-1 align with DNW indices 1:.
        wi = ww[:, 1:-1, :, :]
        c1 = c1f[:, 1:-1]
        c2 = c2f[:, 1:-1]
        delta_eta = dnw[:, 1:]
        mut = mu + mub
        pressure_scale = c1[:, :, None, None] * mut[:, None, :, :] + c2[:, :, None, None]
        bad = {
            'ww_nonfinite': ~np.isfinite(wi),
            'dnw_nonfinite': (~np.isfinite(delta_eta))[:, :, None, None],
            'c1f_nonfinite': (~np.isfinite(c1))[:, :, None, None],
            'c2f_nonfinite': (~np.isfinite(c2))[:, :, None, None],
            'mu_or_mub_nonfinite': (~np.isfinite(mu) | ~np.isfinite(mub))[:, None, :, :],
            'ww_fill_or_missing': fill_masks['WW'][:, 1:-1, :, :],
            'dnw_fill_or_missing': fill_masks['DNW'][:, 1:, None, None],
            'c1f_fill_or_missing': fill_masks['C1F'][:, 1:-1, None, None],
            'c2f_fill_or_missing': fill_masks['C2F'][:, 1:-1, None, None],
            'mu_or_mub_fill_or_missing': (fill_masks['MU'] | fill_masks['MUB'])[:, None, :, :],
            'pressure_scale_nonfinite': ~np.isfinite(pressure_scale),
            'zero_pressure_scale': pressure_scale == 0,
            'zero_dnw': delta_eta[:, :, None, None] == 0,
        }
        invalid_operand = np.zeros(wi.shape, dtype=bool)
        for mask in bad.values():
            invalid_operand |= np.broadcast_to(mask, wi.shape)
        dnw_b = np.broadcast_to(delta_eta[:, :, None, None], wi.shape)
        finite_formula = np.isfinite(wi) & np.isfinite(dnw_b) & np.isfinite(pressure_scale)
        courant = np.full(wi.shape, np.nan, dtype=np.float64)
        valid = finite_formula & (dnw_b != 0) & (pressure_scale != 0) & ~invalid_operand
        with np.errstate(divide='ignore', invalid='ignore', over='ignore'):
            raw_courant = np.abs(wi * DT_SECONDS / dnw_b / pressure_scale)
            courant[valid] = raw_courant[valid]
        invalid_courant = ~np.isfinite(courant)
        per_input_invalid = {k: int(np.count_nonzero(np.broadcast_to(v, wi.shape))) for k, v in bad.items()}
        for ti, stamp in enumerate(times):
            plane = courant[ti]
            finite = np.isfinite(plane)
            row = {'record_index_zero_based': ti, 'time': stamp,
                   'interior_endpoint_count': int(plane.size),
                   'invalid_operand_count': int(np.count_nonzero(invalid_operand[ti])),
                   'nonfinite_courant_count': int(np.count_nonzero(invalid_courant[ti])),
                   'invalid_counts_by_source': {k: int(np.count_nonzero(np.broadcast_to(v, wi.shape)[ti])) for k, v in bad.items()}}
            if np.any(finite):
                # argmax applies only to finite endpoints, without filtering the report counts.
                safe = np.where(finite, plane, -np.inf)
                kk, jj, ii = np.unravel_index(int(np.argmax(safe)), safe.shape)
                row.update({'finite_count': int(np.count_nonzero(finite)),
                            'courant_max_abs': float(plane[kk, jj, ii]),
                            'location_zero_based': {'interface': int(kk + 1), 'south_north': int(jj), 'west_east': int(ii)},
                            'location_fortran_indices': {'interface': int(kk + 2), 'south_north': int(jj + 1), 'west_east': int(ii + 1)}})
            else:
                row.update({'finite_count': 0, 'courant_max_abs': None, 'location_zero_based': None, 'location_fortran_indices': None})
            result['records'].append(row)
        result['aggregate_invalid_counts_by_source'] = per_input_invalid
        result['aggregate_nonfinite_courant_count'] = int(np.count_nonzero(invalid_courant))
        result['aggregate_endpoint_count'] = int(courant.size)
        result['formula_scope'] = 'Interior WW interfaces only. Endpoint history metric, not internal RK/acoustic-stage maximum.'
    return result

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('history', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    result = analyze(args.history)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps({'status': result['status'], 'history_sha256': result['sha256'], 'output': str(args.output), 'records': len(result.get('records', []))}))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
