#!/usr/bin/env python3
"""Inventory installed tools and run bounded compiler/NetCDF scratch probes."""
import hashlib, json, os, pathlib, shlex, shutil, subprocess, time
ROOT = pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
SRC = ROOT/'build/udm-workspace-selected-work'
OUT = ROOT/'build/udm-intel-feasibility'
LIB = pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/Library')
COMP = LIB/'intel/oneapi/compiler/2025.3'
MPI = LIB/'intel/oneapi/mpi/2021.17'
NC = LIB/'WRF_LIBS'
OUT.mkdir(exist_ok=True)
env = os.environ.copy()
controlled = {
 'PATH': str(COMP/'bin')+':'+str(NC/'bin')+':'+os.environ['PATH'],
 'LD_LIBRARY_PATH': str(NC/'lib')+':'+str(COMP/'lib')+':'+str(MPI/'lib')+':/usr/lib/x86_64-linux-gnu',
 'LIBRARY_PATH': str(NC/'lib')+':'+str(COMP/'lib'),
 'NETCDF': str(NC), 'NETCDF_C': str(NC), 'I_MPI_ROOT': str(MPI),
 'OMP_NUM_THREADS':'1', 'OMP_DYNAMIC':'FALSE', 'OMP_STACKSIZE':'64M',
}
env.update(controlled)
for key in list(env):
 if key.startswith('WRF_RRTMGP_') or key == 'WRF_UDM_BOUNDARY_CAPTURE': env.pop(key)
commands=[]
def run(argv, cwd=OUT, input_text=None, use_env=env):
 t=time.time(); p=subprocess.run(argv,cwd=cwd,env=use_env,input=input_text,text=True,capture_output=True,timeout=120)
 commands.append(dict(argv=list(map(str,argv)),cwd=str(cwd),returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,elapsed_s=time.time()-t))
 return p
def sha(p):
 return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
commit=run(['git','rev-parse','HEAD'],SRC).stdout.strip()
assert commit=='6f0f3ea3e73fbd43325fdad1050b000eecd70138',commit
assert not run(['git','status','--porcelain'],SRC).stdout
names={'ifx','ifort','icx','icc','modulecmd','lmod'}
search_roots=['/opt','/usr/local','/usr/bin','/home/korea_keun/intel','/home/korea_keun/.local',str(LIB/'intel')]
found=[]
for root in search_roots:
 if not pathlib.Path(root).exists(): continue
 for directory, dirs, files in os.walk(root,followlinks=False):
  dirs[:]=[d for d in dirs if d not in {'site-packages','__pycache__','.git','node_modules','doc','docs','examples','share'}]
  for name in sorted(names.intersection(files)):
   path=pathlib.Path(directory)/name
   found.append(dict(path=str(path),executable=os.access(path,os.X_OK),resolved=str(path.resolve())))
