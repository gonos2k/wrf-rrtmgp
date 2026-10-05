#!/usr/bin/env python3
"""Stdlib read-only replay-result comparison, never invokes numerical engines."""
import argparse,gzip,hashlib,importlib.util,json,math,struct,sys,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
PKG=Path(__file__).resolve().parent;REPO=PKG.parents[2];CAP=PKG.parent/'bon-night-same-state/captures/OFF'
OUTPUTS={'UP','DN','HR','UPC','DNC','HRC'}
ENGINE={'CLOUD_TAU','CU_CLOUD_TAU','CU_DI_USED','CU_RL_USED','DI_USED','DN','DNC','DS_USED','FROZEN_TAU','GAS_COL_DRY','GAS_TAU','GAS_TAU_RAW','GRAUPEL_TAU_ABS','HAIL_TAU_ABS','HR','HRC','MASK','NATIVE_CLOUD_TAU','PRECIP_TAU','PREPARED_TAU','RL_USED','TOTAL_TAU','UP','UPC'}
EXTRAS={'WRF_GLW','WRF_OLR','WRF_THETA_HR'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def f32(x):return struct.unpack('>f',struct.pack('>f',x))[0]
def bits32(x):return struct.pack('>f',float(x))
def spacing32(x):
 u=struct.unpack('>I',bits32(abs(x)))[0]
 return struct.unpack('>f',struct.pack('>I',u+1))[0]-f32(abs(x))
def compare_values(name,actual,expected):
 need(len(actual)==len(expected) and all(math.isfinite(x) for x in actual+expected),'finite/equal value counts')
 diffs=[abs(x-y) for x,y in zip(actual,expected)];dmax=max(diffs,default=0.)
 if name=='MASK':need(all(x==y for x,y in zip(actual,expected)),'exact MASK');return {'max_abs':dmax,'passed':True,'tolerance':'exact'}
 if name in OUTPUTS:ts=[4.*spacing32(y)+1e-6 for y in expected];label='4 float32 ULP + 1e-6'
 else:ts=[2e-13+2e-12*abs(y) for y in expected];label='2e-13 absolute + 2e-12 relative'
 need(all(d<=t for d,t in zip(diffs,ts)),'unchanged threshold '+name)
 return {'max_abs':dmax,'max_tolerance':max(ts,default=0.),'passed':True,'tolerance':label}
def mapping_checks(prod,raw):
 need(prod['WRF_GLW']['shape']==(1,1,1) and prod['WRF_OLR']['shape']==(1,1,1),'WRF scalar mapping shape')
 need(bits32(prod['WRF_GLW']['values'][0])==bits32(f32(prod['DN']['values'][0])),'GLW exact REAL32 DN surface')
 need(bits32(prod['WRF_OLR']['values'][0])==bits32(f32(prod['UP']['values'][-1])),'OLR exact REAL32 UP TOA')
 pi=raw['PI']['values'];theta=prod['WRF_THETA_HR']['values'];hr=prod['HR']['values'][:32]
 need(raw['PI']['shape']==(32,) and prod['WRF_THETA_HR']['shape']==(1,32,1) and len(theta)==len(pi)==32,'native PI/theta dimensions')
 expected=[f32(f32(f32(h)/f32(86400.))/f32(p)) for h,p in zip(hr,pi)]
 need(all(bits32(a)==bits32(b) for a,b in zip(theta,expected)),'native theta exact two REAL32 divisions')
 return {'GLW_f32_surface_DN':True,'OLR_f32_TOA_UP':True,'native_theta32_f32_f32_HR_over86400_overPI':True,'native_layers_checked':32,'not_an_engine_comparator_section':True}
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m

def verify():
 manifest=json.loads((PKG/'artifact-manifest.json').read_text());files=manifest['files'];names=[r['path'] for r in files]
 expected={'README.md','verify.py','test_verify.py','original-payload-roster.json','frozen/run_once.py'}
 expected|={f'reference/lw_{k:06d}.result.gz' for k in range(1,7)}|{f'comparisons/lw_{k:06d}.json' for k in range(1,7)}
 expected|={f'receipts/{n}' for n in ['inventory.json','plan.json','preflight.json','authorization.json','execution.json','independent-terminal-review.json','independent-terminal-README.md','original-compiled-build-execution.json']}
 actual={p.relative_to(PKG).as_posix() for p in PKG.rglob('*') if p.is_file() and p!=PKG/'artifact-manifest.json'}
 need(len(names)==len(set(names)) and set(names)==actual==expected,'closed expected roster')
 for r in files:
  p=PKG/r['path'];need(not p.is_symlink() and sha(p)==r['sha256'] and p.stat().st_size==r['size_bytes'],'manifest file pin')
 origin=json.loads((PKG/'original-payload-roster.json').read_text());need(len(origin['files'])==21,'origin roster')
 for r in origin['files']:
  b=(PKG/r['relative_path']).read_bytes();need(hashlib.sha256(b).hexdigest()==r['retained_sha256'] and len(b)==r['retained_size_bytes'],'retained pin')
  if r['encoding']=='gzip':b=gzip.decompress(b)
  else:need(r['encoding']=='verbatim','original encoding')
  need(hashlib.sha256(b).hexdigest()==r['original']['sha256'] and len(b)==r['original']['size_bytes'],'original pin')
 for r in origin['repository_dependencies'].values():
  p=REPO/r['repository_relative_path'];need(sha(p)==r['sha256'] and p.stat().st_size==r['size_bytes'],'inherited source/parser pin')
 read=load('bon_reference_portable_trace',REPO/origin['repository_dependencies']['trace_parser']['repository_relative_path']).read_trace
 def j(n):return json.loads((PKG/'receipts'/n).read_text())
 rec=j('execution.json');inv=j('inventory.json');plan=j('plan.json');auth=j('authorization.json');review=j('independent-terminal-review.json');compiled=j('original-compiled-build-execution.json')
 need(rec['status']=='PASS_SIX_DIRECT_LIBRARY_REPLAYS' and rec['actual_solver_invocations']==6 and rec['WRF_REAL_build_invocations']==0 and len(rec['calls'])==6,'six standalone outcome')
 need(rec['before']==rec['after'],'archived immutable pre/post closure')
 need(rec['inventory']['sha256']==sha(PKG/'receipts/inventory.json') and rec['plan']['sha256']==sha(PKG/'receipts/plan.json') and rec['runner']['sha256']==sha(PKG/'frozen/run_once.py') and rec['authorization']['sha256']==sha(PKG/'receipts/authorization.json'),'execution bindings')
 need(auth['maximum_solver_calls']==6 and auth['retries']==0 and auth['inventory_sha256']==rec['inventory']['sha256'] and auth['plan_sha256']==rec['plan']['sha256'] and auth['runner_sha256']==rec['runner']['sha256'] and auth['preflight_sha256']==sha(PKG/'receipts/preflight.json'),'authorization exact call budget')
 need(inv['build_receipt']['sha256']==sha(PKG/'receipts/original-compiled-build-execution.json') and compiled['status']=='BUILD_PASS' and compiled['configure_returncode']==compiled['build_returncode']==0 and compiled['build_invocations']==1 and compiled['solver_invocations']==0,'original compiled build attestation')
 source=origin['source_provenance'];need(source['compiled_source_equals_current'] and source['compiled_reference_source']['sha256']==source['current_reference_source']['sha256']==origin['repository_dependencies']['current_reference_source']['sha256']=='6e82effd7d25242656858a8242c7e6941fced6aec0ec4d906762ef3ccb1b4ff0','actual compiled reference source equals current')
 need(inv['runtime_library_pin_count']==46 and inv['executable']==source['executable'] and inv['runtime_table']==source['runtime_table'],'archived exact reference closure')
 need(review['status']=='PASS_READONLY_TERMINAL_REVIEW','independent terminal status')
 cases={c['case_id']:c for c in inv['cases']};need(set(cases)=={f'lw_{k:06d}' for k in range(1,7)},'inventory case roster')
 need([x['case_id'] for x in rec['calls']]==[f'lw_{k:06d}' for k in range(1,7)] and len({x['pid'] for x in rec['calls']})==6,'exact ordered unique calls')
 checks=[];maxima={}
 with tempfile.TemporaryDirectory(prefix='bon-reference-comparison-') as td:
  t=Path(td)
  for index,c in enumerate(rec['calls'],1):
   stem=c['case_id'];need(c['returncode']==0 and c['passed'] and not c['timed_out'] and c['pid']>0,'actual standalone PID/RC')
   need(c['argv'][0]==inv['executable']['path'] and c['argv'][1]==inv['data_dir'] and c['argv'][2]==c['input']['path'] and c['argv'][3]==c['result']['path'] and c['argv'][4:]==['1',''],'unmodified direct replay argv')
   parsed={};meta={}
   for kind in ['input','raw','result']:
    data=gzip.decompress((CAP/f'{stem}.{kind}.gz').read_bytes());p=t/f'{stem}.{kind}';p.write_bytes(data);meta[kind],parsed[kind]=read(p,kind)
    need(hashlib.sha256(data).hexdigest()==cases[stem][kind]['sha256'],'sibling exact production capture '+kind)
   need(c['input']==cases[stem]['input'] and c['production']==cases[stem]['result'],'exact input/production identity')
   b=gzip.decompress((PKG/f'reference/{stem}.result.gz').read_bytes());need(hashlib.sha256(b).hexdigest()==c['result']['sha256'] and len(b)==c['result']['size_bytes'],'actual reference result pin')
   p=t/(stem+'.reference.result');p.write_bytes(b);rm,ref=read(p,'result');prod=parsed['result'];raw=parsed['raw']
   need(meta['result']==rm=={'phase':'LW','ncol':1,'nlay':45} and meta['raw']['native_nlay']==32 and meta['raw']['i']==13 and meta['raw']['j']==46,'paired phase/native/engine header')
   need(set(ref)==ENGINE and set(prod)==ENGINE|EXTRAS,'24 engine sections plus3 explicitly WRF-only extras')
   archived=json.loads((PKG/f'comparisons/{stem}.json').read_text());need(sha(PKG/f'comparisons/{stem}.json')==c['comparison']['sha256'] and archived['passed'] and archived['sections_compared']==24 and archived['production_only_sections']==sorted(EXTRAS) and archived['reference_only_sections']==[],'archived comparator identity/roster')
   details={}
   for n in sorted(ENGINE):
    need(prod[n]['shape']==ref[n]['shape'],'paired section shapes '+n);d=compare_values(n,prod[n]['values'],ref[n]['values']);need(d==archived['max_differences'][n],'stdlib reproduction of unchanged comparator '+n);details[n]=d;maxima[n]=max(maxima.get(n,0.),d['max_abs'])
   mapping=mapping_checks(prod,raw);checks.append({'case_id':stem,'actual_pid':c['pid'],'returncode':0,'engine_sections_compared':24,'MASK_exact':True,'comparison_max_differences':details,'production_only_WRF_mapping':mapping})
 return {'schema':'bon-night-independent-replay-portable-verification-v1','status':'PASS_RETAINED_RESULTS_UNCHANGED_THRESHOLDS_AND_WRF_MAPPING','manifest_sha256':sha(PKG/'artifact-manifest.json'),'payload_count':len(files),'actual_original_standalone_calls':6,'new_WRF_REAL_build_solver_calls_from_verifier':0,'max_differences':maxima,'cases':checks,'physical_accuracy_or_optical_truth_proven':False,'external_ELF_library_data_contents_reopened':False,'scope':'Same-code/data direct library consistency at six held night states. 24 engine sections use unchanged comparator thresholds;3 extra WRF fields checked separately with exact default-REAL32 mapping. External build/library/source closure retained as attestation only.'}

def main():
 a=argparse.ArgumentParser();a.add_argument('--output',type=Path);args=a.parse_args();r=verify()
 if args.output:
  p=args.output.absolute();need(PKG not in p.parents,'output outside evidence');p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('x') as f:json.dump(r,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
 print(json.dumps({'status':r['status'],'payload_count':r['payload_count'],'calls':r['actual_original_standalone_calls'],'max_differences':r['max_differences']},sort_keys=True))
if __name__=='__main__':main()
