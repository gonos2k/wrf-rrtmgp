#!/usr/bin/env python3
"""Derive selected-column metrics from completed same-state campaign artifacts."""
import csv, hashlib, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = ROOT / 'build/udm37-current-matthew-serial-audit-v1'
OUTDIR = Path(__file__).resolve().parent

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def section(path, name):
    lines=Path(path).read_text().splitlines()
    for i,line in enumerate(lines):
        t=line.split()
        if not t or t[0] != name: continue
        try: dims=[int(x) for x in t[1:]]
        except ValueError: continue
        n=math.prod(dims)
        vals=[]
        for body in lines[i+1:]:
            w=body.split()
            if len(vals)>=n: break
            for q in w:
                try: vals.append(float(q.replace('D','E').replace('d','e')))
                except ValueError: break
                if len(vals)==n: break
        if len(vals)==n: return {'dims':dims,'values':vals}
        raise ValueError(f'{name}: expected {n} values, got {len(vals)} in {path}')
    raise KeyError(f'{name} not found in {path}')

def finite(v):
    if not all(math.isfinite(float(x)) for x in v): raise ValueError('nonfinite input')

def main():
    receipt_path=CAMPAIGN/'execution-receipt.json'
    comp_path=CAMPAIGN/'radius-arm-comparison.json'
    receipt=json.loads(receipt_path.read_text())
    comp=json.loads(comp_path.read_text())
    if receipt['status']!='PASS_SERIAL_AUDIT_OUTPUTS_AND_CAPTURE_PARITY': raise ValueError('campaign not terminal PASS')
    if receipt['counts']!={'REAL':0,'compile':0,'model':3}: raise ValueError('unexpected campaign counts')
    if receipt['model_invocations']!=3 or not all(a['status']=='PASS_ARM' and a['returncode']==0 and not a['timed_out'] for a in receipt['arms'].values()):
        raise ValueError('arm receipts not all PASS')
    if len(comp['records'])!=564 or comp['samples_per_engine_per_call']!=128 or comp['selected_column']!=[24,55]:
        raise ValueError('unexpected comparator record contract')
    csvs={}
    for mode in ('generic','native'):
        path=Path(comp['inputs'][mode]['path'])
        if sha(path)!=comp['inputs'][mode]['sha256']: raise ValueError('CSV pin mismatch')
        with path.open(newline='') as f:
            rows=list(csv.DictReader(f))
        csvs[mode]={(r['phase'],r['domain'],r['step'],r['source_seconds'].strip(),r['metric']):r for r in rows if r['i']=='24' and r['j']=='55'}
    if len(csvs['generic'])!=564 or len(csvs['native'])!=564: raise ValueError('selected CSV row count mismatch')
    recs={}
    for r in comp['records']:
        key=(r['phase'],r['domain'],r['step'],r['source_seconds'].strip(),r['metric'])
        if key not in csvs['generic'] or key not in csvs['native']: raise ValueError(f'CSV missing {key}')
        for mode in ('generic','native'):
            src=csvs[mode][key]
            record_key=f'{mode}4'
            for field in ('value37','value4','mean37','mean4','sample_count'):
                if field=='sample_count':
                    if int(src[field])!=128: raise ValueError(f'{key}: {mode}.{field} mismatch')
                elif not math.isclose(float(src[field]),float(r[record_key][field]),rel_tol=0,abs_tol=0):
                    raise ValueError(f'{key}: {mode}.{field} mismatch')
        if not math.isclose(r['four_native_minus_generic']['operational'],r['native4']['value4']-r['generic4']['value4'],rel_tol=0,abs_tol=1e-14): raise ValueError(f'{key}: op diff mismatch')
        if not math.isclose(r['four_native_minus_generic']['seed_mean'],r['native4']['mean4']-r['generic4']['mean4'],rel_tol=0,abs_tol=1e-14): raise ValueError(f'{key}: mean diff mismatch')
        if r['native4']['value37']!=r['generic4']['value37'] or r['native4']['mean37']!=r['generic4']['mean37']: raise ValueError(f'{key}: RRTMGP37 reference changed across modes')
        recs[key]=r
    # The audit modes must use the same captured physical calls.
    arm_captures={}
    for arm in ('ON_native4_0','ON_native4_1'):
        arm_captures[arm]={(c['phase'].lower(),str(c['radiation_step']),str(c['source_seconds'])):c['files_sha256'] for c in receipt['arms'][arm]['capture_groups']}
    if arm_captures['ON_native4_0']!=arm_captures['ON_native4_1']:
        raise ValueError('generic/native audit capture sets differ')
    calls=[]
    for phase,domain,step,seconds in comp['call_keys']:
        prefix=(phase,domain,step,str(seconds).strip())
        group={k[4]:v for k,v in recs.items() if k[:4]==prefix}
        flux_names=['SURFACE_DOWN','TOA_UP'] if phase=='lw' else ['SURFACE_DOWN','TOA_UP','SW_NET','SW_DIRECT']
        fields={}
        for name in flux_names:
            r=group[name]
            fields[name]={'units':r['units'],'generic4':{'operational':r['generic4']['value4'],'seed_mean_128':r['generic4']['mean4']},
                'native4':{'operational':r['native4']['value4'],'seed_mean_128':r['native4']['mean4']},
                'native4_minus_generic4':{'operational':r['four_native_minus_generic']['operational'],'seed_mean_128':r['four_native_minus_generic']['seed_mean']},
                'rrtmgp37_reference':{'operational':r['native4']['value37'],'seed_mean_128':r['native4']['mean37']},
                'rrtmgp37_minus_generic4':{'operational':r['generic4_contrast']['operational_37_minus_4'],'seed_mean_128':r['generic4_contrast']['seed_mean_37_minus_4']},
                'rrtmgp37_minus_native4':{'operational':r['native4_contrast']['operational_37_minus_4'],'seed_mean_128':r['native4_contrast']['seed_mean_37_minus_4']}}
        phase_groups=[c for c in receipt['arms']['ON_native4_0']['capture_groups'] if c['phase'].lower()==phase]
        matches=[(i,c) for i,c in enumerate(phase_groups,1) if str(c['radiation_step'])==str(step)]
        if len(matches)!=1: raise ValueError(f'no unique capture mapping for {phase} step {step}')
        idx,capture=matches[0]
        stem=f'{phase}_{idx:06d}'
        input_path=CAMPAIGN/'ON_native4_0'/'trace'/f'{stem}.input'
        raw_path=CAMPAIGN/'ON_native4_0'/'trace'/f'{stem}.raw'
        if sha(input_path)!=capture['files_sha256']['input']: raise ValueError(f'capture input hash mismatch {input_path}')
        if sha(raw_path)!=capture['files_sha256']['raw']: raise ValueError(f'capture raw hash mismatch {raw_path}')
        pressure=section(raw_path,'SOURCE_P_PA')['values']
        finite(pressure)
        heat_rows=sorted((r for m,r in group.items() if m.startswith('HEAT_')),key=lambda r:int(r['metric'].split('_')[1]))
        hpeak={}
        for mode in ('generic4','native4'):
            for stat,field in (('operational','value4'),('seed_mean_128','mean4')):
                rr=max(heat_rows,key=lambda r:abs(r[mode][field]))
                layer=int(rr['metric'].split('_')[1])
                hpeak[f'{mode}_{stat}_peak_abs']={'layer':layer,'pressure_pa':pressure[layer-1],'value':rr[mode][field],'units':'K/day'}
        heat_delta={}
        for stat in ('operational','seed_mean'):
            rr=max(heat_rows,key=lambda r:abs(r['four_native_minus_generic'][stat]))
            layer=int(rr['metric'].split('_')[1])
            heat_delta[f'max_abs_native4_minus_generic4_{stat}']={'layer':layer,'pressure_pa':pressure[layer-1],'signed_delta':rr['four_native_minus_generic'][stat],'abs_delta':abs(rr['four_native_minus_generic'][stat]),'units':'K/day'}
            rr=max(heat_rows,key=lambda r:abs(r['native4_contrast']['operational_37_minus_4' if stat=='operational' else 'seed_mean_37_minus_4']))
            layer=int(rr['metric'].split('_')[1])
            contrast='operational_37_minus_4' if stat=='operational' else 'seed_mean_37_minus_4'
            heat_delta[f'max_abs_rrtmgp37_minus_native4_{stat}']={'layer':layer,'pressure_pa':pressure[layer-1],'signed_delta':rr['native4_contrast'][contrast],'abs_delta':abs(rr['native4_contrast'][contrast]),'units':'K/day'}
        sw_context=None
        if phase=='sw':
            mu=section(input_path,'MU0')['values']; cf=section(input_path,'CF')['values']
            iwp=section(input_path,'IWP')['values']; lwp=section(input_path,'LWP')['values']; swp=section(input_path,'SWP')['values']; rwp=section(input_path,'RWP')['values']
            tau=section(input_path,'RAW_CLOUD_TAU'); ptau=section(input_path,'RAW_PRECIP_TAU')
            for vals in (mu,cf,iwp,lwp,swp,rwp,tau['values'],ptau['values']): finite(vals)
            sw_context={'input_sha256':capture['files_sha256']['input'],'mu0':mu[0], 'cloud_fraction_max':max(cf),
                        'cloud_fraction_positive_layers':sum(x>0 for x in cf), 'layer_count_engine_input':len(cf),
                        'sum_input_lwp_g_m2':sum(lwp),'sum_input_iwp_g_m2':sum(iwp),'sum_input_swp_g_m2':sum(swp),'sum_input_rwp_g_m2':sum(rwp),
                        'max_raw_cloud_tau':max(tau['values']), 'max_raw_precip_tau':max(ptau['values']),
                        'tau_caveat':'RAW_CLOUD_TAU is captured before delta scaling in the RRTMGP wrapper. It is a state descriptor, not a cross-engine optical-equivalence proof.'}
        calls.append({'phase':phase,'step':int(step),'source_seconds':float(seconds),'selected_global_column_ij':[24,55],
                      'samples':128,'capture_sha256':capture['files_sha256'],'metrics':fields,'heating_profile':{'levels':len(heat_rows),'peaks':hpeak,'native4_minus_generic4':heat_delta},'sw_state':sw_context})
    extrema={}
    for phase,name in [('sw','SURFACE_DOWN'),('sw','TOA_UP'),('lw','SURFACE_DOWN'),('lw','TOA_UP')]:
        rs=[c['metrics'][name]['native4_minus_generic4'] for c in calls if c['phase']==phase]
        for stat in ('operational','seed_mean_128'):
            vals=[x[stat] for x in rs]
            extrema[f'{phase}_{name}_{stat}']={'min':min(vals),'max':max(vals),'max_abs':max(abs(x) for x in vals)}
    extrema['sw_SW_DIRECT_seed_mean_max_abs_delta']=max(abs(c['metrics']['SW_DIRECT']['native4_minus_generic4']['seed_mean_128']) for c in calls if c['phase']=='sw')
    extrema['sw_SW_DIRECT_operational_max_abs_delta']=max(abs(c['metrics']['SW_DIRECT']['native4_minus_generic4']['operational']) for c in calls if c['phase']=='sw')
    extrema['lw_heat_max_abs_native4_minus_generic4_seed_mean']=max(c['heating_profile']['native4_minus_generic4']['max_abs_native4_minus_generic4_seed_mean']['abs_delta'] for c in calls if c['phase']=='lw')
    extrema['sw_heat_max_abs_native4_minus_generic4_seed_mean']=max(c['heating_profile']['native4_minus_generic4']['max_abs_native4_minus_generic4_seed_mean']['abs_delta'] for c in calls if c['phase']=='sw')
    for phase,name in [('sw','SURFACE_DOWN'),('sw','TOA_UP'),('lw','SURFACE_DOWN'),('lw','TOA_UP')]:
        phase_calls=[c for c in calls if c['phase']==phase]
        for label,series in [
            ('rrtmgp37_operational',[c['metrics'][name]['rrtmgp37_reference']['operational'] for c in phase_calls]),
            ('native4_operational',[c['metrics'][name]['native4']['operational'] for c in phase_calls]),
            ('generic4_operational',[c['metrics'][name]['generic4']['operational'] for c in phase_calls]),
            ('rrtmgp37_minus_native4_seed_mean',[c['metrics'][name]['rrtmgp37_minus_native4']['seed_mean_128'] for c in phase_calls]),
            ('native4_minus_generic4_seed_mean',[c['metrics'][name]['native4_minus_generic4']['seed_mean_128'] for c in phase_calls])]:
            extrema[f'{phase}_{name}_{label}_range']={'min':min(series),'max':max(series)}
    extrema['sw_profile_max_abs_rrtmgp37_minus_native4_seed_mean']=max(c['heating_profile']['native4_minus_generic4']['max_abs_rrtmgp37_minus_native4_seed_mean']['abs_delta'] for c in calls if c['phase']=='sw')
    extrema['lw_profile_max_abs_rrtmgp37_minus_native4_seed_mean']=max(c['heating_profile']['native4_minus_generic4']['max_abs_rrtmgp37_minus_native4_seed_mean']['abs_delta'] for c in calls if c['phase']=='lw')
    out={'schema':'UDM37_CURRENT_RADIUS_AUDIT_SELECTED_CALLS_V1','status':'PASS_DERIVED_FROM_TERMINAL_CAMPAIGN','source_contract_sha256':'c33908bf6f4604381708735817fdae7a4e9b9baa7b14e1653d14d8c1c9948214',
      'campaign':{'execution_receipt':str(receipt_path.resolve()),'execution_receipt_sha256':sha(receipt_path),'radius_arm_comparison':str(comp_path.resolve()),'radius_arm_comparison_sha256':sha(comp_path),
        'arm_count':3,'model_invocations':3,'compile_count':0,'real_count':0,'selected_column_global_ij':[24,55],'all_sky_only':True,'calls':12,'samples_per_engine_call':128,
        'generic_csv_sha256':comp['inputs']['generic']['sha256'],'native_csv_sha256':comp['inputs']['native']['sha256'],'historical_limit':'single selected column; one-hour UDM27 serial restart; deterministic 128-seed descriptive ensemble; not an IID confidence estimate.'},
      'interpretation':{'difference':'native4 minus generic4 scratch RRTMG4 wrapper mode, with same captured state per call',
        'operational':'seed override -1/default scratch invocation; not the operational RRTMG4 forecast arm',
        'seed_mean':'mean over 128 deterministic paired seed indices; descriptive only',
        'causality':'Same-state pairing removes trajectory divergence at each audit call, but the modes change liquid/ice/snow radii and legacy flag/category/path mappings; engines retain distinct gas/cloud/precipitation optics, cloud-fraction and sampling algorithms. Not pure engine-only attribution and not an accuracy verdict.',
        'surface_caution':'Small surface-flux changes do not imply small TOA or heating-profile changes. CF/path/tau are state descriptors, not proof of optical equivalence or a causal explanation.'},
      'per_call':calls,'envelopes':extrema}
    out['campaign']['final_identity']={
      'stage':receipt['campaign_final_identity']['stage'],
      'runtime_executable':receipt['campaign_final_identity']['runtime']['executable'],
      'frozen_table':receipt['campaign_final_identity']['runtime']['frozen_table'],
      'fresh_loader_files':receipt['campaign_final_identity']['runtime']['fresh_loader_files'],
      'runtime_library_count':receipt['campaign_final_identity']['runtime']['runtime_library_count']}
    out['campaign']['exact_output_comparisons']=[{'arm':c['arm'],'file':c['file'],'status':c['status'],'sha256':c['left']['sha256']} for c in receipt['output_comparisons']]
    out['campaign']['capture_parity_count']=len(receipt['capture_comparisons'])
    out['campaign']['rrtmgp37_reference_same_between_radius_modes']=bool(comp['identical_37_reference_between_arms'])
    dest=OUTDIR/'numerical.json'
    dest.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':out['status'],'json':str(dest.resolve()),'sha256':sha(dest),'calls':len(calls),'envelopes':extrema},indent=2))
if __name__=='__main__': main()
