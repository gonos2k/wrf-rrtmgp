#!/usr/bin/env python3
"""Stage one historical-source experiment; no build or solver invocation."""
from pathlib import Path
import difflib, hashlib, json, subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = HERE / 'source'
OLD = SOURCE / 'examples/rfmip-clear-sky/rrtmgp_rfmip_sw.F90'
CURRENT = ROOT / 'build/udm37-rfmip-residual-next-diagnostic-v5/source-snapshot/rrtmgp_rfmip_sw.F90'
PIN = 'ed5b0113109fcd23a010a90c61f21bad551146ef'

def record(path):
    b = path.read_bytes()
    return {'path': str(path), 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Expected one anchor, got {text.count(old)}: {old[:80]!r}')
    return text.replace(old, new, 1)

def section(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]

def main():
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE, text=True).strip() != PIN:
        raise ValueError('Historical source commit changed')
    if subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], cwd=SOURCE, text=True).strip():
        raise ValueError('Historical tracked source is dirty')
    old = OLD.read_text()
    current = CURRENT.read_text()
    decl = section(current, '  ! Optional diagnostic-only state.', '  ! -------------------------------------------------------------------------------------------------\n  !\n  ! Code starts')
    startup = section(current, '  if(nargs >= 5) call get_command_argument', '  !\n  ! How big is the problem?')
    # This copied section ends with the original separator comments; those do
    # not change executable statements or the numerical source.
    modified = replace_once(old, '\nprogram rrtmgp_rfmip_sw\n', '\nprogram rrtmgp_rfmip_sw\n  use iso_fortran_env, only: int32\n')
    marker = '  ! -------------------------------------------------------------------------------------------------\n  !\n  ! Code starts'
    modified = replace_once(modified, marker, decl + marker)
    arg = '  if(nargs >= 4) then\n    call get_command_argument(4, forcing_index_char)\n  end if\n'
    modified = replace_once(modified, arg, arg + startup)
    capture_pre = section(current, '    if(audit_enabled) then\n      do icol = 1, block_size\n        audit_flat', '    ! Boundary conditions')
    modified = replace_once(modified, '                                       toa_flux))\n', '                                       toa_flux))\n' + capture_pre)
    capture_post = section(current, '    if(audit_enabled) then\n      do icol = 1, block_size\n        audit_flat', '    ! Boundary conditions')
    # Use the second capture block, after normalization, from its unique source-post write.
    pos = current.index('          write(audit_u_source_post)')
    begin = current.rfind('    if(audit_enabled) then', 0, pos)
    end = current.index('    !\n    ! Expand the spectrally-constant', pos)
    capture_post = current[begin:end]
    anchor = '    !\n    ! Expand the spectrally-constant'
    modified = replace_once(modified, anchor, capture_post + anchor)
    pos = current.index('          write(audit_u_flux_solver)')
    begin = current.rfind('    if(audit_enabled) then', 0, pos)
    end = current.index('    !\n    ! Zero out fluxes', pos)
    capture_solver = current[begin:end]
    modified = replace_once(modified, '                            fluxes))\n', '                            fluxes))\n' + capture_solver)
    pos = current.index('          write(audit_u_flux_written)')
    begin = current.rfind('    if(audit_enabled) then', 0, pos)
    end = current.index('\n  end do\n', pos) + 1
    capture_written = current[begin:end]
    # Preserve the old nighttime zeroing and add only observer writes after it.
    anchor = '    end do\n  end do\n  !\n  ! End timers'
    modified = replace_once(modified, anchor, '    end do\n' + capture_written + '  end do\n  !\n  ! End timers')
    close = section(current, '  if(audit_enabled) then\n    close(audit_u_source_pre)', '  !$acc exit data delete(optical_props')
    anchor = '  !$acc exit data delete(optical_props'
    modified = replace_once(modified, anchor, close + anchor)
    driver = HERE / 'rrtmgp_rfmip_sw_diag.F90'
    if driver.exists():
        raise FileExistsError('Refusing to replace existing diagnostic driver')
    driver.write_text(modified)
    patch = HERE / 'observer.patch'
    patch.write_text(''.join(difflib.unified_diff(old.splitlines(True), modified.splitlines(True), fromfile='official-v1.0/rrtmgp_rfmip_sw.F90', tofile='diagnostic-copy/rrtmgp_rfmip_sw_diag.F90')))
    tree = json.loads((ROOT / 'build/udm37-rfmip-historical-provenance-v1/v1.0-tree.json').read_text())
    source_records = []
    for row in tree['tree']:
        if row['type'] != 'blob' or row['path'].endswith('.nc'):
            continue
        path = SOURCE / row['path']
        if not path.is_file():
            raise ValueError(f'Missing source checkout file: {row["path"]}')
        data = path.read_bytes()
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if blob != row['sha']:
            raise ValueError(f'Official Git blob mismatch: {row["path"]}')
        source_records.append({**record(path), 'git_blob_sha1': blob})
    coeff = ROOT / 'build/udm37-rfmip-historical-provenance-v1/authentic-v1.0-sw-g224.nc'
    inp = ROOT / 'build/official-rrtmgp-reference/data/examples/rfmip-clear-sky/inputs/multiple_input4MIPs_radiation_RFMIP_UColorado-RFMIP-1-2_none.nc'
    if record(coeff)['sha256'] != 'b9f4b15796d132880fffb49ac45c29753c1ee70a8ee3fed733899cb315c75e9b':
        raise ValueError('Historical coefficient bytes changed')
    if record(inp)['sha256'] != 'b8dc05d7cd2e0e6354b4a6198771ddf3bc09f18d72b49f20a41e2024e2fd51f4':
        raise ValueError('RFMIP input bytes changed')
    plan = {'schema':'udm37-historical-source-experiment-v1', 'status':'STAGED_NOT_RUN',
            'source_commit':PIN, 'source_files':source_records,
            'pins':{'original_driver':record(OLD), 'diagnostic_driver':record(driver),
                    'observer_patch':record(patch), 'observer_predecessor':record(CURRENT),
                    'coefficient':record(coeff), 'input':record(inp),
                    'profile_selector':record(ROOT / 'build/udm37-rfmip-residual-next-diagnostic-v5/execution-v5/old_solar/profiles.txt'),
                    'failure_selector':record(ROOT / 'build/udm37-rfmip-residual-next-diagnostic-v4/failed_points.csv')},
            'build':{'compiler':'/usr/bin/gfortran','flags':['-O0','-ffree-line-length-none'],
                     'NetCDF_include':str(ROOT / 'build/deps/root/usr/include'),
                     'NetCDF_libraries':str(ROOT / 'build/deps/root/usr/lib/x86_64-linux-gnu')},
            'run':{'block_size':8,'forcing_index':1,'new_historical_solver_budget':1,
                   'all_profiles':1800,'captured_profiles':135,'SW_gpoints':224,
                   'strict_atol':1e-5,'strict_rtol':0,'output_flux_dtype':'float32'},
            'scope':'One isolated historical-source candidate with authenticated historical coefficient bytes. Original core/library/helper source is unchanged; diagnostic main adds observer I/O only. Not identified as the original CMIP6 generator; no WRF forecast or production change.'}
    (HERE / 'plan.json').write_text(json.dumps(plan,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':plan['status'],'source_files_exact_Git_blobs':len(source_records),'driver':record(driver)},sort_keys=True))

if __name__ == '__main__': main()
