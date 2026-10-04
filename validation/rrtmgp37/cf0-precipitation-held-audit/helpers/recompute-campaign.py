#!/usr/bin/env python3
"""Independent offline readback for the frozen CF0 campaign-v5 results."""
import argparse, hashlib, json, math
from pathlib import Path

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''): h.update(block)
    return h.hexdigest()

def parse_result(path):
    lines=Path(path).read_text(encoding='ascii').splitlines()
    if len(lines)<2 or lines[0].strip()!='RRTMGP_RESULT_V1': raise ValueError(f'{path}: bad result header')
    h=lines[1].split()
    if len(h)!=3: raise ValueError(f'{path}: malformed dimensions')
    phase,nc,nl=h[0],int(h[1]),int(h[2]); i=2; sections={}; order=[]
    while i<len(lines):
        if not lines[i].strip(): i+=1; continue
        parts=lines[i].split(); i+=1
        if len(parts)!=4: raise ValueError(f'{path}: malformed section header')
        name=parts[0]; shape=tuple(map(int,parts[1:])); n=math.prod(shape)
        if n<=0 or name in sections: raise ValueError(f'{path}: duplicate/empty section {name}')
        tokens=[]
        while len(tokens)<n:
            if i>=len(lines): raise ValueError(f'{path}: truncated {name}')
            tokens.extend(lines[i].split()); i+=1
        if len(tokens)!=n: raise ValueError(f'{path}: overfull {name}')
        values=[float(t.replace('D','E').replace('d','e')) for t in tokens]
        if not all(math.isfinite(x) for x in values): raise ValueError(f'{path}: nonfinite {name}')
        sections[name]={'shape':shape,'tokens':tokens,'values':values}
        order.append(name)
    return {'phase':phase,'nc':nc,'nl':nl,'order':order,'sections':sections}

