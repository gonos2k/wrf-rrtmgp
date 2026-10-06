#!/usr/bin/env python3
"""Build/run installed WRF CMake consumers; no WRF physics execution."""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, signal, subprocess, sys, time
from pathlib import Path

DEFAULT_TIMEOUT, TERM_GRACE = 300, 10
CONSUMERS = {
 'external-only/CMakeLists.txt': '''cmake_minimum_required(VERSION 3.20)
project(wrf_rrtmgp_external_consumer LANGUAGES Fortran)
find_package(WRF CONFIG REQUIRED)
add_executable(external_consumer main.F90)
target_link_libraries(external_consumer PRIVATE WRF::wrf_rrtmgp)
''',
 'external-only/main.F90': '''program external_consumer
  use mo_rte_kind, only: wp
  use mo_rte_util_array, only: zero_array
  implicit none
  real(wp) :: values(3)
  values = 1._wp
  call zero_array(size(values), values)
  if (any(values /= 0._wp)) error stop "RTE external consumer link/API failure"
end program external_consumer
''',
 'core-plus-rte/CMakeLists.txt': '''cmake_minimum_required(VERSION 3.20)
project(wrf_core_rte_consumer LANGUAGES Fortran)
find_package(WRF CONFIG REQUIRED)
add_executable(core_consumer main.F90)
target_link_libraries(core_consumer PRIVATE WRF::WRF_Core WRF::wrf_rrtmgp)
add_executable(optional_api_mirror ../optional_api_mirror.F90)
target_link_libraries(optional_api_mirror PRIVATE WRF::WRF_Core)
''',
 'core-plus-rte/main.F90': '''program core_consumer
  use module_microphysics_driver, only: microphysics_driver
  use mo_rte_kind, only: wp
  implicit none
  procedure(microphysics_driver), pointer :: driver_api
  real(wp) :: rte_probe
  driver_api => microphysics_driver
  if (.not. associated(driver_api)) error stop "Core driver interface unavailable"
  rte_probe = 0._wp
  if (rte_probe /= 0._wp) error stop "unexpected value"
end program core_consumer
''',
 'optional_api_mirror.F90': '''module optional_api_mirror
  implicit none
contains
  subroutine probe(ims, kms, jms, udm_cldfra, udm_cf_step, udm_cf_top)
    integer, intent(in) :: ims, kms, jms
    real, dimension(ims:,kms:,jms:), optional, intent(inout) :: udm_cldfra
    integer, dimension(ims:,jms:), optional, intent(inout) :: udm_cf_step, udm_cf_top
    if (present(udm_cldfra)) then
      if (lbound(udm_cldfra,1) /= ims .or. lbound(udm_cldfra,2) /= kms .or. &
          lbound(udm_cldfra,3) /= jms) error stop "unexpected cldfra lower bound"
      udm_cldfra = -1.0
    end if
    if (present(udm_cf_step)) then
      if (lbound(udm_cf_step,1) /= ims .or. lbound(udm_cf_step,2) /= jms) &
        error stop "unexpected step lower bound"
      udm_cf_step = -1
    end if
    if (present(udm_cf_top)) then
      if (lbound(udm_cf_top,1) /= ims .or. lbound(udm_cf_top,2) /= jms) &
        error stop "unexpected top lower bound"
      udm_cf_top = -1
    end if
  end subroutine probe
end module optional_api_mirror
program optional_api_mirror_test
  use optional_api_mirror, only: probe
  implicit none
  real, allocatable :: c(:,:,:)
  integer, allocatable :: s(:,:), t(:,:)
  integer :: ims, kms, jms
  ims = -2; kms = 0; jms = 4
  allocate(c(ims:1,kms:2,jms:6), s(ims:1,jms:6), t(ims:1,jms:6))
  c = 4.; s = 4; t = 4
  call probe(ims,kms,jms,c,s,t)
  if (any(c /= -1.) .or. any(s /= -1) .or. any(t /= -1)) &
    error stop "present allocatable actuals were not updated"
  call probe(ims,kms,jms)
  deallocate(c,s,t)
end program optional_api_mirror_test
''',
}

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''): h.update(block)
    return h.hexdigest()

