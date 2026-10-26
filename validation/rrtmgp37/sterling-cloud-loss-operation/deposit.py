"""Deposit actual bounded run and derived observations, without launching a model."""
from pathlib import Path
import json,hashlib,tarfile,gzip,io
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
def main():
 run=B/'udm37-sterling-cloud-loss-run-v1';build=B/'udm37-sterling-cloud-loss-build-v3';an=B/'udm37-sterling-cloud-loss-analysis-v1';th=B/'udm37-sterling-cloud-loss-thermo-v1'
 assert json.loads((run/'receipt.json').read_text())['status']=='SUCCESS';payload={}
 for base,key in [(run,'run'),(build,'build'),(th,'thermo')]:
  for pat in ['receipt.json','command-*.*','*.F','*.f90','*.py','executed-plan.json','development.json','input.txt','result.json','host/namelist.input','host/namelist.output','host/radiation_iofields.txt']:
   for p in base.glob(pat):
    if p.is_file():payload[key+'/'+str(p.relative_to(base))]=p.read_bytes()
 for n in ['extracted.json','history-comparison.json','analysis.json'] :payload['derived/'+n]=(an/n).read_bytes()
 payload['observer/cloud_operations.txt']=(run/'host/cloud_operations.txt').read_bytes();payload['public-baseline-receipt.json']=(B/'udm37-vapor-corrected-public-v2/receipt.json').read_bytes();payload['cold-baseline-receipt.json']=(B/'udm37-sterling-interior-day-v1/receipt.json').read_bytes();payload['plan.json']=(P/'plan.json').read_bytes()
 files={};buf=io.BytesIO()
 with tarfile.open(fileobj=buf,mode='w') as t:
  for name,raw in sorted(payload.items()):
   m=tarfile.TarInfo(name);m.size=len(raw);m.mtime=0;t.addfile(m,io.BytesIO(raw));files[name]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
 (P/'saved').mkdir(exist_ok=True);out=P/'saved/evidence.tar.gz';out.write_bytes(gzip.compress(buf.getvalue(),mtime=0))
 sources=['WRF/dyn_em/solve_em.F','WRF/dyn_em/module_advect_em.F','WRF/dyn_em/module_em.F','WRF/dyn_em/module_first_rk_step_part1.F','WRF/dyn_em/module_first_rk_step_part2.F','WRF/phys/module_mp_udm.F','WRF/phys/module_bl_ysu.F','WRF/phys/physics_mmm/bl_ysu.F90','WRF/phys/module_pbl_driver.F','WRF/phys/module_microphysics_driver.F','WRF/phys/module_physics_addtendc.F','WRF/share/module_model_constants.F','WRF/test/rrtmgp/test_netcdf_zz.py','validation/rrtmgp37/vapor-first-operation/compare_history.py','validation/rrtmgp37/real-case-budget/instrument.py']+[str(p.relative_to(R)) for p in P.glob('*.py') if p.name!='deposit.py']
 deps=['sterling-interior-day-evaluation/identity.json','sterling-interior-day-evaluation/result.json','sterling-interior-day-evaluation/analyze.py','real-output-independent-comparison/analyze.py','research-policy-contract/closure-conditions.json','solrad-boundary-site-48h/raw/ste16280.dat','solrad-boundary-site-48h/raw/ste16281.dat']
 deps=['validation/rrtmgp37/'+n for n in deps]
 identity={'base_main':'cb9136a4a5b1f000972a58a0d6c73416b82a5605','base_tree':'5897ebbfac279970476e9f5f00182bc1485c876b','archive':pin(out),'files':files,'current_sources':{n:pin(R/n) for n in sources},'dependencies':{n:pin(R/n) for n in deps},'outputs':{n:pin(P/n) for n in ['result.json','cloud-loss-steps.csv','cloud-loss-processes.png','README.md']},'actual_new_WRF_processes':1,'new_cold24h_processes':0,'new_clean_WRF_builds':0,'private_observer_incremental_build_processes':6,'native_saturation_helper_compile_run_processes':2,'new_standalone_Mie_RTE_processes':0,'new_model_runs_in_saved_replay':0,'production_changes':False,'physical_accuracy_approved':False,'global_water_energy_approved':False,'original_seven_conditions_changed':False,'scope':'same qualified interior-cold11:58checkpoint to19UTC, operator observations16:50–18:10 only, actual1800overlap arrays required; private read-only source insertions, not a new forecast or parameter calibration; scalar native saturation helpers are not full UDM/WRF runs'}
 (P/'identity.json').write_text(json.dumps(identity,indent=2)+'\n');print('ACTUAL_BOUNDED_EVIDENCE_DEPOSITED',len(files),out.stat().st_size)
if __name__=='__main__':main()
