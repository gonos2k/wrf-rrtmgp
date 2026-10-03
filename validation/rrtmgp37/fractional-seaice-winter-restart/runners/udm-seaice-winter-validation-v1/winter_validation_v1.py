#!/usr/bin/env python3
"""Versioned sea-ice validation primitives; no model command at import."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import time
ROOT=Path(__file__).resolve().parents[2]
HIST=ROOT/'build/udm-alternate-jan2000-data/paired-forecast-v2'
LD_DEFAULT=':'.join(str(ROOT/p) for p in ('build/deps/netcdf/lib','build/deps/root/usr/lib/x86_64-linux-gnu','build/deps/mpich-sock/lib'))
MPIEXEC=ROOT/'build/deps/mpich-sock/bin/mpiexec'
STACK_BYTES=512*1024*1024
TIMEOUT=1200
GEOMETRY={'west_east':73,'south_north':60,'bottom_top':32}
TIMES=[(dt.datetime(2000,1,24,12)+dt.timedelta(hours=h)).strftime('%Y-%m-%d_%H:%M:%S') for h in range(25)]
RESTART_TIMES=['2000-01-25_00:00:00','2000-01-25_12:00:00']
EXPECTED={'ra37_namelist': '37806b6230d9a9479bae32611b6b70d0318ce852fe3931af84ba1e7a15bdcc58', 'ra4_namelist': 'e22b0df372e3d909d21ea50881fb8429f3a76a7bd433c1d583ebfd2af2754320', 'wrfinput_d01': '0cc7e188ef585a93ab52550816c6af236932254820fb1bc6937f464bfed38637', 'wrfbdy_d01': 'ba4241de4f4661a77733cf157f0c87f90668f107df86f8c92d092b56d7bd7bd4', 'radiation_iofields.txt': '3890e55c599314f0fddb56585d64164eebaf70b2280589aa679439bc35b505c3', 'frozen-ice-psd-moments.nc': '8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583', 'ra4_history': 'edf0cfbf4efeecbbf69e979c8f4fc21a19a436f4329a3e11330a2c569ea0bcc4'}


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


def library_pins(binary, ld_path):
    env = os.environ.copy()
    env['LD_LIBRARY_PATH'] = ld_path
    env.pop('LD_PRELOAD',None)
    env.pop('LD_AUDIT',None)
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


def clean_run_env(mpiexec, ld_path):
    env = os.environ.copy()
    cleared = sorted(k for k in env if k.startswith('WRF_RRTMGP_') or k.startswith('OMP_') or k in ('LD_PRELOAD', 'LD_AUDIT'))
    for key in cleared:
        env.pop(key, None)
    env.update({'OMP_NUM_THREADS': '1', 'OMP_DYNAMIC': 'FALSE', 'OMP_STACKSIZE': '512M',
                'LD_LIBRARY_PATH': ld_path, 'MPICH_INTERFACE_HOSTNAME': '127.0.0.1',
                'PATH': str(Path(mpiexec).parent) + os.pathsep + env.get('PATH', '')})
    return env, cleared


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


def run_one(entry, args, on_launch=None):
    case = Path(entry['case_path'])
    env, cleared = clean_run_env(args.mpiexec, args.ld_library_path)
    command = [str(Path(args.mpiexec).resolve()), '-launcher', 'fork', '-iface', 'lo', '-n', '4', './wrf.exe']
    def limit_stack():
        resource.setrlimit(resource.RLIMIT_STACK, (STACK_BYTES, STACK_BYTES))
    started_utc=dt.datetime.now(dt.timezone.utc).isoformat()
    started = time.monotonic()
    with (case / 'runner.stdout.log').open('x') as stream:
        proc = subprocess.Popen(command, cwd=case, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                start_new_session=True, preexec_fn=limit_stack)
        timed_out = False
        try:
            if on_launch is not None:
                on_launch(proc.pid)
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
    return {'command': command, 'started_utc': started_utc, 'ended_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'cleared_inherited_env_names': cleared,
            'stack_limit_soft_hard_bytes': [STACK_BYTES, STACK_BYTES], 'timeout_seconds': TIMEOUT,
            'elapsed_seconds': elapsed, 'returncode': proc.returncode, 'timed_out': timed_out,
            'rank_logs': ranks, 'stdout': pin(case / 'runner.stdout.log'), 'model_completed': good}

BASE='8ab95cfa984235622687bf708f94385c2774ceac'
PRODUCTION7=['WRF/phys/'+x for x in ('module_ra_rrtmg_lw.F','module_ra_rrtmg_sw.F','module_ra_rrtmgp.F','module_ra_rrtmgp_input.F','module_ra_rrtmgp_trace.F','module_radiation_driver.F','module_surface_driver.F')]
UNAVAILABLE_SOURCE_LINKS={'WRF/var/run/crtm_coeffs':'/glade/work/wrfhelp/WRFDA_files/crtm_coeffs_2.3.0','WRF/var/test/radiance/crtm_coeffs':'../../run/crtm_coeffs'}


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def collision(path):
    p=Path(path)
    if p.exists() or p.is_symlink():
        raise FileExistsError(f'output collision; preserve prior evidence: {p}')


def check_pin(expected):
    actual=pin(Path(expected['path']))
    if actual != expected:
        raise ValueError(f'file changed: {expected["path"]}')
    return actual


def load_freeze(path, sha):
    spec_pin=require_hash(path,sha)
    spec=json.loads(Path(path).read_text())
    if spec.get('status')!='ROOT_FROZEN' or spec.get('base_commit')!=BASE:
        raise ValueError('requires root-final ROOT_FROZEN spec at exact PR46 base')
    if not spec.get('root_source_freeze'):raise ValueError('requires final rootfreeze-v2 chain')
    rootfreeze=require_hash(spec['root_source_freeze']['path'],'a6c7c0d0fb0471579569fce85c3d943e3dd3a16bb2f3019a88e4406558f756f8')
    if rootfreeze!=spec['root_source_freeze']:raise ValueError('rootfreeze-v2 pin differs')
    rootdata=json.loads(Path(rootfreeze['path']).read_text())
    if spec.get('production7')!=rootdata['production'] or {x['relative_path']:x['source']['sha256'] for x in spec.get('overlay',[])}!=rootdata['overlay']:raise ValueError('derived source spec differs from final rootfreeze-v2')
    if set(spec.get('production7',{}))!=set(PRODUCTION7):
        raise ValueError('requires all exact seven production source pins')
    for value in spec['production7'].values():
        if not isinstance(value,str) or re.fullmatch(r'[0-9a-f]{64}',value) is None:
            raise ValueError('pending/invalid production freeze SHA')
    if not spec.get('overlay') or not spec.get('scripts') or not spec.get('compiled_surface_patterns'):
        raise ValueError('requires explicit overlays/scripts/compiled surface patterns')
    for item in spec['overlay']:
        rel=Path(item['relative_path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('unsafe overlay relative path')
        check_pin(item['source'])
    for item in spec['scripts']:
        check_pin(item)
    config=check_pin(spec['configure_template'])
    if config['sha256']!='44f85b7fc9b6994cb3784567e69d310580740a021b5f1ab1efb0586f25cfcba2':
        raise ValueError('GNU dm+sm config must remain exact44f85 template')
    if spec['symlink_count']!=17:
        raise ValueError('all17 tracked original source links required')
    return spec,spec_pin


def verify_production7(source,spec):
    out={}
    for rel,sha in spec['production7'].items():
        p=Path(source)/rel
        out[rel]=require_hash(p,sha)
        if out[rel]['size_bytes']==0:
            raise ValueError(f'empty production source: {rel}')
    return out


def verify_manifest(manifest_pin,production7=None):
    check_pin(manifest_pin)
    data=json.loads(Path(manifest_pin['path']).read_text())
    source=Path(data['source_path']).resolve(strict=True)
    if data['base_commit']!=BASE or len(data['files'])!=data['entry_count']:
        raise ValueError('wrong/incomplete canonical manifest')
    seen=set();links=0;unavailable=[]
    for item in data['files']:
        rel=item['path'];p=source/rel
        if rel in seen or Path(rel).is_absolute() or '..' in Path(rel).parts:
            raise ValueError('duplicate/unsafe manifest relative path')
        seen.add(rel)
        if item['type']=='file':
            if p.is_symlink() or not p.is_file() or p.stat().st_size!=item['size'] or digest(p)!=item['sha256']:
                raise ValueError(f'source manifest mismatch: {p}')
        elif item['type']=='symlink':
            links+=1
            if not p.is_symlink() or os.readlink(p)!=item['target']:
                raise ValueError(f'source linktext mismatch: {p}')
            if not p.exists():
                if UNAVAILABLE_SOURCE_LINKS.get(rel)!=item['target']:
                    raise ValueError(f'unexpected unavailable source link: {p}')
                unavailable.append({'path':rel,'target':item['target']})
        else:
            raise ValueError('unsupported manifest entry type')
    if links!=17 or links!=data['symlink_count'] or 'WRF/configure.wrf' not in seen:
        raise ValueError('missing symlinks/config from full canonical manifest')
    config=require_hash(source/'WRF/configure.wrf','44f85b7fc9b6994cb3784567e69d310580740a021b5f1ab1efb0586f25cfcba2')
    active='\n'.join(line.split('#',1)[0] for line in Path(config['path']).read_text().splitlines())
    if '-DDM_PARALLEL' not in active or '-fopenmp' not in active:
        raise ValueError('wrong active MPI/OpenMP config')
    for item in data['files']:
        if item['type']=='file' and item['size']==0 and data.get('git_authenticated_empty_files',{}).get(item['path'])!='e69de29bb2d1d6434b8b29ae775ad8c2e48c5391':
            raise ValueError('unauthenticated empty manifested source')
    if production7 is not None:
        verify_production7(source,{'production7':production7})
    return {'source_path':str(source),'entry_count':len(seen),'symlink_count':links,'unavailable_source_links':unavailable,'configure':config}


def build_integrity(build_pin):
    check_pin(build_pin)
    b=json.loads(Path(build_pin['path']).read_text())
    if b['status']!='BUILD_PASS' or not b['source_unchanged'] or not b['dependencies_unchanged']:
        raise ValueError('requires authoritative fresh BUILD_PASS with unchanged source/deps')
    load_freeze(Path(b['freeze_spec']['path']),b['freeze_spec']['sha256'])
    verify_manifest(b['source_manifest'],b['production7'])
    check_pin(b['binary'])
    if library_pins(Path(b['binary']['path']),b['ld_library_path'])!=b['binary_libraries']:
        raise ValueError('resolved executable libraries changed')
    if pin(MPIEXEC)!=b['mpiexec'] or library_pins(MPIEXEC,b['ld_library_path'])!=b['mpiexec_libraries']:
        raise ValueError('launcher/dependencies changed')
    check_pin(b['shared_dependencies'])
    verify_dependency_inventory(json.loads(Path(b['shared_dependencies']['path']).read_text()))
    return b


def snapshot_case(entry):
    case=Path(entry['case_path'])
    out={'namelist':pin(case/'namelist.input'),'links':[link_pin(case/n) for n in entry['link_names']],
         'actual_original_radiation_bindings':historical_arm(entry['arm'])['namelist_absolute_bindings']}
    return out


def checkpoint_diagnostics(path):
    from netCDF4 import Dataset
    import numpy as np
    out={}
    with Dataset(path) as ds:
        for name in ('USTM','QZ0'):
            if name not in ds.variables:
                raise ValueError(f'missing repaired checkpoint diagnostic {name}')
            var=ds.variables[name];var.set_auto_maskandscale(False);a=np.asarray(var[:])
            finite=np.isfinite(a)
            out[name]={'finite_count':int(finite.sum()),'total_count':int(a.size),
                       'min':float(a[finite].min()) if finite.any() else None,
                       'max':float(a[finite].max()) if finite.any() else None,
                       'quantiles':np.quantile(a[finite],[0,.25,.5,.75,1]).tolist() if finite.any() else [],
                       'negative_count':int(np.count_nonzero(a<0)), 'nonzero_count':int(np.count_nonzero(a!=0)),
                       'signed_negative_zero_count':int(np.count_nonzero((a==0)&np.signbit(a))),
                       'old_failure_site_value':None}
            site=a[0,53,27] if name=='USTM' else a[0,58,34]
            out[name]['old_failure_site_value']=float(site) if np.isfinite(site) else None
            out[name]['old_failure_site_raw_ieee_hex']=np.asarray(site,dtype=a.dtype).tobytes().hex()
            out[name]['passed']=bool(finite.all() and (np.all(a>=0) if name=='USTM' else np.all(a==0)))
    out['passed']=all(out[n]['passed'] for n in ('USTM','QZ0'))
    return out


def unused_case(entry,restart=False):
    case=Path(entry['case_path']);bad=list(case.glob('wrfout*'))+list(case.glob('rsl.*'))
    bad+=[case/n for n in ('runner.stdout.log','run-progress.json') if (case/n).exists() or (case/n).is_symlink()]
    allowed=Path(entry['checkpoint']['path']).name if restart else None
    bad += [p for p in case.glob('wrfrst*') if p.name!=allowed]
    if bad:raise FileExistsError(f'case has earlier execution outputs: {bad}')


def restart_namelist(original):
    text=original;changes={'run_hours':('24','1'),'start_day':('24','25'),'start_hour':('12','00'),'end_hour':('12','01'),'restart':(r'\.false\.','.true.')}
    for key,(old,new) in changes.items():
        text,n=re.subn(r'^(\s*'+key+r'\s*=\s*)'+old+r'(\s*,)',lambda mt:mt.group(1)+new+mt.group(2),text,flags=re.M)
        if n!=1:raise ValueError(f'missing/duplicate restart-control {key}')
    reverse=text
    for key,(old,new) in changes.items():
        reverse,n=re.subn(r'^(\s*'+key+r'\s*=\s*)'+re.escape(new)+r'(\s*,)',lambda mt:mt.group(1)+old.replace('\\.','.')+mt.group(2),reverse,flags=re.M)
        if n!=1:raise ValueError('restart reverse validation failed')
    if reverse!=original:raise ValueError('extra namelist byte changes')
    return text


def continuous_slice(path,stamp='2000-01-25_01:00:00'):
    from netCDF4 import Dataset
    import numpy as np
    with Dataset(path) as ds:
        ts=times_from(ds)
        if ts.count(stamp)!=1:raise ValueError('nonunique/missing own13h reference')
        index=ts.index(stamp);records={}
        for name,var in ds.variables.items():
            var.set_auto_maskandscale(False);a=np.asarray(var[:])
            if 'Time' in var.dimensions:a=np.take(a,[index],axis=var.dimensions.index('Time'))
            records[name]={'dtype':a.dtype.str,'shape':list(a.shape),'dimensions':list(var.dimensions),'raw_sha256':hashlib.sha256(a.tobytes()).hexdigest(),'attributes':{k:encoded_attribute(var.getncattr(k)) for k in var.ncattrs()}}
        return {'path':pin(path),'selected_time':stamp,'zero_based_time_index':index,'metadata':metadata(ds),'all_raw_variable_slice_pins':records}


def compare_to_own_slice(candidate, reference):
    from netCDF4 import Dataset
    import numpy as np
    expected = reference['all_raw_variable_slice_pins']
    ref_meta = reference['metadata']
    with Dataset(candidate) as ds:
        got_meta = metadata(ds)
        variables = {}
        names_match = set(ds.variables) == set(expected)
        for name in sorted(set(ds.variables) & set(expected)):
            var = ds.variables[name]
            var.set_auto_maskandscale(False)
            raw = np.asarray(var[:])
            observed = {'dtype': raw.dtype.str, 'shape': list(raw.shape), 'dimensions': list(var.dimensions),
                        'raw_sha256': hashlib.sha256(raw.tobytes()).hexdigest(),
                        'attributes': {k: encoded_attribute(var.getncattr(k)) for k in var.ncattrs()}}
            target = expected[name]
            variables[name] = {'candidate': observed, 'reference': target,
                               'dtype_shape_dimensions_equal': all(observed[k] == target[k] for k in ('dtype', 'shape', 'dimensions')),
                               'raw_bytes_equal': observed['raw_sha256'] == target['raw_sha256'],
                               'all_variable_attributes_equal': observed['attributes'] == target['attributes'],
                               'passed': observed == target}
        global_differences = {}
        expected_runcontrol = {}
        unexplained = {}
        for name in sorted(set(got_meta['global_attributes']) | set(ref_meta['global_attributes'])):
            old = ref_meta['global_attributes'].get(name)
            new = got_meta['global_attributes'].get(name)
            if old != new:
                change = {'continuous': old, 'restart': new}
                global_differences[name] = change
                if name == 'START_DATE' and old == encoded_attribute('2000-01-24_12:00:00') and new == encoded_attribute('2000-01-25_00:00:00'):
                    expected_runcontrol[name] = change
                else:
                    unexplained[name] = change
        variable_attribute_differences = {k: {'continuous': variables[k]['reference']['attributes'], 'restart': variables[k]['candidate']['attributes']}
                                          for k in variables if not variables[k]['all_variable_attributes_equal']}
        dimension_differences = {k: {'continuous': ref_meta['dimensions'].get(k), 'restart': got_meta['dimensions'].get(k)}
                                 for k in sorted(set(ref_meta['dimensions']) | set(got_meta['dimensions']))
                                 if ref_meta['dimensions'].get(k) != got_meta['dimensions'].get(k)}
        expected_dims = dict(ref_meta['dimensions'])
        expected_dims['Time'] = {**expected_dims['Time'], 'size': 1}
        dims_ok = got_meta['dimensions'] == expected_dims
        expected_start_reported = set(expected_runcontrol) == {'START_DATE'}
        raw_ok = names_match and all(v['dtype_shape_dimensions_equal'] and v['raw_bytes_equal'] for v in variables.values())
        metadata_ok = (got_meta['data_model'] == ref_meta['data_model'] and dims_ok and not variable_attribute_differences
                       and not unexplained and expected_start_reported)
    return {'candidate': pin(candidate), 'continuous_reference': reference['path'],
            'reference_time': reference['selected_time'], 'reference_index': reference['zero_based_time_index'],
            'variable_count_expected': len(expected), 'variable_count_observed': len(got_meta['variables']),
            'all_variable_names_equal': names_match, 'all_raw_dtype_shape_dimensions_bytes_equal': raw_ok,
            'variable_results': variables, 'global_attribute_differences': global_differences,
            'expected_run_control_differences': expected_runcontrol, 'unexplained_global_attribute_differences': unexplained,
            'variable_attribute_differences': variable_attribute_differences,
            'dimension_differences': dimension_differences,
            'expected_time_slice_dimension_difference': {'continuous_Time': ref_meta['dimensions']['Time'], 'restart_Time': got_meta['dimensions'].get('Time')},
            'all_dimensions_match_expected_slice': dims_ok, 'all_metadata_matches_explicit_contract': metadata_ok,
            'candidate_metadata': got_meta, 'passed': raw_ok and metadata_ok}


def bounded_process(command,cwd,env,log,timeout):
    collision(log)
    started=utc_now();begin=time.monotonic();timed_out=False
    with Path(log).open('x') as stream:
        proc=subprocess.Popen(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True;os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=30)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        except BaseException:
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=30)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
            raise
    return {'command':command,'cwd':str(cwd),'started_utc':started,'ended_utc':utc_now(),'elapsed_seconds':time.monotonic()-begin,'returncode':proc.returncode,'timed_out':timed_out,'timeout_seconds':timeout,'log':pin(log)}


def verify_dependency_inventory(inventory):
    for entry in inventory['files']:
        if entry['kind']=='file':check_pin(entry['file'])
        elif entry['kind']=='symlink':
            if link_pin(Path(entry['path']))!=entry['link']:raise ValueError('shared dependency symlink/target changed')
        else:raise ValueError('invalid dependency inventory kind')
    for expected in inventory['tools'].values():check_pin(expected)
    check_pin(inventory['compiler_backend'])


def nonempty_artifact(path):
    p=Path(path)
    if not p.is_file() or p.stat().st_size==0:raise ValueError(f'empty/missing generated artifact cannot pass: {p}')
    return pin(p)


def classify_build_log(text,returncode):
    errors=[{'line':i,'text':x} for i,x in enumerate(text.splitlines(),1) if re.search(r'(?i)\berror:|undefined reference to|compilation terminated\.|make(?:\[\d+\])?: \*\*\*.*(?:Error|Stop)',x)]
    footer='Executables successfully built' in text
    return {'successful_footer':footer,'errors':errors,'passed':returncode==0 and footer and not errors}
