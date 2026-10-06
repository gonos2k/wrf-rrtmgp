"""Read-only verification of retained artifact integrity and complete validation gates."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parent
def read(name):return json.loads((ROOT/name).read_text())
def require(condition,message):
 if not condition:raise RuntimeError(message)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for e in read('file-manifest.json')['files']:
 p=ROOT/e['path'];require(p.is_file() and p.stat().st_size==e['bytes'] and sha(p)==e['sha256'],'artifact changed '+e['path'])
oracle=read('receipts/standalone/oracle-results.json')
require({(r['configuration'],r['frozen_mode']) for r in oracle}=={(c,m) for c in ('debug','release') for m in (0,1)} and len(oracle)==4,'original-base oracle cases incomplete')
for r in oracle:
 require(r['all_6_lw_and_17_sw_output_bytes_equal'] and r['output_bytes']==542928 and r['adapter_trace_files']==576 and r['all_adapter_trace_bytes_equal'] and not r['differing_trace_files'],'oracle divergence')
require(read('receipts/standalone/ctest-summary.json')['combined_all_pass'],'standalone checks incomplete')
profile=read('receipts/standalone/allocation-profile-results.json')
require(set(profile)=={'0-baseline','0-candidate','1-baseline','1-candidate'},'allocation profiles incomplete')
for mode in (0,1):
 for phase in ('LW','SW'):
  calls=profile[str(mode)+'-candidate'][phase]['first_four_calls'];require(len(calls)==4,'allocation calls incomplete')
  require(all(int(calls[3][k])==0 for k in ('gas_init','descriptor_init','optics1_alloc','optics2_alloc','source_alloc','diagnostic_malloc')),'warm workspace allocator invoked')
 cold=profile[str(mode)+'-candidate']['SW']['first_four_calls'][0]
 require(int(cold['diagnostic_malloc'])==8 and int(cold['diagnostic_bytes'])==8400,'SW diagnostic counter was not observable')
bench=read('receipts/standalone/benchmark-results.json')['rows']
require(len(bench)==20,'five benchmark pairs per mode incomplete')
for mode in (0,1):
 for repeat in range(5):
  pair=[r for r in bench if r['frozen_mode']==mode and r['repeat']==repeat]
  require(len(pair)==2 and {r['label'] for r in pair}=={'baseline','candidate'} and len({r['checksum'] for r in pair})==1 and all(r['calls']==1500 and r['ncol']==1 and r['nlay']==60 for r in pair),'benchmark pair/input/checksum mismatch')
total=0
for scope,cases in [('serial',['ra37','ra4']),('dm-sm',['ra37-mpi1-omp1','ra37-mpi1-omp2','ra37-mpi4-omp1','ra4-mpi4-omp1'])]:
 for case in cases:
  prefix='receipts/'+scope+'/'+case+'/'
  r=read(prefix+'receipt.json');c=read(prefix+'comparison.json')
  require(r['status']=='COMPLETE_BITWISE_PASS' and c['status']=='BITWISE_PASS' and not c['differences'],case+' comparison failed')
  count=11 if case.startswith('ra37') else 1;vars=211 if count==11 else 208;attrs=1342 if count==11 else 1324
  require(len(c['history_files'])==count,case+' histories incomplete');total+=count
  for h in c['history_files']:
   require(h['variables']==vars and h['attributes']==attrs and not h['differences'] and h['baseline_sha256']==h['candidate_sha256'],case+' output/metadata/file differs')
  require(r['source_before']==r['source_after'] and r['inputs_before']==r['inputs_after'] and r['external_assets_before']==r['external_assets_after'] and r['restart_before_sha256']==r['restart_after_sha256'] and r['executable_sha256']==r['copied_executable_after_sha256'],case+' immutable state changed')
require(total==46,'full model cases incomplete')
dm=read('receipts/dm-sm/summary.json')
require(dm['status']=='DM_SM_ALL_LAYOUTS_NONINTERFERENCE_PASS' and all(r['all_ranks_success'] for r in dm['layouts'].values()),'MPI ranks did not all succeed')
for role in ('baseline','candidate'):
 p=read('receipts/dm-sm/ra37-mpi1-omp2/'+role+'-worker-proof.json')
 require(p['verified_two_radiation_workers'],'OMP2 active radiation worker proof missing '+role)
manifest=read('manifest.json');require(manifest['total_history_files']==46 and not manifest['workspace_persistence_across_timesteps'] and not manifest['wrf_column_batching'] and not manifest['vendor_changes'] and not manifest['physical_policy_changes'] and not manifest['model_speedup_claim'],'scope mismatch')
print('WORKSPACE_VALIDATION_RECEIPTS_PASS: original-base oracle4/4, standalone103/103, serial12+dm-sm34 histories, OMP2 workers verified')
