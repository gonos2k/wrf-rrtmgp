#!/usr/bin/env python3
"""Portable stdlib bundled-content checks; no unbundled NC/live dependency reopening."""
import argparse,csv,gzip,hashlib,importlib.util,json,math,struct,sys,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
PKG=Path(__file__).resolve().parent
REPO=PKG.parents[2]
ARMS=('OFF','ON_native4_0','ON_native4_1')
POINT={'domain':1,'i':13,'j':46,'step':721,'source_seconds':43200.}
CLOCKS=[(721+10*k,43200.+600*k) for k in range(6)]
CSV_HEADER='phase,domain,step,source_seconds,i,j,metric,value37,value4,sample_count,mean37,sd37,mean4,sd4,sd_delta,radius_mode,scope'.split(',')
EXPNAME='rrtmg4_d01_i13_j46_step721_lw.txt'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bit(x):return struct.pack('>d',float(x))
def bit32(x):return struct.pack('>f',float(x))
def same(a,b):return len(a)==len(b) and all(bit(x)==bit(y) for x,y in zip(a,b))
def need(ok,text):
 if not ok:raise ValueError(text)
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def closed_manifest():
 p=PKG/'artifact-manifest.json';m=json.loads(p.read_text());listed=[r['path'] for r in m['files']]
 need(len(listed)==len(set(listed)),'duplicate manifest paths')
 expected={'README.md','verify.py','test_verify.py','original-payload-roster.json','parser/read_export_context.py','frozen/run_bon_once.py','frozen/test_runner_offline.py','frozen/independent-review.py'}
 expected|={f'captures/OFF/lw_{k:06d}.{s}.gz' for k in range(1,7) for s in ['raw','input','result']}
 expected|={'exports/'+EXPNAME+'.gz'}|{f'csv/{a}-same_state.csv' for a in ARMS[1:]}|{f'inputs/{a}-namelist.input.gz' for a in ARMS}
 expected|={f'attestations/{n}' for n in ['independent-terminal-review.json','independent-terminal-README.md','independent-terminal-manifest.json','build-receipt.json','execution-receipt.json','runtime-build-identity.json','runtime-spec.json','readiness-index.json','root-execution-authorization.json','observed-export-selector.json','preflight.json','offline-controls.json']}
 actual={p.relative_to(PKG).as_posix() for p in PKG.rglob('*') if p.is_file() and p!=(PKG/'artifact-manifest.json')}
 need(set(listed)==actual==expected,'closed expected file roster mismatch')
 for r in m['files']:
  p=PKG/r['path'];need(not p.is_symlink() and len(p.read_bytes())==r['size_bytes'] and sha(p)==r['sha256'],'manifest digest/size '+r['path'])
 return m

def csv_rows(path,mode):
 with path.open(newline='') as f:
  d=csv.DictReader(f);need(d.fieldnames==CSV_HEADER,'CSV header');rows=list(d)
 indexed={};groups={}
 for x in rows:
  n={k:float(x[k]) for k in CSV_HEADER if k not in ['phase','metric','scope']}
  need(all(math.isfinite(v) for v in n.values()),'CSV finite')
  need(all(n[k].is_integer() for k in ['domain','step','i','j','radius_mode','sample_count']),'CSV integer context')
  ph=x['phase'].upper();clock=(int(n['step']),n['source_seconds']);point=(int(n['i']),int(n['j']))
  need(ph in ['LW','SW'] and clock in CLOCKS and point in [(13,46),(0,0)] and n['domain']==1 and n['sample_count']==128 and n['radius_mode']==mode and x['scope']=='selected_column','CSV context/clock/samples/radius')
  need(all(n[k]>=0 for k in ['sd37','sd4','sd_delta']),'CSV negative SD')
  key=(ph,*clock,*point,x['metric']);need(key not in indexed,'CSV duplicate');indexed[key]=x;groups.setdefault((ph,*clock,*point),set()).add(x['metric'])
 wantgroups={(ph,*c,*pt) for ph in ['LW','SW'] for c in CLOCKS for pt in [(13,46),(0,0)]}
 need(set(groups)==wantgroups,'CSV exact complete clocks and points')
 for g,names in groups.items():
  want={'SURFACE_DOWN','TOA_UP'}|{f'HEAT_{k}' for k in range(1,33)}|({'SW_NET','SW_DIRECT'} if g[0]=='SW' else set())
  need(names==want,'CSV complete metric roster')
 for key,x in indexed.items():
  need(all(float(x[n])==0 for n in ['sd37','sd4','sd_delta']),'observed nonzero seed spread')
  if key[0]=='SW':need(all(float(x[n])==0 for n in ['value37','value4','mean37','mean4']),'uncaptured night SW nonzero')
 return indexed

