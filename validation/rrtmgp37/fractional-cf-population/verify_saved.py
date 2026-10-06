#!/usr/bin/env python3
"""Stdlib saved archive/source/packet joins only; no model, NetCDF or compiler."""
import argparse,gzip,hashlib,importlib.util,json,math,pathlib,re,shutil,struct,sys,tempfile
sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parent
HEAD='11623344baae090c621f796e93e5d98d78ea1fe0';TREE='8e9d6aea8d1fbfa59765bfd57eb880a7b726378b'
PARENTS={'positive-nc-stage':'a243f7ee893bf50358dcf67bb05924d76be5b5dd5ec0add5e10c2d67958088a1','positive-nc-activation':'4654a613cb91a0acafb41c74e646462df8457a6c1380156fef9470eeb652e305'}
AUTHOR={'README.md','origins.json','scope.json','source-contract.json','verify_saved.py','build/public-build-identity.json'}
SIDES={1:((23,1),(23,2),(1,45,1,25)),2:((68,99),(68,98),(46,90,76,99)),3:((1,74),(2,74),(1,45,51,75)),4:((90,26),(89,26),(46,90,26,50))}
def need(ok,msg):
 if not ok:raise ValueError(msg)
def sha(data):return hashlib.sha256(data).hexdigest()
def bytes_(rel):
 p=ROOT/rel;return gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes()
def load(rel):return json.loads(bytes_(rel))
def check_bytes(data,row):need(sha(data)==row['sha256'] and len(data)==row['size_bytes'],'SHA/size mismatch')
def safe(root,rel):
 r=pathlib.PurePosixPath(rel);need(bool(r.parts) and not r.is_absolute() and '..' not in r.parts,'unsafe payload path')
 p=root.joinpath(*r.parts);need(p.is_file() and not p.is_symlink(),'missing/nonregular payload')
 for q in p.parents:
  if q==root:break
  need(not q.is_symlink(),'symlink parent')
 return p
def roster():
 m=load('manifest.json');need(m['schema']=='FRACTIONAL_CF_ARCHIVE_V1','manifest schema');rows=m['payloads'];want={r['path'] for r in rows}
 need(m['payload_count']==len(rows)==len(want)==88,'payload count/duplicates')
 actual=set()
 for p in ROOT.rglob('*'):
  need(not p.is_symlink(),'package symlink')
  if p.is_file() and p!=ROOT/'manifest.json':actual.add(p.relative_to(ROOT).as_posix())
 need(actual==want,'closed payload roster')
 for r in rows:check_bytes(safe(ROOT,r['path']).read_bytes(),r)
 origins=load('origins.json')['origins'];need(len(origins)==len({o['path'] for o in origins})==82,'origin count')
 need({o['path'] for o in origins}==want-AUTHOR,'origin/authored roster')
 for o in origins:
  data=safe(ROOT,o['path']).read_bytes();need(sha(data)==o['stored_sha256'] and len(data)==o['stored_size_bytes'],'stored origin pin')
  if o['encoding']=='deterministic_lossless_gzip':need(data[4:8]==b'\0'*4,'gzip mtime');data=gzip.decompress(data)
  else:need(o['encoding']=='exact','unknown origin encoding')
  need(sha(data)==o['origin_sha256'] and len(data)==o['origin_size_bytes'],'lossless origin pin')
 return origins

def patch_apply(base,patch):
 source=base.decode().splitlines(keepends=True);p=patch.decode().splitlines(keepends=True);out=[];cursor=0;i=0;hunks=0
 while i<len(p):
  m=re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',p[i])
  if not m:i+=1;continue
  start=int(m[1])-1;oldn=int(m[2] or 1);newn=int(m[4] or 1);need(cursor<=start,'overlapping patch hunk');out.extend(source[cursor:start]);cursor=start;i+=1;oldused=newused=0;hunks+=1
  while i<len(p) and not p[i].startswith('@@ '):
   line=p[i];need(line[0] in ' +-','unexpected patch syntax');text=line[1:]
   if line[0] in ' -':need(cursor<len(source) and source[cursor]==text,'patch parent/context mismatch');cursor+=1;oldused+=1
   if line[0] in ' +':out.append(text);newused+=1
   i+=1
  need(oldused==oldn and newused==newn,'patch hunk extent')
 out.extend(source[cursor:]);need(hunks==5,'five observer-only patch hunks');return ''.join(out).encode()