def get(x,key): return x['sections'][key]['values']
def check_campaign(root):
    root=Path(root); plan=json.loads((root/'invocation-plan.json').read_text())
    execution=json.loads((root/'execution.json').read_text())
    authorization=root/'root-authorizations-v1/campaign-authorization.json'
    if sha(authorization)!=execution['authorization_sha256']: raise ValueError('authorization hash mismatch')
    if execution['status']!='PASS_ALL_EIGHT_CALLS' or execution['solver_invocations']!=8 or execution['calls_completed']!=8:
        raise ValueError('execution is not a completed eight-call campaign')
    post=execution['postflight']
    if not all(post.get(k) is True for k in ('immutable_pins_unchanged','generated_outputs_unchanged','runtime_closure_unchanged')):
        raise ValueError('execution postflight has a failed integrity condition')
    groups=plan['immutable_pin_groups']
    expected_counts={'baseline137':137,'runtime47':47,'source_build':71,'cases_data':105,'all_immutable':281}
    for k,n in expected_counts.items():
        if len(groups[k])!=n: raise ValueError(f'{k} count mismatch')
    checked=[]
    for pin in groups['all_immutable']:
        path=Path(pin['path'])
        if not path.is_file() or sha(path)!=pin['sha256']: raise ValueError(f'immutable pin changed: {path}')
        checked.append(path)
    base_receipt=json.loads(Path(plan['original_baseline_receipt']['path']).read_text())
    rows=[]
    for index,(call,run) in enumerate(zip(plan['calls'],execution['calls'])):
        if call['case_id']!=run['case_id'] or run['index']!=index+1 or run['status']!='CALL_VALIDATED' or run['returncode']!=0:
            raise ValueError(f'call state mismatch {index}')
        output=Path(run['output']); pin=run['generated_output_pin']
        if output.is_symlink() or not output.is_file() or output.stat().st_size!=pin['size_bytes'] or sha(output)!=pin['sha256']:
            raise ValueError(f'generated output pin mismatch: {output}')
        result=parse_result(output)
        if (result['phase'],result['nc'],result['nl'])!=(call['phase'],1,call['engine_layers']):
            raise ValueError(f'result header mismatch: {call["case_id"]}')
        oracle=Path(call['baseline_result']['path'])
        if sha(oracle)!=call['baseline_result']['sha256']: raise ValueError('baseline oracle pin changed')
        if call['mode']=='all-zero-control':
            original=next(x for x in base_receipt['cases'] if x['phase']==call['phase'] and x['species']==call['species'])
            if call['input']['sha256']!=original['input_pin']['sha256'] or call['raw']['sha256']!=original['raw_pin']['sha256']:
                raise ValueError('zero input/raw not paired with original capture')
            if call['baseline_result']['sha256']!=original['exact_double_zero_sidecar_oracle']['result']['sha256']:
                raise ValueError('zero case does not select saved exact double-reference oracle')
            if output.read_bytes()!=oracle.read_bytes(): raise ValueError(f'zero result is not byte-identical: {call["case_id"]}')
            if run['validation']['status']!='ZERO_SIDECAR_EXACT_DOUBLE_ORACLE_BYTE_PASS': raise ValueError('zero execution receipt validation mismatch')
            rows.append({'case_id':call['case_id'],'mode':'all-zero-control','pid':run['pid'],'returncode':0,'output_sha256':sha(output),'whole_output_byte_exact_double_oracle':True,'result_sections':len(result['order'])})
            continue
        base=parse_result(oracle)
        if (base['phase'],base['nc'],base['nl'])!=(result['phase'],result['nc'],result['nl']): raise ValueError('positive baseline dimensions differ')
        if [n for n in result['order'] if n in base['sections']]!=base['order']: raise ValueError('original section ordering changed')
        extras=set(result['sections'])-set(base['sections'])
        expected={'LW':{'AUDIT_EXTRA_PRECIP_TAU'},'SW':{'AUDIT_EXTRA_PRECIP_TAU','AUDIT_EXTRA_PRECIP_TAU_RAW','AUDIT_EXTRA_PRECIP_SSA','AUDIT_EXTRA_PRECIP_G','AUDIT_DIRECT_PREDELTA'}}[call['phase']]
        if extras!=expected: raise ValueError(f'extra section mismatch for {call["case_id"]}')
        mutable={'LW':{'TOTAL_TAU','UP','DN','HR'},'SW':{'TOTAL_TAU','TOTAL_SSA','TOTAL_G','UP','DN','HR','DIRECT','DIFFUSE','VISDIR','VISDIF','NIRDIR','NIRDIF'}}[call['phase']]
        changed=[]; invariant=[]
        for name,old in base['sections'].items():
            cur=result['sections'][name]
            if cur['shape']!=old['shape']: raise ValueError(f'shape changed for {call["case_id"]}:{name}')
            if cur['tokens']!=old['tokens']:
                if name not in mutable: raise ValueError(f'undeclared result changed {call["case_id"]}:{name}')
                changed.append(name)
            else: invariant.append(name)
        extra_stats={}
        for name in sorted(expected):
            sec=result['sections'][name]; a=sec['values']
            if name=='AUDIT_DIRECT_PREDELTA': shape=base['sections']['DIRECT_PREDELTA']['shape']
            else: shape=base['sections']['PRECIP_TAU']['shape']
            if sec['shape']!=shape: raise ValueError(f'audit shape mismatch {call["case_id"]}:{name}')
            if name in ('AUDIT_EXTRA_PRECIP_TAU','AUDIT_EXTRA_PRECIP_TAU_RAW') and min(a)<0: raise ValueError('negative audit extinction')
            if name=='AUDIT_EXTRA_PRECIP_SSA' and (min(a)<0 or max(a)>1): raise ValueError('audit SSA outside [0,1]')
            if name=='AUDIT_EXTRA_PRECIP_G' and (min(a)<-1 or max(a)>1): raise ValueError('audit asymmetry outside [-1,1]')
            if not any(x!=0 for x in a): raise ValueError(f'all-zero positive audit section {name}')
            extra_stats[name]={'shape':sec['shape'],'min':min(a),'max':max(a),'sum':sum(a)}
        nl=result['nl']; native=call['native_layers']; up=get(result,'UP'); dn=get(result,'DN'); hr=get(result,'HR'); up0=get(base,'UP'); dn0=get(base,'DN'); hr0=get(base,'HR')
        if call['phase']=='SW':
            surface={'surface_down_base_w_m2':dn0[0],'surface_down_positive_w_m2':dn[0],'surface_down_delta_w_m2':dn[0]-dn0[0],
                     'surface_net_down_minus_up_base_w_m2':dn0[0]-up0[0],'surface_net_down_minus_up_positive_w_m2':dn[0]-up[0],
                     'surface_net_down_minus_up_delta_w_m2':(dn[0]-up[0])-(dn0[0]-up0[0]),
                     'toa_up_base_w_m2':up0[nl],'toa_up_positive_w_m2':up[nl],'toa_up_delta_w_m2':up[nl]-up0[nl]}
        else:
            surface={'glw_down_surface_base_w_m2':dn0[0],'glw_down_surface_positive_w_m2':dn[0],'glw_down_surface_delta_w_m2':dn[0]-dn0[0],
                     'olr_up_toa_base_w_m2':up0[nl],'olr_up_toa_positive_w_m2':up[nl],'olr_up_toa_delta_w_m2':up[nl]-up0[nl]}
        dh=[hr[i]-hr0[i] for i in range(nl)]
        surface.update({'max_abs_hr_delta_native_k_per_day':max(abs(x) for x in dh[:native]),'max_abs_hr_delta_engine_k_per_day':max(abs(x) for x in dh),'native_layers':native,'engine_layers':nl})
        rows.append({'case_id':call['case_id'],'mode':'positive-omitted-path','pid':run['pid'],'returncode':0,'output_sha256':sha(output),'changed_mutable_original_sections':changed,'unchanged_original_sections':invariant,'audit_sections':extra_stats,'conditional_sensitivity_metrics':surface})
    return {'status':'INDEPENDENT_OFFLINE_READBACK_PASS','campaign_status':execution['status'],'solver_invocations':8,'zero_controls_byte_exact':4,'positive_controls_contract_pass':4,
            'pin_counts':expected_counts,'immutable_paths_rehashed':len(checked),'authorization_sha256':sha(authorization),'execution_sha256':sha(root/'execution.json'),
            'calls':rows,'interpretation':'Held-state occurrence-one sensitivity against the saved exact double-reference baseline. Not a cloud occurrence oracle, independent optical truth, current-backend proof, forecast accuracy, or domain mean.'}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('campaign_root',type=Path); ap.add_argument('--output',type=Path); a=ap.parse_args()
    data=check_campaign(a.campaign_root)
    text=json.dumps(data,indent=2,sort_keys=True)+'\n'
    if a.output: a.output.write_text(text)
    print(text,end='')
if __name__=='__main__':main()
