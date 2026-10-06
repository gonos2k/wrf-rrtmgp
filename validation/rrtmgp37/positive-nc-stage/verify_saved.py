#!/usr/bin/env python3
"""Standard-library archive verifier for saved positive-Nc/QNN observer packets."""
import hashlib
import json
import math
import pathlib
import re
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parent
QNN_RE = re.compile(r"^qnn_d(\d+)_rank(\d+)_tile(\d+)_step(\d+)_rk(\d+)_side(\d+)\.raw$")
NUM_RE = re.compile(r"^number_d(\d+)_tile(\d+)_i(\d+)_j(\d+)_step(\d+)_stage(\d+)_sub(\d+)\.raw$")
NUM_STAGES = {10:0,11:0,20:0,21:1,23:1,30:1,31:1,40:0,50:0,51:0}
AVAIL = {10:0,11:0,20:0,21:17,23:17,30:17,31:29,40:0,50:0,51:2}
BOUNDARY = {1:((23,1),(23,2),(1,45,1,25)),2:((68,99),(68,98),(46,90,76,99)),
            3:((1,74),(2,74),(1,45,51,75)),4:((90,26),(89,26),(46,90,26,50))}


def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''): h.update(block)
    return h.hexdigest()

def load(p): return json.loads(p.read_text())
def f32(x): return struct.unpack('<f',struct.pack('<f',float(x)))[0]
def pincheck(p,row):
    return p.is_file() and not p.is_symlink() and p.stat().st_size==row['size_bytes'] and digest(p)==row['sha256']
def safe(rel):
    q=pathlib.PurePosixPath(rel)
    if q.is_absolute() or '..' in q.parts or not q.parts: raise ValueError('unsafe path '+rel)
    p=ROOT.joinpath(*q.parts)
    if p.is_symlink() or not p.is_file(): raise ValueError('missing/nonregular '+rel)
    return p

def verify_roster():
    m=load(ROOT/'manifest.json')
    if m.get('schema')!='POSITIVE_NC_STAGE_EVIDENCE_ARCHIVE_V1': raise ValueError('manifest schema')
    rows=m.get('payloads')
    if not isinstance(rows,list) or len({r.get('path') for r in rows})!=len(rows): raise ValueError('duplicate manifest path')
    expected={r['path'] for r in rows}
    actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p!=ROOT/'manifest.json'}
    if actual!=expected: raise ValueError(f'closed roster mismatch: missing={sorted(expected-actual)} extra={sorted(actual-expected)}')
    for r in rows:
        if not pincheck(safe(r['path']),r): raise ValueError('payload hash/size '+r['path'])
    origins=load(ROOT/'origins.json').get('origins',[])
    originmap={r['path']:r for r in origins}
    if len(originmap)!=len(origins): raise ValueError('duplicate origin record')
    authored={'README.md','verify_saved.py','origins.json','manifest.json','source/source-pins.json'}
    if set(originmap)!=expected-authored: raise ValueError('origin roster incomplete or extra')
    for rel,o in originmap.items():
        p=safe(rel)
        if digest(p)!=o['origin_sha256'] or p.stat().st_size!=o['origin_size_bytes']:
            raise ValueError('copy/origin mismatch '+rel)
    return m

def verify_source_and_sibling():
    sp=load(ROOT/'source/source-pins.json')
    if sp.get('schema')!='POSITIVE_NC_STAGE_SOURCE_AND_QNN_LINK_V1' or sp.get('base_pr139_head')!='36b55df1b2660dd6d110b8e4249c9ae53d409b4e': raise ValueError('source ancestry metadata')
    if sp.get('runtime_source_head')!='8017ff7caf8f979dc16e1d9119c9a88eaa362a2b' or sp.get('runtime_source_tree')!='eef44b724e452bd412431928bad1d26f15c6dab4': raise ValueError('runtime source identity')
    for rel,pin in sp['positive_number_source_pins'].items():
        p=safe('source/'+pathlib.PurePosixPath(rel).name)
        if not pincheck(p,pin): raise ValueError('source snapshot pin '+rel)
    sibling=ROOT.parent/'qnn-boundary-rk-observer'
    sm=load(sibling/'manifest.json')
    if digest(sibling/'manifest.json')!=sp['qnn_sibling_manifest_sha256']: raise ValueError('inherited QNN package manifest pin')
    if sm.get('schema')!='QNN_BOUNDARY_EVIDENCE_ARCHIVE_V1': raise ValueError('QNN sibling schema')
    return {'runtime_head':sp['runtime_source_head'],'runtime_tree':sp['runtime_source_tree'],'qnn_sibling_manifest_sha256':sp['qnn_sibling_manifest_sha256']}

