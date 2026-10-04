#!/usr/bin/env python3
"""Successor one-use, approval-gated runner for prepared RFMIP SW diagnostics.

This file has NOT been executed. It must not be used until the plan, source patch,
compile/link pins, and this runner receive independent review and explicit approval.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import time
import traceback
import numpy as np
from netCDF4 import Dataset
import netCDF4

WS = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
TASK = WS / 'build/udm37-rfmip-residual-next-diagnostic-v5'
SOURCE = WS / 'build/official-rrtmgp-reference/source'
EXDIR = SOURCE / 'examples/rfmip-clear-sky'
DATA = WS / 'build/official-rrtmgp-reference/data'
INPUT = DATA / 'examples/rfmip-clear-sky/inputs/multiple_input4MIPs_radiation_RFMIP_UColorado-RFMIP-1-2_none.nc'
PUBLISHED = DATA / 'examples/rfmip-clear-sky/reference'
CURRENT_COEFF = DATA / 'rrtmgp-gas-sw-g224.nc'
OLD_COEFF = WS / 'build/udm37-rfmip-solar-counterfactual-v1/stage-v7/rrtmgp-gas-sw-g224-old-solar-counterfactual.nc'
STAGE = WS / 'build/udm37-rfmip-solar-counterfactual-v1/stage-v7'
SOURCE_COPY = TASK / 'source-snapshot/rrtmgp_rfmip_sw.F90'
PREPARE_SCRIPT = TASK / 'prepare_source.py'
PREPARE_SCRIPT_SHA = '7f78f791bbd19b868b1c07f907c9010c3557c5b9542ca58f59730ab745325a4d'
SELECTOR = TASK / 'selected_profiles.txt'
NETCDF_LIB = WS / 'build/deps/root/usr/lib/x86_64-linux-gnu'
NETCDF_INC = WS / 'build/deps/root/usr/include'
PLAN = TASK / 'plan-v5.json'
PLAN_SHA = '14f1d2250db599f898463fbcf990bc32cd72b14a03c16e096e64868f33f16798'
REVIEW = WS / 'build/udm37-rfmip-solar-terminal-review-v1/review-v2.json'
REVIEW_SHA = '0d84d55268cc0c48131bfad3e0e65c6ba4999ad12fd5560f2596a281911cf3d1'
STAGE_EXEC = STAGE / 'execution.json'
STAGE_EXEC_SHA = 'e4a52a17d4d4c6bc4d4eb3a468925a2e67a9a866cd94d6855d61af78201ee45d'
STAGE_MANIFEST = STAGE / 'stage-manifest.json'
STAGE_MANIFEST_SHA = 'f411988a959db309dd42623e4341c72d78e27ae8bebdd528a8d6306ad1ea0012'
GFORTRAN = Path('/usr/bin/gfortran')
GFORTRAN_SHA = '7e292e9d5da17a37bb1c17a06afb6463db786c70827fd6893ed31a86715b03c3'
SOURCE_SHA = '8c55012d7b34722fce2d29a6c13d1cb55cf5f6e919340decad250a8c031f3354'
SELECTOR_SHA = 'b6fda5fbbb97efd13625029d3dad82258779edd003b637a68e67b454d4ade102'
FAILED_POINTS = TASK / 'failed_points.csv'
FAILED_POINTS_SHA = '1c2df6f2ccdb2b9520bdc9eaedadfbac6580be31241d4dd3c22e7c2a013e6b61'
CAPTURE_FORMAT = TASK / 'capture_format.json'
CAPTURE_FORMAT_SHA = 'fa6bbe7a5b92af4c7a6a25f6f89be9481dbb5922dee6920d2629f8bb6b8d9d42'
BASELINE_CLOSURE = TASK / 'baseline-runtime-closure-v4.json'
BASELINE_CLOSURE_SHA = 'e1f0ca84f2c0da5e113b452d10e784edd4c0fcd1b52c31fcc0676c194f6912d5'
BASE_DRIVER_SHA = 'ec874da7f2891f12b389d03243d58211a66bcee331a0618a0d7ae46c1a835821'
INPUT_SHA = 'b8dc05d7cd2e0e6354b4a6198771ddf3bc09f18d72b49f20a41e2024e2fd51f4'
CURRENT_COEFF_SHA = '584f1dd41ea9fc07d4ee3754eb1dafbd46ad3161cd6fd20fa06b6922b6f0702e'
OLD_COEFF_SHA = '02d4cd320696b9b8a3006a373855a3b4b95fdb6495251fe5f5692d6a9fddfaa4'
SOURCE_HEAD = '41c5fcd950fed09b8afe186dede266824eca7fd3'
DATA_HEAD = 'ea788bb39876948fa8d2c235665ccff19b4686b5'
EXE_SHA = 'fcebb76288fec0fceba4d720f61001f495819489a975769eec7de57ca8daa74f'
BASE_EXE = EXDIR / 'rrtmgp_rfmip_sw'
OBJECTS = {
    EXDIR / 'mo_simple_netcdf.o': 'ba7fa4bef03c56c77eb0e1851b7d3a3a0e6e93707ce3a4e18460840b1b50ac75',
    EXDIR / 'mo_rfmip_io.o': '1dc0bf26e5b90cc2c0c2b911383fcc183cf8396c429e9459b51bc18ebcb19fbb',
    EXDIR / 'mo_load_coefficients.o': 'e7f1ea15ea3dcd6176481002d43675ceb9494f5bf0c4df9af095c875d3715fb1',
}
MODULES = {
    NETCDF_INC / 'netcdf.mod': '07fcbcbe7bdf661b06967630c57230c5ae1089f360fbf4c3f2d28f32d6f5e3b5',
    NETCDF_INC / 'netcdf4_f03.mod': '6db1c247115649df550b7e3ee3023cde23246d56dc6e174ae930df9f705781f3',
    NETCDF_INC / 'netcdf4_nc_interfaces.mod': 'e2cf87942b8cd4b23041d113029ac8c2713d01f1217c7ca917b1eef1573a6b9d',
    NETCDF_INC / 'netcdf4_nf_interfaces.mod': '5ddb02db5a802415dc3572d25a4bdf4c6c18ed8798ab20c123543e066432dac5',
    NETCDF_INC / 'netcdf_f03.mod': 'dec401141af8422eae94453ca50bd7c7a936806fd9f7c95351e217d468d7d5b4',
    NETCDF_INC / 'netcdf_fortv2_c_interfaces.mod': '6e09237b1fc90a9feb44b5a20c610caf75b6221009f24815c7e53588aacd1b87',
    NETCDF_INC / 'netcdf_nc_data.mod': '3a88c4ca30f5916a990c3e5ef55fb8a918bc9a7eef3b286bad11dd87afcee858',
    NETCDF_INC / 'netcdf_nc_interfaces.mod': '9d445825bd988f5bda745fcc357a6e949bf07591b7f18941b1117e85605eae31',
    NETCDF_INC / 'netcdf_nf_data.mod': '564920c09edd34319201194f20bdda731a948c86dc289a471cbb195fec10929d',
    NETCDF_INC / 'netcdf_nf_interfaces.mod': '3e6965285c35f618d9409a68767b17f77578a6176000d47f5f2eb55ea7c5983c',
    NETCDF_INC / 'typesizes.mod': 'd9bb144467498a7399e96390c34e2c6e80ae7b8e48938244c9ba46e461f1e053',
    SOURCE / 'build/mo_fluxes.mod': '6da5d50aef54f69a1d2e2927ef6e7ef15a06cd1430bd2e342c0924d6039bb1cd',
    SOURCE / 'build/mo_fluxes_broadband_kernels.mod': 'aa415e38d7b0119b0b0c7bc7f1e428359e64c8060b973a406c6cf8ce2b71d7b4',
    SOURCE / 'build/mo_gas_concentrations.mod': '5a4cfd54b6e9f3a313cc3f8328a54b882519c1e95d524aedb8215e0107ceae10',
    SOURCE / 'build/mo_gas_optics.mod': '80d2fb123d47aea93a1ae9d3c49a84b62c30db752e161b812268efd2d363a6b9',
    SOURCE / 'build/mo_gas_optics_constants.mod': 'd70999e9c7b10bfd8062c576f8f1078c4b29ba6e321fba7fa62c2f7aa5ed5b42',
    SOURCE / 'build/mo_gas_optics_rrtmgp.mod': '8f99bddf3e4840cc902bccacc266e7a993fc7ffad37820c9be2f2580a52e938f',
    SOURCE / 'build/mo_gas_optics_rrtmgp_kernels.mod': 'a0d9baf1d070502682005904161d9feb8676e33523c6d68df1b9bf4cc7ad90ce',
    SOURCE / 'build/mo_gas_optics_util_string.mod': '6d1c28b9bace0d992560a1e499f4fef5681a20dfbae9744125b93fe5619388cb',
    SOURCE / 'build/mo_optical_props.mod': '5b190ab17cc7ee252a3c9280b39bed6f4497e8d1dffe9d5c337accc6ff854f87',
    SOURCE / 'build/mo_optical_props_kernels.mod': 'de46c056aabb70db9d9f9b40d571006491ad833059c884869cea2940a2de2221',
    SOURCE / 'build/mo_rte_config.mod': '8ba8c9a459ea7c83db12ed2f8ef52fb37f39e4257583a13781e7bcff5622d91a',
    SOURCE / 'build/mo_rte_kind.mod': 'ddec64aca7bb6b77f16f4c823dfe6e1df699403033c5fa864c5b3d395d13e211',
    SOURCE / 'build/mo_rte_lw.mod': '87691ad68df7cf8d0235a250b7f93a4028c26a15d1cf84858fa6f7c650f7fc5c',
    SOURCE / 'build/mo_rte_solver_kernels.mod': '20c5eef619c7462595d018196259b9911f2c1e3a00306c9e4fea31a844b5f187',
    SOURCE / 'build/mo_rte_sw.mod': 'd143fb744b9d76b3396ab47daf9aec0263159724666dfc7e6227105d220cd61d',
    SOURCE / 'build/mo_rte_util_array.mod': 'e6ce4a11f0bfc5439dc83103b87b9a0c1a531a8959c0e2c257c4f836b40cf5a5',
    SOURCE / 'build/mo_rte_util_array_validation.mod': '00d47fcae5d90ef00a52dbc333604d011187c4b48d86234fdd3b87cee1b1ea30',
    SOURCE / 'build/mo_source_functions.mod': 'fa4c3709e1606e48757a840f5747591f18beeaa1c58e98ddaede56bc2501d490',
    EXDIR / 'mo_load_coefficients.mod': 'eed2c46b301afe59a4a18725823ff2830c0a95112213ce8518747a2fa5b65cd0',
    EXDIR / 'mo_rfmip_io.mod': 'a266fab9979ec255c88ca3ca24b6f956c51aad51ca12a85e966c7983d3ec6abd',
    EXDIR / 'mo_simple_netcdf.mod': '2dcadcadad97b2e9eedf383e477b86bc259a70df79ab250bffec1caf4bed38eb',
}
PYTHON_EXTENSIONS = {
    Path(np.core._multiarray_umath.__file__): '6a650810a8735cbdb988f74729973740a337645dd1585fef696e73e2dbc65beb',
    Path(netCDF4._netCDF4.__file__): '4a3ed8625392528be6b5bf83f291ceb3a5e4813e2bb496fbf7a694df67827aff',
}
LIBS = {
    SOURCE / 'build/librrtmgp.a': '42f5409a6b98ae0911a93ea4acc34a66be2047953d9610537e2ba40579b23b42',
    SOURCE / 'build/librte.a': '228d414f8f5816439bf2d128fc991692e99d93824889f149eae5402ca2c4acc6',
    NETCDF_LIB / 'libnetcdff.so': '9e8fe96709d71af61b88ad88caff7db8899369162b96aee66ecd6a553a5370f9',
    NETCDF_LIB / 'libnetcdf.so': '04fc972259131718fd96f0ea876654fe0a410a4af1635349dc8ec1590764f0f5',
}
REFS = {}
for var in ('rsd', 'rsu'):
    fn = f'{var}_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc'
    REFS[PUBLISHED / fn] = 'f9b0313fdf74598859a7caf27a5d1395b7fe1e445c9620a66856cc19eaf5e5b9' if var == 'rsd' else '0ea3f4272d9ef088db6ffd07153587863a052e3cf8b3bf04bfb7c9288ed8b324'
    REFS[STAGE / 'control' / fn] = '81381b7e080540d70b122d484eff5799a1ea75e26ad82a7951898c1a1f46acc1' if var == 'rsd' else 'c704f2568b8f7328d80854582043f56f6bfb84c0235f55b3ad42daa6a31f4a34'
    REFS[STAGE / 'old-solar-counterfactual' / fn] = 'e7e6f47d33c5a23d25db105dc5c1e5c003472cca12fd087f698165b0393ee722' if var == 'rsd' else '69d4918403337e182f5a2376644c5cbf5140fa42ac776c78acf73e2594c10c5b'

ATOL = 1e-5
NEXPT, NSITE, NLEV, NGPT = 18, 100, 61, 224
NLAY = NLEV - 1
MAGIC = b''  # Stream layout is pinned by this file/version; arrays have fixed sizes.


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_executable_identity(path: Path, expected_sha: str):
    actual = sha(path)
    if not expected_sha or actual != expected_sha:
        raise RuntimeError(f'diagnostic executable identity mismatch: expected={expected_sha}, actual={actual}')
    return actual


def atomic_json(path: Path, obj):
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w') as f:
        f.write(json.dumps(obj, indent=2, sort_keys=True) + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def verify_pins():
    if (sys.version.split()[0], np.__version__, netCDF4.__version__) != ('3.12.3', '1.26.4', '1.7.4'):
        raise RuntimeError('Python/NumPy/netCDF4 analysis runtime version mismatch')
    expected = {INPUT: INPUT_SHA, CURRENT_COEFF: CURRENT_COEFF_SHA, OLD_COEFF: OLD_COEFF_SHA,
                EXDIR / 'rrtmgp_rfmip_sw.F90': BASE_DRIVER_SHA,
                SOURCE_COPY: SOURCE_SHA, PREPARE_SCRIPT: PREPARE_SCRIPT_SHA, SELECTOR: SELECTOR_SHA,
                FAILED_POINTS: FAILED_POINTS_SHA, CAPTURE_FORMAT: CAPTURE_FORMAT_SHA,
                BASELINE_CLOSURE: BASELINE_CLOSURE_SHA,
                BASE_EXE: EXE_SHA, REVIEW: REVIEW_SHA,
                STAGE_EXEC: STAGE_EXEC_SHA, STAGE_MANIFEST: STAGE_MANIFEST_SHA,
                GFORTRAN: GFORTRAN_SHA, **OBJECTS, **MODULES, **PYTHON_EXTENSIONS, **LIBS, **REFS}
    for p, want in expected.items():
        if not p.is_file() or sha(p) != want:
            raise RuntimeError(f'pin mismatch: {p}')
    if sha(PLAN) != PLAN_SHA:
        raise RuntimeError('plan pin mismatch')
    source_head = subprocess.run(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], check=True,
                                 capture_output=True, text=True).stdout.strip()
    data_head = subprocess.run(['git', '-C', str(DATA), 'rev-parse', 'HEAD'], check=True,
                               capture_output=True, text=True).stdout.strip()
    if source_head != SOURCE_HEAD or data_head != DATA_HEAD:
        raise RuntimeError(f'git pin mismatch: source={source_head}, data={data_head}')
    selector_rows = [tuple(map(int, x.split())) for x in SELECTOR.read_text().splitlines()]
    if len(selector_rows) != 135 or len(set(selector_rows)) != 135 or selector_rows != sorted(selector_rows):
        raise RuntimeError('selector must contain 135 unique sorted profiles')
    return {str(p): {'sha256': sha(p), 'size': p.stat().st_size} for p in expected}


def bitwise_equal(a, b):
    a = np.ascontiguousarray(a)
    b = np.ascontiguousarray(b)
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


def netcdf_var(path: Path, name: str):
    with Dataset(path, 'r') as ds:
        v = ds.variables[name]
        v.set_auto_maskandscale(False)
        a = np.asarray(v[:])
        if a.dtype != np.float32 or a.shape != (NEXPT, NSITE, NLEV):
            raise RuntimeError(f'{path}:{name} unexpected {a.shape}/{a.dtype}')
        if not np.isfinite(a).all():
            raise RuntimeError(f'{path}:{name} contains nonfinite values')
        return a.copy()


def expected_profiles():
    return [tuple(map(int, line.split())) for line in SELECTOR.read_text().splitlines()]


def parse_stream(path: Path, tail_values: int):
    data = path.read_bytes()
    row_bytes = 8 + tail_values * 8
    if len(data) % row_bytes:
        raise RuntimeError(f'{path}: stream length {len(data)} not multiple of {row_bytes}')
    result = {}
    for off in range(0, len(data), row_bytes):
        expt, site = struct.unpack_from('<ii', data, off)
        vals = np.frombuffer(data, dtype='<f8', count=tail_values, offset=off + 8).copy()
        key = (expt, site)
        if key in result or not np.isfinite(vals).all():
            raise RuntimeError(f'{path}: duplicate key or nonfinite data at {key}')
        result[key] = vals
    expected = expected_profiles()
    if len(expected) != 135 or len(set(expected)) != 135 or expected != sorted(expected):
        raise RuntimeError('pinned selector must contain 135 unique sorted profiles')
    if list(result) != expected:
        raise RuntimeError(f'{path}: profile keys/order differ from selector')
    return result


def read_capture(arm_dir: Path):
    prefix = arm_dir / 'diag'
    pre = parse_stream(Path(str(prefix) + '_source_pre.bin'), NGPT)
    post = parse_stream(Path(str(prefix) + '_source_post.bin'), NGPT)
    opt = parse_stream(Path(str(prefix) + '_optics.bin'), 3 * NLAY * NGPT)
    solver = parse_stream(Path(str(prefix) + '_flux_solver.bin'), 2 * NLEV)
    written = parse_stream(Path(str(prefix) + '_flux_written.bin'), 2 * NLEV)
    return {'source_pre': pre, 'source_post': post, 'optics': opt, 'flux_solver': solver, 'flux_written': written}


def check_arm_output(arm_dir: Path, base_arm: str):
    metrics = {}
    for var in ('rsd', 'rsu'):
        fn = f'{var}_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc'
        got = netcdf_var(arm_dir / fn, var)
        expected = netcdf_var(STAGE / base_arm / fn, var)
        metrics[var] = {'bitwise_float32_match_preserved_stage_v7': bool(bitwise_equal(got, expected)),
                        'shape': list(got.shape), 'dtype': str(got.dtype),
                        'sha256': sha(arm_dir / fn)}
        if not metrics[var]['bitwise_float32_match_preserved_stage_v7']:
            raise RuntimeError(f'{base_arm}:{var} differs from preserved stage-v7 result')
    return metrics


def cast_parity_and_residuals(arm_dir: Path, capture, expected_base):
    out_by = {}
    cast_mismatch = 0
    max_cast_delta = 0.0
    max_ulp_distance = 0
    compared_levels = 0
    for var in ('rsd', 'rsu'):
        fn = f'{var}_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc'
        out_by[var] = netcdf_var(arm_dir / fn, var)
    selected_csv = []
    with open(TASK / 'failed_points.csv', newline='') as f:
        import csv
        for row in csv.DictReader(f):
            selected_csv.append(row)
    published_arrays = {v: netcdf_var(PUBLISHED / f'{v}_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc', v)
                        for v in ('rsd', 'rsu')}
    full_cast_checks = {}
    for var, flux_index in (('rsu', 0), ('rsd', 1)):
        failures = []
        count = 0
        for key in expected_profiles():
            e, s = key[0] - 1, key[1] - 1
            written = capture['flux_written'][key]
            wp_values = written[flux_index * NLEV:(flux_index + 1) * NLEV]
            converted = np.asarray(wp_values, dtype=np.float32)
            saved = out_by[var][e, s, :]
            count += NLEV
            if not bitwise_equal(converted, saved):
                mismatches = np.flatnonzero(converted.view(np.uint32) != saved.view(np.uint32))
                failures.extend({'expt_index0': e, 'site_index0': s, 'level_index0': int(k),
                                 'cast_float32': float(converted[k]), 'saved_float32': float(saved[k])}
                                for k in mismatches[:20])
            max_ulp_distance = max(max_ulp_distance,
                                   max((float32_ulp_distance(x, y) for x, y in zip(converted, saved)), default=0))
        compared_levels += count
        full_cast_checks[var] = {'profiles': len(expected_profiles()), 'levels_per_profile': NLEV,
                                 'values_compared': count, 'mismatch_count': len(failures),
                                 'first_mismatches': failures[:20], 'exact_bitwise_cast_gate': not failures}
    residuals = []
    for row in selected_csv:
        var = row['variable']
        e, s, k = (int(row['expt_index0']), int(row['site_index0']), int(row['level_index0']))
        key = (e + 1, s + 1)
        item = capture['flux_written'][key]
        up = item[:NLEV]
        dn = item[NLEV:]
        prewrite = dn[k] if var == 'rsd' else up[k]
        actual = float(out_by[var][e, s, k])
        casted = float(np.float32(prewrite))
        if np.float32(prewrite).tobytes() != np.float32(actual).tobytes():
            cast_mismatch += 1
        max_cast_delta = max(max_cast_delta, abs(casted - actual))
        target = float(published_arrays[var][e, s, k])
        round_lo, round_hi, nearest_f32 = float32_rounding_interval(target)
        residuals.append({'variable': var, 'expt_index0': e, 'site_index0': s, 'level_index0': k,
                          'prewrite_wp': float(prewrite), 'stored_float32': actual, 'published_float32': target,
                          'prewrite_minus_published': float(prewrite) - target,
                          'stored_minus_published': actual - target,
                          'published_float32_rounding_interval': [round_lo, round_hi],
                          'prewrite_inside_published_rounding_interval': bool(round_lo <= float(prewrite) <= round_hi),
                          'nearest_float32_to_published': nearest_f32,
                          'prewrite_to_published_ulp_distance': float32_ulp_distance(prewrite, target),
                          'stored_to_published_ulp_distance': float32_ulp_distance(actual, target),
                          'cast_matches_saved_output': np.float32(prewrite).tobytes() == np.float32(actual).tobytes(),
                          'stored_over_atol': abs(actual - target) > ATOL,
                          'prewrite_over_atol_vs_published_float': abs(float(prewrite) - target) > ATOL})
    return {'selected_cell_cast_match_failures': cast_mismatch, 'max_abs_selected_cast_vs_saved': max_cast_delta,
            'full_profile_level_cast_checks': full_cast_checks,
            'total_full_profile_levels_compared': compared_levels,
            'max_ulp_distance_prewrite_vs_saved': max_ulp_distance,
            'residuals': residuals}


def source_sums(capture):
    with Dataset(INPUT, 'r') as ds:
        v = ds.variables['total_solar_irradiance']
        v.set_auto_maskandscale(False)
        tsi = np.asarray(v[:], dtype=np.float64).reshape(-1)
    if tsi.shape != (NSITE,) or not np.isfinite(tsi).all() or np.any(tsi <= 0.0):
        raise RuntimeError('input TSI must be finite, positive, and have exactly 100 site values')
    checks = []
    for key in expected_profiles():
        site = key[1] - 1
        target = float(tsi[site])
        pre = capture['source_pre'][key]
        post = capture['source_post'][key]
        denom = float(pre.sum(dtype=np.float64))
        post_sum = float(post.sum(dtype=np.float64))
        tol = 32.0 * np.finfo(np.float64).eps * NGPT * max(1.0, abs(target), float(np.sum(np.abs(post), dtype=np.float64)))
        valid = bool(np.isfinite(target) and target > 0.0 and np.isfinite(denom) and denom > 0.0
                     and np.isfinite(post_sum) and abs(post_sum - target) <= tol)
        checks.append({'expt_index0': key[0]-1, 'site_index0': site,
                       'pre_normalization_all_gpoint_sum': denom,
                       'input_broadband_tsi': target, 'post_normalization_all_gpoint_sum': post_sum,
                       'post_minus_input_tsi': post_sum-target,
                       'post_sum_abs_tolerance': tol,
                       'finite_positive_tsi_and_denominator_and_normalization_closure': valid})
    diffs = [abs(x['post_minus_input_tsi']) for x in checks]
    return {'per_profile': checks, 'max_abs_post_sum_error': max(diffs),
            'all_profiles_pass_broadband_normalization_contract': all(x['finite_positive_tsi_and_denominator_and_normalization_closure'] for x in checks)}


def summarize_pair(curr, old):
    profiles = expected_profiles()
    summary = {'profiles': len(profiles), 'cross_arm': {}}
    for stage, expected_len in [('source_pre', NGPT), ('source_post', NGPT), ('optics', 3*NLAY*NGPT),
                                ('flux_solver', 2*NLEV), ('flux_written', 2*NLEV)]:
        equal = []
        max_abs = 0.0
        for key in profiles:
            a, b = curr[stage][key], old[stage][key]
            equal.append(bool(bitwise_equal(a, b)))
            max_abs = max(max_abs, float(np.max(np.abs(a - b))))
        summary['cross_arm'][stage] = {'bitwise_equal_profiles': sum(equal), 'profile_count': len(equal),
                                       'all_profiles_bitwise_equal': all(equal), 'max_abs_delta': max_abs,
                                       'stored_values_per_profile': expected_len}
    return summary


def runtime_libraries(binary: Path):
    env = controlled_env()
    proc = subprocess.run(['ldd', str(binary)], env=env, text=True, capture_output=True, check=True, timeout=30)
    libs = {}
    for line in proc.stdout.splitlines():
        if '=>' in line:
            lhs, rhs = line.split('=>', 1)
            resolved = rhs.strip().split(' ', 1)[0]
        elif line.strip().startswith('/'):
            resolved = line.strip().split(' ', 1)[0]
            lhs = resolved
        else:
            bits = line.strip().split()
            if len(bits) >= 2 and bits[1].startswith('/'):
                lhs, resolved = bits[0], bits[1]
            else:
                continue
        rp = Path(resolved)
        if not rp.is_file():
            raise RuntimeError(f'unresolved runtime dependency: {line}')
        libs[lhs.strip()] = {'path': str(rp.resolve()), 'sha256': sha(rp.resolve()), 'size': rp.stat().st_size}
    return libs


def controlled_env():
    return {'PATH': '/usr/bin:/bin', 'LD_LIBRARY_PATH': str(NETCDF_LIB),
            'LANG': 'C', 'LC_ALL': 'C', 'OMP_NUM_THREADS': '1'}


def run_logged(argv, cwd, log_path, env, timeout, on_launch=None):
    with log_path.open('wb') as log:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            if on_launch is not None:
                on_launch(proc)
            rc = proc.wait(timeout=timeout)
            return proc, rc, False
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                rc = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                rc = proc.wait()
            return proc, rc, True
        except BaseException:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=5)
            except Exception:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                except Exception:
                    pass
            raise


def float32_rounding_interval(target):
    t = np.float32(target)
    lo = np.nextafter(t, np.float32(-np.inf), dtype=np.float32)
    hi = np.nextafter(t, np.float32(np.inf), dtype=np.float32)
    return float((float(lo) + float(t)) * 0.5), float((float(t) + float(hi)) * 0.5), float(t)


def float32_ulp_distance(a, b):
    ua = int(np.asarray(np.float32(a)).view(np.uint32))
    ub = int(np.asarray(np.float32(b)).view(np.uint32))
    oa = ((~ua) & 0xffffffff) if (ua & 0x80000000) else (ua | 0x80000000)
    ob = ((~ub) & 0xffffffff) if (ub & 0x80000000) else (ub | 0x80000000)
    return abs(oa - ob)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--approval', type=Path, required=True)
    ap.add_argument('--run-root', type=Path, required=True)
    args = ap.parse_args()
    run_root = args.run_root.resolve()
    receipt_path = run_root / 'execution.json'
    state = {'schema': 'rfmip-sw-residual-diagnostic-execution-v3', 'status': 'PREPARED',
             'plan_sha256': PLAN_SHA, 'source_sha256': SOURCE_SHA, 'model_invocations': 0, 'calls': []}
    owned_runroot = False
    active_proc = None
    try:
        approval = json.loads(args.approval.read_text())
        expected_approval = {'approved': True, 'plan_sha256': PLAN_SHA,
                             'runner_sha256': sha(Path(__file__).resolve()),
                             'run_root': str(run_root), 'max_solver_calls': 2}
        if approval != expected_approval:
            raise RuntimeError('approval file does not exactly bind plan, runner, output root, and two-call cap')
        if run_root.exists():
            raise RuntimeError('run root already exists; refusing to modify a prior receipt')
        run_root.mkdir(parents=True, exist_ok=False)
        owned_runroot = True
        state['status'] = 'RUNNING'
        state['started_utc_epoch'] = time.time()
        state['pins_before'] = verify_pins()
        frozen_closure_doc = json.loads(BASELINE_CLOSURE.read_text())
        frozen_closure = frozen_closure_doc['resolved_libraries']
        state['frozen_baseline_runtime_closure'] = frozen_closure
        state['observed_baseline_runtime_closure_before_build'] = runtime_libraries(BASE_EXE)
        if state['observed_baseline_runtime_closure_before_build'] != frozen_closure:
            raise RuntimeError('original executable runtime closure drifted from frozen prebuild closure')
        atomic_json(receipt_path, state)
        build_dir = run_root / 'build'
        build_dir.mkdir()
        # The only source compiled is the isolated diagnostic driver; prebuilt objects and archives are read-only.
        compile_argv = [str(GFORTRAN), '-O0', '-ffree-line-length-none',
                        '-I' + str(NETCDF_INC), '-I' + str(SOURCE / 'build'), '-I' + str(EXDIR),
                        '-c', str(SOURCE_COPY), '-o', str(build_dir / 'rrtmgp_rfmip_sw_diag.o')]
        compile_env = controlled_env()
        def record_compile_launch(p):
            state['compile'] = {'argv': compile_argv, 'pid': p.pid, 'status': 'RUNNING', 'environment': compile_env}
            atomic_json(receipt_path, state)
        cproc, crc, ctimeout = run_logged(compile_argv, build_dir, build_dir / 'compile.log', compile_env, 300, record_compile_launch)
        c = type('Result', (), {'returncode': crc})()
        state['compile'] = {'argv': compile_argv, 'pid': cproc.pid, 'returncode': int(c.returncode),
                            'timed_out': ctimeout, 'environment': compile_env, 'status': 'PROCESS_COMPLETE'}
        atomic_json(receipt_path, state)
        state['compile']['log_sha256'] = sha(build_dir / 'compile.log')
        atomic_json(receipt_path, state)
        if c.returncode != 0 or ctimeout:
            raise RuntimeError('isolated diagnostic driver compilation failed')
        exe = build_dir / 'rrtmgp_rfmip_sw_diag'
        link_argv = [str(GFORTRAN), '-O0', '-ffree-line-length-none', '-o', str(exe),
                     str(build_dir / 'rrtmgp_rfmip_sw_diag.o'), str(EXDIR / 'mo_simple_netcdf.o'),
                     str(EXDIR / 'mo_rfmip_io.o'), str(EXDIR / 'mo_load_coefficients.o'),
                     '-L' + str(SOURCE / 'build'), '-L' + str(NETCDF_LIB), '-lrrtmgp', '-lrte', '-lnetcdff', '-lnetcdf']
        def record_link_launch(p):
            state['link'] = {'argv': link_argv, 'pid': p.pid, 'status': 'RUNNING', 'environment': compile_env}
            atomic_json(receipt_path, state)
        lproc, lrc, ltimeout = run_logged(link_argv, build_dir, build_dir / 'link.log', compile_env, 300, record_link_launch)
        l = type('Result', (), {'returncode': lrc})()
        state['link'] = {'argv': link_argv, 'pid': lproc.pid, 'returncode': int(l.returncode),
                         'timed_out': ltimeout, 'environment': compile_env, 'status': 'PROCESS_COMPLETE'}
        atomic_json(receipt_path, state)
        state['link']['log_sha256'] = sha(build_dir / 'link.log')
        if l.returncode == 0:
            state['diagnostic_executable_sha256'] = sha(exe)
        atomic_json(receipt_path, state)
        if l.returncode != 0 or ltimeout:
            raise RuntimeError('isolated diagnostic executable link failed')
        if sha(SOURCE_COPY) != SOURCE_SHA or verify_pins() != state['pins_before']:
            raise RuntimeError('input/source/dependency pin changed during isolated build')
        state['diagnostic_runtime_libraries'] = runtime_libraries(exe)
        state['observed_baseline_runtime_closure_after_build'] = runtime_libraries(BASE_EXE)
        state['runtime_closure_exact_match_to_original'] = (
            state['observed_baseline_runtime_closure_after_build'] == frozen_closure and
            state['diagnostic_runtime_libraries'] == frozen_closure)
        if not state['runtime_closure_exact_match_to_original']:
            raise RuntimeError('diagnostic executable runtime library closure differs from pinned baseline')
        state['controlled_build_environment'] = compile_env
        state['analysis_runtime'] = {'python': sys.version.split()[0], 'numpy': np.__version__,
                                     'netCDF4': netCDF4.__version__,
                                     'extension_pins': {str(p): sha(p) for p in PYTHON_EXTENSIONS}}
        state['gfortran_version'] = subprocess.run([str(GFORTRAN), '--version'], capture_output=True,
                                                    text=True, check=True).stdout.splitlines()[0]

        baseline_arm = {'current': 'control', 'old_solar': 'old-solar-counterfactual'}
        captures = {}
        for arm, coeff, ref_arm in [('current', CURRENT_COEFF, 'control'),
                                    ('old_solar', OLD_COEFF, 'old-solar-counterfactual')]:
            arm_dir = run_root / arm
            arm_dir.mkdir()
            for var in ('rsd', 'rsu'):
                fn = f'{var}_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc'
                shutil.copy2(PUBLISHED / fn, arm_dir / fn)
            (arm_dir / 'input.nc').symlink_to(INPUT)
            (arm_dir / 'coeff.nc').symlink_to(coeff)
            shutil.copy2(SELECTOR, arm_dir / 'profiles.txt')
            prefix = arm_dir / 'diag'
            if len(str(prefix)) > 256 or len(str(arm_dir / 'profiles.txt')) > 256:
                raise RuntimeError('diagnostic prefix or selector path exceeds Fortran argument buffer')
            argv = [str(exe), '8', 'input.nc', 'coeff.nc', '1', str(prefix), 'profiles.txt']
            env = controlled_env()
            log_path = arm_dir / 'run.log'
            call = {'arm': arm, 'argv': argv, 'cwd': str(arm_dir), 'status': 'LAUNCHING'}
            state['calls'].append(call)
            state['launch_attempts'] = len(state['calls'])
            atomic_json(receipt_path, state)
            if len(state['calls']) > 2 or sha(Path(__file__).resolve()) != approval['runner_sha256']:
                raise RuntimeError('runner changed or solver call budget exceeded immediately before launch')
            verify_executable_identity(exe, state['diagnostic_executable_sha256'])
            if verify_pins() != state['pins_before'] or runtime_libraries(exe) != frozen_closure or runtime_libraries(BASE_EXE) != frozen_closure:
                raise RuntimeError('pinned source/dependency/runtime library drift immediately before launch')
            start = time.time()
            def record_launch(p):
                nonlocal active_proc
                active_proc = p
                call['pid'] = p.pid
                call['start_epoch'] = start
                state['model_invocations'] = sum(1 for x in state['calls'] if 'pid' in x)
                call['pid_durable_before_wait'] = True
                atomic_json(receipt_path, state)
            active_proc, rc, timed_out = run_logged(argv, arm_dir, log_path, env, 120, record_launch)
            call['end_epoch'] = time.time()
            call['returncode'] = int(rc)
            call['status'] = 'PROCESS_COMPLETE'
            call['timed_out'] = timed_out
            state['model_invocations'] = sum(1 for x in state['calls'] if 'pid' in x)
            # Persist the actual process outcome before any hashing, ldd, parsing or comparison.
            atomic_json(receipt_path, state)
            active_proc = None
            call['post_process_pins_match'] = (verify_pins() == state['pins_before'] and
                                                verify_executable_identity(exe, state['diagnostic_executable_sha256']) == state['diagnostic_executable_sha256'] and
                                                runtime_libraries(exe) == frozen_closure and
                                                runtime_libraries(BASE_EXE) == frozen_closure)
            call['log_sha256'] = sha(log_path)
            atomic_json(receipt_path, state)
            if timed_out:
                raise RuntimeError(f'{arm} SW process exceeded the 120-second deadline')
            if rc != 0:
                raise RuntimeError(f'{arm} SW process returned {rc}; preserve receipt and stop')
            if not call['post_process_pins_match']:
                raise RuntimeError(f'{arm} changed a pinned source/dependency/runtime library; stop')
            capture = read_capture(arm_dir)
            output_metrics = check_arm_output(arm_dir, ref_arm)
            cast_metrics = cast_parity_and_residuals(arm_dir, capture, ref_arm)
            sums = source_sums(capture)
            call['output_bitwise_gate'] = output_metrics
            call['residual_cells_vs_published'] = cast_metrics['residuals']
            call['cast_diagnostic'] = cast_metrics
            call['broadband_tsi_diagnostic'] = {'max_abs_post_sum_error': sums['max_abs_post_sum_error'],
                    'all_profiles_pass_contract': sums['all_profiles_pass_broadband_normalization_contract']}
            call['capture_hashes'] = {p.name: sha(p) for p in arm_dir.glob('diag_*.bin')}
            if not all(x['bitwise_float32_match_preserved_stage_v7'] for x in output_metrics.values()):
                raise RuntimeError(f'{arm}: zero-change output parity gate failed; stop before next arm')
            if not all(x['exact_bitwise_cast_gate'] for x in cast_metrics['full_profile_level_cast_checks'].values()):
                raise RuntimeError(f'{arm}: full 135-profile x 61-level float32 storage-cast gate failed; stop before next arm')
            if not sums['all_profiles_pass_broadband_normalization_contract']:
                raise RuntimeError(f'{arm}: source normalization finite/positive/closure gate failed; stop before next arm')
            captures[arm] = capture
            atomic_json(receipt_path, state)

        state['diagnostic_summary'] = summarize_pair(captures['current'], captures['old_solar'])
        verify_executable_identity(exe, state['diagnostic_executable_sha256'])
        optical_gate = state['diagnostic_summary']['cross_arm']['optics']['all_profiles_bitwise_equal']
        state['diagnostic_summary']['solar_only_counterfactual_gas_optics_bitwise_gate'] = bool(optical_gate)
        if not optical_gate:
            raise RuntimeError('solar-only counterfactual changed gas optical properties; stop and investigate')
        state['status'] = 'COMPLETE_DIAGNOSTIC_NOT_STRICT_PASS'
        state['strict_published_threshold'] = {'atol': ATOL, 'rtol': 0,
                                               'remaining_failures_from_preserved_baseline': {'rsd': 116, 'rsu': 39}}
        state['pins_after'] = verify_pins()
        if state['pins_after'] != state['pins_before']:
            state['status'] = 'FAIL_PRESERVED_POSTRUN_PIN_DRIFT'
        state['ended_utc_epoch'] = time.time()
        atomic_json(receipt_path, state)
    except BaseException as exc:
        if active_proc is not None and active_proc.poll() is None:
            try:
                os.killpg(active_proc.pid, signal.SIGTERM)
                active_proc.wait(timeout=5)
            except Exception:
                try:
                    os.killpg(active_proc.pid, signal.SIGKILL)
                    active_proc.wait()
                except Exception:
                    pass
        state['status'] = 'FAIL_PRESERVED'
        state['error'] = f'{type(exc).__name__}: {exc}'
        state['traceback'] = traceback.format_exc()
        state['ended_utc_epoch'] = time.time()
        if owned_runroot and run_root.exists():
            atomic_json(receipt_path, state)
        raise


if __name__ == '__main__':
    main()