def source():
 c=load('source-contract.json');need(c['runtime_source']=={'head':HEAD,'tree':TREE} and c['physics_equations_changed'] is False and c['scientific_accepted'] is False,'source identity/scope')
 required={'positive-nc-stage':{'source/module_mp_udm.F','source/module_microphysics_driver.F','source/module_model_constants.F'},'positive-nc-activation':{'source/module_physics_init.F.gz'}}
 need(set(c['parent_manifests'])==set(PARENTS) and set(c['parent_assets'])==set(required),'parent roster')
 for name,expected in PARENTS.items():
  parent=ROOT.parent/name;data=(parent/'manifest.json').read_bytes();need(sha(data)==expected,'frozen parent manifest SHA');check_bytes(data,c['parent_manifests'][name]);pm=json.loads(data);rows=pm['payloads'];mapping={x['path']:x for x in rows}
  need(len(mapping)==len(rows) and len(rows)==(67 if name=='positive-nc-stage' else 72),'parent count');need(pm.get('payload_count',len(rows))==len(rows),'declared parent count');need(set(c['parent_assets'][name])==required[name],'required parent asset roster')
  # Authenticate declared inherited bytes only; run no inherited numerical scripts.
  for path,row in mapping.items():check_bytes(safe(parent,path).read_bytes(),row)
  for path,row in c['parent_assets'][name].items():need(row==mapping[path],'parent source manifest join')
 base=(ROOT.parent/'positive-nc-stage/source/module_mp_udm.F').read_bytes();need(sha(base)==c['parent_UDM_sha256']=='9f25a1aaebd0d29ba3ecdf86c9fe65065cf920fc187bdfd904e8b8192bc7e3c8','parent UDM')
 patch=bytes_('source/fractional-cf-observer.patch.gz');need(sha(patch)==c['patch_origin_sha256'],'patch original SHA');new=patch_apply(base,patch)
 need(sha(new)==c['new_UDM_sha256']=='84f507242683661799ea61ccb80e614f9f2e856790d03d9485707e61f62b0b0b','reconstructed UDM SHA')
 text=new.decode();stripped=re.sub(r'^! BEGIN UDM_CF_POPULATION_OBSERVER\n.*?^! END UDM_CF_POPULATION_OBSERVER\n','',text,flags=re.M|re.S)
 need(stripped.encode()==base and text.count('! BEGIN UDM_CF_POPULATION_OBSERVER')==5,'marker strip exact physical parent')
 for phase in range(1,5):need(f'itimestep,{phase},loop,number_observer_tile' in text,'CF phase/source identity')
 implementation=load('source/implementation.json');need(implementation['marker_stripped_byte_equal'] is True and implementation['source']['sha256']==sha(new),'implementation source receipt')
 return sha(new)