def verify_qnn(result):
    files=sorted((ROOT/'capture/qnn').glob('*.raw'))
    expected={(rank,tile,step,rk,side) for rank,tile,side in ((0,1,1),(1,2,4),(2,1,3),(3,2,2)) for step in (1,2) for rk in (1,2,3)}
    seen=set();branches={0:0,1:0};rhos=[];rows=0
    resultpins={pathlib.Path(x['path']).name:x for x in result['qnn_boundary']['capture_pins']}
    if len(files)!=24 or len(resultpins)!=24: raise ValueError('QNN packet count')
    for p in files:
        m=QNN_RE.fullmatch(p.name)
        if not m: raise ValueError('QNN filename '+p.name)
        d,rank,tile,step,rk,side=map(int,m.groups());key=(rank,tile,step,rk,side)
        if d!=1 or key not in expected or key in seen: raise ValueError('QNN identity '+p.name)
        seen.add(key)
        lines=p.read_text().splitlines()
        if len(lines)!=46 or lines[0]!='UDM37QNNB1': raise ValueError('QNN magic/rows '+p.name)
        dest,source,bounds=BOUNDARY[side]
        h=list(map(int,lines[1].split()))
        if h != [1,step,rk,rank,tile,side,*dest,1,44,32,*bounds]: raise ValueError('QNN header '+p.name)
        pin=resultpins.get(p.name)
        if pin is None or not pincheck(p,pin): raise ValueError('QNN readback pin '+p.name)
        for k,line in enumerate(lines[2:],1):
            f=line.split()
            if len(f)!=18: raise ValueError('QNN row width '+p.name)
            ints=list(map(int,f[:5]));v=[float(x) for x in f[5:]]
            if ints[0]!=k or ints[4]!=1 or not all(math.isfinite(x) for x in v): raise ValueError('QNN row key/nonfinite '+p.name)
            _,branch,si,sj,_=ints
            vel,ccn,q0,q1,nc0,nc1,nr0,nr1,al,alb,total,rho,source_qnn=v
            if branch not in (0,1) or nc0!=nc1 or nr0!=nr1: raise ValueError('QNN passivity '+p.name)
            inflow=vel>=0 if side in (1,3) else vel<=0
            if branch!=int(inflow): raise ValueError('QNN flow branch '+p.name)
            if branch:
                if (si,sj,source_qnn)!=(0,0,0.) or ccn!=1e8 or q1!=ccn: raise ValueError('QNN inflow assignment '+p.name)
            elif (si,sj)!=source or q1!=source_qnn: raise ValueError('QNN outflow source copy '+p.name)
            s=f32(f32(al)+f32(alb)); r=f32(1./s)
            if s<=0 or total!=s or rho!=r: raise ValueError('QNN REAL32 density '+p.name)
            branches[branch]+=1;rhos.append(r)
        rows+=44
    if seen!=expected or rows!=1056: raise ValueError('QNN roster incomplete')
    if result['qnn_boundary']['row_count']!=1056 or result['qnn_boundary']['branches']!={'outflow':branches[0],'inflow':branches[1]}: raise ValueError('QNN result summary mismatch')
    return {'packets':len(files),'rows':rows,'inflow_rows':branches[1],'outflow_rows':branches[0],'rho_min':min(rhos),'rho_max':max(rhos)}

def parse_num(p):
    lines=p.read_text().splitlines()
    if len(lines)!=47 or lines[0]!='UDM37NUM1': raise ValueError('NUMBER magic/row count '+p.name)
    h=list(map(int,lines[1].split()));clock=[float(v) for v in lines[2].split()]
    rows=[]
    for k,line in enumerate(lines[3:],1):
        f=line.split()
        if len(f)!=15 or int(f[0])!=k: raise ValueError('NUMBER row shape/key '+p.name)
        vals=[float(v) for v in f[1:]]
        if not all(math.isfinite(v) and f32(v)==v for v in vals): raise ValueError('NUMBER nonfinite/non-REAL32 '+p.name)
        rows.append([int(f[0]),*vals])
    return h,clock,rows

