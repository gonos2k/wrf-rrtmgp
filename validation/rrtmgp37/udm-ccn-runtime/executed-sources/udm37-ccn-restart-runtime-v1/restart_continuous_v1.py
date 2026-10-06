#!/usr/bin/env python3
"""Prepare/run/compare the fresh CCN-init same-state restart contract.

This harness is separate from the frozen 3-hour runner. Its prepare/run entry
points are provided for the parent to use after the 3-hour OMP1/OMP2 arms pass.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, time
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
THREE_HOUR_RUNNER=ROOT/'build/udm37-ccn-current-runtime-v1/runtime.py'
THREE_HOUR_SHA='9d48cb124387a77363f7888b54e2dc876b94b497e293f32a157a37b0d1efd0aa'
EXPECTED_STAGE_SHA='383f613a567c57a5f6f2c1e814a50a86c78ad4ba7f43d0f3364a06a3aa8089ee'
STAGE_DEFAULT=ROOT/'build/udm37-ccn-current-runtime-v1/cases/stage-v3'
TIMES4=[f'2000-01-24_{h:02d}:00:00' for h in range(12,17)]
RESTART_TIMES=['2000-01-24_15:00:00','2000-01-24_16:00:00']

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

if hashlib.sha256(THREE_HOUR_RUNNER.read_bytes()).hexdigest()!=THREE_HOUR_SHA:
    raise RuntimeError('frozen three-hour runner changed')
rt=load(THREE_HOUR_RUNNER,'frozen_ccn_runtime')
m=rt.m

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def pin(path):return m.pin(Path(path))
def check_pin(x):return m.check_pin(x)
def assert_three_hour_stage(path=STAGE_DEFAULT,expected_sha=EXPECTED_STAGE_SHA):
    if sha(path/'stage.json')!=expected_sha:raise ValueError('three-hour stage pin changed')
    stage=json.loads((path/'stage.json').read_text())
    if stage['status']!='STAGED_NOT_RUN' or stage['model_invocations']!=0:raise ValueError('wrong parent stage contract')
    if stage['runner']['sha256']!=THREE_HOUR_SHA:raise ValueError('three-hour runner changed')
    rt.integrity.verify_build()
    rt.integrity.verify_donor_inputs()
    return stage

def validated_parent_arms(stage_root=STAGE_DEFAULT):
    stage=assert_three_hour_stage(stage_root)
    arms={}
    for arm in ('ra37-omp1','ra37-omp2'):
        e=stage['arms'][arm];recpath=Path(e['case_path'])/'execution.json'
        if not recpath.is_file():raise ValueError('three-hour arm has no result yet: '+arm)
        rec=json.loads(recpath.read_text())
        if rec.get('status')!='PASS' or rec.get('actual_model_invocations')!=1 or not rec.get('before_pins_valid') or not rec.get('after_pins_valid'):
            raise ValueError('three-hour parent arm is not accepted: '+arm)
        if rec.get('runner',{}).get('sha256')!=THREE_HOUR_SHA or rec.get('stage',{}).get('sha256')!=EXPECTED_STAGE_SHA:
            raise ValueError('three-hour parent receipt lineage differs')
        for fld in ('history','checkpoint'):
            check_pin(rec['outputs'][fld]['file'])
        cp=rec['outputs']['checkpoint']
        if not cp['passed'] or not cp['surface']['passed']:
            raise ValueError('three-hour parent checkpoint failed strict validity: '+arm)
        cp_path=Path(cp['file']['path'])
        if cp_path.name!='wrfrst_d01_2000-01-24_15:00:00':raise ValueError('wrong own 15:00 checkpoint')
        arms[arm]={'stage_entry':e,'receipt':pin(recpath),'execution':rec,'checkpoint':cp['file']}
    return stage,arms

def edit_namelist(original,kind):
    """Only run-clock/restart interval edits; reverse-check every changed byte."""
    text=original
    if kind=='continuous4':
        changes={'run_hours':('3','4'),'end_hour':('15','16'),'restart_interval':('180','60')}
        expect_restart='.false.'
    elif kind=='restart1h':
        changes={'run_hours':('3','1'),'start_hour':('12','15'),'end_hour':('15','16'),'restart_interval':('180','60')}
        expect_restart='.false.'
    else:raise ValueError(kind)
    for key,(before,after) in changes.items():
        pattern=r'(?im)^([ \t]*'+re.escape(key)+r'[ \t]*=[ \t]*)'+re.escape(before)+r'([ \t]*,?[ \t]*)$'
        text,n=re.subn(pattern,lambda mt:mt[1]+after+mt[2],text)
        if n!=1:raise ValueError(f'expected one original {key}={before}, found {n}')
    if kind=='restart1h':
        pattern=r'(?im)^([ \t]*restart[ \t]*=[ \t]*)\.false\.([ \t]*,?[ \t]*)$'
        text,n=re.subn(pattern,lambda mt:mt[1]+'.true.'+mt[2],text)
        if n!=1:raise ValueError('restart flag not uniquely false')
        if re.search(r'(?im)^\s*(override_restart_timers|write_hist_at_0h_rst)\s*=',text):
            raise ValueError('restart timer/history controls unexpectedly present')
        pattern=r'(?im)^([ \t]*restart_interval[ \t]*=[ \t]*60[ \t]*,[ \t]*)$'
        text,n=re.subn(pattern,lambda mt:mt[1]+'\n override_restart_timers = .true.,\n write_hist_at_0h_rst = .true.,',text)
        if n!=1:raise ValueError('restart flag insertion point not unique')
    # Reverse all requested clock changes; this guards accidental broad nml edits.
    reverse=text
    for key,(before,after) in changes.items():
        pattern=r'(?im)^([ \t]*'+re.escape(key)+r'[ \t]*=[ \t]*)'+re.escape(after)+r'([ \t]*,?[ \t]*)$'
        reverse,n=re.subn(pattern,lambda mt:mt[1]+before+mt[2],reverse)
        if n!=1:raise ValueError(f'cannot reverse {key}')
    if kind=='restart1h':
        reverse,n=re.subn(r'(?im)^\s*override_restart_timers\s*=\s*\.true\.\s*,\s*\n\s*write_hist_at_0h_rst\s*=\s*\.true\.\s*,\s*\n','',reverse)
        if n!=1:raise ValueError('cannot reverse explicit restart timer/history controls')
        reverse,n=re.subn(r'(?im)^([ \t]*restart[ \t]*=[ \t]*)\.true\.([ \t]*,?[ \t]*)$',lambda mt:mt[1]+'.false.'+mt[2],reverse)
        if n!=1:raise ValueError('cannot reverse restart flag')
    if reverse!=original:raise ValueError('namelist has unapproved byte changes')
    return text

def metadata(ds):return m.metadata(ds)

def raw_values(v,indices=None):
    v.set_auto_maskandscale(False);a=np.asarray(v[:])
    if indices is not None and 'Time' in v.dimensions:
        axis=v.dimensions.index('Time');a=np.take(a,indices,axis=axis)
    return a

def compare_series(candidate,continuous,indices,expected_start):
    """Compare candidate complete arrays to selected continuous times raw-bitwise."""
    with Dataset(candidate) as c,Dataset(continuous) as b:
        c.set_auto_maskandscale(False);b.set_auto_maskandscale(False)
        cmeta=metadata(c);bmeta=metadata(b)
        names_equal=set(c.variables)==set(b.variables)
        vars_out={};raw_ok=names_equal
        for name in sorted(set(c.variables)&set(b.variables)):
            ca=raw_values(c.variables[name]);ba=raw_values(b.variables[name],indices)
            dims_equal=list(c.variables[name].dimensions)==list(b.variables[name].dimensions)
            attrs_c={k:m.encoded_attribute(c.variables[name].getncattr(k)) for k in c.variables[name].ncattrs()}
            attrs_b={k:m.encoded_attribute(b.variables[name].getncattr(k)) for k in b.variables[name].ncattrs()}
            equal=ca.dtype==ba.dtype and ca.shape==ba.shape and ca.tobytes()==ba.tobytes()
            att_equal=attrs_c==attrs_b
            vars_out[name]={'dtype':ca.dtype.str,'shape':list(ca.shape),'raw_bytes_equal':equal,'dimensions_equal':dims_equal,'attributes_equal':att_equal}
            raw_ok &= equal and dims_equal and att_equal
        global_diffs={}
        for key in sorted(set(cmeta['global_attributes'])|set(bmeta['global_attributes'])):
            x=bmeta['global_attributes'].get(key);y=cmeta['global_attributes'].get(key)
            if x!=y:global_diffs[key]={'continuous':x,'restart':y}
        # Restarting changes the run anchor only; all other global/variable metadata is exact.
        start_expected=global_diffs.get('START_DATE')=={'continuous':m.encoded_attribute('2000-01-24_12:00:00'),'restart':m.encoded_attribute(expected_start)}
        unexplained={k:v for k,v in global_diffs.items() if k!='START_DATE'}
        dim_diffs={k:{'candidate':cmeta['dimensions'].get(k),'continuous':bmeta['dimensions'].get(k)}
                   for k in set(cmeta['dimensions'])|set(bmeta['dimensions'])
                   if cmeta['dimensions'].get(k)!=bmeta['dimensions'].get(k)}
        # Time record count necessarily differs in continuous and restarted files.
        only_time_dim=set(dim_diffs)<= {'Time'}
        non_time_dims={k:v for k,v in dim_diffs.items() if k!='Time'}
        meta_ok=(cmeta['data_model']==bmeta['data_model'] and only_time_dim and not non_time_dims and not unexplained and start_expected)
        return {'candidate':pin(candidate),'continuous':pin(continuous),'indices':indices,'variables':vars_out,
                'variable_names_equal':names_equal,'raw_all_variables_equal':bool(raw_ok),'global_attribute_differences':global_diffs,
                'expected_start_date_difference_only':start_expected,'unexplained_global_differences':unexplained,
                'dimension_differences':dim_diffs,'metadata_contract_passed':meta_ok,'passed':bool(raw_ok and meta_ok)}

def compare_checkpoint(candidate,continuous):
    with Dataset(candidate) as c,Dataset(continuous) as b:
        c.set_auto_maskandscale(False);b.set_auto_maskandscale(False)
        cm,bm=metadata(c),metadata(b);names=set(c.variables)==set(b.variables);vars_out={};raw_ok=names
        for name in sorted(set(c.variables)&set(b.variables)):
            ca=raw_values(c.variables[name]);ba=raw_values(b.variables[name])
            equal=ca.dtype==ba.dtype and ca.shape==ba.shape and ca.tobytes()==ba.tobytes()
            ad_c={k:m.encoded_attribute(c.variables[name].getncattr(k)) for k in c.variables[name].ncattrs()}
            ad_b={k:m.encoded_attribute(b.variables[name].getncattr(k)) for k in b.variables[name].ncattrs()}
            attrs_equal=ad_c==ad_b
            vars_out[name]={'dtype':ca.dtype.str,'shape':list(ca.shape),'raw_bytes_equal':equal,'attributes_equal':attrs_equal}
            raw_ok &= equal and attrs_equal and list(c.variables[name].dimensions)==list(b.variables[name].dimensions)
        diffs={k:{'continuous':bm['global_attributes'].get(k),'restart':cm['global_attributes'].get(k)}
               for k in set(cm['global_attributes'])|set(bm['global_attributes']) if cm['global_attributes'].get(k)!=bm['global_attributes'].get(k)}
        expected=diffs.get('START_DATE')=={'continuous':m.encoded_attribute('2000-01-24_12:00:00'),'restart':m.encoded_attribute('2000-01-24_15:00:00')}
        unexplained={k:v for k,v in diffs.items() if k!='START_DATE'}
        dims_equal=cm['dimensions']==bm['dimensions'];model_equal=cm['data_model']==bm['data_model']
        return {'candidate':pin(candidate),'continuous':pin(continuous),'variables':vars_out,'raw_all_variables_equal':bool(raw_ok),
                'global_attribute_differences':diffs,'expected_start_date_difference_only':expected,'unexplained_global_differences':unexplained,
                'dimensions_equal':dims_equal,'data_model_equal':model_equal,'passed':bool(raw_ok and expected and not unexplained and dims_equal and model_equal)}

def compare_continuous_prefix(short_history,long_history):
    """Exact first four records of 4h output versus completed 3h OMP2 history."""
    with Dataset(short_history) as a,Dataset(long_history) as b:
        a.set_auto_maskandscale(False);b.set_auto_maskandscale(False);am,bm=metadata(a),metadata(b)
        names=set(a.variables)==set(b.variables);vars_out={};raw_ok=names
        for name in sorted(set(a.variables)&set(b.variables)):
            aa=raw_values(a.variables[name]);bb=raw_values(b.variables[name],[0,1,2,3])
            same=aa.dtype==bb.dtype and aa.shape==bb.shape and aa.tobytes()==bb.tobytes()
            da=list(a.variables[name].dimensions)==list(b.variables[name].dimensions)
            aa_attr={k:m.encoded_attribute(a.variables[name].getncattr(k)) for k in a.variables[name].ncattrs()}
            bb_attr={k:m.encoded_attribute(b.variables[name].getncattr(k)) for k in b.variables[name].ncattrs()}
            at=same and aa_attr==bb_attr
            vars_out[name]={'raw_bytes_equal':same,'dimensions_equal':da,'attributes_equal':aa_attr==bb_attr}
            raw_ok &= same and da and aa_attr==bb_attr
        ga=am['global_attributes']==bm['global_attributes']
        da={k:v for k,v in am['dimensions'].items() if k!='Time'}=={k:v for k,v in bm['dimensions'].items() if k!='Time'}
        model_equal=am['data_model']==bm['data_model']
        time_diff=am['dimensions']['Time']['size']==4 and bm['dimensions']['Time']['size']==5
        return {'short_history':pin(short_history),'long_history':pin(long_history),'variables':vars_out,
                'raw_all_variables_equal':bool(raw_ok),'global_attributes_equal':ga,'data_model_equal':model_equal,'non_time_dimensions_equal':da,
                'expected_time_dimension_4_vs_5':time_diff,'passed':bool(raw_ok and ga and model_equal and da and time_diff)}

def run_env_for(threads):
    old=m._original.clean_run_env
    def clean(*args):
        env,cleared=old(*args)
        extras=[k for k in env if k.startswith(('WRF_UDM_','WRF_OMP_','GOMP_','KMP_'))]
        for k in extras:env.pop(k,None)
        env.update({'OMP_NUM_THREADS':str(threads),'OMP_DYNAMIC':'FALSE','OMP_MAX_ACTIVE_LEVELS':'1','OMP_NESTED':'FALSE','OMP_PROC_BIND':'FALSE','OPENBLAS_NUM_THREADS':'1'})
        return env,sorted(set(cleared+extras))
    return old,clean

def run_model(entry,args,threads,receipt_path,execute):
    if receipt_path.exists():raise FileExistsError('execution receipt collision: '+str(receipt_path))
    m.unused_case(entry,restart='checkpoint' in entry)
    if not execute:return {'status':'READY_NOT_RUN','model_invocations':0}
    r={'status':'RUNNING','actual_model_invocations':0,'entry':{'case_path':entry['case_path'],'threads':threads}}
    with receipt_path.open('x') as f:f.write(json.dumps(r,indent=2)+'\n')
    old,clean=run_env_for(threads)
    try:
        m._original.clean_run_env=clean
        def launched(pid):r.update(actual_model_invocations=1,process_group_pid=pid);m.write_json(receipt_path,r)
        r['model']=m.run_one(entry,args,on_launch=launched)
        r['status']='MODEL_PASS' if r['model']['model_completed'] else 'MODEL_FAIL_PRESERVED'
    except Exception as e:r.update(status='MODEL_FAIL_PRESERVED',error=f'{type(e).__name__}: {e}')
    finally:m._original.clean_run_env=old;m.write_json(receipt_path,r)
    return r

def outputs(entry):
    case=Path(entry['case_path']);hist=sorted(case.glob('wrfout_d01_*'));rst=sorted(case.glob('wrfrst_d01_*'))
    want_hist=TIMES4 if entry['kind']=='continuous4' else RESTART_TIMES
    want_rst='2000-01-24_16:00:00'
    if [p.name for p in hist]!=['wrfout_d01_'+t for t in [want_hist[0]]]:
        # WRF writes one history file containing all Time records.
        raise ValueError('expected one history file containing the exact requested Time series')
    rst=filter_restart_checkpoint_input(entry,case,rst)
    expected_rst=([f'wrfrst_d01_2000-01-24_{h:02d}:00:00' for h in range(13,17)] if entry['kind']=='continuous4' else ['wrfrst_d01_'+want_rst])
    if [p.name for p in rst]!=expected_rst:raise ValueError('wrong hourly checkpoint file set')
    h=m.validate_dataset(hist[0],want_hist,37);h['default_fill_check']=rt.base.default_fills(hist[0])
    checkpoint_checks=[]
    for p in rst:
        stamp=p.name.removeprefix('wrfrst_d01_')
        check=m.validate_dataset(p,[stamp],37)
        check['default_fill_check']=rt.base.default_fills(p);check['surface']=m.checkpoint_diagnostics(p)
        check['passed']=check['passed'] and check['variable_count']==664 and check['numeric_variable_count']==663 and check['default_fill_check']['passed'] and check['surface']['passed']
        checkpoint_checks.append({'file':pin(p),'validation':check})
    c=checkpoint_checks[-1]['validation']
    good=h['passed'] and h['variable_count']==225 and h['numeric_variable_count']==224 and h['default_fill_check']['passed'] and all(x['validation']['passed'] for x in checkpoint_checks)
    return {'passed':bool(good),'history':h,'checkpoint':c,'checkpoint_files':checkpoint_checks}

def filter_restart_checkpoint_input(entry,case,rst):
    """Remove only the immutable input checkpoint symlink from output discovery."""
    if entry['kind']!='restart1h':return rst
    checkpoint=entry['checkpoint'];cp_path=Path(checkpoint['path']).resolve(strict=True);cp_link=case/cp_path.name
    if not cp_link.is_symlink() or cp_link.resolve(strict=True)!=cp_path or pin(cp_path)!=checkpoint:
        raise ValueError('input checkpoint link/bytes changed')
    if sum(p.name==cp_path.name for p in rst)!=1:
        raise ValueError('expected precisely one retained input checkpoint symlink')
    return [p for p in rst if p.name!=cp_path.name]

def cli_status_ok(status):
    return status in ('READY_WAITING_FOR_3H_RA37_OMP1_OMP2_PASS','READY_RESTART_INPUTS_NOT_STAGED','READY_NOT_RUN','SELFTEST_PASS','STAGED_NOT_RUN','PASS')

def prepare(stage_root,go=False,three_hour_root=STAGE_DEFAULT):
    """Stage only when explicitly requested; this task calls preflight/selftest only."""
    stage_root=stage_root.resolve()
    if stage_root.exists():raise FileExistsError('restart stage path exists; preserve it')
    three_stage,parents=validated_parent_arms(three_hour_root)
    _,_,runargs=rt.base.parent()
    if not go:return {'status':'READY_RESTART_INPUTS_NOT_STAGED','source_arms':{k:v['receipt'] for k,v in parents.items()},'model_invocations':0}
    integrity=rt.integrity.verify_build()
    stage_root.parent.mkdir(parents=True,exist_ok=True);stage_root.mkdir()
    receipt={'schema':'udm37-ccn-restart-stage-v1','status':'STAGED_NOT_RUN','runner':pin(Path(__file__)),
             'three_hour_runner':pin(THREE_HOUR_RUNNER),'three_hour_stage':pin(three_hour_root/'stage.json'),
             'build_identity':integrity,'source_arms':{k:v['receipt'] for k,v in parents.items()},'arms':{},'model_invocations':0}
    try:
        for name,kind,threads,src_arm in [('continuous-omp2','continuous4',2,'ra37-omp2'),('restart-omp1','restart1h',1,'ra37-omp1'),('restart-omp2','restart1h',2,'ra37-omp2')]:
            source_entry=three_stage['arms'][src_arm];source_case=Path(source_entry['case_path']);case=stage_root/name;case.mkdir()
            for link in source_entry['link_names']:
                target=(source_case/link).resolve(strict=True)
                (case/link).symlink_to(target)
            source_nml=Path(source_entry['original_namelist']['path'])
            base3=rt.base.nml(source_nml.read_text())
            updated=edit_namelist(base3,kind)
            (case/'namelist.input').write_text(updated)
            e=dict(source_entry);e.update({'case_path':str(case),'threads':threads,'kind':kind,'original_namelist':pin(source_nml)})
            e['expected_history_times']=TIMES4 if kind=='continuous4' else RESTART_TIMES
            e['snapshot']=m.snapshot_case(e)
            if kind=='restart1h':
                cp=parents[src_arm]['checkpoint'];cp_path=Path(cp['path'])
                if not cp_path.is_file() or cp_path.name!='wrfrst_d01_2000-01-24_15:00:00':raise ValueError('wrong own-arm 15:00 restart checkpoint')
                (case/cp_path.name).symlink_to(cp_path);e['checkpoint']=cp;e['link_names']=sorted(list(e['link_names'])+[cp_path.name]);e['snapshot']=m.snapshot_case(e)
            receipt['arms'][name]=e
        for name,e in receipt['arms'].items():
            if m.snapshot_case(e)!=e['snapshot']:raise ValueError('staged case changed: '+name)
            m.unused_case(e,restart='checkpoint' in e)
        if rt.integrity.verify_build()!=integrity:raise ValueError('build changed while preparing restart cases')
        m.write_json(stage_root/'stage.json',receipt)
    except Exception as exc:
        m.write_json(stage_root/'stage-failure.json',{'status':'STAGE_FAIL_PRESERVED','error':f'{type(exc).__name__}: {exc}','model_invocations':0});raise
    return {'status':'STAGED_NOT_RUN','stage':pin(stage_root/'stage.json'),'arms':sorted(receipt['arms'])}

def stage_invariants(stage_root,stage_sha):
    p=stage_root/'stage.json'
    if sha(p)!=stage_sha:raise ValueError('restart stage digest mismatch')
    r=json.loads(p.read_text())
    if r['status']!='STAGED_NOT_RUN' or r['model_invocations']!=0:raise ValueError('restart stage already used')
    if r['runner']!=pin(Path(__file__)) or r['three_hour_runner']!=pin(THREE_HOUR_RUNNER):raise ValueError('restart runner chain changed')
    if rt.integrity.verify_build()!=r['build_identity']:raise ValueError('fresh binary/source/dependencies changed')
    assert_three_hour_stage()
    _,parents=validated_parent_arms()
    for key,pp in parents.items():
        if r['source_arms'][key]!=pp['receipt']:raise ValueError('own parent run changed: '+key)
    for name,e in r['arms'].items():
        if m.snapshot_case(e)!=e['snapshot']:raise ValueError('restart static case changed: '+name)
        if e['kind']=='restart1h':check_pin(e['checkpoint'])
    _,_,args=rt.base.parent()
    return r,args

def execute_arm(stage_root,stage_sha,arm,go=False):
    r,args=stage_invariants(stage_root,stage_sha);e=r['arms'][arm];out=stage_root/arm/'execution.json'
    if out.exists():raise FileExistsError('execution receipt exists; preserve it')
    if not go:return {'status':'READY_NOT_RUN','model_invocations':0}
    m.unused_case(e,restart='checkpoint' in e)
    before=rt.integrity.verify_build()
    result={'status':'RUNNING','runner':pin(Path(__file__)),'stage':pin(stage_root/'stage.json'),'arm':arm,'actual_model_invocations':0,'before_build_identity':before}
    with out.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    old,clean=run_env_for(e['threads'])
    try:
        m._original.clean_run_env=clean
        def launched(pid):result.update(actual_model_invocations=1,process_group_pid=pid);m.write_json(out,result)
        result['model']=m.run_one(e,args,on_launch=launched)
        result['outputs']=outputs(e)
        result['status']='PASS' if result['model']['model_completed'] and result['outputs']['passed'] else 'FAIL_PRESERVED'
    except Exception as exc:result.update(status='FAIL_PRESERVED',error=f'{type(exc).__name__}: {exc}')
    finally:
        m._original.clean_run_env=old
        try:
            stage_invariants(stage_root,stage_sha)
            result['after_build_identity']=rt.integrity.verify_build()
            result['after_pins_valid']=result['after_build_identity']==result['before_build_identity']
            if not result['after_pins_valid']:result['status']='FAIL_PRESERVED'
        except Exception as exc:result.update(status='FAIL_PRESERVED',after_pins_valid=False,pin_error=repr(exc))
        m.write_json(out,result)
    return result

def compare_all(stage_root,stage_sha):
    stage,args=stage_invariants(stage_root,stage_sha)
    results={}
    for arm in stage['arms']:
        p=stage_root/arm/'execution.json';r=json.loads(p.read_text())
        if r['status']!='PASS' or r.get('actual_model_invocations')!=1 or not r.get('after_pins_valid'):raise ValueError('all three accepted restart/continuous arms required')
        for f in ('history','checkpoint'):check_pin(r['outputs'][f]['file'])
        results[arm]=r
    cont=results['continuous-omp2']['outputs'];continuous_history=Path(cont['history']['file']['path']);continuous_cp=Path(cont['checkpoint']['file']['path'])
    pairs=[]
    three_stage=assert_three_hour_stage()
    three_hist=Path(three_stage['arms']['ra37-omp2']['case_path'])/'wrfout_d01_2000-01-24_12:00:00'
    pairs.append({'kind':'4h-continuous-first-three-hours-vs-3h-OMP2','field':'history',**compare_continuous_prefix(three_hist,continuous_history)})
    for arm in ('restart-omp1','restart-omp2'):
        out=results[arm]['outputs'];rh=Path(out['history']['file']['path']);rcp=Path(out['checkpoint']['file']['path'])
        pairs.append({'kind':'restart-history-vs-continuous-15-16','arm':arm,**compare_series(rh,continuous_history,[3,4],'2000-01-24_15:00:00')})
        pairs.append({'kind':'restart-checkpoint-vs-continuous-16','arm':arm,**compare_checkpoint(rcp,continuous_cp)})
    for field in ('history','checkpoint'):
        pairs.append({'kind':'OMP1-vs-OMP2-own-restart','field':field,**rt.base.compare_file(Path(results['restart-omp1']['outputs'][field]['file']['path']),Path(results['restart-omp2']['outputs'][field]['file']['path']))})
    result={'status':'PASS' if all(x['passed'] for x in pairs) else 'FAIL_PRESERVED','runner':pin(Path(__file__)),'stage':pin(stage_root/'stage.json'),'pairs':pairs}
    m.collision(stage_root/'comparison.json');m.write_json(stage_root/'comparison.json',result);return result

def selftest():
    """Manufactured NetCDF proves time-slice selection, exact bytes, and mutation rejection."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix='udm37-restart-selftest-') as td:
        d=Path(td); cont=d/'continuous.nc'; short=d/'short.nc'; short_badmodel=d/'short-badmodel.nc'; rst=d/'restart.nc'; bad=d/'bad.nc'; cp=d/'cp.nc'; cpc=d/'continuous_cp.nc'
        data=np.arange(15,dtype=np.float32).reshape(5,1,3)
        # Compact synthetic NetCDF histories exercise actual comparison routines.
        def nc(path,vals,start,fmt=None):
            ds=Dataset(path,'w',format=fmt) if fmt else Dataset(path,'w')
            with ds:
                ds.createDimension('Time',len(vals));ds.createDimension('x',3);ds.START_DATE=start
                v=ds.createVariable('state','f4',('Time','x'));v[:]=vals
        nc(cont,data[:,0,:],'2000-01-24_12:00:00');nc(short,data[:4,0,:],'2000-01-24_12:00:00');nc(rst,data[3:5,0,:],'2000-01-24_15:00:00')
        ok=compare_series(rst,cont,[3,4],'2000-01-24_15:00:00')
        if not ok['passed']:raise AssertionError('manufactured restart match rejected')
        prefix=compare_continuous_prefix(short,cont)
        if not prefix['passed']:raise AssertionError('manufactured continuous prefix rejected')
        nc(short_badmodel,data[:4,0,:],'2000-01-24_12:00:00',fmt='NETCDF3_CLASSIC')
        badmodel=compare_continuous_prefix(short_badmodel,cont)
        if badmodel['passed'] or badmodel['data_model_equal']:raise AssertionError('prefix data-model mismatch accepted')
        nc(cp,data[4:5,0,:],'2000-01-24_15:00:00');nc(cpc,data[4:5,0,:],'2000-01-24_12:00:00')
        checkpoint=compare_checkpoint(cp,cpc)
        if not checkpoint['passed']:raise AssertionError('manufactured checkpoint match rejected')
        nc(bad,np.array([[999,1,2],[12,13,14]],dtype=np.float32),'2000-01-24_15:00:00')
        no=compare_series(bad,cont,[3,4],'2000-01-24_15:00:00')
        if no['passed'] or no['raw_all_variables_equal']:raise AssertionError('corrupt restart fixture was accepted')
        # The input checkpoint is retained as a symlink and excluded from the
        # output file list only after its exact path and bytes are authenticated.
        casedir=d/'restart-case';casedir.mkdir();source_cp=d/'wrfrst_d01_2000-01-24_15:00:00';source_cp.write_bytes(b'checkpoint-fixture')
        link=casedir/source_cp.name;link.symlink_to(source_cp);newcp=casedir/'wrfrst_d01_2000-01-24_16:00:00';newcp.write_bytes(b'new-checkpoint')
        item={'kind':'restart1h','checkpoint':pin(source_cp)}
        selected=filter_restart_checkpoint_input(item,casedir,[link,newcp])
        if selected!=[newcp]:raise AssertionError('restart input checkpoint not excluded exactly')
        other=d/'other-checkpoint';other.write_bytes(b'wrong');link.unlink();link.symlink_to(other)
        try:filter_restart_checkpoint_input(item,casedir,[link,newcp])
        except ValueError:pass
        else:raise AssertionError('rebound input checkpoint link accepted')
        if not all(cli_status_ok(s) for s in ('PASS','STAGED_NOT_RUN','READY_NOT_RUN','SELFTEST_PASS')) or cli_status_ok('FAIL_PRESERVED'):
            raise AssertionError('CLI success/failure classification regression')
    return {'status':'SELFTEST_PASS','exact_series_match':True,'prefix_match':True,'checkpoint_match':True,'mutation_rejected':True,'data_model_mismatch_rejected':True,'input_checkpoint_binding_checked':True,'cli_statuses_checked':True,'model_invocations':0}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('preflight','selftest','prepare','run','compare'));ap.add_argument('--stage-root',type=Path);ap.add_argument('--stage-sha');ap.add_argument('--arm',choices=('continuous-omp2','restart-omp1','restart-omp2'));ap.add_argument('--prepare-go',action='store_true');ap.add_argument('--execute',action='store_true');a=ap.parse_args()
    if a.mode=='preflight':
        s,arms=validated_parent_arms()
        out={'status':'READY_WAITING_FOR_3H_RA37_OMP1_OMP2_PASS','stage':pin(STAGE_DEFAULT/'stage.json'),'parents':{k:v['receipt'] for k,v in arms.items()},'build':rt.integrity.verify_build(),'new_model_invocations':0}
    elif a.mode=='selftest':out=selftest()
    elif a.mode=='prepare':
        if a.stage_root is None:ap.error('--stage-root required')
        out=prepare(a.stage_root,a.prepare_go)
    elif a.mode=='run':
        if a.stage_root is None or a.stage_sha is None or a.arm is None:ap.error('--stage-root, --stage-sha and --arm required')
        out=execute_arm(a.stage_root,a.stage_sha,a.arm,a.execute)
    else:
        if a.stage_root is None or a.stage_sha is None:ap.error('--stage-root and --stage-sha required')
        out=compare_all(a.stage_root,a.stage_sha)
    print(json.dumps(out,indent=2));return 0 if cli_status_ok(out['status']) else 1
if __name__=='__main__':raise SystemExit(main())
