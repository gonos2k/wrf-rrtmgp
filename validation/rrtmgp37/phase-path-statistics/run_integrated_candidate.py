"""Run a bounded, immutable-input workspace candidate and compare all NetCDF data."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,resource,shutil,subprocess,time
import numpy as np
from netCDF4 import Dataset
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
TASK=ROOT/'build/udm-phase-path-statistics-real-wrf'
spec=importlib.util.spec_from_file_location('runner',ROOT/'build/udm-selected-real-audit/run_selected_column_audit.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
runner.SOURCE_MANIFEST_REL=Path('build/udm-phase-path-statistics-real-wrf/source-manifest.json')
runner.BUILD_RECEIPT_REL=Path('build/udm-phase-path-statistics-real-wrf/build-receipt.json')
def sha(p):return runner.sha256(p)
def write(p,o):p.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n')
def attrbytes(v):
 a=np.asarray(v)
 if a.dtype.kind=='O':return (str(a.dtype),a.shape,repr(v))
 return (str(a.dtype),a.shape,a.tobytes())
def compare(baseline,candidate):
 bf={p.name:p for p in baseline.glob('wrfout_d01_*')};cf={p.name:p for p in candidate.glob('wrfout_d01_*')}
 if set(bf)!=set(cf):raise RuntimeError('history filenames differ')
 reports=[];failures=[]
 for name in sorted(bf):
  rec={'file':name,'baseline_sha256':sha(bf[name]),'candidate_sha256':sha(cf[name]),'variables':0,'attributes':0,'differences':[]}
  with Dataset(bf[name]) as a,Dataset(cf[name]) as b:
   a.set_auto_maskandscale(False);b.set_auto_maskandscale(False)
   if {(n,len(d),d.isunlimited()) for n,d in a.dimensions.items()}!={(n,len(d),d.isunlimited()) for n,d in b.dimensions.items()}:rec['differences'].append('dimensions')
   if set(a.variables)!=set(b.variables):rec['differences'].append('variable names')
   for label,x,y in [('global',a,b)]+[(n,a[n],b[n]) for n in sorted(set(a.variables)&set(b.variables))]:
    if set(x.ncattrs())!=set(y.ncattrs()):rec['differences'].append(label+':attribute names')
    for k in sorted(set(x.ncattrs())&set(y.ncattrs())):
     rec['attributes']+=1
     if attrbytes(x.getncattr(k))!=attrbytes(y.getncattr(k)):rec['differences'].append(label+':attribute:'+k)
    if label!='global':
     rec['variables']+=1
     if x.dtype!=y.dtype or x.dimensions!=y.dimensions or x.shape!=y.shape:rec['differences'].append(label+':layout');continue
     # Every variable, including character Times and floating NaN payloads.
     if np.asarray(x[:]).tobytes()!=np.asarray(y[:]).tobytes():rec['differences'].append(label+':data bits')
  reports.append(rec)
  failures.extend([name+':'+s for s in rec['differences']])
 return {'status':'BITWISE_PASS' if not failures else 'DIFFERENCES','history_files':reports,'differences':failures}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--phase',choices=['ra37','ra4'],required=True);ap.add_argument('--timeout',type=int,default=3600);a=ap.parse_args()
 baseline=ROOT/('build/udm-workspace-real-runtime/ra37-candidate/run' if a.phase=='ra37' else 'build/udm-workspace-real-runtime/ra4-candidate/run')
 out=ROOT/'build/udm-phase-path-statistics-real-runtime'/(a.phase+'-candidate');target=out/'run'
 if out.exists():raise RuntimeError('fresh output required')
 source=TASK/'source';exe=source/'WRF/main/wrf.exe'
 manifest_sha,pre_source=runner.verify_build_manifest(ROOT,source,exe)
 target.mkdir(parents=True)
 for p in sorted(baseline.iterdir()):
  if p.is_file() and (not runner.MUTABLE_RE.match(p.name) or p.name=='wrfrst_d01_2010-06-11_12:00:00') and p.name not in {'wrf.exe','real.exe'}:
   shutil.copy2(p,target/p.name)
 shutil.copy2(exe,target/'wrf.exe')
 pre=runner.immutable_tree_hashes(target)
 checkpoint='wrfrst_d01_2010-06-11_12:00:00'
 restart_pre=sha(target/checkpoint)
 if restart_pre!=sha(baseline/checkpoint):raise RuntimeError('restart input differs')
 if pre!=runner.immutable_tree_hashes(baseline):raise RuntimeError('candidate inputs differ from baseline')
 # Hash assets selected by absolute namelist paths as well as run-tree copies.
 external={str(p):sha(p) for p in sorted((ROOT/'build/udm-selected-real-wrf/source/WRF/run').glob('rrtmgp-*.nc'))}
 table=ROOT/'build/pr-wrf-rrtmgp/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc'
 external[str(table)]=sha(table)
 baseline_histories={p.name:sha(p) for p in sorted(baseline.glob('wrfout_d01_*'))}
 receipt={'status':'RUNNING','phase':a.phase,'baseline_run':str(baseline),'run':str(target),'source_manifest_sha256':manifest_sha,'source_before':pre_source,'executable_sha256':sha(exe),'copied_executable_sha256':sha(target/'wrf.exe'),'inputs_before':pre,'restart_before_sha256':restart_pre,'external_assets_before':external,'namelist_sha256':sha(target/'namelist.input'),'launcher_sha256':sha(Path(__file__)),'baseline_histories_before':baseline_histories}
 write(out/'receipt.json',receipt)
 try:
  env={k:v for k,v in os.environ.items() if not k.startswith(('WRF_RRTMGP_','WRF_UDM_BOUNDARY_CAPTURE'))}
  env.update(OMP_NUM_THREADS='1',OMP_DYNAMIC='FALSE',OMP_STACKSIZE='512M',OPENBLAS_NUM_THREADS='1')
  env['LD_LIBRARY_PATH']=str(ROOT/'build/deps/netcdf/lib')+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
  receipt['runtime_environment']={k:env[k] for k in ('OMP_NUM_THREADS','OMP_DYNAMIC','OMP_STACKSIZE','OPENBLAS_NUM_THREADS','LD_LIBRARY_PATH')}
  receipt['diagnostics_environment_cleared']=not any(k.startswith(('WRF_RRTMGP_','WRF_UDM_BOUNDARY_CAPTURE')) for k in env)
  receipt['stack_limit_bytes']=resource.getrlimit(resource.RLIMIT_STACK)
  started=time.monotonic();log=target/'wrf.stdout.log'
  with log.open('wb') as f:proc=subprocess.run([str(target/'wrf.exe')],cwd=target,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=a.timeout)
  receipt.update(returncode=proc.returncode,elapsed_seconds=time.monotonic()-started,log_sha256=sha(log))
  success='SUCCESS COMPLETE WRF' in log.read_text(errors='replace') or any('SUCCESS COMPLETE WRF' in p.read_text(errors='replace') for p in target.glob('rsl.error.*'))
  receipt['success_marker']=success
  if proc.returncode or not success:raise RuntimeError('candidate WRF failed')
  post_sha,post_info=runner.verify_build_manifest(ROOT,source,exe)
  post=runner.immutable_tree_hashes(target);restart_post=sha(target/checkpoint);external_post={p:sha(Path(p)) for p in external}
  receipt.update(source_after=post_info,inputs_after=post,restart_after_sha256=restart_post,external_assets_after=external_post,copied_executable_after_sha256=sha(target/'wrf.exe'))
  if post_sha!=manifest_sha or restart_post!=restart_pre or post!=pre or external_post!=external or sha(target/'wrf.exe')!=receipt['executable_sha256']:raise RuntimeError('source/executable/input/assets changed')
  if baseline_histories!={p.name:sha(p) for p in sorted(baseline.glob('wrfout_d01_*'))}:raise RuntimeError('baseline histories changed')
  comparison=compare(baseline,target);write(out/'comparison.json',comparison)
  
  diag=[]
  for logpath in [log,*sorted(target.glob('rsl.error.*'))]:
   if logpath.is_file():
    for line in logpath.read_text(errors='replace').splitlines():
     if 'RRTMGP_UDM_CF0_OMITTED' in line or 'RRTMGP_UDM_LUT_CLIP' in line:
      diag.append(line.strip())
  receipt['phase_path_diagnostics']=diag
  receipt.update(status='COMPLETE_BITWISE_PASS' if comparison['status']=='BITWISE_PASS' else 'COMPLETE_DIFFERENCES',comparison_sha256=sha(out/'comparison.json'),comparison_status=comparison['status'])
 except Exception as e:receipt.update(status='FAIL',error=repr(e))
 write(out/'receipt.json',receipt);print(receipt['status'],out/'receipt.json')
 return 0 if receipt['status']=='COMPLETE_BITWISE_PASS' else 1
if __name__=='__main__':raise SystemExit(main())