def verify_number(result):
    files=sorted((ROOT/'capture/number').glob('*.raw'))
    exp={(s,g,u) for s in (1,2) for g,u in NUM_STAGES.items()}
    seen=set();packs={};positive_entry={};positive_helper={};resultpins={pathlib.Path(x['path']).name:x for x in result['number_stages']['packet_pins']}
    if len(files)!=20 or len(resultpins)!=20: raise ValueError('NUMBER packet count')
    for p in files:
        m=NUM_RE.fullmatch(p.name)
        if not m: raise ValueError('NUMBER filename '+p.name)
        d,tile,i,j,step,stage,sub=map(int,m.groups());key=(step,stage,sub)
        if (d,tile,i,j)!=(1,1,23,2) or key not in exp or key in seen: raise ValueError('NUMBER identity '+p.name)
        seen.add(key)
        h,clock,rows=parse_num(p)
        if h!=[1,step,stage,sub,1,23,2,1,44,32,AVAIL[stage],int(step==1)]: raise ValueError('NUMBER header '+p.name)
        if clock != [float(step-1),60.,1e8]: raise ValueError('NUMBER clock/CCN '+p.name)
        pin=resultpins.get(p.name)
        if pin is None or not pincheck(p,pin): raise ValueError('NUMBER readback pin '+p.name)
        packs[(step,stage,sub)]=rows
        if stage in (20,50):
            wet={r[0]:r[4]>0 and r[7]>0 for r in rows}
            (positive_entry if stage==20 else positive_helper)[step]=wet
    if seen!=exp: raise ValueError('NUMBER roster incomplete')
    # Step-1 initializer changes QNN at selected levels only; QC and QNC stay exact.
    for step in (1,2):
        before=packs[(step,10,0)];after=packs[(step,11,0)]
        if any(a[4]!=b[4] or a[7]!=b[7] for a,b in zip(before,after)): raise ValueError('initializer changed QC/QNC')
        changed=sum(a[6]!=b[6] for a,b in zip(before,after))
        if step==1 and (changed!=16 or any(b[6]!=f32(1e8) for b in after)): raise ValueError('step-1 CCN init')
        if step==2 and changed!=0: raise ValueError('step-2 unexpected QNN init')
        if any(r[12]!=0. or r[13]!=0. for r in packs[(step,31,1)]): raise ValueError('activation rates nonzero')
        if any(a[7]!=b[7] for a,b in zip(packs[(step,30,1)],packs[(step,31,1)])): raise ValueError('QNC changed across zero activation')
    overlaps=[]
    for step in (1,2):
        for k in range(1,45):
            if positive_entry[step][k] and positive_helper[step][k]: overlaps.append([step,k])
    if overlaps!=[[1,7],[1,18],[1,44],[2,44]]: raise ValueError('positive entry/helper joins')
    # Default REAL32 reproduction of the saved liquid-radius expression at stages 50/51.
    pi=f32(f32(4.)*math.atan(1.));pidnc=f32(f32(pi*f32(1000.))/f32(6.));obmr=f32(1./3.)
    active={}
    for step in (1,2):
        x=packs[(step,50,0)];y=packs[(step,51,0)];levels=[]
        for a,b in zip(x,y):
            if a[1:10]!=b[1:10]: raise ValueError('radius helper modified input state')
            qc,nc,den=a[4],a[7],a[9]
            rqc=max(f32(1e-12),f32(qc*den));rnc=max(f32(1e-6),f32(nc*den))
            re=f32(2.51e-6)
            if rqc>f32(1e-12) and rnc>f32(1e-6):
                ratio=f32(f32(pidnc*nc)/rqc);lam=f32(math.pow(ratio,obmr));re=max(f32(2.51e-6),min(f32(.5*f32(1./lam)),f32(50e-6)));levels.append(a[0])
            if b[11]!=re: raise ValueError('REAL32 radius expression differs')
        active[str(step)]=levels
    if active!={'1':[7,18,44],'2':[44]}: raise ValueError('radius active levels')
    saved=result['number_stages']
    if saved['packet_count']!=20 or saved['row_count']!=880 or saved['positive_QC_and_QNC_rows']['same_step_k_intersection']!=overlaps: raise ValueError('NUMBER result summary')
    if not saved['activation']['stage31_NC_ACT_RATE_all_zero'] or not saved['activation']['stage31_PC_ACT_RATE_all_zero'] or saved['liquid_radius']['physical_unit_authority'] is not False: raise ValueError('scope flags')
    return {'packets':len(files),'rows':880,'positive_entry_helper_step_k':overlaps,'activation':'NON_DISCRIMINATING_ACTIVATION_NOT_OCCURRED','radius_replay_all_levels':True,'active_levels':active}

