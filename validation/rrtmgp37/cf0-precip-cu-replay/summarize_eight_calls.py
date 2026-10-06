#!/usr/bin/env python3
"""Verify and summarize the frozen eight-call CF0/CU replay package (no solver)."""
from __future__ import annotations
import csv, gzip, hashlib, json, math, tempfile
from pathlib import Path
import importlib.util
HERE=Path(__file__).resolve().parent
WORKTREE=HERE.parents[2]
CAP=WORKTREE/'validation/rrtmgp37/rrtmg4-same-call-attribution/traces/NEW_ON'
REVIEW=HERE/'receipts/independent-terminal-review.json'
EXEC=HERE/'receipts/eight-call-execution.json'
ROSTER=HERE/'case-roster.json'


def sha_bytes(b: bytes)->str:return hashlib.sha256(b).hexdigest()
def read_gzip(path: Path)->bytes:
    with gzip.open(path,'rb') as f:return f.read()
def parse_result_bytes(data: bytes, label: str):
    lines=data.decode('utf-8').splitlines()
    if len(lines)<2 or lines[0].strip()!='RRTMGP_RESULT_V1':raise ValueError(f'{label}: bad result magic')
    h=lines[1].split()
    if len(h)!=3:raise ValueError(f'{label}: malformed result header')
    phase=h[0].upper(); nc,nl=map(int,h[1:])
    if phase not in ('LW','SW') or nc!=1 or nl!=(57 if phase=='LW' else 45):raise ValueError(f'{label}: phase/dimension mismatch')
    i=2; sections={}
    while i<len(lines):
        if not lines[i].strip():i+=1;continue
        header=lines[i].split();i+=1
        if len(header)!=4:raise ValueError(f'{label}: malformed section header')
        name=header[0].upper(); shape=tuple(map(int,header[1:])); count=math.prod(shape)
        if name in sections:raise ValueError(f'{label}: duplicate section {name}')
        if shape[0]!=nc or any(x<1 for x in shape):raise ValueError(f'{label}: invalid shape {name} {shape}')
        tokens=[]
        while len(tokens)<count and i<len(lines):
            toks=lines[i].split();i+=1
            if toks:tokens.extend(toks)
        if len(tokens)!=count:raise ValueError(f'{label}: truncated section {name}')
        vals=[]
        for t in tokens:
            v=float(t.replace('D','E').replace('d','e'))
            if not math.isfinite(v):raise ValueError(f'{label}: non-finite {name}')
            vals.append(v)
        sections[name]={'shape':shape,'tokens':tokens,'values':vals}
    if not sections:raise ValueError(f'{label}: empty result')
    required={'GAS_COL_DRY','GAS_TAU','CLOUD_TAU','PREPARED_TAU','MASK','RL_USED','DI_USED','DS_USED','UP','DN','HR','UPC','DNC','HRC'}
    if phase=='SW':required|={'GAS_SSA','GAS_G','CLOUD_SSA','CLOUD_G','PREPARED_SSA','PREPARED_G','TOTAL_SSA','TOTAL_G','DIRECT','DIFFUSE','DIRECTC','VISDIR','VISDIF','NIRDIR','NIRDIF','DIRECT_PREDELTA','DIRECTC_PREDELTA','VISDIR_PREDELTA','NIRDIR_PREDELTA'}
    if required-set(sections):raise ValueError(f'{label}: missing sections {sorted(required-set(sections))}')
    for field in ('UP','DN','UPC','DNC'):
        if sections[field]['shape']!=(1,nl+1,1):raise ValueError(f'{label}: {field} has wrong interface shape')
    for field in ('HR','HRC'):
        if sections[field]['shape']!=(1,nl,1):raise ValueError(f'{label}: {field} has wrong layer shape')
    return {'phase':phase,'nc':nc,'nl':nl,'sections':sections}
def exact_section(a,b,name):
    sa=a['sections'].get(name);sb=b['sections'].get(name)
    return sa is not None and sb is not None and sa['shape']==sb['shape'] and sa['tokens']==sb['tokens']
def profile(section):
    sh=section['shape']; vals=section['values']
    # Result arrays are serialized in Fortran order; for nc=1, each level profile
    # is contiguous when nband/ngpt=1 (radiative flux/heating sections).
    if sh[0]!=1 or sh[2]!=1:raise ValueError(f'expected profile shape (1,n,1), got {sh}')
    return vals

