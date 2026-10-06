#!/usr/bin/env python3
"""Read retained one-call dry-column intervention only; no engine invocation."""
import argparse,csv,gzip,hashlib,importlib.util,json,math,struct,sys,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
PKG=Path(__file__).resolve().parent;REPO=PKG.parents[2];NIGHT=PKG.parent/'bon-night-same-state';REPLAY=PKG.parent/'bon-night-independent-replay'
HELD={'CLOUD_TAU','CU_CLOUD_TAU','CU_DI_USED','CU_RL_USED','DI_USED','DS_USED','FROZEN_TAU','GRAUPEL_TAU_ABS','HAIL_TAU_ABS','MASK','NATIVE_CLOUD_TAU','PRECIP_TAU','PREPARED_TAU','RL_USED'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def bit(x):return struct.pack('>d',float(x))
def same(a,b):return len(a)==len(b) and all(bit(x)==bit(y) for x,y in zip(a,b))
def f32(x):return struct.unpack('>f',struct.pack('>f',float(x)))[0]
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def mass_only_edit(original,changed):
 o=original.splitlines(keepends=True);c=changed.splitlines(keepends=True)
 def locate(ls):return [i for i,l in enumerate(ls) if l.split()[:1]==[b'NATIVE_DRY_LAYER_MASS_KG_M2']]
 oi=locate(o);ci=locate(c);need(len(oi)==len(ci)==1 and oi==ci,'unique same section location');i=oi[0]
 need(o[i].split()==[b'NATIVE_DRY_LAYER_MASS_KG_M2',b'1',b'32'] and c[i].split()==[b'NATIVE_DRY_LAYER_MASS_KG_M2',b'1',b'45'],'32 to45 mass carrier header')
 need(b''.join(o[:i])==b''.join(c[:i]) and b''.join(o[i+33:])==b''.join(c[i+46:]),'exact byte prefix/suffix unchanged')
 need(all(len(l.split())==1 for l in o[i+1:i+33]+c[i+1:i+46]),'one numeric value per mass line')
 return {'original_count':32,'counterfactual_count':45,'prefix_suffix_bytes_exact':True}
def verify():
 m=json.loads((PKG/'artifact-manifest.json').read_text());names=[x['path'] for x in m['files']]
 want={'README.md','verify.py','test_verify.py','original-payload-roster.json','counterfactual/input.gz','counterfactual/result.gz','frozen/run_once.py'}|{f'receipts/{n}' for n in ['plan.json','preflight-v2.json','authorization.json','execution.json','metrics.json','independent-terminal-review.json','independent-terminal-README.md']}
 actual={p.relative_to(PKG).as_posix() for p in PKG.rglob('*') if p.is_file() and p!=PKG/'artifact-manifest.json'}
 need(len(names)==len(set(names)) and set(names)==actual==want,'closed expected roster')
 for x in m['files']:
  p=PKG/x['path'];need(not p.is_symlink() and sha(p)==x['sha256'] and p.stat().st_size==x['size_bytes'],'payload pin')
 origins=json.loads((PKG/'original-payload-roster.json').read_text())['files'];need(len(origins)==10,'original payload roster count')
 for x in origins:
  data=(PKG/x['relative_path']).read_bytes();need(len(data)==x['retained_size_bytes'] and hashlib.sha256(data).hexdigest()==x['retained_sha256'],'retained original')
  if x['encoding']=='gzip':data=gzip.decompress(data)
  else:need(x['encoding']=='verbatim','encoding')
  need(len(data)==x['original']['size_bytes'] and hashlib.sha256(data).hexdigest()==x['original']['sha256'],'decompressed/verbatim original')
 def j(n):return json.loads((PKG/'receipts'/n).read_text())
 rec=j('execution.json');plan=j('plan.json');auth=j('authorization.json');metrics=j('metrics.json');review=j('independent-terminal-review.json')
 need(rec['status']=='PASS_ONE_DRY_COLUMN_INTERVENTION' and rec['actual_solver_invocations']==1 and rec['WRF_REAL_build_invocations']==0 and rec['returncode']==0 and not rec['timed_out'] and rec['pid']>0,'actual one-call status/PID/RC')
 need(rec['before']==rec['after'],'recorded pre/post immutable closure')
 need(rec['plan']['sha256']==sha(PKG/'receipts/plan.json') and rec['runner']['sha256']==sha(PKG/'frozen/run_once.py') and rec['authorization']['sha256']==sha(PKG/'receipts/authorization.json') and rec['metrics']['sha256']==sha(PKG/'receipts/metrics.json'),'receipt joins')
 need(auth['maximum_solver_calls']==1 and auth['retries']==0 and auth['runner_sha256']==rec['runner']['sha256'] and auth['plan_sha256']==rec['plan']['sha256'] and auth['preflight_sha256']==sha(PKG/'receipts/preflight-v2.json'),'one-call auth')
 need(review['status']=='PASS_READONLY_ONE_CALL_REVIEW' and review['pid']==rec['pid'] and review['returncode']==0 and review['execution_receipt']['sha256']==sha(PKG/'receipts/execution.json'),'terminal independent review binding')
 replay_inv=json.loads((REPLAY/'receipts/inventory.json').read_text());need(plan['inventory']['sha256']==sha(REPLAY/'receipts/inventory.json') and plan['baseline_execution']['sha256']==sha(REPLAY/'receipts/execution.json'),'reused source/library/baseline identity')
 need(rec['argv'][0]==replay_inv['executable']['path'] and rec['argv'][1]==replay_inv['data_dir'] and rec['argv'][2]==plan['counterfactual_input']['path'] and rec['argv'][3]==rec['result']['path'] and rec['argv'][4:]==['1',''],'unmodified one-call argv except diagnostic input/output')
 deps=json.loads((REPLAY/'original-payload-roster.json').read_text())['repository_dependencies']
 for n in ['trace_parser','trace_parser_import_index','current_reference_source']:
  d=deps[n];need(sha(REPO/d['repository_relative_path'])==d['sha256'],'inherited parser/reference source pin')
 parser=load('bon_dry_trace_parser',REPO/deps['trace_parser']['repository_relative_path']).read_trace
 reader=load('bon_dry_export_reader',NIGHT/'parser/read_export_context.py');need(sha(NIGHT/'parser/read_export_context.py')==plan['export_parser']['sha256'],'inherited exact export reader')
 original=gzip.decompress((NIGHT/'captures/OFF/lw_000001.input.gz').read_bytes());changed=gzip.decompress((PKG/'counterfactual/input.gz').read_bytes());edit=mass_only_edit(original,changed)
 need(hashlib.sha256(original).hexdigest()==plan['original_input']['sha256'] and hashlib.sha256(changed).hexdigest()==plan['counterfactual_input']['sha256'],'exact input pins')
 baseline=gzip.decompress((REPLAY/'reference/lw_000001.result.gz').read_bytes());variant=gzip.decompress((PKG/'counterfactual/result.gz').read_bytes());need(hashlib.sha256(baseline).hexdigest()==plan['baseline_result']['sha256'] and hashlib.sha256(variant).hexdigest()==rec['result']['sha256'],'exact result pins')
 with tempfile.TemporaryDirectory(prefix='bon-dry-retained-') as td:
  t=Path(td);parsed={};metas={}
  for n,data,kind in [('original',original,'input'),('changed',changed,'input'),('baseline',baseline,'result'),('variant',variant,'result'),('production',gzip.decompress((NIGHT/'captures/OFF/lw_000001.result.gz').read_bytes()),'result')]:
   p=t/n;p.write_bytes(data);metas[n],parsed[n]=parser(p,kind)
  need(metas['original']==metas['changed'] and metas['baseline']==metas['variant']==metas['production']=={'phase':'LW','ncol':1,'nlay':45},'headers fixed')
  a=parsed['original'];b=parsed['changed'];need(set(a)==set(b) and len(a)==50,'50 input fields')
  for n in set(a)-{'NATIVE_DRY_LAYER_MASS_KG_M2'}:need(a[n]['shape']==b[n]['shape'] and same(a[n]['values'],b[n]['values']),'49 held input sections '+n)
  exname='rrtmg4_d01_i13_j46_step721_lw.txt';export=gzip.decompress((NIGHT/'exports'/(exname+'.gz')).read_bytes());need(hashlib.sha256(export).hexdigest()==plan['legacy_export']['sha256'],'same-call export pin');p=t/exname;p.write_bytes(export);ex=reader.read_export(p,expected_phase='LW',expected_context=plan['expected_context']);coldry=ex['fields']['INPUT','COLDry'].values
  need(same(coldry,plan['expected_COLDry_molecule_cm2']) and len(coldry)==45,'target actual exported molecular dry')
  md=plan['M_dry_kg_mol'];av=plan['avogad_molecules_mol'];need(a['MOL_WEIGHT_DRY']['values']==[md] and av==6.02214076e23,'unchanged source conversion constants')
  expected=[x*md*10000./av for x in coldry];need(same(expected,b['NATIVE_DRY_LAYER_MASS_KG_M2']['values']),'exact diagnostic mass construction')
  ba=parsed['baseline'];cf=parsed['variant'];need(set(ba)==set(cf) and len(ba)==24,'full24 result roster')
  need(all(math.isfinite(float(v)) for obj in (ba,cf) for field in obj.values() for v in field['values']),'all retained result values finite')
  for n in HELD:need(ba[n]['shape']==cf[n]['shape'] and same(ba[n]['values'],cf[n]['values']),'14 exact held optical/mask/size fields '+n)
  gas=cf['GAS_COL_DRY']['values'];need(len(gas)==45,'45 achieved molecular columns');rel=max(abs(x/y-1.) for x,y in zip(gas,coldry));need(rel<=1e-15,'achieved matching molecular dry <=1e-15')
  fn=ba['DN']['values'][0];fc=cf['DN']['values'][0];f4=ex['fields']['RESULT','DOWN_FLUX'].values[0]
  prod=parsed['production'];boundary=f32(prod['DN']['values'][0])-f32(f4)
  nums={'reference_native_dry_surface_W_m2':fn,'reference_legacy_dry_surface_W_m2':fc,'legacy_export_surface_W_m2':f4,'native37_minus_legacy4_direct_F64_W_m2':fn-f4,'dry_construction_native_minus_matched_W_m2':fn-fc,'matched37_minus_legacy4_residual_W_m2':fc-f4,'legacy_dry_injection_response_W_m2':fc-fn,'original_WRF_boundary_REAL32_delta_W_m2':boundary,'gas_dry_matching_max_relative':rel,'algebra_residual_W_m2':(fn-f4)-((fn-fc)+(fc-f4))}
  need(nums['algebra_residual_W_m2']==0.,'direct F64 decomposition')
  for n,v in nums.items():need(bit(v)==bit(metrics[n]),'recomputed metric exact '+n)
  need(metrics['held_exact_sections']==sorted(HELD),'exact14 held roster')
 rows=list(csv.DictReader((NIGHT/'csv/ON_native4_0-same_state.csv').open()));row=next(x for x in rows if x['phase'].upper()=='LW' and int(x['step'])==721 and int(x['i'])==13 and x['metric']=='SURFACE_DOWN');csv_delta=float(row['value37'])-float(row['value4'])
 return {'schema':'bon-night-one-dry-column-portable-verification-v1','status':'PASS_EXACT_MASS_ONLY_INPUT_HELD_FIELDS_AND_DIRECT_DECOMPOSITION','manifest_sha256':sha(PKG/'artifact-manifest.json'),'payload_count':len(m['files']),'recorded_additional_standalone_calls':1,'recorded_total_replay_calls_in_siblings':7,'new_WRF_REAL_build_solver_calls_from_verifier':0,'input_edit':edit,'other_input_sections_held':49,'output_fields_exact_held':14,'actual_molecular_dry_match_max_relative':rel,'direct_F64_metrics':nums,'operational_CSV_decimal_encoding_delta_W_m2':csv_delta,'actual_WRF_REAL32_boundary_delta_W_m2':boundary,'scope':'45-layer diagnostic mass carrier at one held state, not new WRF native state. Residual retains combined spectral/engine/other construction effects; no optical truth, observation accuracy or general causal resolution.'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path);a=p.parse_args();r=verify()
 if a.output:
  out=a.output.absolute();need(PKG not in out.parents,'output outside evidence');out.parent.mkdir(parents=True,exist_ok=True)
  with out.open('x') as f:json.dump(r,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
 print(json.dumps(r,sort_keys=True,allow_nan=False))
if __name__=='__main__':main()
