"""Archive exact read subsets, native scalar receipts and existing input provenance."""
from common import *
import json,tarfile,gzip,io,subprocess
def main():
 payload={'plan.json':(P/'plan.json').read_bytes()};O=B/'udm37-sterling-low-level-extract-v2';N=B/'udm37-sterling-low-level-native-v2'
 for n in ['extracted.json','enriched.json','support-audit.json']:payload['read/'+n]=(O/n).read_bytes()
 for n in ['input.json','input.txt','native_saturation.f90','receipt.json','stdout.txt','stderr.txt']:payload['native/'+n]=(N/n).read_bytes()
 for n in ['udm37-sterling-low-level-extract-v1.log','udm37-sterling-low-level-extract-v2.log','udm37-sterling-low-level-native-v1.log','udm37-sterling-low-level-native-v2.log','udm37-sterling-low-level-report-v1.log','udm37-sterling-low-level-report-v4.log','udm37-sterling-low-level-support-audit.log']:payload['execution/'+n]=(B/n).read_bytes()
 payload['execution/development-native-receipt.json']=(B/'udm37-sterling-low-level-native-v1/receipt.json').read_bytes()
 deps={'existing-REAL-receipt.json':B/'udm37-sterling-interior-real-v1/receipt.json','existing-WPS-receipt.json':B/'udm37-sterling-interior-wps-v3/receipt.json','existing-download-receipt.json':B/'udm37-sterling-interior-inputs-v1/download-receipt.json','REAL-namelist.output':B/'udm37-sterling-interior-real-v1/host/namelist.output','forecast.namelist.input':B/'udm37-sterling-interior-real-v1/forecast.namelist.input','WPS-METGRID.TBL.ARW':B/'udm37-sterling-wps-source-v1/metgrid/METGRID.TBL.ARW','prior-native-helper-receipt.json':B/'udm37-sterling-independent-atmosphere-saturation-v1/receipt.json'}
 for n,p in deps.items():payload['provenance/'+n]=p.read_bytes()
 production=['WRF/dyn_em/module_initialize_real.F','WRF/main/real_em.F','WRF/dyn_em/module_big_step_utilities_em.F','WRF/phys/module_mp_udm.F','WRF/phys/physics_mmm/bl_ysu.F90','WRF/dyn_em/solve_em.F','WRF/dyn_em/module_advect_em.F','WRF/dyn_em/module_bc_em.F','WRF/phys/module_physics_addtendc.F','WRF/phys/module_ra_rrtmg_sw.F','WRF/phys/module_ra_rrtmg_lw.F']
 base=json.loads((P/'plan.json').read_text())['base_main']
 for n in production:require(subprocess.check_output(['git','show',base+':'+n],cwd=R)==(R/n).read_bytes(),'production source changed '+n)
 deps_repo=['sterling-independent-atmosphere/identity.json','sterling-independent-atmosphere/saved/evidence.tar.gz','sterling-independent-atmosphere/result.json','sterling-independent-atmosphere/parse.py','sterling-interior-day-evaluation/result.json','sterling-interior-day-evaluation/identity.json','sterling-interior-day-evaluation/saved/evidence.tar.gz','sterling-interior-day-evaluation/hourly-comparison.csv','sterling-boundary-forcing-decision/identity.json','research-policy-contract/closure-conditions.json']
 files={};buf=io.BytesIO()
 with tarfile.open(fileobj=buf,mode='w:') as t:
  for n,b in sorted(payload.items()):
   m=tarfile.TarInfo(n);m.size=len(b);m.mtime=0;t.addfile(m,io.BytesIO(b));files[n]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
 (P/'saved').mkdir(exist_ok=True);archive=P/'saved/evidence.tar.gz';archive.write_bytes(gzip.compress(buf.getvalue(),mtime=0))
 ident={'base_main':base,'archive':pin(archive),'files':files,'current_sources':{str(p.relative_to(R)):pin(p) for p in sorted(P.glob('*.py'))},'unchanged_production_sources':{n:pin(R/n) for n in production},'dependencies':{'validation/rrtmgp37/'+n:pin(P.parent/n) for n in deps_repo},'outputs':{n:pin(P/n) for n in ['README.md','result.json','hourly-pressure.csv','state-development.png']},'new_WRF_WPS_REAL_RTE_Mie_processes':0,'new_compile_processes':0,'scalar_helper_processes_development_and_final':2,'production_calculation_changes':False,'coefficient_or_policy_changes':False,'original_seven_conditions_changed':False,'physical_accuracy_approved':False,'new_model_runs_in_saved_replay':0,'large_sources':'retained local nativeCDF/GRIB/WPS inputs pinned in read/extracted.json; standard-library saved replay consumes exact read subsets and existing sealed observations, not large source files'}
 (P/'identity.json').write_text(json.dumps(ident,indent=2)+'\n');print('EXISTING_LOW_LEVEL_CHAIN_DEPOSITED',len(files),archive.stat().st_size)
if __name__=='__main__':main()
