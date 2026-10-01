#!/usr/bin/env python3
"""Full serial EM Registry and real clear-sky core tests; never a WRF forecast."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]

def execute(args, cwd, log):
    text = '+ ' + shlex.join(map(str, args)) + '\n'
    print(text, end='', flush=True)
    with log.open('a') as stream:
        stream.write(text); stream.flush()
        cp = subprocess.run(list(map(str,args)), cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    if cp.returncode:
        print(log.read_text()[-16000:], flush=True)
        raise RuntimeError(f'COMMAND_FAILED_{cp.returncode}: {args[0]}')

def verify_import(path):
    manifest = json.loads((ROOT / 'config/imported-sources.json').read_text())
    source = next(s for s in manifest['sources'] if s['path'] == path)
    count = 0
    for item in source['entries']:
        p = ROOT / path / item['path']
        if 'symlink' in item:
            if not p.is_symlink() or str(p.readlink()) != item['symlink']:
                raise ValueError('UPSTREAM_SYMLINK_MISMATCH: ' + str(p))
        else:
            if p.is_symlink() or not p.is_file() or p.stat().st_size != item['bytes']:
                raise ValueError('UPSTREAM_FILE_MISMATCH: ' + str(p))
            if hashlib.sha256(p.read_bytes()).hexdigest() != item['sha256']:
                raise ValueError('UPSTREAM_HASH_MISMATCH: ' + str(p))
        count += 1
    return {'commit': source['commit'], 'verified_entries': count, 'bytes': source['bytes']}

def registry(out, log):
    # Original Registry C main and all generators; communications stub is SERIAL.
    src = ROOT / 'WRF'
    for name in ('tools', 'Registry', 'inc'):
        shutil.copytree(src / name, out / name, symlinks=True)
    (out / 'frame').mkdir()
    (out / 'objects').mkdir()
    execute(['make','-C','tools','-B','registry','CC_TOOLS=gcc',
             'CC_TOOLS_CFLAGS=-O0 -g -fcommon -Wno-error=implicit-function-declaration'],out,log)
    execute([out/'tools/registry','-DEM_CORE=1','-DNMM_CORE=0','-DDA_CORE=0',
             '-DWRF_CHEM=0','-DNEW_BDYS',out/'Registry/Registry.EM'],out,log)
    required = ['frame/module_state_description.F','inc/scalar_indices.inc','inc/state_struct.inc',
                'inc/namelist_defines.inc','inc/wrf_bdyin.inc','inc/wrf_bdyout.inc']
    required += [f'inc/allocs_{i}.F' for i in range(32)]
    required += [f'inc/deallocs_{i}.F' for i in range(12)]
    for name in required:
        if not (out/name).is_file() or (out/name).stat().st_size == 0:
            raise ValueError('MISSING_GENERATED_FILE: ' + name)
    text = (out/'frame/module_state_description.F').read_text()
    for band in ('lw','sw'):
        for name, number in ((f'rrtmg_{band}scheme',4),(f'rrtmk_{band}scheme',14),
                             (f'rrtmg_{band}scheme_fast',24),(f'rrtmgp_{band}scheme',37)):
            if not re.search(r'\b'+name+r'\s*=\s*'+str(number)+r'\b',text,re.I):
                raise ValueError('GENERATED_CONSTANT_MISSING: ' + name)
    if 'REGISTRY ERROR' in log.read_text():
        raise ValueError('REGISTRY_REPORTED_ERROR')
    execute(['gfortran','-cpp','-ffree-form','-ffree-line-length-none','-I'+str(out/'inc'),
             '-c',out/'frame/module_state_description.F'],out/'objects',log)
    alloc='\n'.join((out/f'inc/allocs_{i}.F').read_text() for i in range(32))
    for field in ('swdnb','lwdnb','o3rad','ozmixm','aerod'):
        if 'grid%'+field not in alloc.lower(): raise ValueError('MISSING_ALLOCATION: '+field)
    generated = sorted(p for d in ('inc','frame') for p in (out/d).iterdir() if p.is_file())
    return {'scope':'FULL_OFFICIAL_SERIAL_EM_REGISTRY_AND_GENERATED_CONSTANT_MODULE',
            'generated_or_copied_inc_frame_files':len(generated),
            'required_generated_files':len(required),
            'allocation_subroutines_generated':32,'deallocation_subroutines_generated':12,
            'wrf_executable_built':False,'mpi_generator_used':False}

def core(out,log):
    provenance={p:verify_import(p) for p in ('external/rte-rrtmgp','external/rrtmgp-data')}
    shutil.copytree(ROOT/'external/rte-rrtmgp',out/'core',symlinks=True)
    work=out/'adapter';work.mkdir()
    flags=['-O0','-g','-ffree-line-length-none','-fcheck=bounds','-fbacktrace','-frecursive','-DRTE_USE_DP']
    execute(['make','-j2','libs','FC=gfortran','FCFLAGS='+shlex.join(flags)],out/'core',log)
    for name in ('librte.a','librrtmgp.a'):
        if not (out/'core/build'/name).is_file(): raise ValueError('MISSING_REAL_LIBRARY: '+name)
    cflags=shlex.split(subprocess.check_output(['nc-config','--cflags'],text=True))
    libs=shlex.split(subprocess.check_output(['nc-config','--libs'],text=True))
    execute(['gcc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',*cflags,
             '-c',ROOT/'port/src/rrtmgp37_netcdf.c','-o','nc_bridge.o'],work,log)
    names=['rrtmgp37_netcdf','rrtmgp37_coefficients','rrtmgp37_contract','rrtmgp37_host_bridge',
           'rrtmgp37_core_loader','rrtmgp37_clear_backend']
    sources=[ROOT/'port'/('integration' if name in names[-2:] else 'src')/(name+'.F90') for name in names]
    includes=['-I'+str(out/'core/build')]
    execute(['gfortran',*flags,*includes,'-c',*sources],work,log)
    objects=['nc_bridge.o']+[name+'.o' for name in names]
    execute(['gfortran',*flags,*includes,ROOT/'port/integration/test_real_clear_backend.F90',*objects,
             '-L'+str(out/'core/build'),'-lrrtmgp','-lrte',*libs,'-o','test_real_clear_backend'],work,log)
    execute([work/'test_real_clear_backend', ROOT/'external/rrtmgp-data/rrtmgp-gas-lw-g128.nc',
             ROOT/'external/rrtmgp-data/rrtmgp-gas-sw-g112.nc'],work,log)
    text=log.read_text()
    if 'REAL_CORE_SYNTHETIC_COLUMN_ASSERTIONS_PASS=' not in text:
        raise ValueError('MISSING_REAL_CORE_SUCCESS_MARKER')
    return {'scope':'REAL_PINNED_RRTMGP_COEFFICIENTS_SYNTHETIC_CLEAR_COLUMNS',
            'sources':provenance,'wrf_executable_built':False,'cloud_aerosol_tested':False,
            'result_lines':[line for line in text.splitlines() if 'PASS' in line or 'residual' in line or 'CO2' in line]}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind',choices=['registry','core'])
    args=parser.parse_args()
    out=ROOT/'build'/args.kind
    if out.exists():raise ValueError('REFUSING_EXISTING_BUILD_DIRECTORY: '+str(out))
    out.mkdir(parents=True)
    log=out/'run.log'
    record={'status':'RUNNING','kind':args.kind,'start_unix':time.time(),'backend_enabled_in_wrf':False}
    try:
        record.update((registry if args.kind=='registry' else core)(out,log))
        record['status']='PASS'
    except Exception as exc:
        record.update(status='FAIL',error=str(exc))
        raise
    finally:
        record['end_unix']=time.time()
        (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
        print(json.dumps(record,indent=2),flush=True)

if __name__=='__main__':main()