def atomic(path, value):
    path = Path(path); tmp = path.with_name(path.name + '.tmp')
    with tmp.open('xb') as f:
        f.write((json.dumps(value, sort_keys=True, indent=2) + '\n').encode()); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def stage(state, receipt, name, argv, cwd, env, log_path, timeout):
    rec = {'name':name,'status':'STARTING','argv':argv,'cwd':str(cwd),'log':str(log_path),
           'timeout_seconds':timeout,'started_unix':time.time(),'pid':None,'returncode':None}
    state['stages'].append(rec); state['current_stage']=name; atomic(receipt,state)
    with Path(log_path).open('xb') as log:
        try: child=subprocess.Popen(argv,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        except BaseException as e:
            rec.update(status='FAILED_TO_SPAWN',spawn_error=f'{type(e).__name__}: {e}',ended_unix=time.time())
            state['status']='FAIL_PRESERVED'; atomic(receipt,state); raise
        rec.update(status='RUNNING',pid=child.pid,process_group=child.pid)
        timed_out=False
        try:
            atomic(receipt,state)
            rc=child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out=True
            try: os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: rc=child.wait(timeout=TERM_GRACE)
            except subprocess.TimeoutExpired:
                try: os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                try: rc=child.wait(timeout=TERM_GRACE)
                except subprocess.TimeoutExpired:
                    rec.update(status='TIMED_OUT_REAP_PENDING',returncode=child.poll(),
                               timed_out=True,reaped=False,ended_unix=time.time())
                    state['status']='FAIL_PRESERVED'; atomic(receipt,state)
                    raise RuntimeError(f'{name}: child not reaped after bounded SIGKILL wait')
        except BaseException as e:
            err=None
            try:
                if child.poll() is None:
                    os.killpg(child.pid,signal.SIGTERM)
                    try: child.wait(timeout=TERM_GRACE)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid,signal.SIGKILL); child.wait(timeout=TERM_GRACE)
            except BaseException as cleanup: err=f'{type(cleanup).__name__}: {cleanup}'
            rc=child.poll(); rec.update(status='INTERRUPTED_CHILD_REAPED' if rc is not None else 'INTERRUPTED_REAP_PENDING',
                returncode=rc,timed_out=False,ended_unix=time.time(),interrupted_error=f'{type(e).__name__}: {e}',cleanup_error=err)
            state['status']='FAIL_PRESERVED'; atomic(receipt,state); raise
        rec.update(status='CHILD_REAPED',returncode=rc,timed_out=timed_out,ended_unix=time.time(),reaped=True); atomic(receipt,state)
        log.flush(); os.fsync(log.fileno())
    rec.update(log_sha256=digest(log_path),log_size_bytes=Path(log_path).stat().st_size)
    if rc != 0 or timed_out:
        rec['status']='COMMAND_FAILED'; state['status']='FAIL_PRESERVED'; atomic(receipt,state)
        raise RuntimeError(f'{name} failed with actual child RC {rc}; see {log_path}')
    rec['status']='COMPLETE'; atomic(receipt,state)

