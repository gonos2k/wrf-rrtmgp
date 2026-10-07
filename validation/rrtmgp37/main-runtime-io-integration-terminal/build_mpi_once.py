from pathlib import Path
import importlib.util, json, os, shutil, subprocess

BASE=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
SOURCE=BASE/'build/udm37-main-runtime-io-mpi-source-v1'
OUT=BASE/'build/udm37-main-runtime-io-mpi-build-v1'
HEAD='dd7eb1da3a23ca8f21bd4d5bf82f7feecf813fc5'
HELPER=SOURCE/'WRF/test/rrtmgp/test_netcdf_zz.py'
spec=importlib.util.spec_from_file_location('runner',HELPER)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def git(*args): return subprocess.check_output(['git',*args],cwd=SOURCE,text=True).strip()
if OUT.exists(): raise RuntimeError('one-use MPI build output exists')
if git('rev-parse','HEAD') != HEAD or git('status','--porcelain','--untracked-files=no'):
    raise RuntimeError('source is not the clean frozen PR146 head')
OUT.mkdir()
old=BASE/'build/udm37-netcdf-zz-mpi-build-v1/wrf_gnu_mpi_openmp.cmake'
tool=OUT/'wrf_gnu_mpi_openmp.cmake'
shutil.copyfile(old,tool)
mpi=BASE/'build/deps/mpich-sock';netcdf=BASE/'build/deps/netcdf'
env=dict(os.environ)
env.update(PATH=str(mpi/'bin')+':'+str(netcdf/'bin')+':'+env['PATH'],NETCDF=str(netcdf),NETCDF_C=str(netcdf),NETCDF_classic='1',LD_LIBRARY_PATH=str(netcdf/'lib')+':'+str(BASE/'build/deps/root/usr/lib/x86_64-linux-gnu')+':'+str(mpi/'lib')+':'+env.get('LD_LIBRARY_PATH',''),LC_ALL='C',PYTHONDONTWRITEBYTECODE='1')
cmake='/usr/local/bin/cmake';build=OUT/'cmake';install=OUT/'install'
steps=[('configure',[cmake,'-S',str(SOURCE/'WRF'),'-B',str(build),'-DCMAKE_INSTALL_PREFIX='+str(install),'-DCMAKE_TOOLCHAIN_FILE='+str(tool),'-DWRF_CORE=ARW','-DWRF_CASE=EM_REAL','-DUSE_ALLOCATABLES=ON','-DUSE_MPI=ON','-DUSE_OPENMP=ON','-DUSE_IPO=OFF','-DFORCE_NETCDF_CLASSIC=ON']),('build',[cmake,'--build',str(build),'--parallel','4']),('install',[cmake,'--install',str(build)])]
source_pins=[m.pin(SOURCE/n) for n in ('WRF/external/io_netcdf/wrf_io.F90','WRF/frame/module_io.F','WRF/tools/gen_allocs.c','WRF/phys/module_mp_udm.F','WRF/CMakeLists.txt','WRF/test/rrtmgp/test_netcdf_zz.py')]
tool_pins=[m.pin(p) for p in (old,tool,'/usr/bin/gfortran-13','/usr/bin/gcc-13',cmake,mpi/'bin/mpif90',mpi/'bin/mpicc',netcdf/'bin/nf-config',__file__)]
plan={'schema':'UDM37_MAIN_RUNTIME_IO_MPI_BUILD_V1','source_head':HEAD,'source_tree':git('rev-parse','HEAD^{tree}'),'source_pins':source_pins,'tool_pins':tool_pins,'commands':steps,'model_calls':0,'maximum_children':3,'timeout_per_child_seconds':1800,'runtime_target':{'mpi':4,'openmp':2},'physical_accepted':False}
m.write_json(OUT/'plan.json',plan)
r=m.Runner(OUT,1800,env,3)
try:
    for name,argv in steps:
        r.run(argv,SOURCE,name)
        print(name+': RC0',flush=True)
    if git('rev-parse','HEAD') != HEAD or git('status','--porcelain','--untracked-files=no'):
        raise RuntimeError('source changed during build')
    if source_pins != [m.pin(q['path']) for q in source_pins] or tool_pins != [m.pin(q['path']) for q in tool_pins]:
        raise RuntimeError('pinned source/tool changed during build')
    result={'status':'PASS_BUILD_INSTALL_SCOPED','source_head':HEAD,'source_tree':plan['source_tree'],'commands':r.commands,'models':0,'executables':{n:m.pin(install/'bin'/n) for n in ('real','wrf')},'source_and_tool_pins_unchanged':True,'physical_accepted':False}
    m.write_json(OUT/'result.json',result)
except BaseException as error:
    m.write_json(OUT/'result.json',{'status':'FAIL_BUILD_INSTALL_PRESERVED','error':repr(error),'commands':r.commands,'source_head':HEAD,'models':0,'physical_accepted':False})
    raise
