#!/usr/bin/env python3
"""Verify packaged dry-gas replay evidence using only Python's standard library."""
from __future__ import annotations
import gzip, hashlib, importlib.util, json, math, struct, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
EXPECTED_COUNTS = {'LW': 24, 'SW': 54}
EXPECTED_SECTIONS = {
    'LW': {'CLOUD_TAU','CU_CLOUD_TAU','CU_DI_USED','CU_RL_USED','DI_USED','DN','DNC','DS_USED','FROZEN_TAU','GAS_COL_DRY','GAS_TAU','GAS_TAU_RAW','GRAUPEL_TAU_ABS','HAIL_TAU_ABS','HR','HRC','MASK','NATIVE_CLOUD_TAU','PRECIP_TAU','PREPARED_TAU','RL_USED','TOTAL_TAU','UP','UPC'},
    'SW': {'CLOUD_G','CLOUD_SSA','CLOUD_TAU','CU_CLOUD_G','CU_CLOUD_SSA','CU_CLOUD_TAU','CU_DI_USED','CU_RL_USED','DIFFUSE','DIRECT','DIRECTC','DIRECTC_PREDELTA','DIRECT_PREDELTA','DI_USED','DN','DNC','DS_USED','FROZEN_G','FROZEN_SSA','FROZEN_TAU','GAS_COL_DRY','GAS_G','GAS_SSA','GAS_TAU','GRAUPEL_TAU_EXT','GRAUPEL_TAU_SCA','GRAUPEL_TAU_SCA_G','HAIL_TAU_EXT','HAIL_TAU_SCA','HAIL_TAU_SCA_G','HR','HRC','MASK','NATIVE_CLOUD_G','NATIVE_CLOUD_SSA','NATIVE_CLOUD_TAU','NIRDIF','NIRDIR','NIRDIR_PREDELTA','PRECIP_G','PRECIP_SSA','PRECIP_TAU','PREPARED_G','PREPARED_SSA','PREPARED_TAU','RL_USED','TOTAL_G','TOTAL_SSA','TOTAL_TAU','UP','UPC','VISDIF','VISDIR','VISDIR_PREDELTA'}
}
AVOGADRO = 6.02214076e23


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def sha_file(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def pin(p: Path) -> dict:
    return {'sha256':sha_file(p),'size_bytes':p.stat().st_size}

def parse_num(s: str) -> float:
    x=float(s.replace('D','E').replace('d','e'))
    if not math.isfinite(x): raise ValueError(f'nonfinite numeric token: {s}')
    return x

def parse_blocks(path: Path, is_gzip=False) -> tuple[list[str],dict]:
    if is_gzip:
        with gzip.open(path,'rt',encoding='ascii') as f: lines=f.read().splitlines()
    else: lines=path.read_text(encoding='ascii').splitlines()
    if len(lines)<2: raise ValueError(f'{path}: truncated file')
    initial=lines[:2]
    sections={}; i=2
    while i<len(lines):
        line=lines[i].strip(); i+=1
        if not line: continue
        tok=line.split()
        if len(tok)<2: raise ValueError(f'{path}: bad section header {line!r}')
        name=tok[0]
        try: dims=tuple(int(x) for x in tok[1:])
        except ValueError as e: raise ValueError(f'{path}: noninteger section shape {line!r}') from e
        if not dims or any(d<=0 for d in dims): raise ValueError(f'{path}: invalid shape for {name}')
        count=math.prod(dims); vals=[]
        while len(vals)<count:
            if i>=len(lines): raise ValueError(f'{path}: truncated section {name}')
            row=lines[i].split(); i+=1
            if not row: raise ValueError(f'{path}: empty numeric row {name}')
            vals.extend(parse_num(x) for x in row)
            if len(vals)>count: raise ValueError(f'{path}: excess data for {name}')
        if name in sections: raise ValueError(f'{path}: duplicate section {name}')
        sections[name]={'shape':dims,'values':vals}
    return initial,sections

def load_manifest():
    m=json.loads((HERE/'manifest.json').read_text())
    listed={x['path']:x for x in m['files']}
    actual={p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json'}
    if actual!=set(listed): raise ValueError(f'package roster mismatch: missing={sorted(set(listed)-actual)} extra={sorted(actual-set(listed))}')
    for rel,x in listed.items():
        p=HERE/rel
        if p.stat().st_size!=x['size_bytes'] or sha_file(p)!=x['sha256']:
            raise ValueError(f'package file pin mismatch: {rel}')
    ep=json.loads((HERE/'external-pins.json').read_text())
    for x in ep['artifacts']:
        p=REPO/x['path']
        if not p.is_file() or p.stat().st_size!=x['size_bytes'] or sha_file(p)!=x['sha256']:
            raise ValueError(f'external PR75 pin mismatch: {x["path"]}')
    return ep

def load_export(path: Path, phase: str) -> dict:
    parser_path=HERE/'source/read_export.py'
    spec=importlib.util.spec_from_file_location('drygas_read_export',parser_path)
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    with tempfile.TemporaryDirectory(prefix='drygas-export-') as td:
        tmp=Path(td)/'export.txt'
        with gzip.open(path,'rb') as f: tmp.write_bytes(f.read())
        return mod.read_export(tmp,expected_phase=phase)

def require_same(a,b,what):
    if a!=b: raise ValueError(f'{what} differs')

def delta(a,b):
    if len(a)!=len(b): raise ValueError('delta shape mismatch')
    d=[y-x for x,y in zip(a,b)]
    return {'count':len(d),'changed_values':sum(v!=0 for v in d),'max_abs':max(map(abs,d),default=0.0),'mean_signed':sum(d)/len(d) if d else 0.0}

def f32(x): return struct.unpack('<f',struct.pack('<f',x))[0]
def f64_bytes(values): return b''.join(struct.pack('<d',x) for x in values)
def ulp_distance(a,b):
    def ordered(x):
        u=struct.unpack('<Q',struct.pack('<d',x))[0]
        return (~u & ((1<<64)-1)) if (u>>63) else (u | (1<<63))
    return abs(ordered(a)-ordered(b))

def validate_output_schema(callid, header, sections, receipt):
    phase=receipt['phase']; nl=57 if phase=='LW' else 45; nb=16 if phase=='LW' else 14; ng=128 if phase=='LW' else 112; ni=nl+1
    if header != ['RRTMGP_RESULT_V1', f'{phase} 1 {nl}']:
        raise ValueError(f'{callid}: result phase/column/layer header mismatch: {header}')
    if len(sections)!=EXPECTED_COUNTS[phase] or set(sections)!=EXPECTED_SECTIONS[phase]:
        raise ValueError(f'{callid}: exact {phase} result section roster mismatch')
    if set(receipt.get('output_sections',{}))!=EXPECTED_SECTIONS[phase]:
        raise ValueError(f'{callid}: receipt section roster mismatch')
    if phase=='LW':
        band={'CLOUD_TAU','CU_CLOUD_TAU','FROZEN_TAU','GRAUPEL_TAU_ABS','HAIL_TAU_ABS','NATIVE_CLOUD_TAU','PRECIP_TAU','PREPARED_TAU'}
        gpoint={'GAS_TAU','GAS_TAU_RAW','MASK','TOTAL_TAU'}
    else:
        gpoint={'GAS_G','GAS_SSA','GAS_TAU','MASK','TOTAL_G','TOTAL_SSA','TOTAL_TAU'}
        layer={'CU_DI_USED','CU_RL_USED','DI_USED','DS_USED','GAS_COL_DRY','HR','HRC','RL_USED'}
        interface={'DIFFUSE','DIRECT','DIRECTC','DIRECTC_PREDELTA','DIRECT_PREDELTA','DN','DNC','NIRDIF','NIRDIR','NIRDIR_PREDELTA','UP','UPC','VISDIF','VISDIR','VISDIR_PREDELTA'}
        band=EXPECTED_SECTIONS[phase]-gpoint-layer-interface
    if phase=='LW':
        layer={'CU_DI_USED','CU_RL_USED','DI_USED','DS_USED','GAS_COL_DRY','HR','HRC','RL_USED'}
        interface=EXPECTED_SECTIONS[phase]-band-gpoint-layer
    for key in EXPECTED_SECTIONS[phase]:
        shape=[1,nl,ng] if key in gpoint else [1,nl,1] if key in layer else [1,ni,1] if key in interface else [1,nl,nb]
        if key not in sections or tuple(sections[key]['shape'])!=tuple(shape):
            raise ValueError(f'{callid}: {key} shape absent or incorrect; expected {shape}')
        if receipt['output_sections'][key].get('shape')!=shape:
            raise ValueError(f'{callid}: receipt shape differs for {key}')

def main():
    ep=load_manifest()
    ex=json.loads((HERE/'evidence/four-call-execution.json').read_text())
    if (ex.get('status')!='ALL_FOUR_VALIDATED_DESCRIPTIVE' or ex.get('calls_started')!=4 or
        ex.get('standalone_reference_invocations')!=4 or ex.get('wrf_model_invocations')!=0):
        raise ValueError('four-call receipt status/counters do not match scope')
    call_ids=[x.get('id') for x in ex['calls']]
    if len(call_ids)!=4 or len(set(call_ids))!=4: raise ValueError('four-call receipt must contain four unique call IDs')
    calls={x['id']:x for x in ex['calls']}
    if set(calls)!={'baseline_lw','baseline_sw','legacy_dry_lw','legacy_dry_sw'}: raise ValueError('unexpected call roster')
    output_sections={}; input_sections={}; column_residuals={}
    for cid,c in calls.items():
        if c.get('returncode')!=0 or c.get('status')!='VALIDATED': raise ValueError(f'{cid} did not validate with RC0')
        out=HERE/f'outputs/{cid}.result.gz'
        raw=gzip.decompress(out.read_bytes())
        if sha_bytes(raw)!=c['output']['sha256'] or len(raw)!=c['output']['size_bytes']:
            raise ValueError(f'{cid} decompressed output differs from frozen execution receipt')
        header,sections=parse_blocks(out,is_gzip=True)
        validate_output_schema(cid,header,sections,c)
        output_sections[cid]=sections
    # Baseline input files are intentionally reused from PR75; counterfactual files are included here.
    baseline_ext={
        'baseline_lw': REPO/'validation/rrtmgp37/rrtmg4-same-call-attribution/traces/NEW_ON/lw_000001.input',
        'baseline_sw': REPO/'validation/rrtmgp37/rrtmg4-same-call-attribution/traces/NEW_ON/sw_000001.input'}
    for cid,c in calls.items():
        ip=(baseline_ext[cid] if cid in baseline_ext else HERE/f'inputs/{cid}.input')
        if sha_file(ip)!=c['input']['sha256'] or ip.stat().st_size!=c['input']['size_bytes']:
            raise ValueError(f'{cid}: replay input pin differs from receipt')
        header,sections=parse_blocks(ip)
        input_sections[cid]=(header,sections)
    for phase,base_id,cf_id,field in [('LW','baseline_lw','legacy_dry_lw','COLDry'),('SW','baseline_sw','legacy_dry_sw','COLDRY')]:
        bh,bs=input_sections[base_id]; ch,cs=input_sections[cf_id]
        require_same(bh,ch,f'{phase} replay header')
        require_same(set(bs),set(cs),f'{phase} input record roster')
        for k in bs:
            require_same(bs[k]['shape'],cs[k]['shape'],f'{phase} input {k} shape')
            if k!='NATIVE_DRY_LAYER_MASS_KG_M2' and f64_bytes(bs[k]['values'])!=f64_bytes(cs[k]['values']):
                raise ValueError(f'{phase}: non-mass input {k} is not bitwise-identical')
        mass0=bs['NATIVE_DRY_LAYER_MASS_KG_M2']['values'];mass1=cs['NATIVE_DRY_LAYER_MASS_KG_M2']['values']
        if len(mass0)!=44 or len(mass1)!=44: raise ValueError(f'{phase}: expected44 native dry-mass levels')
        ed=ep['artifacts']
        eref=next(x['path'] for x in ed if x['path'].endswith(f'_step2161_{phase.lower()}.txt.gz'))
        export=load_export(REPO/eref,phase)
        legacy_name=('INPUT',field)
        if legacy_name not in export['fields']: raise ValueError(f'{phase}: missing exported {field}')
        legacy=export['fields'][legacy_name]
        if legacy.units!='molecule_cm-2' or len(legacy.values)<44: raise ValueError(f'{phase}: legacy column units/shape wrong')
        mdry=bs['MOL_WEIGHT_DRY']['values']
        if len(mdry)!=1 or mdry[0]<=0: raise ValueError(f'{phase}: invalid captured dry molar mass')
        transformed=[x*mdry[0]*10000.0/AVOGADRO for x in legacy.values[:44]]
        native_gp=output_sections[base_id]['GAS_COL_DRY']['values'][:44]
        residual=[(legacy.values[k]-native_gp[k])/native_gp[k] for k in range(44)]
        cf_gp=output_sections[cf_id]['GAS_COL_DRY']['values'][:44]
        cf_residual=[(cf_gp[k]-legacy.values[k])/legacy.values[k] for k in range(44)]
        cf_ulp=[ulp_distance(a,b) for a,b in zip(cf_gp,legacy.values[:44])]
        if max(cf_ulp,default=0)>1: raise ValueError(f'{phase}: achieved counterfactual GAS_COL_DRY exceeds one binary64 ULP from export')
        if f64_bytes(output_sections[base_id]['GAS_COL_DRY']['values'][44:])!=f64_bytes(output_sections[cf_id]['GAS_COL_DRY']['values'][44:]):
            raise ValueError(f'{phase}: GAS_COL_DRY upper extension changed')
        column_residuals[phase]={'mean_abs_legacy_minus_native_over_native':sum(abs(x) for x in residual)/44,'max_abs_legacy_minus_native_over_native':max(abs(x) for x in residual),'max_layer_1based':max(range(44),key=lambda k:abs(residual[k]))+1,'max_abs_counterfactual_minus_legacy_over_legacy':max(abs(x) for x in cf_residual),'max_counterfactual_vs_export_binary64_ulp':max(cf_ulp,default=0)}
        for k,(actual,want) in enumerate(zip(mass1,transformed)):
            if struct.pack('<d',actual)!=struct.pack('<d',want): raise ValueError(f'{phase}: transformed native dry mass not binary64-exact at {k+1}')
        if mass0==mass1: raise ValueError(f'{phase}: dry mass counterfactual did not change native values')
        # Output checks: all non-gas input-component diagnostics remain exact.
        b=output_sections[base_id];c=output_sections[cf_id]
        require_same(set(b),set(c),f'{phase} result sections')
        for k in b: require_same(b[k]['shape'],c[k]['shape'],f'{phase} output {k} shape')
        components=[k for k in b if any(t in k for t in ('CLOUD','PRECIP','FROZEN','MASK','_USED','PREPARED','GRAUPEL','HAIL'))]
        for k in components:
            if f64_bytes(b[k]['values'])!=f64_bytes(c[k]['values']): raise ValueError(f'{phase}: held component {k} not bitwise-identical')
        if b['GAS_COL_DRY']['values'][:44]==c['GAS_COL_DRY']['values'][:44]: raise ValueError(f'{phase}: dry column did not respond')
    # Actual-capture comparison: aggregate flux/heating values round to captured REAL32; SW partitions are reported, not required equal.
    capture_refs={
      'LW':REPO/'validation/rrtmgp37/rrtmg4-same-call-attribution/traces/NEW_ON/lw_000001.result',
      'SW':REPO/'validation/rrtmgp37/rrtmg4-same-call-attribution/traces/NEW_ON/sw_000001.result'}
    capture={ph:parse_blocks(path)[1] for ph,path in capture_refs.items()}
    capture_checks={}
    for phase,baseid in [('LW','baseline_lw'),('SW','baseline_sw')]:
        matches={}
        mandatory=('UP','DN','HR','UPC','DNC','HRC')
        if phase=='SW': mandatory+=('DIRECT','DIRECTC','DIRECT_PREDELTA','DIRECTC_PREDELTA')
        for key in mandatory:
            if key not in capture[phase] or key not in output_sections[baseid]: raise ValueError(f'{phase}: mandatory actual-capture field missing: {key}')
            x=output_sections[baseid][key]['values'];y=capture[phase][key]['values']
            require_same(output_sections[baseid][key]['shape'],capture[phase][key]['shape'],f'{phase} capture {key} shape')
            matches[key]=all(f32(a)==f32(b) for a,b in zip(x,y))
        if not matches or not all(matches.values()): raise ValueError(f'{phase}: aggregate capture float32 identity failed')
        capture_checks[phase]=matches
    sw_partition_f32={}
    for key in ('VISDIR','VISDIF','NIRDIR','NIRDIF','VISDIR_PREDELTA','NIRDIR_PREDELTA'):
        if key in capture['SW'] and key in output_sections['baseline_sw']:
            a=output_sections['baseline_sw'][key]['values'];b=capture['SW'][key]['values']
            sw_partition_f32[key]=all(f32(x)==f32(y) for x,y in zip(a,b))
    phase_summary={}; selected_metrics={}
    for phase,baseid,cfid in [('LW','baseline_lw','legacy_dry_lw'),('SW','baseline_sw','legacy_dry_sw')]:
        b=output_sections[baseid];c=output_sections[cfid]
        phase_summary[phase]={}; selected_metrics[phase]={}
        for name in ('DN','UP','DNC','UPC','HR','HRC','GAS_COL_DRY','GAS_TAU_RAW','DIRECT','DIRECTC','DIRECT_PREDELTA','DIRECTC_PREDELTA'):
            if name not in b: continue
            vals=delta(b[name]['values'],c[name]['values'])
            phase_summary[phase][name]=vals
        for name,index,label in [('DN',0,'surface_down'),('UP',-1,'toa_up'),('DNC',0,'surface_clear_down'),('UPC',-1,'toa_clear_up')]:
            selected_metrics[phase][label]={'baseline':b[name]['values'][index],'counterfactual':c[name]['values'][index],'delta':c[name]['values'][index]-b[name]['values'][index]}
        if phase=='SW':
            for name,index,label in [('DIRECT',0,'surface_direct'),('DIRECT',-1,'toa_direct'),('DIRECTC',0,'surface_clear_direct'),('DIRECTC',-1,'toa_clear_direct')]:
                selected_metrics[phase][label]={'baseline':b[name]['values'][index],'counterfactual':c[name]['values'][index],'delta':c[name]['values'][index]-b[name]['values'][index]}
        hr0=b['HR']['values']; hr1=c['HR']['values']; dh=[y-x for x,y in zip(hr0,hr1)]; native=dh[:44]; ext=dh[44:]
        selected_metrics[phase]['heating']={'layer31_delta':dh[30],'native44_max_abs_delta':max(map(abs,native)),'native44_max_abs_delta_layer_1based':max(range(44),key=lambda k:abs(native[k]))+1,'extension_count':len(ext),'extension_max_abs_delta':max(map(abs,ext),default=0.0)}
    report={'status':'PASS_PORTABLE_DRY_GAS_REPLAY_CHECKS','four_call_receipt_sha256':sha_file(HERE/'evidence/four-call-execution.json'),
      'scope':{'standalone_reference_calls':4,'wrf_or_real_calls':0,'native_layers':44,'upper_extension_inputs_unchanged':{'LW':13,'SW':1},'counterfactual_changes':'only NATIVE_DRY_LAYER_MASS_KG_M2 native values; no physical-accuracy claim'},
      'input_checks':{'legacy_mass_conversion':'exported RRTMG4 INPUT COLDry/COLDRY molecule_cm-2 × captured MOL_WEIGHT_DRY × 10000 / 6.02214076e23','components_unchanged':'all parsed non-mass input sections exact; held cloud/CU/precip/frozen/mask/radius output components exact'},
      'actual_capture_aggregate_real32_identity':capture_checks,'sw_partition_real32_identity_vs_capture':sw_partition_f32,'native_dry_column_residuals':column_residuals,'selected_flux_and_heating':selected_metrics,'counterfactual_minus_baseline':phase_summary,
      'note':'SW visible/NIR partition fields may differ at the REAL32 serialization boundary; no whole-output equality is claimed.'}
    archived=json.loads((HERE/'evidence/causal-analysis-original.json').read_text())
    for phase in ('LW','SW'):
        old=archived['phase_results'][phase]['flux_and_heating']
        for metric,oldname in [('surface_down','surface_down'),('toa_up','toa_up'),('surface_clear_down','surface_clear_down'),('toa_clear_up','toa_clear_up')]:
            for key in ('baseline','counterfactual','delta_cf_minus_baseline'):
                newkey={'baseline':'baseline','counterfactual':'counterfactual','delta_cf_minus_baseline':'delta'}[key]
                if not math.isclose(selected_metrics[phase][metric][newkey],old[oldname][key],rel_tol=0.0,abs_tol=1e-12):
                    raise ValueError(f'{phase}: {metric}.{key} disagrees with archived analysis')
        for key,newkey in [('HR_layer31_delta','layer31_delta'),('HR_native44_max_abs_delta','native44_max_abs_delta')]:
            if not math.isclose(selected_metrics[phase]['heating'][newkey],old[key],rel_tol=0.0,abs_tol=1e-12):
                raise ValueError(f'{phase}: selected heating metric {key} disagrees with archived analysis')
    print(json.dumps(report,indent=2,sort_keys=True,allow_nan=False))

if __name__=='__main__': main()