def compiler_includes(text, cwd):
    found=[]
    for line in text.splitlines():
        if not re.search(r'(?:gfortran|Fortran)\b',line): continue
        tokens=line.split(); i=0
        while i < len(tokens):
            t=tokens[i]
            if t in ('-I','-J') and i+1 < len(tokens): found.append(tokens[i+1]); i+=1
            elif t.startswith(('-I','-J')) and len(t)>2: found.append(t[2:])
            i+=1
    return sorted({str((Path(p) if Path(p).is_absolute() else cwd/Path(p)).resolve()) for p in found})

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--install-prefix',type=Path,required=True); ap.add_argument('--output-dir',type=Path,required=True)
    ap.add_argument('--cmake',default=shutil.which('cmake'))
    ap.add_argument('--forbidden-root',type=Path,action='append',default=[],help='producer source/build tree forbidden in compiler -I/-J paths')
    ap.add_argument('--timeout-seconds',type=int,default=DEFAULT_TIMEOUT); a=ap.parse_args()
    prefix=a.install_prefix.resolve(); out=a.output_dir.resolve(); cmake=shutil.which(a.cmake) if a.cmake else None
    if cmake is None: raise SystemExit('cmake executable not found')
    if out.exists(): raise SystemExit(f'refusing existing output directory: {out}')
    if a.timeout_seconds <= 0: raise SystemExit('--timeout-seconds must be positive')
    pkg=prefix/'lib/cmake/WRF'; required_pkg=[pkg/'WRFConfig.cmake',pkg/'WRFConfigVersion.cmake',pkg/'WRFTargets.cmake']
    if any(not p.is_file() for p in required_pkg): raise SystemExit(f'incomplete installed WRF package: {required_pkg}')
    mods={'external/mo_rte_kind':prefix/'include/rte_rrtmgp/mo_rte_kind.mod',
          'external/mo_rte_util_array':prefix/'include/rte_rrtmgp/mo_rte_util_array.mod',
          'core/module_microphysics_driver':prefix/'modules/module_microphysics_driver.mod',
          'core/mo_rte_kind':prefix/'include/rte_rrtmgp/mo_rte_kind.mod'}
    if any(not p.is_file() for p in mods.values()): raise SystemExit(f'missing installed module files: {mods}')
    out.mkdir(parents=True); project_root=out/'consumer-sources'; project_root.mkdir()
    projects={k:project_root/('external-only' if k=='external' else 'core-plus-rte') for k in ('external','core')}
    for rel,content in CONSUMERS.items():
        path=project_root/rel; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(content)
    source_pins={str(p.relative_to(project_root)):{'size_bytes':p.stat().st_size,'sha256':digest(p)}
                 for p in sorted(project_root.rglob('*')) if p.is_file()}
    env=os.environ.copy(); env['CMAKE_PREFIX_PATH']=str(prefix); receipt=out/'execution.json'
    compiler=shutil.which('gfortran')
    state={'schema':'wrf-installed-cmake-consumers-v1','status':'RUNNING','install_prefix':str(prefix),
        'package_files':{str(p.relative_to(prefix)):{'size_bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(pkg.glob('*.cmake'))},
        'modules_preflight':{k:{'path':str(p),'size_bytes':p.stat().st_size,'sha256':digest(p)} for k,p in mods.items()},
        'consumer_source_pins':source_pins,'cmake':str(Path(cmake).resolve()),
        'cmake_sha256':digest(Path(cmake).resolve()),'compiler_path':compiler,
        'compiler_sha256':digest(Path(compiler).resolve()) if compiler else None,
        'environment':{'PATH':env.get('PATH'),'LD_LIBRARY_PATH':env.get('LD_LIBRARY_PATH'),'CMAKE_PREFIX_PATH':str(prefix)},
        'forbidden_roots':[str(p.resolve()) for p in a.forbidden_root],
        'timeout_seconds':a.timeout_seconds,'stages':[],'claims':['installed RRTMGP-only consumer','installed WRF Core plus RRTMGP consumer',
        'optional-array mirror only; no full microphysics_driver invocation']}
    atomic(receipt,state)
    if compiler is None: state.update(status='FAIL_PRESERVED',postflight_error='gfortran not found'); atomic(receipt,state); raise SystemExit('gfortran not found')
    stage(state,receipt,'cmake-version',[cmake,'--version'],out,env,out/'cmake-version.log',a.timeout_seconds)
    state['cmake_version']=(out/'cmake-version.log').read_text(errors='replace').splitlines()[0]; atomic(receipt,state)
    stage(state,receipt,'compiler-version',[compiler,'--version'],out,env,out/'compiler-version.log',a.timeout_seconds)
    state['compiler_version']=(out/'compiler-version.log').read_text(errors='replace').splitlines()[0]; atomic(receipt,state)
    exe_paths={}; logs={}
    for key,src in projects.items():
        build=out/f'{key}-build'
        stage(state,receipt,f'{key}-configure',[cmake,'-S',str(src),'-B',str(build),f'-DCMAKE_PREFIX_PATH={prefix}',f'-DCMAKE_Fortran_COMPILER={compiler}'],out,env,out/f'{key}-configure.log',a.timeout_seconds)
        stage(state,receipt,f'{key}-build',[cmake,'--build',str(build),'--verbose','--parallel','2'],out,env,out/f'{key}-build.log',a.timeout_seconds)
        logs[key]=out/f'{key}-build.log'
        targets=['external_consumer'] if key=='external' else ['core_consumer','optional_api_mirror']
        for target in targets:
            exe=build/target; exe_paths[f'{key}/{target}']=exe
            stage(state,receipt,f'{key}-{target}-run',[str(exe)],out,env,out/f'{key}-{target}.log',a.timeout_seconds)
    state['compiler_include_paths']={k:compiler_includes(p.read_text(errors='replace'),out/f'{k}-build') for k,p in logs.items()}
    for key,paths in state['compiler_include_paths'].items():
        need=[prefix/'include/rte_rrtmgp']+([prefix/'modules'] if key=='core' else [])
        missing=[str(p) for p in need if str(p.resolve()) not in paths]
        if missing: state.update(status='FAIL_PRESERVED',postflight_error={'missing_installed_include_paths':missing,'consumer':key,'paths':paths}); atomic(receipt,state); raise RuntimeError(f'{key}: required installed module include path absent')
        for forbidden in state['forbidden_roots']:
            if any(Path(p).is_relative_to(Path(forbidden)) for p in paths):
                state.update(status='FAIL_PRESERVED',postflight_error={'forbidden_include_root':forbidden,'consumer':key,'paths':paths}); atomic(receipt,state); raise RuntimeError(f'{key}: producer include path leaked')
    state['modules']={k:{'path':str(p),'size_bytes':p.stat().st_size,'sha256':digest(p)} for k,p in mods.items()}
    state['executables']={k:{'path':str(p),'size_bytes':p.stat().st_size,'sha256':digest(p)} for k,p in exe_paths.items()}
    state['stage_counts']={'commands':len(state['stages']),'configure':sum(s['name'].endswith('-configure') for s in state['stages']),
        'build':sum(s['name'].endswith('-build') for s in state['stages']),'consumer_runs':sum(s['name'].endswith('-run') for s in state['stages'])}
    state.update(status='PASS_INSTALLED_PACKAGE_CONSUMERS',ended_unix=time.time(),nonclaims=['No WRF model/physics execution.','Optional API mirror does not call microphysics_driver.'])
    atomic(receipt,state); return 0

if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print(f'FAILED_PRESERVED: {type(exc).__name__}: {exc}',file=sys.stderr); raise SystemExit(1)
