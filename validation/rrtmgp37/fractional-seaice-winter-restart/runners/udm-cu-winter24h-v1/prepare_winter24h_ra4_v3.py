#!/usr/bin/env python3
"""Independent RA4-only exact-namelist Jan24h staging; --execute requires root review."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
HIST = ROOT / 'build/udm-alternate-jan2000-data/paired-forecast-v2'
SOURCE_MANIFEST = ROOT / 'build/udm-cu-fresh-gnu-v2/source-manifest.json'
BINARY = ROOT / 'build/udm-cu-fresh-gnu-v2/source/WRF/main/wrf.exe'
MPIEXEC = ROOT / 'build/deps/mpich-sock/bin/mpiexec'
LD_DEFAULT = ':'.join(str(ROOT / p) for p in ('build/deps/netcdf/lib', 'build/deps/root/usr/lib/x86_64-linux-gnu', 'build/deps/mpich-sock/lib'))
EXPECTED = {
    'binary': '9e01ffa17d08995f24e46c82fbbad32325cfedf0d2af43d54f69df24eb20cbd4',
    'source_manifest': '446b7fd2e5827595d0f42514bc325a8ea2bb8e7b3604a3fdd145a899d3f35c8d',
    'configure': '44f85b7fc9b6994cb3784567e69d310580740a021b5f1ab1efb0586f25cfcba2',
    'ra37_namelist': '37806b6230d9a9479bae32611b6b70d0318ce852fe3931af84ba1e7a15bdcc58',
    'ra4_namelist': 'e22b0df372e3d909d21ea50881fb8429f3a76a7bd433c1d583ebfd2af2754320',
    'wrfinput_d01': '0cc7e188ef585a93ab52550816c6af236932254820fb1bc6937f464bfed38637',
    'wrfbdy_d01': 'ba4241de4f4661a77733cf157f0c87f90668f107df86f8c92d092b56d7bd7bd4',
    'radiation_iofields.txt': '3890e55c599314f0fddb56585d64164eebaf70b2280589aa679439bc35b505c3',
    'frozen-ice-psd-moments.nc': '8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583',
    'ra4_history': 'edf0cfbf4efeecbbf69e979c8f4fc21a19a436f4329a3e11330a2c569ea0bcc4',
    'predecessor_runner': '815ca1250da4fe7591f623562862d0d9a68d32e4b78a7cb898747b55dd363627',
}
INPUTS = ('wrfinput_d01', 'wrfbdy_d01', 'radiation_iofields.txt')
TIMES = [(dt.datetime(2000, 1, 24, 12) + dt.timedelta(hours=h)).strftime('%Y-%m-%d_%H:%M:%S') for h in range(25)]
RESTART_TIMES = ['2000-01-25_00:00:00', '2000-01-25_12:00:00']
GEOMETRY = {'west_east': 73, 'south_north': 60, 'bottom_top': 32}
STACK_BYTES = 512 * 1024 * 1024
TIMEOUT = 1200


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def pin(path):
    p = Path(path).resolve(strict=True)
    if not p.is_file():
        raise ValueError(f'expected regular file: {p}')
    return {'path': str(p), 'size_bytes': p.stat().st_size, 'sha256': digest(p)}


def require_hash(path, expected):
    got = pin(path)
    if got['sha256'] != expected:
        raise ValueError(f'pin mismatch: {path}')
    return got


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def link_pin(path):
    p = Path(path)
    if not p.is_symlink():
        raise ValueError(f'expected symlink: {p}')
    resolved = p.resolve(strict=True)
    return {'name': p.name, 'link_text': os.readlink(p), 'resolved_target': str(resolved),
            'target': pin(resolved) if resolved.is_file() else {'directory': True, 'path': str(resolved)}}


def source_check(manifest_path):
    manifest = require_hash(manifest_path, EXPECTED['source_manifest'])
    data = json.loads(Path(manifest_path).read_text())
    source = Path(data['source_path']).resolve(strict=True)
    if data['base_commit'] != '22ab474286c7b808d6f81e08ce457ddf6ba8e9cb' or len(data['files']) != 6709:
        raise ValueError('wrong source base/count')
    links = 0
    unavailable_external_links = []
    for item in data['files']:
        p = source / item['path']
        if item['type'] == 'file':
            if p.is_symlink() or not p.is_file() or p.stat().st_size != item['size'] or digest(p) != item['sha256']:
                raise ValueError(f'source file changed: {p}')
        elif item['type'] == 'symlink':
            links += 1
            if not p.is_symlink() or os.readlink(p) != item['target']:
                raise ValueError(f'source symlink changed: {p}')
            if not p.exists():
                unavailable_external_links.append({'path': item['path'], 'target': item['target']})
        else:
            raise ValueError(f'unsupported manifest type: {item}')
    allowed_unavailable = [
        {'path': 'WRF/var/run/crtm_coeffs', 'target': '/glade/work/wrfhelp/WRFDA_files/crtm_coeffs_2.3.0'},
        {'path': 'WRF/var/test/radiance/crtm_coeffs', 'target': '../../run/crtm_coeffs'}]
    if unavailable_external_links != allowed_unavailable:
        raise ValueError(f'unexpected unavailable source links: {unavailable_external_links}')
    if links != 17:
        raise ValueError('expected all 17 tracked source symlinks')
    config = require_hash(source / 'WRF/configure.wrf', EXPECTED['configure'])
    text = '\n'.join(line.split('#', 1)[0] for line in Path(config['path']).read_text().splitlines())
    if '-DDM_PARALLEL' not in text or '-fopenmp' not in text:
        raise ValueError('expected final dm+sm build')
    return {'source_manifest': manifest, 'configure': config, 'source_root': str(source),
            'verified_files_and_symlinks': len(data['files']), 'verified_symlinks': links, 'unavailable_external_WRFDA_links': unavailable_external_links}


def library_pins(binary, ld_path):
    env = os.environ.copy()
    env['LD_LIBRARY_PATH'] = ld_path
    proc = subprocess.run(['ldd', str(binary)], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode or 'not found' in proc.stdout:
        raise ValueError(f'ldd failed: {proc.stdout}')
    libs = {}
    for line in proc.stdout.splitlines():
        m = re.search(r'=>\s+(/\S+)\s+\(', line) or re.match(r'\s*(/\S+)\s+\(', line)
        if m:
            p = Path(m.group(1)).resolve(strict=True)
            libs[str(p)] = pin(p)
    if not libs:
        raise ValueError('empty resolved-library inventory')
    return {'normalized_ldd': re.sub(r'\(0x[0-9a-fA-F]+\)', '(ASLR_ADDRESS)', proc.stdout),
            'libraries': [libs[k] for k in sorted(libs)]}


def coefficient_inventory(directory):
    p = Path(directory).resolve(strict=True)
    files = sorted(p.glob('rrtmgp*.nc'))
    if len(files) != 4:
        raise ValueError(f'expected four RRTMGP coefficient files: {p}: {files}')
    return [pin(f) for f in files]


def historical_arm(arm):
    src = HIST / arm
    nml = require_hash(src / 'namelist.input', EXPECTED[arm + '_namelist'])
    inputs = {name: require_hash(src / name, EXPECTED[name]) for name in INPUTS}
    nml_text = (src / 'namelist.input').read_text()
    bindings = {}
    for key in ('rrtmgp_data_path', 'rrtmgp_udm_frozen_table'):
        matches = re.findall(r'^\s*' + key + r"\s*=\s*'([^']+)'", nml_text, re.M)
        if len(matches) != 1 or not Path(matches[0]).is_absolute():
            raise ValueError(f'expected original absolute namelist binding for {key}')
        path = Path(matches[0])
        if path.parent != src:
            raise ValueError(f'wrong historical binding for {arm}/{key}: {path}')
        bindings[key] = {'literal_path': str(path), 'symlink': link_pin(path)}
    bindings['rrtmgp_data_path']['coefficient_files'] = coefficient_inventory(bindings['rrtmgp_data_path']['literal_path'])
    bindings['rrtmgp_udm_frozen_table']['file'] = require_hash(bindings['rrtmgp_udm_frozen_table']['literal_path'], EXPECTED['frozen-ice-psd-moments.nc'])
    inv = json.loads((HIST / 'runtime-link-manifest.json').read_text())['arms'][arm]
    runtime = []
    for item in inv:
        if item['name'] in ('namelist.input', 'wrf.exe'):
            continue
        actual = link_pin(src / item['name'])
        if actual['resolved_target'] != item['resolved_target'] or actual['target']['sha256'] != item['sha256']:
            raise ValueError(f'historical runtime manifest mismatch: {arm}/{item["name"]}')
        runtime.append(actual)
    return {'arm': arm, 'source_case': str(src), 'namelist': nml, 'inputs': inputs,
            'namelist_absolute_bindings': bindings, 'runtime_links': runtime}


def baseline_pin():
    history = HIST / 'ra4/wrfout_d01_2000-01-24_12:00:00'
    return {'history': require_hash(history, EXPECTED['ra4_history']),
            'official_whole_file_proof': require_hash(ROOT / 'build/pristine-jan-ra4/root-whole-file-identity.json',
                '3593d8c6593ed0cb0bd9b41cd5dd42d9ad6675693e2f1bd935b5bb3aaefefdef')}


def build_snapshot(args):
    return {'source': source_check(args.source_manifest),
            'binary': require_hash(args.binary, EXPECTED['binary']),
            'binary_libraries': library_pins(args.binary, args.ld_library_path),
            'mpiexec': pin(args.mpiexec), 'mpiexec_libraries': library_pins(args.mpiexec, args.ld_library_path)}


def case_snapshot(entry):
    case = Path(entry['case_path'])
    return {'namelist': require_hash(case / 'namelist.input', EXPECTED[entry['arm'] + '_namelist']),
            'links': [link_pin(case / name) for name in entry['link_names']],
            'historical_arm': historical_arm(entry['arm'])}


def clean_run_env(mpiexec, ld_path):
    env = os.environ.copy()
    cleared = sorted(k for k in env if k.startswith('WRF_RRTMGP_') or k.startswith('OMP_') or k in ('LD_PRELOAD', 'LD_AUDIT'))
    for key in cleared:
        env.pop(key, None)
    env.update({'OMP_NUM_THREADS': '1', 'OMP_DYNAMIC': 'FALSE', 'OMP_STACKSIZE': '512M',
                'LD_LIBRARY_PATH': ld_path, 'MPICH_INTERFACE_HOSTNAME': '127.0.0.1',
                'PATH': str(Path(mpiexec).parent) + os.pathsep + env.get('PATH', '')})
    return env, cleared


def stage(args):
    dest = args.stage_root.absolute()
    # This test is deliberately first, before pinning/importing or creating files.
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f'stage collision: {dest}')
    if args.timeout != TIMEOUT:
        raise ValueError('reviewed timeout must be exactly 1200s')
    predecessor = require_hash(ROOT / 'build/udm-cu-corrected-winter-v1/prepare_corrected_winter.py', EXPECTED['predecessor_runner'])
    build = build_snapshot(args)
    arms = [historical_arm(a) for a in ('ra4',)]
    baseline = baseline_pin()
    runtime_manifest = pin(HIST / 'runtime-link-manifest.json')
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.mkdir(exist_ok=False)
    try:
        entries = []
        for original in arms:
            arm = original['arm']
            case = dest / (arm + '-jan24h-mpi4')
            case.mkdir()
            src = Path(original['source_case'])
            link_names = []
            for item in original['runtime_links']:
                name = item['name']
                # Preserve the actual historical runtime target, including CAM SSP245.
                (case / name).symlink_to(item['resolved_target'])
                link_names.append(name)
            for name in INPUTS:
                if name not in link_names:
                    (case / name).symlink_to((src / name).resolve(strict=True))
                    link_names.append(name)
            for name in ('rrtmgp_data', 'frozen-ice-psd-moments.nc'):
                (case / name).symlink_to((src / name).resolve(strict=True))
                link_names.append(name)
            (case / 'wrf.exe').symlink_to(Path(args.binary).resolve(strict=True))
            link_names.append('wrf.exe')
            shutil.copy2(src / 'namelist.input', case / 'namelist.input')
            if (case / 'namelist.input').read_bytes() != (src / 'namelist.input').read_bytes():
                raise ValueError('namelist copy is not byte-identical')
            entry = {'arm': arm, 'case_path': str(case), 'link_names': sorted(link_names),
                     'expected_times': TIMES, 'expected_geometry': GEOMETRY,
                     'expected_radiation': 37 if arm == 'ra37' else 4,
                     'expected_restarts': RESTART_TIMES, 'namelist_changes': 'NONE; original bytes and absolute asset bindings retained'}
            entry['snapshot'] = case_snapshot(entry)
            entries.append(entry)
        env, cleared = clean_run_env(args.mpiexec, args.ld_library_path)
        shutil.copy2(Path(__file__), dest / Path(__file__).name)
        shutil.copy2(HERE / 'README-ra4-only-v3.md', dest / 'README.md')
        receipt = {'schema': 'udm-cu-winter24h-ra4-only-stage-v3', 'status': 'STAGED_NOT_RUN',
                   'model_invocations': 0, 'runner': pin(Path(__file__)), 'staged_runner': pin(dest / Path(__file__).name),
                   'predecessor': predecessor, 'build': build, 'runtime_link_manifest': runtime_manifest,
                   'baseline_ra4': baseline, 'cases': entries, 'ld_library_path': args.ld_library_path,
                   'runtime': {'ranks': 4, 'omp_threads': 1, 'master_stack_bytes': STACK_BYTES,
                               'per_case_timeout_seconds': TIMEOUT, 'timeout_scope': 'whole new process group; TERM then KILL after 30s',
                               'inherited_cleared_env_names': cleared, 'explicit_env': {k: env[k] for k in ('OMP_NUM_THREADS', 'OMP_DYNAMIC', 'OMP_STACKSIZE', 'LD_LIBRARY_PATH', 'MPICH_INTERFACE_HOSTNAME', 'PATH')},
                               'command': [str(Path(args.mpiexec).resolve()), '-launcher', 'fork', '-iface', 'lo', '-n', '4', './wrf.exe']},
                   'future_restart_gate': 'NOT STAGED/NOT RUN: each arm must use its OWN newly produced 00Z (12h) restart. Its reviewed 12→13h case must compare all common raw arrays/Times against that same arm continuous 01Z (13h) slice, with run-control metadata differences reported explicitly. No RA4/RA37 or historical restart substitution.'}
        # Verify all shared data/source pins again after staging.
        if build_snapshot(args) != build or baseline_pin() != baseline:
            raise ValueError('source/binary/library/baseline changed while staging')
        for entry in entries:
            if case_snapshot(entry) != entry['snapshot']:
                raise ValueError('staged or historical asset changed while staging')
        if pin(HIST / 'runtime-link-manifest.json') != runtime_manifest:
            raise ValueError('runtime manifest changed while staging')
        write_json(dest / 'stage-receipt.json', receipt)
        return receipt
    except Exception as exc:
        write_json(dest / 'stage-failure.json', {'status': 'STAGE_FAILED', 'error': f'{type(exc).__name__}: {exc}', 'model_invocations': 0})
        raise


def encoded_attribute(value):
    """Lossless, type-aware metadata representation, including signed zero."""
    import numpy as np
    if isinstance(value, str):
        return {'string': value}
    if isinstance(value, bytes):
        return {'bytes_hex': value.hex()}
    arr = np.asarray(value)
    if arr.dtype.kind in 'OUS':
        return {'dtype': arr.dtype.str, 'shape': list(arr.shape), 'values': arr.tolist()}
    return {'dtype': arr.dtype.str, 'shape': list(arr.shape), 'bytes_hex': arr.tobytes().hex()}


def metadata(ds):
    return {'data_model': ds.data_model,
            'dimensions': {k: {'size': len(v), 'unlimited': v.isunlimited()} for k, v in ds.dimensions.items()},
            'global_attributes': {k: encoded_attribute(ds.getncattr(k)) for k in ds.ncattrs()},
            'variables': {k: {'dtype': str(v.dtype), 'dimensions': list(v.dimensions), 'shape': list(v.shape),
                              'attributes': {a: encoded_attribute(v.getncattr(a)) for a in v.ncattrs()}} for k, v in ds.variables.items()}}


def times_from(ds):
    import numpy as np
    var = ds.variables['Times']
    var.set_auto_maskandscale(False)
    rows = np.asarray(var[:])
    return [(b''.join(row).decode('ascii') if rows.dtype.kind == 'S' else ''.join(row)).strip() for row in rows]


def numeric_check(var):
    import numpy as np
    var.set_auto_maskandscale(True)
    decoded = var[:]
    masks = int(np.count_nonzero(np.ma.getmaskarray(decoded)))
    decoded_array = np.asarray(np.ma.getdata(decoded))
    decoded_nf = int(np.count_nonzero(~np.isfinite(decoded_array)))
    var.set_auto_maskandscale(False)
    raw = np.asarray(var[:])
    raw_nf = int(np.count_nonzero(~np.isfinite(raw)))
    attr_hits = {}
    for label in ('_FillValue', 'missing_value'):
        if label in var.ncattrs():
            count = 0
            for val in np.asarray(var.getncattr(label)).reshape(-1):
                count += int(np.count_nonzero(np.isnan(raw) if np.isnan(val) else raw == val))
            attr_hits[label] = count
    return {'mask_hits': masks, 'raw_nonfinite': raw_nf, 'decoded_nonfinite': decoded_nf,
            'explicit_fill_or_missing_hits': attr_hits, 'raw_sha256': hashlib.sha256(raw.tobytes()).hexdigest(),
            'passed': masks == raw_nf == decoded_nf == 0 and not any(attr_hits.values())}


def scalar_value(value):
    return value.item() if hasattr(value, 'item') else value


def validate_dataset(path, expected_times, radiation, geometry=GEOMETRY):
    from netCDF4 import Dataset
    import numpy as np
    with Dataset(path) as ds:
        got_times = times_from(ds)
        dims = {k: len(ds.dimensions[k]) if k in ds.dimensions else None for k in geometry}
        physical = {'MP_PHYSICS': scalar_value(ds.getncattr('MP_PHYSICS')) if 'MP_PHYSICS' in ds.ncattrs() else None,
                    'RA_LW_PHYSICS': scalar_value(ds.getncattr('RA_LW_PHYSICS')) if 'RA_LW_PHYSICS' in ds.ncattrs() else None,
                    'RA_SW_PHYSICS': scalar_value(ds.getncattr('RA_SW_PHYSICS')) if 'RA_SW_PHYSICS' in ds.ncattrs() else None}
        variables = {k: numeric_check(v) for k, v in ds.variables.items() if np.issubdtype(v.dtype, np.number)}
        meta = metadata(ds)
        passed = (got_times == expected_times and dims == geometry and physical == {'MP_PHYSICS': 27, 'RA_LW_PHYSICS': radiation, 'RA_SW_PHYSICS': radiation}
                  and bool(variables) and all(x['passed'] for x in variables.values()))
    return {'file': pin(path), 'ordered_times': got_times, 'expected_times': expected_times, 'geometry': dims,
            'physics': physical, 'variable_count': len(meta['variables']), 'numeric_variable_count': len(variables),
            'metadata': meta, 'numeric_variables': variables, 'passed': bool(passed)}


def compare_datasets(candidate, baseline):
    from netCDF4 import Dataset
    import numpy as np
    mismatch = {}
    with Dataset(candidate) as a, Dataset(baseline) as b:
        ma, mb = metadata(a), metadata(b)
        meta_equal = ma == mb
        if set(a.variables) != set(b.variables):
            mismatch['variable_names'] = {'candidate': sorted(a.variables), 'baseline': sorted(b.variables)}
        for name in sorted(set(a.variables) & set(b.variables)):
            av, bv = a.variables[name], b.variables[name]
            av.set_auto_maskandscale(False)
            bv.set_auto_maskandscale(False)
            aa, bb = np.asarray(av[:]), np.asarray(bv[:])
            if aa.dtype != bb.dtype or aa.shape != bb.shape or aa.tobytes() != bb.tobytes():
                mismatch[name] = {'candidate_shape': list(aa.shape), 'baseline_shape': list(bb.shape),
                                  'candidate_raw_sha256': hashlib.sha256(aa.tobytes()).hexdigest(),
                                  'baseline_raw_sha256': hashlib.sha256(bb.tobytes()).hexdigest()}
    pa, pb = pin(candidate), pin(baseline)
    whole = pa['size_bytes'] == pb['size_bytes'] and pa['sha256'] == pb['sha256']
    return {'candidate': pa, 'baseline': pb, 'whole_file_byte_identity': whole, 'all_metadata_equal': meta_equal,
            'all_variable_raw_bytes_equal': not mismatch, 'raw_mismatches': mismatch,
            'passed': whole and meta_equal and not mismatch}


def validate_outputs(entry, baseline):
    case = Path(entry['case_path'])
    histories = sorted(case.glob('wrfout_d01_*'))
    if len(histories) != 1:
        raise ValueError(f'expected single frames_per_outfile=1000 history, got {histories}')
    history = validate_dataset(histories[0], TIMES, entry['expected_radiation'])
    restarts = sorted(case.glob('wrfrst_d01_*'))
    expected_names = ['wrfrst_d01_' + t for t in RESTART_TIMES]
    if [p.name for p in restarts] != expected_names:
        raise ValueError(f'expected exact own 12h/24h checkpoints, got {restarts}')
    restart_checks = [validate_dataset(p, [stamp], entry['expected_radiation']) for p, stamp in zip(restarts, RESTART_TIMES)]
    parity = compare_datasets(histories[0], Path(baseline['history']['path'])) if entry['arm'] == 'ra4' else None
    return {'history': history, 'own_checkpoints': restart_checks, 'ra4_historical_preservation': parity,
            'passed': history['passed'] and all(c['passed'] for c in restart_checks) and (parity is None or parity['passed'])}


def run_one(entry, args):
    case = Path(entry['case_path'])
    env, cleared = clean_run_env(args.mpiexec, args.ld_library_path)
    command = [str(Path(args.mpiexec).resolve()), '-launcher', 'fork', '-iface', 'lo', '-n', '4', './wrf.exe']
    def limit_stack():
        resource.setrlimit(resource.RLIMIT_STACK, (STACK_BYTES, STACK_BYTES))
    started = time.monotonic()
    with (case / 'runner.stdout.log').open('x') as stream:
        proc = subprocess.Popen(command, cwd=case, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                start_new_session=True, preexec_fn=limit_stack)
        timed_out = False
        try:
            while proc.poll() is None:
                elapsed = time.monotonic() - started
                write_json(case / 'run-progress.json', {'elapsed_seconds': elapsed, 'returncode': None})
                if elapsed >= TIMEOUT:
                    timed_out = True
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                    break
                time.sleep(1)
        except BaseException:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
            raise
    logs = sorted(case.glob('rsl.error.[0-9][0-9][0-9][0-9]'))
    ranks = []
    for log in logs:
        text = log.read_text(errors='replace')
        ranks.append({'file': pin(log), 'success': 'SUCCESS COMPLETE WRF' in text,
                      'fatal': bool(re.search(r'FATAL|MPI_ABORT|SIGSEGV|SIGABRT|forrtl: severe|Backtrace|Program received signal', text, re.I))})
    elapsed = time.monotonic() - started
    good = proc.returncode == 0 and not timed_out and len(ranks) == 4 and all(r['success'] and not r['fatal'] for r in ranks)
    write_json(case / 'run-progress.json', {'elapsed_seconds': elapsed, 'returncode': proc.returncode, 'timed_out': timed_out})
    return {'command': command, 'cleared_inherited_env_names': cleared,
            'stack_limit_soft_hard_bytes': [STACK_BYTES, STACK_BYTES], 'timeout_seconds': TIMEOUT,
            'elapsed_seconds': elapsed, 'returncode': proc.returncode, 'timed_out': timed_out,
            'rank_logs': ranks, 'stdout': pin(case / 'runner.stdout.log'), 'model_completed': good}


def stage_invariants(receipt, args):
    if build_snapshot(args) != receipt['build']:
        raise ValueError('build/source/dependencies no longer match reviewed stage')
    if pin(HIST / 'runtime-link-manifest.json') != receipt['runtime_link_manifest'] or baseline_pin() != receipt['baseline_ra4']:
        raise ValueError('historical runtime manifest or RA4 baseline changed')
    for entry in receipt['cases']:
        if case_snapshot(entry) != entry['snapshot']:
            raise ValueError(f'case asset change: {entry["arm"]}')
    if pin(Path(__file__)) != receipt['runner'] or pin(Path(receipt['staged_runner']['path'])) != receipt['staged_runner']:
        raise ValueError('reviewed runner changed')
    if args.ld_library_path != receipt['ld_library_path'] or args.timeout != TIMEOUT:
        raise ValueError('runtime arguments differ from reviewed stage')


def execute(args):
    root = args.stage_root.resolve(strict=True)
    output = root / 'execution-receipt.json'
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'execution receipt collision: {output}')
    receipt = json.loads((root / 'stage-receipt.json').read_text())
    if receipt['status'] != 'STAGED_NOT_RUN':
        raise ValueError('expected staged-only receipt')
    stage_invariants(receipt, args)
    for entry in receipt['cases']:
        case = Path(entry['case_path'])
        if any(case.glob('wrfout*')) or any(case.glob('wrfrst*')) or any(case.glob('rsl.*')) or (case / 'runner.stdout.log').exists():
            raise FileExistsError(f'case already has execution outputs: {case}')
    result = {'schema': 'udm-cu-winter24h-ra4-only-execution-v3', 'status': 'RUNNING', 'stage_receipt': pin(root / 'stage-receipt.json'), 'runs': [], 'actual_model_invocations': 0}
    with output.open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    try:
        for entry in receipt['cases']:
            stage_invariants(receipt, args)
            item = {'arm': entry['arm'], 'case_path': entry['case_path']}
            try:
                result['actual_model_invocations'] += 1
                item['model'] = run_one(entry, args)
                # Keep finite/metadata/output evidence even when model completion fails.
                item['outputs'] = validate_outputs(entry, receipt['baseline_ra4'])
                item['passed'] = item['model']['model_completed'] and item['outputs']['passed']
            except Exception as exc:
                item['passed'] = False
                item['error'] = f'{type(exc).__name__}: {exc}'
            finally:
                try:
                    stage_invariants(receipt, args)
                    item['all_source_inputs_assets_libraries_unchanged'] = True
                except Exception as exc:
                    item['all_source_inputs_assets_libraries_unchanged'] = False
                    item['invariant_error'] = f'{type(exc).__name__}: {exc}'
                    item['passed'] = False
            result['runs'].append(item)
            result['status'] = 'RUNNING' if item['passed'] else 'FAIL_STOPPED'
            write_json(output, result)
            if not item['passed']:
                break
        result['status'] = 'PASS_RA4_PRESERVATION24H' if len(result['runs']) == 1 and all(r['passed'] for r in result['runs']) else 'FAIL_STOPPED'
    except Exception as exc:
        result['status'] = 'FAIL_STOPPED'
        result['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        try:
            stage_invariants(receipt, args)
            result['final_all_pins_unchanged'] = True
        except Exception as exc:
            result['final_all_pins_unchanged'] = False
            result['final_pin_error'] = f'{type(exc).__name__}: {exc}'
            result['status'] = 'FAIL_STOPPED'
        write_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage-root', type=Path, default=HERE / 'staged-ra4-only-v3')
    parser.add_argument('--binary', type=Path, default=BINARY)
    parser.add_argument('--source-manifest', type=Path, default=SOURCE_MANIFEST)
    parser.add_argument('--mpiexec', type=Path, default=MPIEXEC)
    parser.add_argument('--ld-library-path', default=LD_DEFAULT)
    parser.add_argument('--timeout', type=int, default=TIMEOUT)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    try:
        result = execute(args) if args.execute else stage(args)
    except FileExistsError as exc:
        print(json.dumps({'status': 'OUTPUT_COLLISION', 'error': str(exc)}))
        return 2
    except Exception as exc:
        print(json.dumps({'status': 'SETUP_FAILED', 'error': f'{type(exc).__name__}: {exc}'}))
        return 1
    print(json.dumps({'status': result['status'], 'stage_root': str(args.stage_root.absolute()), 'actual_model_invocations': result.get('actual_model_invocations', 0)}))
    return 0 if result['status'] in ('STAGED_NOT_RUN', 'PASS_RA4_PRESERVATION24H') else 1


if __name__ == '__main__':
    raise SystemExit(main())
