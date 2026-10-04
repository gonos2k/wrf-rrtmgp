#!/usr/bin/env python3
"""Generate hash manifest for the prepared one-hour RA37 failure diagnostic. No model launch."""
from pathlib import Path
import hashlib,json
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
D=ROOT/'build/udm37-matthew-fatal-diagnostic-v1'; BASE=ROOT/'build/udm37-matthew-paired-48h-v1'
source=json.loads((BASE/'stage-manifest.json').read_text()); a=source['arms']['ra37']; case=D/'case'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p): p=Path(p).resolve(strict=True); return {'path':str(p),'size_bytes':p.stat().st_size,'sha256':sha(p)}
assets={}
for n,entry in a['assets_by_name'].items():
 p=case/n
 if not p.is_symlink() or p.is_dir() and not p.is_symlink() or p.readlink().as_posix()!=entry['link_text']: raise SystemExit(f'symlink mismatch {n}')
 got=pin(p)
 if got['size_bytes']!=entry['size_bytes'] or got['sha256']!=entry['sha256']: raise SystemExit(f'asset mismatch {n}')
 assets[n]={'link_text':entry['link_text'],'sha256':got['sha256'],'size_bytes':got['size_bytes'],'resolved_path':got['path']}
common={}
for n,e in a['common_inputs'].items():
 got=pin(case/n)
 if got['size_bytes']!=e['size_bytes'] or got['sha256']!=e['sha256']: raise SystemExit(f'input mismatch {n}')
 common[n]={'sha256':got['sha256'],'size_bytes':got['size_bytes']}
base_nml=(BASE/'ra37/namelist.input').read_bytes(); nml=(case/'namelist.input').read_bytes()
if nml.count(b'run_hours')!=1 or b'run_hours                           = 1,' not in nml or b'end_day                              = 06,' not in nml or b'end_hour                             = 01,' not in nml: raise SystemExit('duration edits not exact')
from datetime import datetime
start=datetime(2016,10,6,0); end=datetime(2016,10,6,1)
if (end-start).total_seconds()!=3600: raise SystemExit('diagnostic duration is not exactly one hour')
if (case/'radiation_iofields.txt').read_bytes()!=(BASE/'ra37/radiation_iofields.txt').read_bytes(): raise SystemExit('iofields changed')
plan={
 'schema':'matthew-ra37-mpi-fatal-diagnostic-stage-v1','status':'STAGED_NOT_RUN_REQUIRES_ROOT_AUTHORIZATION',
 'source_stage_manifest_sha256':sha(BASE/'stage-manifest.json'),'source_pair_plan_sha256':sha(BASE/'execution-plan.json'),
 'source_pair_receipt_sha256':sha(BASE/'execution-receipt.json'),'source_ra4_v2_sha256':sha(BASE/'ra4-postflight-v2-final.json'),'source_ra4_log_review_sha256':sha(BASE/'ra4-expanded-log-review-v1.json'),
 'runner_sha256':sha(D/'run_once.py'),
 'source_ra37_original_case':str((BASE/'ra37').resolve()),'case_dir':str(case.resolve()),
 'namelist':{'sha256':sha(case/'namelist.input'),'size_bytes':(case/'namelist.input').stat().st_size,'source_sha256':hashlib.sha256(base_nml).hexdigest(),'only_changed_assignments':{'run_hours':{'from':'48','to':'1'},'end_day':{'from':'08','to':'06'},'end_hour':{'from':'00','to':'01'}},'validated_elapsed_seconds':3600,'unchanged_physics_and_forcing':True},
 'common_inputs':common,'radiation_iofields':pin(case/'radiation_iofields.txt'),'assets':assets,
 'executable':source['wrf_executable'],'mpiexec':source['mpiexec'],'runtime_libraries':source['runtime_libraries'],'coefficient_files':source['coefficient_files'],'frozen_table':source['frozen_table'],
 'launch':{'command':[source['mpiexec']['path'],'-launcher','fork','-iface','lo','-n','4',str(case/'wrf.exe')],'mpi_ranks':4,'omp_threads':1,'omp_stacksize':'512M','batch_size':'32','timeout_seconds':3600,'attempts_max':1,'no_retry':True,'case_env_clean_prefixes':['WRF_RRTMGP_','WRF_UDM_BOUNDARY_CAPTURE','OMP_','GOMP_','KMP_'],'case_env_clean_exact':['LD_PRELOAD','LD_AUDIT'],'ld_library_path':source['execution_env']['LD_LIBRARY_PATH'],'mpich_interface_hostname':'127.0.0.1'},
 'diagnostic_scope':{'purpose':'capture original fatal/error line for one-hour RA37 run after the preserved 00:40 MPI_Abort','expected_start':'2016-10-06_00:00:00','expected_end':'2016-10-06_01:00:00','full_48h_completion_claim':False,'full_postflight_validator':None,'collect_case_insensitive_markers':['fatal','mpi_abort','error: fatal','application called mpi_abort'],'collect_success_markers_per_rank':True,'collect_last_timing_line_per_rank':True,'preserve_all_logs_and_partial_outputs':True},
 'authorization_contract':{'status':'AUTHORIZED_ONE_HOUR_RA37_DIAGNOSTIC','plan_sha256':'sha256(this plan)','manifest_sha256':'sha256(diagnostic-manifest.json)','runner_sha256':'sha256(run_once.py)','corrected_ra4_postflight_sha256':sha(BASE/'ra4-postflight-v2-final.json'),'root_scope':'one MPI4/OMP1/B32 forecast invocation, 1h only; no retry'},
 'model_invocations':0
}
(D/'diagnostic-plan.json').write_text(json.dumps(plan,indent=2,sort_keys=True)+'\n')
manifest={'schema':'matthew-ra37-diagnostic-manifest-v1','status':'STAGED_NOT_RUN','plan_sha256':sha(D/'diagnostic-plan.json'),'case_dir':str(case.resolve()),'namelist':plan['namelist'],'inputs':common,'iofields':plan['radiation_iofields'],'assets':assets,'executable':plan['executable'],'mpiexec':plan['mpiexec'],'runtime_libraries':plan['runtime_libraries'],'coefficient_files':plan['coefficient_files'],'frozen_table':plan['frozen_table']}
(D/'diagnostic-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
print('prepared',len(assets),'assets',len(common),'common inputs','no model invocation')
