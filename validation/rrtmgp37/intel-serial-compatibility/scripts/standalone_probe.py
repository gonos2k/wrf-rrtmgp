#!/usr/bin/env python3
import hashlib,json,os,pathlib,subprocess,time
ROOT=pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
SRC=ROOT/'build/udm-workspace-selected-work'
OUT=ROOT/'build/udm-intel-feasibility'
BUILD=OUT/'standalone'
inventory=json.loads((OUT/'inventory-probe-receipt.json').read_text())
env=os.environ.copy();env.update(inventory['controlled_environment'])
for key in list(env):
 if key.startswith('WRF_RRTMGP_') or key=='WRF_UDM_BOUNDARY_CAPTURE': env.pop(key)
steps=[]
def run(argv):
 t=time.time()
 with (OUT/f'standalone-{len(steps)+1}.log').open('w') as f:
  p=subprocess.run(argv,env=env,cwd=OUT,stdout=f,stderr=subprocess.STDOUT,timeout=360)
 steps.append(dict(argv=argv,returncode=p.returncode,elapsed_s=time.time()-t,log=str(OUT/f'standalone-{len(steps)+1}.log')))
 (OUT/'standalone-probe-receipt.json').write_text(json.dumps(dict(steps=steps,controlled_environment=inventory['controlled_environment']),indent=2)+'\n')
 print('step',len(steps),'returncode',p.returncode,flush=True)
 return p.returncode
comp='/NHNHOME/WORKSPACE/26weather002_A/Library/intel/oneapi/compiler/2025.3/bin/ifx'
nc='/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS'
files=['WRF/phys/module_ra_rrtmgp.F','WRF/phys/module_ra_rrtmg_lw.F','WRF/phys/module_ra_rrtmg_sw.F','WRF/test/rrtmgp/CMakeLists.txt','WRF/external/rte_rrtmgp/CMakeLists.txt']
before={f:hashlib.sha256((SRC/f).read_bytes()).hexdigest() for f in files}
assert run(['cmake','-S',str(SRC/'WRF/test/rrtmgp'),'-B',str(BUILD),'-G','Ninja','-DCMAKE_Fortran_COMPILER='+comp,'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_Fortran_FLAGS=-fp-model precise -convert big_endian','-DNETCDF_INCLUDE_DIR='+nc+'/include','-DNETCDF_LIBRARY_DIR='+nc+'/lib','-DRRTMGP_DATA_DIR='+str(SRC/'WRF/run'),'-DFROZEN_TABLE='+str(SRC/'validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc'),'-DRRTMGP_TEST_OPENMP=ON'])==0
assert run(['cmake','--build',str(BUILD),'--target','test_rrtmgp_workspace','test_rrtmgp_hash','test_rrtmgp_columns','test_rrtmgp_sw_predelta_direct','test_rrtmgp_openmp','test_rrtmgp_frozen_openmp','--parallel','12'])==0
regex='^(workspace_.*|wrf_rrtmgp_columns|sw_predelta_direct_(clear|cloud|overlap_zero|night)|frozen_file_sha256|cpu_openmp_reentrancy|frozen_openmp_queries)$'
status=run(['ctest','--test-dir',str(BUILD),'-R',regex,'--output-on-failure'])
after={f:hashlib.sha256((SRC/f).read_bytes()).hexdigest() for f in files}
dependencies_post={p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in inventory['dependencies']}
receipt=dict(steps=steps,controlled_environment=inventory['controlled_environment'],production_base='6f0f3ea3e73fbd43325fdad1050b000eecd70138',test_cmake_includes_reviewed_default_path_reorder=True,source_hashes_before=before,source_hashes_after=after,source_unchanged=before==after,dependency_hashes_after=dependencies_post,dependencies_unchanged=all(h==inventory['dependencies'][p]['sha256'] for p,h in dependencies_post.items()),tests_pass=status==0)
(OUT/'standalone-probe-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('tests_pass',status==0,flush=True)
