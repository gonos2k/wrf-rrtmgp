#!/usr/bin/env python3
"""Build a fresh reversible serial SCM snapshot and run the host join test."""
import argparse
import os
from pathlib import Path
import shutil
import sys
from test_netcdf_zz import Runner, write_json, pin

TOOLCHAIN = '''set(CMAKE_Fortran_COMPILER gfortran CACHE STRING "" FORCE)
set(CMAKE_C_COMPILER gcc CACHE STRING "" FORCE)
set(CMAKE_C_PREPROCESSOR /lib/cpp CACHE STRING "" FORCE)
set(CMAKE_C_PREPROCESSOR_FLAGS "" CACHE STRING "" FORCE)
set(CMAKE_Fortran_FLAGS_INIT "-w -fconvert=big-endian -frecord-marker=4")
set(CMAKE_C_FLAGS_INIT "-w -O3")
set(WRF_ARCH_LOCAL NONSTANDARD_SYSTEM_SUBR CACHE STRING "" FORCE)
set(WRF_M4_FLAGS -G CACHE STRING "" FORCE)
set(WRF_FCOPTIM "-O2 -ftree-vectorize -funroll-loops" CACHE STRING "" FORCE)
set(WRF_FCNOOPT -O0 CACHE STRING "" FORCE)
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('wrf',type=Path)
    p.add_argument('--workdir',type=Path,required=True)
    p.add_argument('--parallel',type=int,default=2)
    a=p.parse_args()
    if a.parallel<1:
        raise ValueError('positive parallel count required')
    source,work=a.wrf.resolve(),a.workdir.resolve()
    work.mkdir(exist_ok=False)
    env=os.environ.copy()
    for key in list(env):
        if key.startswith(('WRF_RRTMGP_','WRF_UDM_HOST_','OMP_','GOMP_','KMP_')):
            del env[key]
    runner=Runner(work,3600,env,5)
    toolchain=work/'gnu-serial.cmake'
    toolchain.write_text(TOOLCHAIN)
    scripts=Path(__file__).resolve().parent
    result={'status':'STARTING','toolchain':pin(toolchain),
            'scope':'fresh full WRF serial REAL32 snapshot plus actual manufactured host runtime',
            'production_accepted':False}
    write_json(work/'build-receipt.json',result)
    try:
        runner.run(['gfortran','--version'],work,'compiler-version')
        runner.run([sys.executable,str(scripts/'prepare_udm_connected_host.py'),str(source),
                    '--snapshot',str(work/'source/WRF')],work,'prepare-reversible-observer')
        runner.run(['cmake','-S',str(work/'source/WRF'),'-B',str(work/'producer'),
                    '-DCMAKE_TOOLCHAIN_FILE='+str(toolchain),'-DCMAKE_INSTALL_PREFIX='+str(work/'install'),
                    '-DWRF_CORE=ARW','-DWRF_CASE=EM_SCM_XY',
                    '-DUSE_ALLOCATABLES=ON','-DUSE_MPI=OFF','-DUSE_OPENMP=OFF','-DUSE_IPO=OFF',
                    '-DFORCE_NETCDF_CLASSIC=ON'],work,'configure')
        runner.run(['cmake','--build',str(work/'producer'),'--parallel',str(a.parallel)],work,'full-build')
        runner.run([sys.executable,str(scripts/'test_udm_connected_host.py'),
                    '--wrf-source',str(work/'source/WRF'),'--binary-dir',str(work/'producer/main'),
                    '--workdir',str(work/'runtime')],work,'connected-host-runtime')
        result.update(status='PASS_SCOPED_CONNECTED_HOST_BUILD_AND_RUNTIME',
                      executables={n:pin(work/'producer/main'/n) for n in ('ideal','wrf')})
    except BaseException as error:
        result.update(status='FAIL',error=repr(error))
        raise
    finally:
        result['commands']=runner.commands
        write_json(work/'build-receipt.json',result)


if __name__=='__main__':
    main()
