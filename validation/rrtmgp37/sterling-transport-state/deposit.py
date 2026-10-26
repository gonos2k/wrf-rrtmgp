"""Deposit actual native faces/read-only run and existing-state coordinates."""
from pathlib import Path
import json,hashlib,tarfile,gzip,io,subprocess
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;BASE='85af9c7f8e1fec2dd9dbefb8591e4df06197d16a'
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
def main():
 RUN=B/'udm37-sterling-transport-run-v1';BUILD=B/'udm37-sterling-transport-build-v1';O=B/'udm37-sterling-transport-analysis-v1';payload={}
 for folder,prefix in [(RUN,'run/'),(BUILD,'build/')]:
  for pat in ['receipt.json','command-*.*']:
   for p in folder.glob(pat):payload[prefix+p.name]=p.read_bytes()
 build=json.loads((BUILD/'receipt.json').read_text())
 for n in build['sources']:payload['build/sources/'+n]=(BUILD/n).read_bytes()
 for n in ['extracted.json','history-comparison.json']:payload['extract/'+n]=(O/n).read_bytes()
 payload['native/transport_faces.txt']=(RUN/'host/transport_faces.txt').read_bytes();payload['prior/prior-state-and-coordinate.json']=(B/'udm37-sterling-transport-prior-v1/prior-state-and-coordinate.json').read_bytes()
 for n in ['namelist.input','radiation_iofields.txt']:payload['run/'+n]=(RUN/'host'/n).read_bytes()
 payload['plan.json']=(P/'plan.json').read_bytes();payload['publication/root-README.md']=(R/'README.md').read_bytes();payload['before/root-README.md']=subprocess.check_output(['git','show',BASE+':README.md'],cwd=R)
 files={};buf=io.BytesIO()
 with tarfile.open(fileobj=buf,mode='w:') as t:
  for n,b in sorted(payload.items()):
   m=tarfile.TarInfo(n);m.size=len(b);m.mtime=0;t.addfile(m,io.BytesIO(b));files[n]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
 (P/'saved').mkdir(exist_ok=True);f=P/'saved/evidence.tar.gz';f.write_bytes(gzip.compress(buf.getvalue(),mtime=0))
 prod=['WRF/dyn_em/solve_em.F','WRF/dyn_em/module_em.F','WRF/dyn_em/module_advect_em.F','WRF/dyn_em/module_big_step_utilities_em.F','WRF/dyn_em/module_small_step_em.F','WRF/share/module_model_constants.F','WRF/phys/module_mp_udm.F','WRF/phys/module_ra_rrtmg_lw.F','WRF/phys/module_ra_rrtmg_sw.F']
 for n in prod:assert subprocess.check_output(['git','show',BASE+':'+n],cwd=R)==(R/n).read_bytes(),n
 deps=['sterling-thermodynamic-tendencies/identity.json','sterling-thermodynamic-tendencies/result.json','sterling-thermodynamic-tendencies/step-processes.csv','sterling-thermodynamic-tendencies/saved/evidence.tar.gz','sterling-independent-atmosphere/identity.json','sterling-independent-atmosphere/result.json','sterling-low-level-evolution/identity.json','sterling-low-level-evolution/result.json','sterling-interior-day-evaluation/hourly-comparison.csv','research-policy-contract/closure-conditions.json','real-case-budget/instrument.py','vapor-first-operation/compare_history.py']
 ident={'base_main':BASE,'archive':pin(f),'files':files,'current_sources':{str(p.relative_to(R)):pin(p) for p in sorted(P.glob('*.py'))},'probe_source':pin(P/'probe.f90'),'unchanged_production_sources':{n:pin(R/n) for n in prod},'dependencies':{'validation/rrtmgp37/'+n:pin(P.parent/n) for n in deps},'outputs':{n:pin(P/n) for n in ['README.md','result.json','step-faces.csv','transport-state.png']},'new_bounded_WRF_processes':1,'new_cold24h_WRF_processes':0,'private_compile_archive_link_processes':6,'new_WPS_REAL_standalone_RTE_Mie_or_saturation_processes':0,'production_calculation_changes':False,'coefficient_or_policy_changes':False,'physical_accuracy_approved':False,'original_seven_conditions_changed':False,'new_model_runs_in_saved_replay':0,'root_navigation_scope':'exact before/after publication snapshots retained; future root navigation can advance without relabelling this result'}
 (P/'identity.json').write_text(json.dumps(ident,indent=2)+'\n');print('ACTUAL_TRANSPORT_EVIDENCE_DEPOSITED',len(files),f.stat().st_size)
if __name__=='__main__':main()