roster=json.loads(ROSTER.read_text()); execution=json.loads(EXEC.read_text()); review=json.loads(REVIEW.read_text())
SIDE=HERE/'tools'/'cf0_precip_sidecar.py'
sspec=importlib.util.spec_from_file_location('cf0_precip_sidecar',SIDE); side_mod=importlib.util.module_from_spec(sspec); sspec.loader.exec_module(side_mod)
if execution.get('status')!='ALL_EIGHT_CALLS_VALIDATED' or len(execution.get('calls',[]))!=8:raise ValueError('execution receipt is not the expected eight-call terminal PASS')
if review.get('status')!='PASS_SCOPED_EIGHT_CALL_RECEIPT_ROSTERS_HELD_BITS':raise ValueError('independent terminal review not PASS')
exec_cases={c['case_id']:c for c in execution['calls']}; roster_cases={c['case_id']:c for c in roster['calls']}; names=['baseline-lw','baseline-sw','zero-lw','zero-sw','rain-lw','rain-sw','snow-lw','snow-sw']
if set(roster_cases)!=set(names) or len(roster['calls'])!=8: raise ValueError('duplicate/missing case IDs in package roster')
sidecar_validation={}
for name,cfg in roster_cases.items():
    phase=cfg['phase'].lower(); inp=CAP/f'{phase}_000001.input'; raw=CAP/f'{phase}_000001.raw'
    if sha_bytes(inp.read_bytes())!=cfg['input_sha256'] or sha_bytes(raw.read_bytes())!=cfg['raw_sha256']:
        raise ValueError(f'{name}: reused PR75 input/raw identity drift')
    if cfg['sidecar'] is None: continue
    side=HERE/cfg['sidecar']['path']
    if sha_bytes(side.read_bytes())!=cfg['sidecar']['sha256']: raise ValueError(f'{name}: sidecar pin mismatch')
    zero=cfg['mode']=='zero'
    sidecar_validation[name]=side_mod.validate_against_raw(side.read_text(),raw,cfg['species'],57 if cfg['phase']=='LW' else 45,inp,zero_control=zero)
# Semantic negative controls exercise failure paths without touching payloads or invoking the solver.
negatives={}
try:
    side_mod.validate_payload('LW',1,2,1,1.0,[[1.0,0.0]],[[0.0,0.0]],[[0.25,0.0]],3)
except side_mod.SidecarError: negatives['positive_path_at_nonzero_CF_rejected']=True
else: raise ValueError('CF-positive sidecar negative control was not rejected')
try:
    side_mod.validate_payload('LW',1,2,1,0.5,[[0.0,0.0]],[[0.0,0.0]],[[0.0,0.0]],3)
except side_mod.SidecarError: negatives['nonunit_occurrence_rejected']=True
else: raise ValueError('nonunit-occurrence negative control was not rejected')
try:
    side_mod.validate_payload('SW',2,2,1,1.0,[[0.0,0.0],[0.0,0.0]],[[0.0,0.0],[0.0,0.0]],[[0.0,0.0],[0.0,0.0]],3)
except side_mod.SidecarError: negatives['multicolumn_rejected']=True
else: raise ValueError('multicolumn negative control was not rejected')
if set(exec_cases)!=set(names):raise ValueError('execution call roster mismatch')
parsed={}; call_pins={}
for name in names:
    c=exec_cases[name]; cfg=roster_cases[name]
    if c['status']!='CALL_VALIDATED' or c['returncode']!=0 or c['timed_out']:raise ValueError(f'{name}: nonpassing/ambiguous execution record')
    out=HERE/'outputs'/f'{name}.result.txt.gz'; raw=read_gzip(out)
    if sha_bytes(raw)!=c['output_pin']['sha256'] or len(raw)!=c['output_pin']['size_bytes']:raise ValueError(f'{name}: raw output does not match execution receipt')
    lg=HERE/'logs'/f'{name}.log.gz'; log=read_gzip(lg)
    if sha_bytes(log)!=c['log_pin']['sha256'] or len(log)!=c['log_pin']['size_bytes']:raise ValueError(f'{name}: raw log does not match execution receipt')
    parsed[name]=parse_result_bytes(raw,name)
    audit_names={'AUDIT_EXTRA_PRECIP_TAU','AUDIT_EXTRA_PRECIP_TAU_RAW','AUDIT_EXTRA_PRECIP_SSA','AUDIT_EXTRA_PRECIP_G','AUDIT_DIRECT_PREDELTA'}
    found=audit_names & set(parsed[name]['sections'])
    expected_audit=(set() if cfg['mode'] in ('baseline','zero') else ({'AUDIT_EXTRA_PRECIP_TAU'} if cfg['phase']=='LW' else audit_names))
    if found!=expected_audit:raise ValueError(f'{name}: audit output roster mismatch {sorted(found)}')
    call_pins[name]={'pid':c['pid'],'returncode':c['returncode'],'output_raw_sha256':sha_bytes(raw),'output_raw_bytes':len(raw),'log_raw_sha256':sha_bytes(log),'log_raw_bytes':len(log)}
if len({x['pid'] for x in call_pins.values()})!=8:raise ValueError('actual solver child PIDs are not unique')
# The two all-zero controls are whole-file identical to their same-executable phase baselines.
for base,zero in [('baseline-lw','zero-lw'),('baseline-sw','zero-sw')]:
    if call_pins[base]['output_raw_sha256']!=call_pins[zero]['output_raw_sha256']:raise ValueError(f'{zero} differs from {base}')