module_locations=['/usr/share/Modules','/etc/profile.d/modules.sh','/usr/share/lmod','/etc/modulefiles','/usr/share/modulefiles','/opt/intel']
for a in ([str(COMP/'bin/ifx'),'--version'],[str(COMP/'bin/icx'),'--version'],['cmake','--version'],['ninja','--version'],['gfortran','--version'],[str(NC/'bin/nf-config'),'--all'],[str(NC/'bin/nc-config'),'--all'],[str(MPI/'bin/mpiifx'),'-show']): run(a)
libraries=[NC/'lib/libnetcdff.so',NC/'lib/libnetcdf.so',MPI/'lib/libmpi.so',COMP/'bin/ifx']
for p in libraries: run(['ldd',str(p)])
tracked=run(['git','ls-files','-z'],SRC).stdout.split('\0')
entries={x:sha(SRC/x) for x in tracked if x and (SRC/x).is_file()}
source_manifest_sha=hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(',',':')).encode()).hexdigest()
dep_paths=[COMP/'bin/ifx',COMP/'bin/icx',NC/'bin/nf-config',NC/'bin/nc-config',NC/'include/netcdf.mod',NC/'include/netcdf.inc',NC/'lib/libnetcdff.so',NC/'lib/libnetcdf.so',NC/'lib/libhdf5.so',NC/'lib/libhdf5_hl.so',NC/'lib/libz.so',COMP/'lib/libimf.so',COMP/'lib/libifport.so',COMP/'lib/libifcoremt.so',COMP/'lib/libsvml.so',COMP/'lib/libintlc.so',COMP/'lib/libirng.so',COMP/'lib/libiomp5.so',MPI/'bin/mpiifx',MPI/'include/mpi/mpi.mod',MPI/'lib/libmpi.so',MPI/'lib/libmpifort.so']
dependencies={str(p):dict(resolved=str(p.resolve()),sha256=sha(p)) for p in dep_paths if p.is_file()}
source='''program netcdf_probe
  use netcdf
  implicit none
  integer :: fid, did, vid, status
  real(8) :: values(3) = [1.25d0, -2.5d0, 3.75d0], got(3)
  call check(nf90_create('probe.nc', ior(nf90_clobber,nf90_netcdf4), fid))
  call check(nf90_def_dim(fid, 'x', 3, did))
  call check(nf90_def_var(fid, 'x', nf90_double, [did], vid))
  call check(nf90_enddef(fid))
  call check(nf90_put_var(fid, vid, values))
  call check(nf90_close(fid))
  call check(nf90_open('probe.nc', nf90_nowrite, fid))
  call check(nf90_inq_varid(fid, 'x', vid))
  call check(nf90_get_var(fid, vid, got))
  call check(nf90_close(fid))
  if (any(got /= values)) error stop 'round trip mismatch'
  print *, 'NETCDF_USE_CREATE_READ_PASS ', trim(nf90_inq_libvers())
contains
  subroutine check(code)
    integer, intent(in) :: code
    if (code /= nf90_noerr) then
      print *, trim(nf90_strerror(code))
      error stop 1
    end if
  end subroutine
end program
'''
(OUT/'netcdf_probe.f90').write_text(source)
flags=['-O0','-fp-model','precise','-convert','big_endian','-real-size','32','-i4','-I'+str(NC/'include')]
flibs=shlex.split(run([str(NC/'bin/nf-config'),'--flibs']).stdout)
compile=run([str(COMP/'bin/ifx'),*flags,'netcdf_probe.f90',*flibs,'-o','netcdf_probe'])
probe=run([str(OUT/'netcdf_probe')]) if compile.returncode==0 else None
if compile.returncode==0: run(['ldd',str(OUT/'netcdf_probe')])
post={p:sha(p) for p in dependencies}
unchanged=all(post[p]==v['sha256'] for p,v in dependencies.items())
source_unchanged=all(sha(SRC/p)==h for p,h in entries.items())
objects=run(['make','-s','-C',str(SRC/'WRF/external/rte_rrtmgp/build'),'print-wrf-objects']).stdout.splitlines()
vendor=SRC/'WRF/external/rte_rrtmgp'
glob_sources=sorted(str(p.relative_to(vendor)) for d in ['rte-frontend','rte-kernels','gas-optics','rrtmgp-frontend','rrtmgp-kernels','extensions'] for p in (vendor/d).glob('*.F90'))
cmake_basenames=sorted(pathlib.Path(p).stem+'.o' for p in glob_sources)
result=dict(commit=commit,controlled_environment=controlled,path_inventory={n:shutil.which(n) for n in sorted(names|{'cmake','ninja','gfortran','module'})},search_roots=search_roots,compiler_matches=found,module_locations={p:pathlib.Path(p).exists() for p in module_locations},module_env={k:os.environ.get(k) for k in ['MODULEPATH','LOADEDMODULES','INTEL_ONEAPI_ROOT','ONEAPI_ROOT','I_MPI_ROOT','CMPLR_ROOT','LMOD_CMD']},broken_library_mpi_alias=dict(path=str(LIB/'2021.17'),symlink=os.path.islink(LIB/'2021.17'),exists=(LIB/'2021.17').exists(),resolved=str((LIB/'2021.17').resolve())),source_manifest=dict(entries=entries,canonical_sha256=source_manifest_sha),dependencies=dependencies,dependencies_post_sha256=post,dependencies_unchanged=unchanged,source_unchanged=source_unchanged,netcdf_probe=dict(compile_pass=compile.returncode==0,run_pass=probe is not None and probe.returncode==0,source_sha256=sha(OUT/'netcdf_probe.f90'),exe_sha256=sha(OUT/'netcdf_probe') if compile.returncode==0 else None),vendor_make_objects=objects,vendor_cmake_sources=glob_sources,vendor_same_object_basenames=sorted(objects)==cmake_basenames,commands=commands)
(OUT/'inventory-probe-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ['commit','dependencies_unchanged','source_unchanged','netcdf_probe','vendor_same_object_basenames']},indent=2))
