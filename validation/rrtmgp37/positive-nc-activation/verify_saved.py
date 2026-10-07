#!/usr/bin/env python3
"""Verify saved activation evidence only. No native code, model or NetCDF reader."""
import gzip, hashlib, json, math, pathlib, re, struct, sys
sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parent
PARENT_SHA='a243f7ee893bf50358dcf67bb05924d76be5b5dd5ec0add5e10c2d67958088a1'
HEAD='8017ff7caf8f979dc16e1d9119c9a88eaa362a2b'
TREE='eef44b724e452bd412431928bad1d26f15c6dab4'
STAGES={10:0,11:0,20:0,21:1,23:1,30:1,31:1,40:0,50:0,51:0}
AVAIL={10:0,11:0,20:0,21:17,23:17,30:17,31:29,40:0,50:0,51:2}
SIDES={1:((23,1),(23,2),(1,45,1,25)),2:((68,99),(68,98),(46,90,76,99)),3:((1,74),(2,74),(1,45,51,75)),4:((90,26),(89,26),(46,90,26,50))}
def need(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(rel):return json.loads((ROOT/rel).read_text())
def f(x):return struct.unpack('<f',struct.pack('<f',float(x)))[0]
def mul(a,b):return f(f(a)*f(b))
def add(a,b):return f(f(a)+f(b))
def sub(a,b):return f(f(a)-f(b))
def div(a,b):return f(f(a)/f(b))
def safe(root,rel):
    r=pathlib.PurePosixPath(rel);need(not r.is_absolute() and '..' not in r.parts and bool(r.parts),'unsafe relative path')
    p=root.joinpath(*r.parts);need(p.is_file() and not any(x.is_symlink() for x in [p,*p.parents] if x!=root.parent),'nonregular payload '+rel)
    return p
def checkpin(p,row):need(p.stat().st_size==row['size_bytes'] and sha(p)==row['sha256'],'pin mismatch '+str(p))
def roster():
    m=load('manifest.json');need(m['schema']=='POSITIVE_ACTIVATION_ARCHIVE_V1','manifest schema');rows=m['payloads']
    want={r['path'] for r in rows};need(m['payload_count']==len(want)==len(rows)==72,'manifest count/duplicates')
    actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p!=ROOT/'manifest.json'}
    need(want==actual,'closed roster mismatch')
    for r in rows:checkpin(safe(ROOT,r['path']),r)
    origins=load('origins.json')['origins'];need(len(origins)==67 and len({o['path'] for o in origins})==67,'origin count')
    authored={'README.md','origins.json','scope.json','source-contract.json','verify_saved.py'}
    need({o['path'] for o in origins}==want-authored,'origin roster')
    for o in origins:
        data=safe(ROOT,o['path']).read_bytes();need(hashlib.sha256(data).hexdigest()==o['stored_sha256'] and len(data)==o['stored_size_bytes'],'stored origin mismatch')
        if o['encoding']=='deterministic_lossless_gzip':
            need(data[4:8]==b'\0'*4,'gzip timestamp');data=gzip.decompress(data)
        else:need(o['encoding']=='exact','unknown origin encoding')
        need(hashlib.sha256(data).hexdigest()==o['origin_sha256'] and len(data)==o['origin_size_bytes'],'inflated/copy origin mismatch')
def source():
    c=load('source-contract.json');parent=ROOT.parent/'positive-nc-stage';need(c['parent_manifest_sha256']==PARENT_SHA==sha(parent/'manifest.json'),'parent manifest')
    need(c['runtime_source']=={'head':HEAD,'tree':TREE},'source head/tree')
    pm={r['path']:r for r in json.loads((parent/'manifest.json').read_text())['payloads']}
    for name,p in c['parent_assets'].items():need(p==pm[name],'parent asset manifest join');checkpin(safe(parent,name),p)
    text=gzip.decompress((ROOT/'source/module_physics_init.F.gz').read_bytes()).decode()
    need('calludminit(rhoair0,rhowater,rhosnow,cliq,cpv,ccn_conc,allowed_to_read)' in re.sub(r'\s+','',text).lower(),'udminit host argument join')
    u=(parent/'source/module_mp_udm.F').read_text();constants=(parent/'source/module_model_constants.F').read_text()
    for statement in ('cpm(k,i) = cpd*(1.-max(q(k,i),qmin)) + max(q(k,i),qmin)*cpv','xlv(k,i) = xlv0 - xlv1*(t(k,i)-t0c)','xlv1 = cl-cv','ncact(k) =min(ncact(k),max(ncr(k,i,1),0.)*rdtcld)','ncr(k,i,1) = max(ncr(k,i,1) - ncact(k)*dtcld, ccnmin)'):need(statement in u,'source statement '+statement)
    for name,value in [('r_d','287.'),('r_v','461.6'),('cliq','4190.'),('svpt0','273.15')]:need(re.search(r'::\s*'+name+r'\s*=\s*'+re.escape(value),constants,re.I),'host constant '+name)
    need(re.search(r'::\s*cpv\s*=\s*4\.\*r_v',constants,re.I),'CPV host expression')
    need(re.search(r'::\s*cp\s*=\s*7\.\*r_d/2\.',constants,re.I) and div(mul(f(7),f(287)),f(2))==f(1004.5),'CP host expression')
    return parent