# Validate positive calls preserve every held input/source diagnostic enumerated by independent review.
positive_summary={}; delta_rows=[]
for name in ('rain-lw','rain-sw','snow-lw','snow-sw'):
    c=exec_cases[name]; cfg=roster_cases[name]; base='baseline-'+cfg['phase'].lower(); br=parsed[base]; ar=parsed[name]
    held=review['checks'][name]['held_exact_names']; changed=[]
    for section in held:
        if not exact_section(br,ar,section):changed.append(section)
    if changed:raise ValueError(f'{name}: held sections differ: {changed}')
    phase_fields=['UP','DN','HR'] if cfg['phase']=='LW' else ['UP','DN','HR','DIRECT','DIFFUSE','VISDIR','VISDIF','NIRDIR','NIRDIF','AUDIT_DIRECT_PREDELTA']
    metrics={}
    for field in phase_fields:
        if field=='AUDIT_DIRECT_PREDELTA' and cfg['phase']=='SW':
            if field not in ar['sections'] or 'DIRECT_PREDELTA' not in br['sections']:
                raise ValueError(f'{name}: missing separate audit/original SW pre-delta diagnostics')
            av=profile(ar['sections'][field]); bv=profile(br['sections']['DIRECT_PREDELTA'])
        else:
            if field not in br['sections'] or field not in ar['sections']:
                raise ValueError(f'{name}: missing flux/heating field {field}')
            av=profile(ar['sections'][field]); bv=profile(br['sections'][field])
        if len(av)!=len(bv):raise ValueError(f'{name}: profile size mismatch {field}')
        dv=[a-b for a,b in zip(av,bv)]
        metrics[field]={'profile_points':len(dv),'max_abs_delta':max(abs(x) for x in dv),'max_signed_delta':max(dv),'min_signed_delta':min(dv),
                        'first_index_delta':dv[0],'last_index_delta':dv[-1], 'index_0_is_surface_for_interface_fields':field in ('UP','DN','DIRECT','DIFFUSE','VISDIR','VISDIF','NIRDIR','NIRDIF','AUDIT_DIRECT_PREDELTA')}
        for idx,(a,b,dlt) in enumerate(zip(av,bv,dv)):
            delta_rows.append([name,cfg['phase'],field,idx,b,a,dlt])
    cucn=ar['sections']['CU_CLOUD_TAU']; cuvals=cucn['values']
    cu_pos=sum(x>0 for x in cuvals); cu_max=max(cuvals)
    positive_summary[name]={'held_sections_exact':held,'allsky_profile_delta_metrics':metrics,
       'actual_cu_tau_positive_values':cu_pos,'actual_cu_tau_max':cu_max,
       'audit_species':c['sidecar_context']['report']['species'],'audit_path_sum_g_m2':c['sidecar_context']['report']['omitted_path_sum_g_m2'],
       'review_moment_residuals':{k:v for k,v in review['checks'][name].items() if 'residual' in k}}

csv_path=HERE/'results'/'allsky-profile-deltas.csv';csv_path.parent.mkdir(exist_ok=True)
with csv_path.open('w',newline='') as f:
    w=csv.writer(f,lineterminator='\n');w.writerow(['case_id','phase','field','profile_index_zero_based','baseline_value','counterfactual_value','delta'])
    w.writerows(delta_rows)
summary={'schema':'cf0-cu-eight-call-derived-summary-v1','status':'PASS_SCOPED_EIGHT_CALLS_AND_INDEPENDENT_REVIEW',
 'execution_receipt_sha256':sha_bytes(EXEC.read_bytes()),'independent_review_sha256':sha_bytes(REVIEW.read_bytes()),
 'actual_solver_invocations':execution.get('solver_invocations'),'wrf_forecasts':0,'all_call_pids_returncodes':call_pins,
 'zero_controls_whole_file_bitwise_equal':{'LW':True,'SW':True},'sidecar_validation':sidecar_validation,'semantic_negative_controls':negatives,'positive_cases':positive_summary,
 'scope':'One low-sun, thick-CU-shielded captured column; occurrence-one CF0 sidecar sensitivity only. Tiny positive snow paths are retained without cutoff but are very low signal; results do not establish a snow accuracy bound, production occurrence rule, global negligible effect, or forecast accuracy.',
 'clear_sky_note':'UPC/DNC/HRC are held and remain exact; the extra object is inserted after the clear solve, so this is not evidence of physical clear-sky precipitation insensitivity.'}
(HERE/'results'/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':summary['status'],'call_count':len(call_pins),'profile_rows':len(delta_rows),'summary_sha256':sha_bytes((HERE/'results/summary.json').read_bytes())},sort_keys=True))
