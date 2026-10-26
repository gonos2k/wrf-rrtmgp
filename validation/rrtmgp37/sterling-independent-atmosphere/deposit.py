"""Preserve actual public downloads, exact subsets and the native read/diagnostics."""
from pathlib import Path
import json,hashlib,tarfile,gzip,io,subprocess
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;BASE='d2223f13c28f06d9886f5d5febaeb2ad18b3a5a0'
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
def main():
 F=B/'udm37-sterling-independent-atmosphere-fetch-v1';O=B/'udm37-sterling-independent-atmosphere-analysis-v1';N=B/'udm37-sterling-independent-atmosphere-saturation-v1';payload={}
 for p in F.glob('*.receipt.json'):payload['fetch/'+p.name]=p.read_bytes()
 for n in ['receipt.json','final-retrieval-receipt.json','selected-soundings.json','executed-fetch-v1.py','igra-metadata.txt']:payload['fetch/'+n]=(F/n).read_bytes()
 for n in ['model-profiles.json','enriched.json']:payload['derived/'+n]=(O/n).read_bytes()
 for p in O.glob('development-*'):payload['development/'+p.name]=p.read_bytes()
 for pat in ['receipt.json','input.json','input.txt','native_saturation.f90','command-*.*']:
  for p in N.glob(pat):payload['native/'+p.name]=p.read_bytes()
 payload['plan.json']=(P/'plan.json').read_bytes()
 for n in ['README.md','WRF/test/rrtmgp/UDM_SPECIFIED_NUMBER.md','WRF/doc/rrtmgp/UDM_FROZEN_EXPERIMENT.md','config/registration37.json']:payload['before/'+n]=subprocess.check_output(['git','show',BASE+':'+n],cwd=R)
 buf=io.BytesIO();files={}
 with tarfile.open(fileobj=buf,mode='w') as t:
  for n,b in sorted(payload.items()):
   m=tarfile.TarInfo(n);m.size=len(b);m.mtime=0;t.addfile(m,io.BytesIO(b));files[n]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
 (P/'saved').mkdir(exist_ok=True);out=P/'saved/evidence.tar.gz';out.write_bytes(gzip.compress(buf.getvalue(),mtime=0))
 native=['WRF/dyn_em/solve_em.F','WRF/dyn_em/module_big_step_utilities_em.F','WRF/phys/module_microphysics_driver.F','WRF/phys/module_mp_udm.F','WRF/phys/module_ra_rrtmg_lw.F','WRF/phys/module_ra_rrtmg_sw.F','WRF/phys/physics_mmm/bl_ysu.F90']
 for n in native:assert subprocess.check_output(['git','show',BASE+':'+n],cwd=R)==(R/n).read_bytes()
 docs=['README.md','WRF/test/rrtmgp/UDM_SPECIFIED_NUMBER.md','WRF/doc/rrtmgp/UDM_FROZEN_EXPERIMENT.md','config/registration37.json']
 deps=['historical-source/binding.py','historical-source/snapshot-d2223f13.json','historical-source/snapshot-d2223f13/UDM_FROZEN_EXPERIMENT.md.gz','sterling-interior-day-evaluation/identity.json','sterling-interior-day-evaluation/result.json','sterling-cloud-loss-operation/identity.json','sterling-cloud-loss-operation/result.json','research-policy-contract/closure-conditions.json','acceptance/review-resolution-checklist.json']
 ident={'base_main':BASE,'archive':pin(out),'files':files,'raw_files':{p.name:pin(p) for p in (P/'raw').iterdir() if p.is_file()},'current_sources':{str(p.relative_to(R)):pin(p) for p in P.glob('*.py') if p.name!='deposit.py'},'unchanged_production_sources':{n:pin(R/n) for n in native},'current_documents':{n:pin(R/n) for n in docs},'dependencies':{'validation/rrtmgp37/'+n:pin(R/'validation/rrtmgp37'/n) for n in deps},'outputs':{n:pin(P/n) for n in ['result.json','pressure-comparison.csv','independent-atmosphere.png','README.md']},'native_scalar_compile_run_processes':2,'new_WRF_WPS_REAL_RTE_Mie_processes':0,'production_calculation_changes':False,'physics_or_coefficient_changes':False,'original_seven_conditions_changed':False,'physical_accuracy_approved':False,'raw_scope':'exact4IGRAsoundingblocks plus fetchedMETAR/export anddocs. Full101775974-byteIGRA ZIP and large nativeNetCDF retained locally and pinned, not bundled. Subset byteoffsets/member/wholeZIPdigest allow independent external recovery; saved replay uses exact subset bytes','new_model_runs_in_saved_replay':0}
 (P/'identity.json').write_text(json.dumps(ident,indent=2)+'\n');print('ACTUAL_INDEPENDENT_OBSERVATIONS_DEPOSITED',len(files),out.stat().st_size)
if __name__=='__main__':main()