def cf_number():
 spec=importlib.util.spec_from_file_location('saved_cf_validator',ROOT/'scripts/validate_cf_population.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 # The executed parser accepts CF and NUMBER files in one directory. Adapt only
 # the directory layout using exact copied bytes, leaving its source untouched.
 with tempfile.TemporaryDirectory(prefix='cf-saved-') as td:
  d=pathlib.Path(td)
  for folder,glob in [('cf','*.cfpop'),('number','*.raw')]:
   for p in (ROOT/'capture'/folder).glob(glob):shutil.copyfile(p,d/p.name)
  result=m.validate(d)
 saved=load('runtime/cf-packet-validation.json')
 for key in ('status','CF_packet_count','CF_row_count','NUMBER_packet_count','NUMBER_row_count','transformation_checks','unchanged_number_checks','predivision_NUMBER23_joins','return_helper_state_joins','discriminating_selected_levels','intervening_process_changes','helper'):
  need(result[key]==saved[key],'saved/recomputed CF relation '+key)
 need(result['status']=='PASS_DISCRIMINATING_FRACTIONAL_CF_SOURCE_RELATIONS' and result['transformation_checks']==1056 and result['unchanged_number_checks']==528,'actual fractionalCF gates/check counts')
 declared={pathlib.Path(x['path']).name:x for x in saved['packet_pins']};need(len(declared)==28,'CF/NUMBER saved packet count')
 for folder,glob in [('cf','*.cfpop'),('number','*.raw')]:
  for p in (ROOT/'capture'/folder).glob(glob):check_bytes(p.read_bytes(),declared[p.name])
 return {k:result[k] for k in ('CF_packet_count','CF_row_count','NUMBER_packet_count','NUMBER_row_count','transformation_checks','unchanged_number_checks','predivision_NUMBER23_joins','return_helper_state_joins','discriminating_selected_levels')}

def f(x):return struct.unpack('<f',struct.pack('<f',float(x)))[0]
def qnn():
 expected={(rank,tile,step,rk,side) for rank,tile,side in ((0,1,1),(1,2,4),(2,1,3),(3,2,2)) for step in (1,2) for rk in (1,2,3)};seen=set();branches={0:0,1:0}
 cap=load('runtime/capture-validation.json.gz');pins={x['path']:x for x in cap['packets']};files=list((ROOT/'capture/qnn').glob('*.raw'));need(len(files)==24,'QNN count')
 for p in files:
  check_bytes(p.read_bytes(),{'sha256':pins[p.name]['sha256'],'size_bytes':pins[p.name]['bytes']})
  match=re.fullmatch(r'qnn_d1_rank(\d+)_tile(\d+)_step([12])_rk([123])_side([1234])\.raw',p.name);need(match is not None,'QNN filename');rank,tile,step,rk,side=map(int,match.groups());key=(rank,tile,step,rk,side);need(key in expected and key not in seen,'QNN identity/duplicate');seen.add(key)
  lines=p.read_text().splitlines();dest,src,bounds=SIDES[side];need(len(lines)==46 and lines[0]=='UDM37QNNB1','QNN format')
  need(list(map(int,lines[1].split()))==[1,step,rk,rank,tile,side,*dest,1,44,32,*bounds],'QNN header')
  for k,line in enumerate(lines[2:],1):
   x=line.split();need(len(x)==18,'QNN row');level,branch,si,sj,valid=map(int,x[:5]);a=list(map(float,x[5:]));need(all(math.isfinite(z) and f(z)==z for z in a),'QNN native32/finite');vel,ccn,before,after,n0,n1,r0,r1,al,alb,total,rho,source=a
   need(level==k and valid==1 and branch==int(vel>=0 if side in (1,3) else vel<=0),'QNN branch');need(n0==n1 and r0==r1,'QNN readonly QNC/QNR')
   need((after==ccn==1.e8 and (si,sj,source)==(0,0,0.)) if branch else ((si,sj)==src and after==source),'QNN actual assignment')
   s=f(f(al)+f(alb));need(s>0 and total==s and rho==f(f(1)/s)>0,'QNN dryrho native operation');branches[branch]+=1
 need(seen==expected and cap['packet_count']==24 and cap['rows']==1056 and branches[1]==cap['inflow_rows']>0 and branches[0]==cap['outflow_rows'],'QNN roster/branch totals')
 return {'QNN_packets':24,'QNN_rows':1056,'inflow_rows':branches[1],'outflow_rows':branches[0]}

def receipts():
 e=load('runtime/execution.json.gz');plan=load('runtime/stage-plan.json');scope=load('scope.json');build=load('build/result.json');identity=load('build/public-build-identity.json');review=load('reviews/terminal-review.json');groups=load('runtime/root-process-group-postflight.json')
 need(e['status']=='PASS_PAIRED_FRACTIONAL_CF_OBSERVER_RUNTIME_SCOPED' and e['model_calls']==2 and e['scientific_accepted'] is False and e['inputs_before']==e['inputs_after'],'actual runtime scope/invariants')
 need(e['source']=={'head':HEAD,'tree':TREE} and all(plan['source'][k]==e['source'][k] for k in ('head','tree')),'runtime source head/tree')
 need(build['status']=='PASS_BUILD_INSTALL_SCOPED' and build['source_head']==identity['source_head']==HEAD and build['source_tree']==identity['source_tree']==TREE,'new build identity')
 need(len(build['processes'])==3 and all(x['actual_rc']==0 and x['reaped'] and not x.get('error') for x in build['processes']),'actual configure/build/install RC')
 check_bytes(bytes_('build/result.json'),plan['build_result']);need(identity['private_original_plan']['sha256']==plan['build_plan']['sha256'],'receipt-attested private buildplan pin')
 need(not any(x in identity for x in ('controlled_env','authorization','sessionMetadata','internalIPs')),'public build allowlist')
 need(plan['source']['selected_files']==e['selected_source_pins'],'runtime selected source pins')
 need(set(identity['source_files'])==set(e['selected_source_pins']),'public selected source roster')
 for n,row in identity['source_files'].items():need(all(row[k]==e['selected_source_pins'][n][k] for k in ('sha256','size_bytes')),'public/runtime selected source join')
 need(identity['source_files']['WRF/phys/module_mp_udm.F']['sha256']==load('source-contract.json')['new_UDM_sha256'],'actual reconstructed UDM/runtime pin')
 need(identity['configure_log_pin']=={k:build['processes'][0]['log'][k] for k in ('sha256','size_bytes')},'compiler readback actual log pin')
 need(identity['compiler_readback_from_configure_log'] and any('GNU' in x for x in identity['compiler_readback_from_configure_log']),'actual compiler identification readback')
 need(identity['explicit_configure_flags']==['-DWRF_CORE=ARW','-DWRF_CASE=EM_REAL','-DUSE_ALLOCATABLES=ON','-DUSE_MPI=ON','-DUSE_OPENMP=ON','-DUSE_IPO=OFF','-DFORCE_NETCDF_CLASSIC=ON'],'explicit build flags')
 check_bytes(bytes_('build/toolchain.cmake'),identity['toolchain'])
 need(set(identity['library_pins'])==set(e['library_pins']),'runtime library roster')
 for name,row in identity['library_pins'].items():need(all(row[k]==e['library_pins'][name][k] for k in ('sha256','size_bytes')),'actual library pin join')
 check_bytes(bytes_('scripts/run_once.py'),e['runner']);check_bytes(bytes_('runtime/stage-plan.json'),e['stage_pins']['stage-plan.json']);check_bytes(bytes_('scripts/validate_cf_population.py'),plan['cf_validator']);check_bytes(bytes_('scripts/verify_stage.py'),plan['stage_validator'])
 for arm in ('off','on'):
  a=e['arms'][arm];need(a['actual_rc']==0 and a['reaped'] is True and a['models']==1 and a['status']=='PASS_RUNTIME_SCOPED' and not a.get('timed_out') and not a.get('cleanup_errors') and not a.get('error'),'actual model terminal')
  need(len(e['inputs_before'][arm])==104 and all(e['inputs_before'][arm]['wrf.exe'][k]==build['executables']['wrf'][k]==identity['executables']['wrf'][k] for k in ('sha256','size_bytes')),'new actual executable join')
  need(e['inputs_before'][arm]==plan['cases'][arm]['files'] and e['inputs_before'][arm]['wrfinput_d01']['sha256']==plan['positive_input']['sha256']==scope['input']['sha256'],'104 same-arm input join')
 need(groups['execution_sha256']==sha(bytes_('runtime/execution.json.gz')) and groups['actual_rc']==[0,0] and groups['reaped']==[True,True] and groups['status']=='PASS_EMPTY_GROUPS' and not any(groups['process_group_members'].values()),'retained root group check')
 need(set(groups['process_group_members'])=={str(e['arms'][a]['pid']) for a in ('off','on')},'actual group PID roster')
 for a in ('off','on'):need(review['children'][a]['pid']==e['arms'][a]['pid'] and review['children'][a]['actual_rc']==0 and review['children'][a]['reaped'] is True,'independent actual child identity')
 check_bytes(bytes_('runtime/cf-packet-validation.json'),e['arms']['on']['number_validation']);check_bytes(bytes_('runtime/capture-validation.json.gz'),e['arms']['on']['capture_validation']);check_bytes(bytes_('runtime/history-source-join.json'),e['arms']['on']['history_source_join'])
 need(review['status']=='PASS_SCOPED_SAVED_RUNTIME_AUDIT' and review['execution_sha256']==sha(bytes_('runtime/execution.json.gz')) and review['postflight_sha256']==sha(bytes_('runtime/root-process-group-postflight.json')) and review['empty_process_groups'] is True and review['model_calls']==2,'independent terminal provenance')
 check_bytes(bytes_('reviews/independent-saved-check.py'),review['audit_script'])
 need(review['CF_source_relations']['mass_transform_checks']==1056 and review['CF_source_relations']['unchanged_number_checks']==528,'independent actual CF counts')
 outs=e['off_on_comparisons'];need(len(outs)==2 and len(review['full_output_pairs'])==2,'output pair count')
 for x,n,pair in zip(outs,(231,668),review['full_output_pairs']):
  need(x['left']['sha256']==x['right']['sha256']==pair['sha256'] and x['left']['size_bytes']==x['right']['size_bytes']==pair['size_bytes'] and pair['byte_identical'] is True and x['pass_exact'] is True,'wholefile independent hash/byte join')
  need(len(x['variables'])==n and all(v['arrays_exact'] for v in x['variables']) and all(not x[k] for k in ('array_mismatches','dimension_differences','global_attribute_differences','variable_attribute_differences')),'saved allvariables/schema/attrs exact')
 hj=load('runtime/history-source-join.json');need(hj['profile_checks']==616 and len(hj['joins'])==14 and all(x['exact'] and x['levels']==44 for x in hj['joins']),'saved bounded history/helper/CF profile joins')
 inp=load('input/input-variable-join.json');need(inp['schema_variables']==197 and inp['all_dimensions_and_attributes_unchanged'] is True and inp['other_196_variable_arrays_byte_equal'] is True and inp['qcloud_other_stored_elements_byte_equal'] is True and inp['python_index']==[0,6,1,22] and inp['changed_variable']=='QCLOUD','oneQC 197-variable receipt')
 need(inp['derived']['sha256']==scope['input']['sha256'] and sum(x['changed_stored_elements'] for x in inp['variables'])==1 and {x['name'] for x in inp['variables'] if x['changed_stored_elements']}=={'QCLOUD'},'QC oneelement source proof')
 need(scope['scientific_accepted'] is False and scope['actual_model_calls']==2,'physical nonapproval')
 return {'actual_root_models':2,'actual_model_rcs':[0,0],'history_variables':231,'restart_variables':668,'external_NetCDF':'Original independent byte/schema/array receipts authenticated; no NetCDF file opened in CI.'}

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=pathlib.Path);args=ap.parse_args()
 origins=roster();new=source();result={**cf_number(),**qnn(),**receipts(),'status':'PASS_SAVED_CF_ARCHIVE_SOURCE_AND_PACKET_RELATIONS','source_sha256':new,'payloads':88,'origin_copies':len(origins),'new_models':0,'new_compilers':0,'scientific_accepted':False,'scope':'Stdlib saved-source and immediate binary32 relations; NetCDF, original native build and physical units remain receipt-only/open as documented.'}
 if args.output:
  args.output.parent.mkdir(parents=True,exist_ok=True)
  with args.output.open('x') as out:out.write(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,sort_keys=True));return 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except (ValueError,KeyError,TypeError,OSError,OverflowError,AssertionError) as e:print('FAIL: '+str(e),file=sys.stderr);raise SystemExit(1)