def verify_outputs(result):
    expected={'wrfout_d01_2016-10-06_00:00:00':(231,136,['2016-10-06_00:00:00','2016-10-06_00:01:00','2016-10-06_00:02:00']),
              'wrfrst_d01_2016-10-06_00:02:00':(668,198,None)}
    outs=result['off_on_outputs']
    if set(outs)!=set(expected): raise ValueError('external output roster')
    for name,(nvars,nattrs,times) in expected.items():
        x=outs[name]
        if not x.get('whole_file_bytes_exact') or not x.get('all_variable_arrays_schema_and_attributes_exact'): raise ValueError('saved output compare gate '+name)
        if x['variable_count']!=nvars or x['global_attribute_count']!=nattrs: raise ValueError('output roster/attribute count '+name)
        if x['off']['sha256']!=x['on']['sha256'] or x['off']['size_bytes']!=x['on']['size_bytes']: raise ValueError('output byte pin disagreement '+name)
        if times is not None and x.get('Times')!=times: raise ValueError('history time sequence')
    return {k:{'sha256':v['off']['sha256'],'size_bytes':v['off']['size_bytes'],'variable_count':v['variable_count'],'global_attribute_count':v['global_attribute_count'],'byte_equal_off_on':True} for k,v in outs.items()}

def main():
    verify_roster()
    source=verify_source_and_sibling()
    result=load(ROOT/'receipts/readback-result.json')
    if result.get('status')!='PASS_SCOPED_SAVED_READBACK' or result.get('scientific_accepted') is not False: raise ValueError('readback scope/status')
    exe=load(ROOT/'receipts/runtime-execution.json')
    if exe.get('status')!='PASS_PAIRED_POSITIVE_NC_OBSERVER_RUNTIME_SCOPED' or exe.get('scientific_accepted') is not False or exe.get('model_calls')!=2: raise ValueError('runtime execution scope')
    for arm in ('off','on'):
        a=exe['arms'][arm]
        if a.get('actual_rc')!=0 or not a.get('reaped'): raise ValueError('runtime process completion '+arm)
    if exe.get('source')!={'head':source['runtime_head'],'tree':source['runtime_tree']}: raise ValueError('execution/source identity')
    prep=load(ROOT/'receipts/preparation-plan-v3.json')
    if prep.get('status')!='PREPARED_UNRUN_REQUIRES_ROOT_REVIEW': raise ValueError('preparation status')
    pre=load(ROOT/'receipts/prelaunch-review.json')
    if pre.get('status')!='PASS_SCOPED_PRELAUNCH': raise ValueError('prelaunch review status')
    build=load(ROOT/'receipts/build-result.json')
    if build.get('status')!='PASS_BUILD_INSTALL_SCOPED' or build.get('source_head')!=source['runtime_head'] or build.get('source_tree')!=source['runtime_tree']: raise ValueError('build/source join')
    prev=load(ROOT/'receipts/prior-j1-runtime-failure.json')
    if prev.get('status')!='FAIL_PRESERVED': raise ValueError('prior j1 failure chronology')
    q=verify_qnn(result);n=verify_number(result);out=verify_outputs(result)
    print(json.dumps({'status':'PASS_SCOPED_POSITIVE_NC_SAVED_EVIDENCE','scientific_accepted':False,'source':source,'qnn':q,'number':n,'external_off_on_outputs':out},sort_keys=True))
if __name__=='__main__': main()