def packets():
    saved=load('runtime/activation-packet-validation.json');resultpins={pathlib.Path(p['path']).name:p for p in saved['packet_pins']};need(len(resultpins)==20,'saved packet pins')
    seen={};files=sorted((ROOT/'capture/number').glob('*.raw'));need(len(files)==20,'number count')
    for p in files:
        m=re.fullmatch(r'number_d1_tile1_i23_j2_step([12])_stage(\d+)_sub([01])\.raw',p.name);need(m is not None,'number filename');step,stage,sb=map(int,m.groups());key=(step,stage,sb)
        need(stage in STAGES and sb==STAGES[stage] and key not in seen,'number identity duplicate/unknown')
        lines=p.read_text().splitlines();need(len(lines)==47 and lines[0]=='UDM37NUM1','number protocol');h=list(map(int,lines[1].split()));clock=list(map(float,lines[2].split()))
        need(h==[1,step,stage,sb,1,23,2,1,44,32,AVAIL[stage],int(step==1)] and clock==[float(step-1),60.,1e8],'number header/clock')
        a=[]
        for k,line in enumerate(lines[3:],1):
            row=line.split();need(len(row)==15 and int(row[0])==k,'number row');v=list(map(float,row[1:]));need(all(math.isfinite(x) and f(x)==x for x in v),'number nonfinite/nonreal32');a.append(v)
        checkpin(p,resultpins[p.name]);seen[key]=a
    need(set(seen)=={(s,g,b) for s in (1,2) for g,b in STAGES.items()},'number complete roster')
    need(saved['packet_count']==20 and saved['row_count']==880 and saved['scientific_accepted'] is False,'activation report scope/count')
    summaries=load('reviews/independent-saved-details.json')['selected_steps'];need(len(summaries)==2,'selected review steps')
    for step in (1,2):
        entry=seen[(step,21,1)][6];pre=seen[(step,30,1)][6];post=seen[(step,31,1)][6];s=summaries[step-1];v=saved['selected_source'][step-1]
        need(s['step']==v['step']==step and s['RH']==v['RH_source_replay'] and s['NC_ACT_observed']==post[11]==v['NC_ACT_RATE_m3_s'] and s['PC_ACT_observed']==post[12]==v['PC_ACT_RATE_kgkg_s'],'selected report packet join')
        if step==1:
            need(v['RH_source_replay']==1.0134907960891724 and v['RH_source_replay']>1.+f(.0048) and s['activation_fraction']==1. and post[11]>0 and post[12]>0,'positive saturated activation')
            base=mul(max(f(0),sub(add(pre[5],pre[6]),pre[6])),div(f(1),post[13]));cap=mul(max(pre[5],f(0)),div(f(1),post[13]));need(post[11]==min(base,cap) and base<cap,'saturated number rate/order and inactive second cap')
        else:need(v['RH_source_replay']<1. and post[11]==post[12]==0.,'step2 inactive')
        dt=post[13];dn=mul(post[11],dt);dm=mul(post[12],dt);q=max(entry[2],f(1e-15));cv=mul(f(4),f(461.6));cpm=add(mul(f(1004.5),sub(f(1),q)),mul(q,cv));lv=sub(f(2500000),mul(sub(f(4190),cv),sub(entry[0],f(273.15))))
        expected={5:max(sub(pre[5],dn),f(5e7)),6:max(add(pre[6],dn),f(.001)),2:max(sub(pre[2],dm),f(0)),3:max(add(pre[3],dm),f(0)),0:add(pre[0],mul(div(mul(post[12],lv),cpm),dt))}
        need(all(post[i]==x for i,x in expected.items()) and cpm==s['CPM_cached'] and lv==s['XLV_cached'],'source stored-state arithmetic')
        if step==1:need(sub(pre[5],dn)==0. and post[5]==5e7 and post[5]+post[6]-pre[5]-pre[6]==49999992.,'CCN floor behavior retained')
        for a,b in ((seen[(step,40,0)],seen[(step,50,0)]),(seen[(step,50,0)],seen[(step,51,0)])):need(all(x[:9]==y[:9] for x,y in zip(a,b)),'postreturn/helper state join')
        need(s['helper50_QC']==seen[(step,50,0)][6][3] and s['helper50_NC']==seen[(step,50,0)][6][6] and s['helper51_RE_cloud_m']==seen[(step,51,0)][6][10],'helper report join')
    positive=[(step,k+1) for step in (1,2) for k,r in enumerate(seen[(step,31,1)]) if r[11]>0]
    need(positive==[(1,7)],'positive rate roster')
    return {'number_packets':20,'number_rows':880,'positive_NC_ACT_step_k':positive}