def validate_contents():
 manifest=closed_manifest();origin=json.loads((PKG/'original-payload-roster.json').read_text())
 origins={r['relative_path']:r for r in origin['files']};need(len(origins)==len(origin['files'])==40,'original payload count')
 for name,r in origins.items():
  data=(PKG/name).read_bytes();need(hashlib.sha256(data).hexdigest()==r['retained_sha256'] and len(data)==r['retained_size_bytes'],'retained original hash')
  if r['encoding']=='gzip':data=gzip.decompress(data)
  else:need(r['encoding']=='verbatim','encoding')
  need(hashlib.sha256(data).hexdigest()==r['original']['sha256'] and len(data)==r['original']['size_bytes'],'verbatim/decompressed original digest '+name)
 for d in origin['repository_parser_dependencies'].values():
  q=REPO/d['repository_relative_path'];need(sha(q)==d['sha256'] and q.stat().st_size==d['size_bytes'],'inherited repository parser pin')
 trace=load('bon_portable_trace_parser',REPO/origin['repository_parser_dependencies']['tracked_trace_parser']['repository_relative_path'])
 reader=load('bon_portable_context_reader',PKG/'parser/read_export_context.py')
 original=(REPO/origin['repository_parser_dependencies']['tracked_export_parser']['repository_relative_path']).read_text()
 expected=original.replace('expected_phase: str | None = None) -> dict:','expected_phase: str | None = None, expected_context: dict | None = None) -> dict:').replace('for key, value in CONTEXT.items():','for key, value in (CONTEXT if expected_context is None else expected_context).items():')
 need(expected==(PKG/'parser/read_export_context.py').read_text(),'only declared export-context adapter delta')
 def j(n):return json.loads((PKG/'attestations'/n).read_text())
 rec=j('execution-receipt.json');review=j('independent-terminal-review.json');build=j('build-receipt.json');identity=j('runtime-build-identity.json');spec=j('runtime-spec.json');auth=j('root-execution-authorization.json');sel=j('observed-export-selector.json')
 need(rec['status']=='PASS_BON_NIGHT_OUTPUT_CAPTURE_AUDIT_LW_EXPORT' and rec['model_invocations']==3 and rec['REAL_solver_build_invocations']==0,'exact actual forecast count/status')
 need(review['status']=='PASS_SCOPED_READONLY_TERMINAL' and review['actual_forecasts_this_campaign']==3,'independent attestation scope')
 need(review['frozen_inputs']['execution-receipt.json']['sha256']==sha(PKG/'attestations/execution-receipt.json'),'terminal original receipt join')
 need(build['status']=='BUILD_PASS' and build['returncode']==0 and build['build_invocations']==1 and build['model_invocations']==0,'build attestation')
 need(identity['snapshot']['build_receipt']['sha256']==sha(PKG/'attestations/build-receipt.json'),'build identity receipt join')
 need(identity['runtime_spec']['sha256']==sha(PKG/'attestations/runtime-spec.json') and identity['runner']['sha256']==sha(PKG/'frozen/run_bon_once.py'),'runtime source/spec joins')
 need(auth['runtime_identity_sha256']==sha(PKG/'attestations/runtime-build-identity.json') and auth['runtime_spec_sha256']==sha(PKG/'attestations/runtime-spec.json') and auth['runner_sha256']==sha(PKG/'frozen/run_bon_once.py') and rec['authorization']['sha256']==sha(PKG/'attestations/root-execution-authorization.json'),'authorization joins')
 need(identity['snapshot']['source_head']==origin['source_provenance']['source_head']==build['source_checks']['source_head']=='f731bb993a86a1836a64152d9b936edb7c315c19','executed source identity')
 need(len(identity['snapshot']['runtime_libraries'])==48,'recorded library closure count')
 need(sel['selector']==POINT and sel==rec['selector'],'selected actual first LW clock')
 for arm in ARMS:
  a=rec['arms'][arm];need(a['status']=='PASS_ARM' and a['actual_invocations']==1 and a['returncode']==0 and not a['timed_out'] and not a['process_error'],'per-arm actual outcome')
  need(a['master_stack_limit_bytes'][0]==536870912 and a['log_validation']['success_ranks_deduplicated']==[0],'stack/serial success attestation')
 need(len({rec['arms'][a]['pid'] for a in ARMS})==3,'distinct actual PIDs')
 need(len(review['full_output_quality'])==9 and len(review['full_output_comparisons'])==6,'unbundled numerical attestation roster')
 for x in review['full_output_quality']:need(x['variables']==(667 if 'wrfrst' in x['file']['path'] else 225) and x['raw_decoded_finite_no_fill_or_mask'],'unbundled quality attestation')
 for x in review['full_output_comparisons']:need(x['status']=='PASS_EXACT' and x['raw_schema_dtype_dimensions_all_attributes_data_model_equal'],'unbundled exact attestation')
 for arm in ARMS[1:]:
  need(rec['arms'][arm]['outputs']=={k:{**v,'path':rec['arms'][arm]['outputs'][k]['path']} for k,v in rec['arms']['OFF']['outputs'].items()},'unbundled output SHA/size attestation equality')
 namelists=[gzip.decompress((PKG/f'inputs/{a}-namelist.input.gz').read_bytes()) for a in ARMS];need(namelists[0]==namelists[1]==namelists[2],'same namelist all arms')
 rows0=csv_rows(PKG/'csv/ON_native4_0-same_state.csv',0);rows1=csv_rows(PKG/'csv/ON_native4_1-same_state.csv',1);need(set(rows0)==set(rows1),'CSV radius keysets')
 for k,x in rows0.items():
  need(all(bit(float(x[n]))==bit(float(rows1[k][n])) for n in ['value37','value4','mean37','mean4','sd37','sd4','sd_delta']),'radius-mode numeric equality')
  agg=(k[0],k[1],k[2],0,0,k[-1]);need(all(bit(float(x[n]))==bit(float(rows0[agg][n])) for n in ['value37','value4','mean37','mean4','sd37','sd4','sd_delta']),'single selected-column aggregate equality')
 states=[];parsed={}
 with tempfile.TemporaryDirectory(prefix='bon-bundled-reader-') as td:
  temp=Path(td)
  for index,(step,sec) in enumerate(CLOCKS,1):
   group={};metas={}
   for kind in ['raw','input','result']:
    name=f'lw_{index:06d}.{kind}';rel=f'captures/OFF/{name}.gz';raw=gzip.decompress((PKG/rel).read_bytes());p=temp/name;p.write_bytes(raw)
    meta,data=trace.read_trace(p,kind);group[kind]=data;metas[kind]=meta
    need(meta['phase']=='LW' and (meta.get('ncol',1)==1),'LW selected column schema')
    for arm in ARMS:
     g=rec['arms'][arm]['captures'][index-1];need(g['phase']=='LW' and g['step']==step and g['source_seconds']==sec and g['files'][kind]['sha256']==hashlib.sha256(raw).hexdigest(),'cross-arm archived capture digest join')
   need(metas['raw']['i']==13 and metas['raw']['j']==46 and metas['raw']['native_nlay']==32 and metas['input']['nlay']==metas['result']['nlay']==45,'native/engine dimensions')
   i=group['input'];r=group['result'];w=group['raw'];need(w['RADIATION_STEP']['values']==[float(step)] and w['SOURCE_TIME_SECONDS']['values']==[sec],'actual clock join')
   need(all(not any(i[n]['values']) for n in ['CF','LWP','IWP','SWP','RWP','CU_LWP','CU_IWP']),'inactive cloud/CU/precip paths')
   need(all(not any(r[n]['values']) for n in ['MASK','NATIVE_CLOUD_TAU','CU_CLOUD_TAU','PRECIP_TAU','PREPARED_TAU']),'inactive masks/optics')
   for n in ['DN','UP','HR']:need(same(r[n]['values'],r[{'DN':'DNC','UP':'UPC','HR':'HRC'}[n]]['values']),'allsky/clear captured bits')
   need(i['CF']['shape']==(1,45) and i['PLEV']['shape']==(1,46) and i['PLAY']['shape']==(1,45),'input shape')
   need(all(x>y for x,y in zip(i['PLEV']['values'],i['PLEV']['values'][1:])),'bottom-up pressure monotonic')
   need(i['FROZEN_MODE']['values']==[1.] and i['ICE_ROUGHNESS']['values']==[1.],'experimental settings')
   outidx=0
   surface=float(rows0['LW',step,sec,13,46,'SURFACE_DOWN']['value37']);need(bit32(surface)==bit32(r['DN']['values'][outidx]),'CSV vs actual GP surface REAL32 boundary')
   need(bit32(float(rows0['LW',step,sec,13,46,'TOA_UP']['value37']))==bit32(r['UP']['values'][-1]),'CSV GP TOA boundary')
   parsed[step]=group;states.append({'step':step,'source_seconds':sec,'cloud_paths_masks_tau_zero':True,'frozen_tau_max':max(r['FROZEN_TAU']['values']),'GWP_max_g_m2':max(i['GWP']['values']),'HWP_max_g_m2':max(i['HWP']['values']),'input_raw_result_sections':[len(i),len(w),len(r)]})
  p=temp/EXPNAME;p.write_bytes(gzip.decompress((PKG/'exports'/ (EXPNAME+'.gz')).read_bytes()));exp=reader.read_export(p,expected_phase='LW',expected_context=POINT);f=exp['fields'];inp=parsed[721]['input'];result=parsed[721]['result']
  mapping={'PLAY':'PLAY','PLEV':'PLEV','TLAY':'TLAY','TLEV':'TLEV','TSFC':'TSFC','H2O_VMR':'H2O','CO2_VMR':'CO2','O3_VMR':'O3','N2O_VMR':'N2O','CH4_VMR':'CH4','O2_VMR':'O2','CFC11_VMR':'VMR_CFC11','CFC12_VMR':'VMR_CFC12','CFC22_VMR':'VMR_CFC22','CCl4_VMR':'VMR_CCL4','SURFACE_EMISSIVITY':'EMIS'}
  for legacy,gp in mapping.items():need(same(f['INPUT',legacy].values,inp[gp]['values']),'mandatory IEEE64 input join '+legacy)
  for n in ['MCICA_MASK','CLDPRMC_TAU','RRTMG_INPUT_CLOUD_TAU']:need(not any(f['CLOUD',n].values),'legacy cloud zero')
  need(same(f['RESULT','DOWN_FLUX'].values,f['RESULT','DOWN_CLEAR_FLUX'].values),'legacy allsky/clear downward')
  need(bit32(float(rows0['LW',721,43200.,13,46,'SURFACE_DOWN']['value4']))==bit32(f['RESULT','DOWN_FLUX'].values[0]),'CSV selected legacy surface boundary')
  need(bit32(float(rows0['LW',721,43200.,13,46,'TOA_UP']['value4']))==bit32(f['RESULT','UP_FLUX'].values[-1]),'CSV selected legacy TOA boundary')
  legacy=f['INPUT','COLDry'].values;gp=result['GAS_COL_DRY']['values'];need(len(legacy)==len(gp)==45 and all(x>0 for x in legacy+tuple(gp)),'molecular dry column size/positive')
  ratios=[x/y for x,y in zip(legacy,gp)]
 surface=[];heat=[]
 for step,sec in CLOCKS:
  x=rows0['LW',step,sec,13,46,'SURFACE_DOWN'];surface.append({'step':step,'source_seconds':sec,'engine37_W_m2':float(x['value37']),'engine4_W_m2':float(x['value4']),'delta37_minus4_W_m2':float(x['value37'])-float(x['value4'])})
  heat.extend(abs(float(rows0['LW',step,sec,13,46,f'HEAT_{k}']['value37'])-float(rows0['LW',step,sec,13,46,f'HEAT_{k}']['value4'])) for k in range(1,33))
 need(surface==review['surface_LW_W_m2'],'recomputed surface table vs independent review')
 need(max(heat)==review['native_heating_delta_K_day_max_abs'],'recomputed heating contrast vs attestation')
 ratio_native=[min(ratios[:32]),max(ratios[:32])];ratio_ext=[min(ratios[32:]),max(ratios[32:])]
 need(ratio_native==review['selected_legacy_LW_export']['legacy_over_GP_native32_dry_column_ratio_range'] and ratio_ext==review['selected_legacy_LW_export']['legacy_over_GP_extension13_dry_column_ratio_range'],'dry ratios recomputation')
 return {'schema':'bon-night-portable-content-verification-v1','status':'PASS_BUNDLED_CONTENT_AND_ARCHIVED_ATTESTATION_JOINS','manifest_sha256':sha(PKG/'artifact-manifest.json'),'payload_count':len(manifest['files']),'original_payload_count':len(origins),'actual_forecasts_recorded':3,'new_forecasts_REAL_solver_build_calls':0,'capture_triples':6,'native_layers':32,'engine_layers':45,'LW_export_field_count':len(f),'IEEE64_input_joins':len(mapping),'CSV_rows_per_arm':len(rows0),'128_samples_SD_zero_radius_numeric_equal':True,'surface_LW_W_m2':surface,'surface_delta_range_W_m2':[min(x['delta37_minus4_W_m2'] for x in surface),max(x['delta37_minus4_W_m2'] for x in surface)],'native_heating_max_abs_delta_K_day':max(heat),'legacy_over_GP_dry_column_ratio_native':ratio_native,'legacy_over_GP_dry_column_ratio_extensions':ratio_ext,'call_states':states,'unbundled_NetCDF_source_ELF_library_arrays_reopened':False,'scope':'Bundled captures/CSV/export recomputed. Full forecast output/source/dependency preservation is archived independent attestation; no optical truth, observational accuracy or complete causal resolution.'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path);a=p.parse_args();r=validate_contents()
 if a.output:
  out=a.output.absolute();need(PKG not in out.parents and out!=PKG,'output must be outside immutable evidence');out.parent.mkdir(parents=True,exist_ok=True)
  with out.open('x') as f:json.dump(r,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
 print(json.dumps(r,sort_keys=True,allow_nan=False))
if __name__=='__main__':main()
