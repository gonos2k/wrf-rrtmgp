#!/usr/bin/env python3
"""Saved-output-only recovery of the v2 QNN boundary observer packet parse.

This script never launches WRF. It checks the authenticated Registry boundary
coordinates against the already completed v2 OFF/ON histories, restarts, and
packets, then writes a compact scoped receipt.
"""
import argparse, hashlib, importlib.util, json, os, pathlib, re, sys
import numpy as np
from netCDF4 import Dataset

BASE=pathlib.Path(__file__).resolve().parent.parent
STAGE=BASE/'build/udm37-qnn-boundary-runtime-2min-v2/stage'
RUNNER=BASE/'build/udm37-qnn-boundary-runtime-2min-runner-v2.py'
SOURCE=BASE/'build/udm37-qnn-boundary-observer-source-v1'
STOCH=SOURCE/'WRF/Registry/registry.stoch'
SCHEMA=BASE/'build/udm37-qnn-boundary-observer-implementation-v1/schema.json'
REGISTRY=SOURCE/'WRF/Registry/Registry.EM_COMMON'

def sha(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def pin(p):
    p=pathlib.Path(p)
    return {'path':str(p.resolve()),'sha256':sha(p),'size_bytes':p.stat().st_size,
            'link':os.readlink(p) if p.is_symlink() else None}
def atomic(p,obj):
    p=pathlib.Path(p);tmp=p.with_name(p.name+'.tmp')
    with tmp.open('x') as f:
        json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,p);fd=os.open(p.parent,os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args()
    out=a.output.resolve()
    if out.exists():raise FileExistsError(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    stageplan=STAGE/'stage-plan.json';execpath=STAGE/'execution.json'
    plan=json.loads(stageplan.read_text());execution=json.loads(execpath.read_text())
    spec=importlib.util.spec_from_file_location('qnn_v2_saved_helpers',RUNNER)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    # Packet coordinates are the observer destinations and remain the frozen
    # solve_em selections. The fourth tuple is the branch source: Registry
    # spec_zone=1 gives the adjacent interior source coordinate.
    helper.EXPECTED_COLUMNS={
      (0,1):(0,1,23,1,'Y-start',(1,45,1,25),(23,2)),
      (1,4):(1,4,90,26,'X-end',(46,90,26,50),(89,26)),
      (2,3):(2,3,1,74,'X-start',(1,45,51,75),(2,74)),
      (3,2):(3,2,68,99,'Y-end',(46,90,76,99),(68,98)),
    }
    checks={}
    if pin(stageplan)!=execution['stage_pins']['stage-plan.json']:
        raise ValueError('stage plan differs from failed-runner receipt')
    if pin(RUNNER)!=plan['runner'] or pin(RUNNER)!=execution['runner']:
        raise ValueError('v2 runner pin mismatch')
    if execution.get('status')!='FAIL_PRESERVED' or execution.get('model_calls')!=2:
        raise ValueError('expected the preserved two-call v2 parser failure')
    for arm in ('off','on'):
        row=execution['arms'][arm]
        if row.get('actual_rc')!=0 or row.get('reaped') is not True or row.get('timed_out'):
            raise ValueError(f'{arm} was not a completed RC0/reaped arm')
        if row.get('models')!=1:raise ValueError(f'{arm} model count mismatch')
        cases=plan['cases'][arm]
        for name,expected in cases['files'].items():
            actual=pin(STAGE/arm/name)
            if actual!=expected:raise ValueError(f'{arm}/{name} staged input pin changed')
        files=[STAGE/arm/casesname for casesname in ('wrfout_d01_2016-10-06_00:00:00',
                                                      'wrfrst_d01_2016-10-06_00:02:00')]
        if [p.name for p in files]!=[cases['expected_history_file'],cases['expected_restart']]:
            raise ValueError(f'{arm}: expected output naming is inconsistent')
        recorded={x['path']:x for x in row.get('outputs',[])}
        for p in files:
            rec=recorded.get(str(p.resolve()))
            if rec is None or pin(p)!=rec:raise ValueError(f'{arm}/{p.name} output pin differs from execution receipt')
        checks[arm]={'rc':row['actual_rc'],'reaped':row['reaped'],'pid':row.get('pid'),
                     'outputs':[pin(p) for p in files]}
    # Recheck immutable source/build/library closure from the saved run receipt.
    sourcepins={n:pin(SOURCE/n) for n in plan['source']['selected_files']}
    if sourcepins!=execution['selected_source_pins']:raise ValueError('selected source pins changed')
    if pin(STOCH)!=plan['source']['registry_stoch']:raise ValueError('Registry pin changed')
    registry_text=REGISTRY.read_text()
    for field,want in [('spec_bdy_width','5'),('spec_zone','1')]:
        matches=[line for line in registry_text.splitlines()
                 if re.search(r'^\s*rconfig\s+integer\s+'+field+r'\s+namelist,bdy_control\s+1\s+'+want+r'\s+irh\b',line,re.I)]
        if len(matches)!=1:raise ValueError(f'Registry {field} default is not uniquely {want}: {len(matches)} lines')
    for arm in ('off','on'):
        nml=(STAGE/arm/'namelist.input').read_text()
        if helper.fscalar(nml,'e_we')!='91' or helper.fscalar(nml,'e_sn')!='100' or helper.fscalar(nml,'spec_bdy_width')!='5':
            raise ValueError(f'{arm}: captured coordinates do not match 90x99/width-5 domain')
    if execution['source']['head']!=plan['source']['head'] or execution['source']['tree']!=plan['source']['tree']:
        raise ValueError('runtime source identity differs from frozen plan')
    if pin(pathlib.Path(plan['build_result']['path']))!=plan['build_result']:raise ValueError('build result pin changed')
    for path,r in execution['library_pins'].items():
        if pin(path)!=r:raise ValueError(f'runtime library changed: {path}')
    schema=json.loads(SCHEMA.read_text())
    if pin(SCHEMA)!=plan['observer_schema']:raise ValueError('observer schema pin changed')
    # Check the complete existing output records, including ordered variable
    # schema, dimensions, every array, all attributes, and the whole-file hash.
    names=[plan['cases']['off']['expected_history_file'],plan['cases']['off']['expected_restart']]
    comparisons=[]
    for name in names:
        result=helper.compare_nc(STAGE/'off'/name,STAGE/'on'/name)
        comparisons.append(result)
        if not result['pass_exact']:raise ValueError(f'OFF/ON saved NetCDF differs: {name}')
    with Dataset(STAGE/'off'/names[0]) as ds:
        t=helper.times(ds)
        if t!=plan['cases']['off']['expected_history_times']:
            raise ValueError(f'OFF history Times mismatch: {t}')
        history_times=t
    with Dataset(STAGE/'on'/names[0]) as ds:
        if helper.times(ds)!=history_times:raise ValueError('ON history Times mismatch')
    capture=helper.read_capture(STAGE/'on'/'capture',schema)
    if capture['status']!='PASS_PACKET_STRUCTURE_AND_SOURCE_RELATIONS':
        raise ValueError('capture did not establish selected-column nonzero inflow')
    flat=[r for packet in capture['row_summary'] for r in packet['rows']]
    rho=[r['rho_dry'] for r in flat];qnc=[r['qnc_before'] for r in flat];qnr=[r['qnr_before'] for r in flat]
    inflows=sum(r['branch']==1 for r in flat);outflows=sum(r['branch']==0 for r in flat)
    if len(flat)!=1056 or inflows<1 or inflows+outflows!=1056:raise ValueError('selected packet row/branch count mismatch')
    result={'schema':'UDM37_QNN_BOUNDARY_SAVED_RECOVERY_V1','status':'PASS_SAVED_RUNTIME_CONSISTENCY_SCOPED',
      'source_failure_preserved':{'status':execution['status'],'reason':execution['arms']['on'].get('error'),
        'actual_rcs':{a:execution['arms'][a]['actual_rc'] for a in ('off','on')},
        'note':'The original v2 parser failure is preserved; this recovery applies authenticated spec_zone/spec_bdy_width coordinates to its unchanged saved packets.'},
      'pins':{'stage_plan':pin(stageplan),'v2_execution':pin(execpath),'v2_runner':pin(RUNNER),
        'observer_source':{'head':execution['source']['head'],'tree':execution['source']['tree'],'selected_files':sourcepins},
        'registry_stoch':pin(STOCH),'registry_boundary_defaults':pin(REGISTRY),'observer_schema':pin(SCHEMA),'build_result':pin(pathlib.Path(plan['build_result']['path']))},
      'arms':checks,'history_times':history_times,'off_on_saved_outputs':comparisons,
      'capture':{'status':capture['status'],'packet_count':capture['packet_count'],'row_count':capture['rows'],
        'inflow_rows':inflows,'outflow_rows':outflows,'rho_dry_minmax':[min(rho),max(rho)],
        'qnc_minmax':[min(qnc),max(qnc)],'qnc_nonzero_rows':sum(v!=0 for v in qnc),
        'qnr_minmax':[min(qnr),max(qnr)],'qnr_nonzero_rows':sum(v!=0 for v in qnr),
        'packets':capture['packets'],'scope':capture['scope']},
      'scope':'Saved two-minute OFF/ON identity and selected-boundary observer consistency only; no physical approval, unit authority, all-domain coverage, or unmodified-source comparison.'}
    atomic(out,result)
    print(json.dumps({'status':result['status'],'output':str(out),'history_times':history_times,
      'inflow_rows':inflows,'outflow_rows':outflows,'rho_dry_minmax':result['capture']['rho_dry_minmax']}))

if __name__=='__main__':main()