def qnn():
    expected={(rank,tile,step,rk,side) for rank,tile,side in ((0,1,1),(1,2,4),(2,1,3),(3,2,2)) for step in (1,2) for rk in (1,2,3)};seen=set();branches={0:0,1:0};files=sorted((ROOT/'capture/qnn').glob('*.raw'));need(len(files)==24,'QNN count')
    cap=load('runtime/capture-validation.json');need(cap['packet_count']==24 and cap['rows']==1056,'QNN saved counts')
    for p in files:
        m=re.fullmatch(r'qnn_d1_rank(\d+)_tile(\d+)_step([12])_rk([123])_side([1234])\.raw',p.name);need(m is not None,'QNN filename');rank,tile,step,rk,side=map(int,m.groups());key=(rank,tile,step,rk,side);need(key in expected and key not in seen,'QNN key');seen.add(key)
        lines=p.read_text().splitlines();need(len(lines)==46 and lines[0]=='UDM37QNNB1','QNN schema');dest,src,bounds=SIDES[side];need(list(map(int,lines[1].split()))==[1,step,rk,rank,tile,side,*dest,1,44,32,*bounds],'QNN header')
        for k,line in enumerate(lines[2:],1):
            x=line.split();need(len(x)==18,'QNN row');level,branch,si,sj,valid=map(int,x[:5]);vel,ccn,a,z,n0,n1,r0,r1,al,alb,total,rho,source_value=map(float,x[5:]);need(level==k and valid==1 and all(math.isfinite(float(v)) for v in x[5:]),'QNN finite/key')
            inflow=vel>=0 if side in (1,3) else vel<=0;need(branch==int(inflow) and n0==n1 and r0==r1,'QNN branch/passivity')
            need((z==ccn==1e8 and (si,sj,source_value)==(0,0,0.)) if branch else ((si,sj)==src and z==source_value),'QNN original assignment/source')
            s=add(al,alb);need(s>0 and total==s and rho==div(f(1),s),'QNN dry density');branches[branch]+=1
    need(seen==expected and branches[1]==cap['inflow_rows'] and branches[0]==cap['outflow_rows'],'QNN roster/branch totals')
    return {'qnn_packets':24,'qnn_rows':1056,'inflow_rows':branches[1],'outflow_rows':branches[0]}

