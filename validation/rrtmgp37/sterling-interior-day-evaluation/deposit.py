"""Deposit actual completed run/extraction; never rerun a model or overwrite old scores."""
from pathlib import Path
import json,hashlib,tarfile,io,gzip
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent

def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
def main():
 payload={};run=B/'udm37-sterling-interior-day-v1';extract=B/'udm37-sterling-interior-day-extract-v1';assert json.loads((run/'receipt.json').read_text())['status']=='SUCCESS'
 for d,key in [(run,'run'),(extract,'extract'),(B/'udm37-sterling-interior-components-v1','diagnostic')]:
  for pat in ['receipt.json','command-*.*','*.json','host/namelist.input','host/namelist.output','host/radiation_iofields.txt']:
   for p in d.glob(pat):
    if p.is_file():payload[key+'/'+str(p.relative_to(d))]=p.read_bytes()
 for src,key in [('udm37-sterling-interior-input-contrast-v2/input-contrast.json','input-contrast.json'),('udm37-sterling-interior-input-contrast-v1.log','development/input-contrast-v1.log'),('udm37-sterling-interior-input-contrast-v1/compare_inputs.py','development/input-contrast-v1.py'),('udm37-sterling-interior-real-v1/forecast.namelist.input','prepared-forecast.namelist'),('udm37-vapor-corrected-public-v2/receipt.json','public-baseline-receipt.json')]:payload[key]=(B/src).read_bytes()
 payload['development/phase-count-v1.log']=(B/'udm37-sterling-interior-day-finish-v1-failed.log').read_bytes();payload['development/analyze-phase-count-v1.py']=(extract/'analyze-phase-count-v1.py').read_bytes();payload['development/finish-phase-count-v1.py']=(extract/'finish-phase-count-v1.py').read_bytes();payload['development/empty-aux-header-snapshot.nc']=(B/'udm37-sterling-aux-header-diagnostic.nc').read_bytes();payload['development/executed-run.py']=(run/'executed-run.py').read_bytes();payload['development/original-plan.json']=(run/'original-plan.json').read_bytes();payload['diagnostic/history-comparison.json']=(B/'udm37-sterling-interior-components-comparison.json').read_bytes();payload['plan.json']=(P/'plan.json').read_bytes();buf=io.BytesIO();files={}
 with tarfile.open(fileobj=buf,mode='w') as t:
  for n,b in sorted(payload.items()):
   x=tarfile.TarInfo(n);x.mtime=0;x.size=len(b);t.addfile(x,io.BytesIO(b));files[n]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
 (P/'saved').mkdir(exist_ok=True);file=P/'saved/evidence.tar.gz';file.write_bytes(gzip.compress(buf.getvalue(),mtime=0))
 deps=['validation/rrtmgp37/'+n for n in ['sterling-boundary-forcing-decision/identity.json','sterling-boundary-forcing-decision/input-use-decision.json','real-output-independent-comparison/analyze.py','real-output-independent-comparison/result.json','real-output-independent-comparison/identity.json','sterling-cloud-radiation-attribution/result.json','research-policy-contract/closure-conditions.json','solrad-boundary-site-48h/raw/ste16280.dat','solrad-boundary-site-48h/raw/ste16281.dat']]
 sources=['WRF/frame/module_domain.F','WRF/phys/module_ra_rrtmg_lw.F','validation/rrtmgp37/vapor-first-operation/compare_history.py','WRF/phys/module_ra_rrtmg_sw.F','WRF/phys/module_radiation_driver.F','WRF/dyn_em/module_first_rk_step_part1.F','WRF/share/module_model_constants.F','WRF/test/rrtmgp/test_netcdf_zz.py']+[str(p.relative_to(R)) for p in P.glob('*') if p.suffix=='.py' and p.name!='deposit.py']
 coeffs=[R/'WRF/run'/n for n in json.loads((run/'receipt.json').read_text())['coefficient_files']]+[R/'validation/rrtmgp37/frozen-planck-coverage/expanded/frozen-ice-psd-moments.nc']
 ident={'base_main':'eef6e4a593e886162af1e0ff786928dc18b5bbda','base_tree':'448c3229895270f9969b15ba1d34cd62311b50f5','archive':pin(file),'files':files,'dependencies':{n:pin(R/n) for n in deps},'current_sources':{n:pin(R/n) for n in sources},'coefficient_repo_files':{str(p.relative_to(R)):pin(p) for p in coeffs},'outputs':{n:pin(P/n) for n in ['result.json','hourly-comparison.csv','sterling-interior-day-sw.png']},'new_actual_WRF_processes':2,'cold24h_processes':1,'bounded_diagnostic_restart_processes':1,'new_build_WPS_REAL_Mie_RTE_processes':0,'history_native_read_locally':True,'saved_replay_opens_large_native_NetCDF':False,'production_changes':False,'physical_accuracy_approved':False,'original_seven_conditions_changed':False,'scope':'one prepared-domain cold24h plus one bounded11:58–17:00 diagnostic restart to recover IO masks after blank-line termination;1350overlap arrays required; unchanged public executable; no isolated domain or optical improvement claim'}
 (P/'identity.json').write_text(json.dumps(ident,indent=2)+'\n');print('ACTUAL_DAY_DEPOSITED',len(files),file.stat().st_size)
if __name__=='__main__':main()
