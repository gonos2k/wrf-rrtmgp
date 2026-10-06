#!/usr/bin/env python3
"""Generate experimental homogeneous-ice exponential-PSD band moments.

This offline tool does not select or enable WRF graupel/hail optics.
Coefficients multiplied by particle bulk density are shared between species.
SW uses NOAA NNLSSI1 BaselineModel, distinct from RRTMGP gas NRLSSI2.
LW uses Planck source weighting at each requested temperature; both absorption
and scattering are retained so extinction is never mislabeled absorption.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import ctypes
import difflib
import hashlib
import json
import math
from pathlib import Path
import resource
import subprocess
import time
import urllib.request
from importlib.metadata import version

import numpy as np
from netCDF4 import Dataset
from laguerre import rule as laguerre_rule

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INPUTS = {
    'IOP_2008_ASCIItable.dat': {
        'url': 'https://atmos.uw.edu/ice_optical_constants/IOP_2008_ASCIItable.dat',
        'sha256': '891d0e0690cc6c6ed2dfe81291fa20a3af177fa85ef93127c58c5f86d3c370af',
        'meaning': 'Warren-Brandt ice-Ih static refractive-index compilation; not a universal temperature-specific material'},
    'tsi-ssi_v03r00_reference-spectra_c20240830.txt': {
        'url': 'https://www.ncei.noaa.gov/data/solar-spectral-irradiance/access/ancillary-data/tsi-ssi_v03r00_reference-spectra_c20240830.txt',
        'sha256': '4a38b3f2343a0271c49fa5678a4eb6d289ea840159cb84b30a6be5f44feacb85',
        'meaning': 'NOAA NNLSSI1 Reference Spectra, BaselineModel column, W m-2 nm-1; not NRLSSI2'},
}
_KERNEL = None
_ICE = None
_SOLAR = None
_U = None
_GW = None
_MAX_TERMS = None
EXPECTED_BOUNDS = {
    'SW': [[820,2680],[2680,3250],[3250,4000],[4000,4650],[4650,5150],
           [5150,6150],[6150,7700],[7700,8050],[8050,12850],[12850,16000],
           [16000,22650],[22650,29000],[29000,38000],[38000,50000]],
    'LW': [[10,250],[250,500],[500,630],[630,700],[700,820],[820,980],
           [980,1080],[1080,1180],[1180,1390],[1390,1480],[1480,1800],
           [1800,2080],[2080,2250],[2250,2390],[2390,2680],[2680,3250]],
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs_at(directory: Path, fetch: bool) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, spec in INPUTS.items():
        path = directory / name
        if not path.exists():
            if not fetch:
                raise FileNotFoundError(f'{path}; supply pinned inputs or --fetch-inputs')
            with urllib.request.urlopen(spec['url'], timeout=60) as response:
                raw = response.read()
            if hashlib.sha256(raw).hexdigest() != spec['sha256']:
                raise ValueError(f'Fetched input hash differs: {name}')
            path.write_bytes(raw)
        if sha(path) != spec['sha256']:
            raise ValueError(f'Input hash differs: {path}')
        paths[name] = path
    return paths


def build_kernel(directory: Path) -> tuple[Path, dict[str, str]]:
    directory.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((HERE / 'SOURCE.json').read_text())
    for name, spec in manifest['files'].items():
        if sha(HERE / 'socrates' / name) != spec['sha256']:
            raise ValueError(f'Pinned SOCRATES source differs: {name}')
    files = [HERE / 'socrates' / name for name in ('realtype_rd.f90', 'def_std_io_icf.f90',
                                                'error_pcf.f90', 'mie_scatter.f')]
    files.append(HERE / 'mie_dynamic_api.f90')
    # Original vendored bytes remain identical to the public pin. The three
    # Riccati-Bessel constructors otherwise convert RealK to default COMPLEX
    # (single precision), then back to RealK. This explicit local adaptation
    # retains RealK at construction; no efficiencies/tolerances are projected.
    original = files[3].read_text()
    adapted = original
    for operands in ('0.0_RealK, 0.0_RealK', 'psi_nm2, -chi_nm2',
                     'psi_nm1, -chi_nm1', 'psi_n, -chi_n'):
        before = 'CMPLX('+operands+')'
        if adapted.count(before) != 1:
            raise ValueError('Pinned CMPLX adaptation context differs')
        adapted = adapted.replace(before, 'CMPLX('+operands+', KIND=RealK)')
    adapted_file = directory / 'mie_scatter_realK.f'
    adapted_file.write_text(adapted)
    (directory / 'realK-constructor.diff').write_text(''.join(difflib.unified_diff(
        original.splitlines(True),adapted.splitlines(True),fromfile='pinned/mie_scatter.f',
        tofile='local/mie_scatter_realK.f')))
    (directory / 'source-adaptation.json').write_text(json.dumps({
        'original_sha256': sha(files[3]), 'compiled_mie_sha256': sha(adapted_file),
        'adaptation': 'Four CMPLX constructors explicitly preserve KIND=RealK; no other source changes',
        'constructors': 4},indent=2)+'\n')
    library = directory / 'libmie_dynamic.so'
    compile_files=files[:3]+[adapted_file]+files[4:]
    subprocess.run(['gfortran', '-O3', '-fPIC', '-shared', '-ffree-line-length-none',
                    '-J', str(directory), '-I', str(directory), *map(str, compile_files),
                    '-o', str(library)], check=True)
    return library, {str(p.relative_to(ROOT)): sha(p) for p in files+[HERE/'SOURCE.json',HERE/'laguerre.py']}


def initialize(library: str, ice_path: str, solar_path: str, order: int, max_terms: int) -> None:
    global _KERNEL, _ICE, _SOLAR, _U, _GW, _MAX_TERMS
    _KERNEL = ctypes.CDLL(library)
    _KERNEL.mie_checked.argtypes = [ctypes.c_double] * 3 + [ctypes.c_int] + \
        [ctypes.POINTER(ctypes.c_double)] * 3 + [ctypes.POINTER(ctypes.c_int)] * 2
    _ICE = np.loadtxt(ice_path)
    solar = np.loadtxt(solar_path, delimiter=',', skiprows=2)
    # Only the RRTMGP SW range, plus a bracket at each end, is needed.
    # Printed far-IR wavelength rounding creates duplicate rows outside this range.
    solar = solar[(solar[:, 0] >= 190.) & (solar[:, 0] <= 12500.)]
    if not np.all(np.diff(solar[:, 0]) > 0) or not np.all(solar[:, 1] > 0):
        raise ValueError('SW solar wavelengths must increase and baseline weights be positive')
    _SOLAR = solar[:, :2]
    if not np.all(np.diff(_ICE[:, 0]) > 0) or not np.all(_ICE[:, 1:] > 0):
        raise ValueError('Refractive-index input must be increasing and positive')
    _U, _GW = laguerre_rule(order)
    _MAX_TERMS = max_terms


def index_at(wn: float) -> tuple[float, float]:
    wave = 1.e4 / wn
    if not _ICE[0, 0] < wave < _ICE[-1, 0]:
        raise ValueError(f'Refractive-index range: {wave} microns')
    log_wave = np.log(_ICE[:, 0])
    n = np.interp(math.log(wave), log_wave, _ICE[:, 1])
    k = math.exp(np.interp(math.log(wave), log_wave, np.log(_ICE[:, 2])))
    return float(n), float(k)


def solar_weight(wn: np.ndarray) -> np.ndarray:
    wave_nm = 1.e7 / wn
    flux_per_nm = np.interp(wave_nm, _SOLAR[:, 0], _SOLAR[:, 1])
    # Change of variables: lambda_nm=1e7/nu_cm, |d lambda_nm/d nu_cm|=1e7/nu_cm^2.
    return flux_per_nm * 1.e7 / wn ** 2


def planck_weight(wn: np.ndarray, temperatures: np.ndarray) -> np.ndarray:
    c2_cm_k = (6.62607015e-34 * 299792458. / 1.380649e-23) * 100.
    # Band normalization removes the common radiance prefactor.
    return wn[None, :] ** 3 / np.expm1(c2_cm_k * wn[None, :] / temperatures[:, None])


def integrate(task: tuple) -> dict:
    phase, band, lo, hi, slope, temperatures, step = task[:7]
    started = time.monotonic()
    count = int(math.ceil((hi - lo) / step))
    all_wn = np.linspace(lo, hi, count + 1)
    start,stop=(0,count+1) if len(task)==7 else task[7:9]
    if not 0<=start<stop<=count+1:
        raise ValueError('Invalid spectral chunk node range')
    wn = all_wn[start:stop]
    # Nonoverlapping node slices retain the FULL band's trapezoid weights.
    # Their weighted integrals sum to the unsliced band, including endpoints.
    spectral_weights=np.full(wn.size,(hi-lo)/count)
    if start==0:spectral_weights[0]*=.5
    if stop==count+1:spectral_weights[-1]*=.5
    source = solar_weight(wn)[None, :] if phase == 'SW' else planck_weight(wn, np.asarray(temperatures))
    normalization = np.sum(source*spectral_weights[None,:],axis=1)
    if not np.all(np.isfinite(source)) or not np.all(normalization > 0):
        raise ValueError('Spectral source weight is not positive finite')
    moments = np.zeros((4, wn.size))
    selected = _GW * _U ** 2 > 1.e-16
    # This tiny quadrature tail threshold is reported, separately from workspace.
    dropped_area_fraction = float(np.sum((_GW * _U ** 2)[~selected]) / 2.)
    dropped_mass_fraction = float(np.sum((_GW * _U ** 3)[~selected]) / 6.)
    needed_max = 0
    for j, nu in enumerate(wn):
        n, k = index_at(float(nu))
        for u, w in zip(_U[selected], _GW[selected]):
            x = 100. * math.pi * float(u) * float(nu) / slope
            ext, sca, asym = ctypes.c_double(), ctypes.c_double(), ctypes.c_double()
            needed, status = ctypes.c_int(), ctypes.c_int()
            _KERNEL.mie_checked(n, k, x, _MAX_TERMS, ctypes.byref(ext), ctypes.byref(sca),
                                ctypes.byref(asym), ctypes.byref(needed), ctypes.byref(status))
            if status.value != 0:
                raise RuntimeError(f'Mie refused {phase} band{band+1}, lambda={slope}, '
                                   f'nu={nu}, u={u}, needed={needed.value}, status={status.value}; '
                                   'no workspace-limited node is silently discarded')
            needed_max = max(needed_max, needed.value)
            e, s, g = ext.value, sca.value, asym.value
            if not all(map(math.isfinite, (e, s, g))) or e < 0 or s < 0 or s > e + 1.e-11 or not -1 <= g <= 1:
                raise ValueError(f'Nonphysical Mie result {e,s,g}; {phase} band{band+1}, '
                                 f'lambda={slope}, nu={nu}, u={u}, n={n}, k={k}, x={x}')
            weight = float(w * u ** 2)
            # Keep Qabs independently rather than subtracting averaged moments.
            moments[:, j] += weight * np.asarray([e, s, s * g, max(0., e - s)])
    result = np.sum(moments[:, None, :] * source[None, :, :] * spectral_weights[None,None,:],axis=2) / normalization[None, :]
    result *= slope / 4.  # kappa*rho_bulk, m-1; kappa = result/rho_bulk.
    if not np.all(np.isfinite(result)) or not np.all(result[0]>0):
        raise ValueError('Nonfinite/zero integrated optical moments')
    return {'phase': phase, 'band': band, 'slope': slope, 'moments': result.tolist(),
            'source_integral': normalization.tolist(), 'spectral_nodes': wn.size,
            'spectral_node_start': start,'spectral_node_stop': stop,'full_band_node_count':count+1,
            'needed_terms_max': needed_max, 'dropped_area_weight_fraction': dropped_area_fraction,
            'dropped_mass_weight_fraction': dropped_mass_fraction,
            'seconds': time.monotonic() - started,
            'worker_max_rss_kb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def combine_chunks(chunks: list[dict]) -> list[dict]:
    """Combine in fixed node order; no dependence on worker completion order."""
    groups={}
    for row in chunks:groups.setdefault((row['phase'],row['slope'],row['band']),[]).append(row)
    rows=[]
    for key,parts in sorted(groups.items()):
        parts.sort(key=lambda x:x['spectral_node_start']); next_node=0
        for row in parts:
            if row['spectral_node_start']!=next_node or row['full_band_node_count']!=parts[0]['full_band_node_count']:
                raise ValueError('Spectral chunk gap/duplicate or inconsistent node count')
            next_node=row['spectral_node_stop']
        if next_node!=parts[0]['full_band_node_count']:
            raise ValueError('Spectral chunks do not cover the whole band')
        norm=np.sum([np.asarray(x['source_integral']) for x in parts],axis=0)
        total=np.sum([np.asarray(x['moments'])*np.asarray(x['source_integral'])[None,:] for x in parts],axis=0)/norm[None,:]
        first=parts[0]
        rows.append(dict(phase=key[0],slope=key[1],band=key[2],moments=total.tolist(),source_integral=norm.tolist(),
            spectral_nodes=next_node,spectral_chunks=len(parts),needed_terms_max=max(x['needed_terms_max'] for x in parts),
            dropped_area_weight_fraction=first['dropped_area_weight_fraction'],
            dropped_mass_weight_fraction=first['dropped_mass_weight_fraction'],
            seconds=sum(x['seconds'] for x in parts),worker_max_rss_kb=max(x['worker_max_rss_kb'] for x in parts)))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--fetch-inputs', action='store_true')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'WRF/run')
    parser.add_argument('--lambda-grid', type=float, nargs='+', required=True, help='inverse metres, positive and increasing')
    parser.add_argument('--temperatures', type=float, nargs='+', default=[180., 233., 250., 300.])
    parser.add_argument('--order', type=int, default=64)
    parser.add_argument('--spectral-step', type=float, default=25., help='maximum uniform spacing in cm-1')
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--spectral-chunk-size',type=int,default=32,help='nonoverlapping weighted spectral nodes per worker task')
    parser.add_argument('--max-terms', type=int, default=32_000_000)
    args = parser.parse_args()
    slope = np.asarray(args.lambda_grid)
    temps = np.asarray(args.temperatures)
    for label, values in [('lambda', slope), ('temperature', temps)]:
        if not np.all(np.isfinite(values)) or not np.all(values > 0) or not np.all(np.diff(values) > 0):
            parser.error(f'{label} values must be positive finite and strictly increasing')
    if not 4 <= args.order <= 512 or args.workers < 1 or args.spectral_chunk_size<1 or not 16 <= args.max_terms <= np.iinfo(np.int32).max or not math.isfinite(args.spectral_step) or args.spectral_step <= 0:
        parser.error('Invalid numerical integration controls')
    if args.output_dir.exists():
        parser.error('Use a new output directory; completed and failed evidence is preserved')
    args.output_dir.mkdir(parents=True)
    started = time.monotonic()
    script_hash = sha(Path(__file__))
    # Fail before spectral work if an integration library returns bad weights.
    quadrature_nodes,quadrature_weights=laguerre_rule(args.order)
    paths = inputs_at(args.input_dir.resolve(), args.fetch_inputs)
    library, sources = build_kernel(args.output_dir.resolve() / 'kernel')
    bounds = {}
    gas_files = {'SW': args.data_dir / 'rrtmgp-gas-sw-g112.nc', 'LW': args.data_dir / 'rrtmgp-gas-lw-g128.nc'}
    gas_hashes = {phase: sha(path) for phase, path in gas_files.items()}
    for phase, path in gas_files.items():
        with Dataset(path) as nc:
            bounds[phase] = np.asarray(nc['bnd_limits_wavenumber'][:], dtype=float)
        expected = 14 if phase == 'SW' else 16
        if bounds[phase].shape != (expected, 2) or not np.array_equal(bounds[phase], EXPECTED_BOUNDS[phase]):
            raise ValueError(f'Pinned {phase} band contract differs')
    tasks=[]
    for phase in ('SW','LW'):
        for lam in slope:
            for b,(lo,hi) in enumerate(bounds[phase]):
                nn=int(math.ceil((hi-lo)/args.spectral_step))+1
                for begin in range(0,nn,args.spectral_chunk_size):
                    tasks.append((phase,b,float(lo),float(hi),float(lam),list(temps),args.spectral_step,
                                  begin,min(begin+args.spectral_chunk_size,nn)))
    chunks = []
    with ProcessPoolExecutor(max_workers=args.workers, initializer=initialize,
            initargs=(str(library), str(paths['IOP_2008_ASCIItable.dat']),
                      str(paths['tsi-ssi_v03r00_reference-spectra_c20240830.txt']), args.order, args.max_terms)) as pool:
        pending = [pool.submit(integrate, task) for task in tasks]
        for future in as_completed(pending):
            row = future.result(); chunks.append(row)
            print(f"{len(chunks)}/{len(tasks)} {row['phase']} band{row['band']+1} lambda={row['slope']} nodes={row['spectral_node_start']}:{row['spectral_node_stop']}", flush=True)
            (args.output_dir / 'partial-progress.json').write_text(json.dumps(chunks, indent=2) + '\n')
    rows=combine_chunks(chunks)
    if len(rows)!=30*len(slope):raise ValueError('Missing final spectral bands')
    if sha(Path(__file__)) != script_hash or any(sha(ROOT / p) != h for p, h in sources.items()):
        raise RuntimeError('Generator/kernel source changed during execution; refusing final attribution')
    if any(sha(path) != INPUTS[name]['sha256'] for name, path in paths.items()):
        raise RuntimeError('Material/solar input changed during execution; refusing final attribution')
    if any(sha(path) != gas_hashes[phase] for phase, path in gas_files.items()):
        raise RuntimeError('Gas band input changed during execution; refusing final attribution')
    table = args.output_dir / 'frozen-ice-psd-moments.nc'
    with Dataset(table, 'w') as nc:
        nc.setncattr('model', 'EXPERIMENTAL_HOMOGENEOUS_ICE_EXPONENTIAL_PSD_V1')
        nc.setncattr('status', 'NUMERICAL_GENERATION_ONLY_NOT_WRF_VALIDATED')
        nc.setncattr('size_coordinate', 'lambda of N(D)=N0 exp(-lambda D); geometric sphere diameter D in m')
        nc.setncattr('mass_normalization', 'kappa*rho_bulk=lambda/4 * integral exp(-u) u^2 Q du; divide by species bulk density')
        nc.setncattr('solar_source', INPUTS['tsi-ssi_v03r00_reference-spectra_c20240830.txt']['meaning'])
        nc.setncattr('LW_temperature', 'Planck source weighting only; material index is a static ice-Ih compilation')
        nc.setncattr('udm_constants', 'graupel:N0=4e6,rho_bulk=500;hail:N0=4e4,rho_bulk=912;lambda_max=20000; process q cutoff=1e-9')
        for name, size in [('lambda', len(slope)), ('temperature', len(temps)), ('sw_band', 14), ('lw_band', 16), ('bound', 2)]:
            nc.createDimension(name, size)
        for name, dims, data, units in [('lambda', ('lambda',), slope, 'm-1'), ('temperature', ('temperature',), temps, 'K'),
                ('sw_bounds', ('sw_band', 'bound'), bounds['SW'], 'cm-1'), ('lw_bounds', ('lw_band', 'bound'), bounds['LW'], 'cm-1')]:
            var = nc.createVariable(name, 'f8', dims); var[:] = data; var.units = units
        for phase, nb in [('SW', 14), ('LW', 16)]:
            cube = np.zeros((4, len(slope), len(temps) if phase == 'LW' else 1, nb))
            for row in rows:
                if row['phase'] == phase:
                    il = int(np.where(slope == row['slope'])[0][0])
                    cube[:, il, :, row['band']] = np.asarray(row['moments'])
            for j, moment in enumerate(('extinction', 'scattering', 'scatter_times_g', 'absorption')):
                dims = ('lambda', 'temperature', 'lw_band') if phase == 'LW' else ('lambda', 'sw_band')
                var = nc.createVariable(f'{phase.lower()}_{moment}_times_density', 'f8', dims, zlib=True)
                var[:] = cube[j] if phase == 'LW' else cube[j, :, 0, :]; var.units = 'm-1'
    receipt = {'status': 'COMPLETE_NUMERICAL_GENERATION_NOT_MODEL_VALIDATION',
        'generator_sha256': script_hash, 'kernel_source_sha256': sources, 'kernel_binary_sha256': sha(library),
        'kernel_source_adaptation': json.loads((library.parent/'source-adaptation.json').read_text()),
        'input_sources': INPUTS, 'gas_data_sha256': gas_hashes,
        'table_sha256': sha(table), 'lambda_grid_m_inv': slope.tolist(), 'temperatures_K': temps.tolist(),
        'order': args.order, 'max_spectral_step_cm_inv': args.spectral_step, 'workers': args.workers,
        'max_terms': args.max_terms, 'quadrature_area_weight_pruning_threshold': 1e-16,
        'quadrature_algorithm': 'Golub-Welsch alpha=0, LAPACK STEV; polynomial moments checked before work',
        'quadrature_nodes_weights_sha256': hashlib.sha256(quadrature_nodes.tobytes()+quadrature_weights.tobytes()).hexdigest(),
        'spectral_chunk_size':args.spectral_chunk_size,'worker_tasks':len(chunks),
        'numerical_packages': {name: version(name) for name in ('numpy','scipy','netCDF4')},
        'compiler': subprocess.check_output(['gfortran','--version'],text=True).splitlines()[0],
        'kernel_flags': ['-O3','-fPIC','-shared','-ffree-line-length-none'],
        'elapsed_seconds': time.monotonic()-started, 'rows': rows,
        'limitations': ['No UDM radius or graupel/hail diameter convention is validated by Mie arithmetic.',
            'Bulk density enters mass normalization; no porosity, habit or wet-particle material model is inferred.',
            'This is not Hill coefficient reproduction, RRTMGP NRLSSI2 reproduction or observational validation.',
            'Neither interpolation nor live WRF G/H optics is implemented by this generator.',
            'Convergence of order, spectral step, size and temperature axes requires separate comparisons.']}
    (args.output_dir / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'status': receipt['status'], 'table': str(table), 'tasks': len(rows), 'elapsed_seconds': receipt['elapsed_seconds']}))


if __name__ == '__main__':
    main()