def receipts(parent):
    e=load('runtime/execution.json');plan=load('runtime/stage-plan.json');groups=load('runtime/root-process-group-postflight.json');scope=load('scope.json');review=load('reviews/terminal-review.json')
    need(e['status']=='PASS_PAIRED_ACTIVATION_OBSERVER_RUNTIME_SCOPED' and e['model_calls']==2 and e['scientific_accepted'] is False and e['inputs_before']==e['inputs_after'],'runtime status/input invariance')
    need(e['source']=={'head':HEAD,'tree':TREE} and all(plan['source'][k]==e['source'][k] for k in ('head','tree')),'runtime source identity')
    build=json.loads((parent/'receipts/build-result.json').read_text());need(build['status']=='PASS_BUILD_INSTALL_SCOPED' and build['source_head']==HEAD and build['source_tree']==TREE,'inherited actual build scope');checkpin(parent/'receipts/build-result.json',plan['build_result'])
    for rel,asset in [('WRF/phys/module_microphysics_driver.F','source/module_microphysics_driver.F'),('WRF/phys/module_mp_udm.F','source/module_mp_udm.F'),('WRF/share/module_model_constants.F','source/module_model_constants.F')]:checkpin(parent/asset,e['selected_source_pins'][rel])
    init=load('source-contract.json')['host_physics_init'];need(init['origin_sha256']==e['selected_source_pins']['WRF/phys/module_physics_init.F']['sha256'] and init['origin_size_bytes']==e['selected_source_pins']['WRF/phys/module_physics_init.F']['size_bytes'],'host initializer runtime source pin')
    checkpin(ROOT/'scripts/run_once_v4.py',e['runner']);checkpin(ROOT/'runtime/stage-plan.json',e['stage_pins']['stage-plan.json'])
    for arm in ('off','on'):
        a=e['arms'][arm];need(a['actual_rc']==0 and a['reaped'] is True and a['models']==1 and a['status']=='PASS_RUNTIME_SCOPED','actual model RC/reap')
        need(all(e['inputs_before'][arm]['wrf.exe'][k]==build['executables']['wrf'][k] for k in ('sha256','size_bytes')),'actual runtime executable/build join')
        need(len(e['inputs_before'][arm])==104 and e['inputs_before'][arm]['wrfinput_d01']['sha256']==scope['input']['sha256']==plan['positive_input']['sha256'],'input arm pin')
    need(groups['execution_sha256']==sha(ROOT/'runtime/execution.json') and groups['all_recorded_groups_empty_at_postflight'] is True and groups['actual_model_RC']=={'off':0,'on':0} and all(not x for x in groups['checked_pgrp_members'].values()),'root process group postflight')
    checkpin(ROOT/'runtime/activation-packet-validation.json',e['arms']['on']['number_validation']);checkpin(ROOT/'runtime/capture-validation.json',e['arms']['on']['capture_validation'])
    outs=e['off_on_comparisons'];need(len(outs)==2,'output receipt count')
    for x,n,times in zip(outs,(231,668),(['2016-10-06_00:00:00','2016-10-06_00:01:00','2016-10-06_00:02:00'],['2016-10-06_00:02:00'])):
        need(x['left']['sha256']==x['right']['sha256'] and x['left']['size_bytes']==x['right']['size_bytes'] and x['pass_exact'] is True,'whole file pin equality')
        need(len(x['variables'])==n and all(v['arrays_exact'] for v in x['variables']) and all(not x[k] for k in ('array_mismatches','dimension_differences','global_attribute_differences','variable_attribute_differences')),'saved complete metadata/array passivity')
        joined=next(v for v in scope['external_outputs'] if v['kind']==pathlib.Path(x['left']['path']).name);need(joined['sha256']==x['left']['sha256'] and joined['variables']==n and joined['times']==times and joined['entire_file_exact'] is True,'independent NetCDF receipt join')
    need(review['status']=='PASS_SCOPED_TERMINAL_ACTIVATION_AND_PASSIVITY_REVIEW' and review['scientific_accepted'] is False,'independent terminal review scope');checkpin(ROOT/'runtime/execution.json',review['execution']);checkpin(ROOT/'reviews/independent-saved-details.json',review['independent_saved_details'])
    diff=load('input/input-diff.json');join=load('input/input-variable-join.json');need(diff['changed_element_count']==1 and diff['changed_variable_data_arrays']==['QVAPOR'] and diff['python_index_0based']==[0,6,1,22] and diff['target_rh']==1.003,'one-QV intervention receipt')
    need(join['variable_roster_count']==197 and join['variable_data_changes']==['QVAPOR'] and join['dimensions_equal'] and join['global_attributes_equal'] and join['variable_metadata_all_equal'],'full input receipt')
    need(diff['derived_input']['sha256']==scope['input']['sha256'] and scope['scientific_accepted'] is False and scope['observer_passivity_exact'] and scope['activation_observed'],'final scope')
    return {'actual_models':2,'history_variables':231,'restart_variables':668,'external_NetCDF':'Pinned original comparisons only; no external NetCDF files opened by this verifier.'}
def main():
    roster();parent=source();result={**packets(),**qnn(),**receipts(parent),'status':'PASS_SAVED_ACTIVATION_ARCHIVE_AND_SOURCE_STATE_JOINS','scientific_accepted':False,'scope':'Integrity, saved packet and binary32 stored-state arithmetic only; native/transcendental rate proof and NetCDF reads belong to pinned original reviews.'}
    print(json.dumps(result,sort_keys=True));return 0
if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,KeyError,TypeError,OSError,OverflowError) as e:print('FAIL: '+str(e),file=sys.stderr);sys.exit(1)
