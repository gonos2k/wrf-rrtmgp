#!/usr/bin/env python3
"""Prepare exact-band SW cloud-optics control and legacy-swap inputs; no solver calls."""
from __future__ import annotations
import argparse, gzip, hashlib, importlib.util, json, math, sys, tempfile
from pathlib import Path
import netCDF4
import numpy as np

SCHEMA='same-call-exact-band-cloud-swap-preparation-v1'
EXPECTED_LAYERS=(30,31,32)  # native, one-based
PROPERTIES=('TAU','SSA','ASYM')

class PrepError(ValueError): pass

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def pin(path:Path,root:Path)->dict:
    st=path.stat(); return {'path':path.relative_to(root).as_posix(),'sha256':sha(path),'size_bytes':st.st_size}
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod);return mod

def read_text_section(path:Path,name:str,rank:int):
    lines=path.read_text(encoding='ascii').splitlines()
    for i,line in enumerate(lines):
        words=line.split()
        if not words or words[0]!=name: continue
        try: dims=tuple(int(x) for x in words[1:])
        except ValueError: continue
        if len(dims)!=rank: continue
        count=math.prod(dims); vals=[]; j=i+1
        while len(vals)<count and j<len(lines):
            vals.extend(float(x.replace('D','E').replace('d','e')) for x in lines[j].split()); j+=1
        if len(vals)!=count: raise PrepError(f'{path}: truncated {name}')
        return np.asarray(vals,dtype=np.float64).reshape(dims)
    raise PrepError(f'{path}: missing {name} rank-{rank} section')

def exact_band_map(legacy_bounds,gp_bounds):
    """Return (gp band 0-based, legacy band 0-based) exact physical edge joins."""
    out=[]; used=set()
    for gi,(lo,hi) in enumerate(gp_bounds):
        matches=[li for li,pair in enumerate(legacy_bounds) if float(pair[0])==float(lo) and float(pair[1])==float(hi)]
        if len(matches)>1: raise PrepError(f'ambiguous exact physical band pair {lo,hi}')
        if matches:
            li=matches[0]
            if li in used: raise PrepError(f'legacy band reused by more than one GP band: {li+1}')
            used.add(li);out.append((gi,li))
    return out

def validate_layer_set(layers):
    if tuple(layers)!=EXPECTED_LAYERS: raise PrepError(f'layer scope must be exactly native layers {EXPECTED_LAYERS}')

def require_shape(name,actual,expected):
    if tuple(actual)!=tuple(expected): raise PrepError(f'{name}: recorded shape {tuple(actual)} differs from required {tuple(expected)}')

def exact_constant(values,label):
    if not values or any(float(x)!=float(values[0]) for x in values[1:]): raise PrepError(f'{label}: values are not exactly constant across all legacy g points')
    return float(values[0])

def validate_mask(mask_values,label):
    if not mask_values or any(float(x)!=1.0 for x in mask_values): raise PrepError(f'{label}: every mapped legacy/GP sample must be cloudy (mask=1)')

def ensure_change_scope(changed,allowed):
    extra=set(changed)-set(allowed)
    if extra: raise PrepError(f'optics changed outside allowed native-layer/exact-band scope: {sorted(extra)[:8]}')

def make_override(path,bounds,tau,ssa,asym):
    # Arrays are [column, native-layer, GP-band], flattened in Fortran order.
    nc,nl,nb=tau.shape
    lines=['WRF_SW_OPTICS_OVERRIDE_V1',f'{nc} {nl} {nb}',f'BAND_LIMITS 2 {nb}']
    lines.extend(f'{x:.16E}' for x in np.asarray(bounds,dtype=np.float64).reshape((2,nb),order='F').ravel(order='F'))
    for name,arr in (('TAU',tau),('SSA',ssa),('ASYM',asym)):
        lines.append(f'{name} {nc} {nl} {nb}')
        lines.extend(f'{x:.16E}' for x in np.asarray(arr,dtype=np.float64).ravel(order='F'))
    path.write_text('\n'.join(lines)+'\n',encoding='ascii')


def read_override(path):
    lines=path.read_text(encoding='ascii').splitlines()
    if len(lines)<5 or lines[0]!='WRF_SW_OPTICS_OVERRIDE_V1': raise PrepError('bad generated override magic')
    nc,nl,nb=map(int,lines[1].split()); cursor=2
    if lines[cursor].split()!=['BAND_LIMITS','2',str(nb)]: raise PrepError('bad generated BAND_LIMITS header')
    cursor+=1; count=2*nb; bandvals=[]
    while len(bandvals)<count: bandvals.extend(float(x) for x in lines[cursor].split());cursor+=1
    bands=np.asarray(bandvals,dtype=np.float64).reshape((2,nb),order='F')
    fields={}
    for wanted in ('TAU','SSA','ASYM'):
        if lines[cursor].split()!=[wanted,str(nc),str(nl),str(nb)]: raise PrepError(f'bad generated {wanted} header')
        cursor+=1; vals=[]; n=nc*nl*nb
        while len(vals)<n: vals.extend(float(x) for x in lines[cursor].split());cursor+=1
        fields[wanted]=np.asarray(vals,dtype=np.float64).reshape((nc,nl,nb),order='F')
    if cursor!=len(lines): raise PrepError('trailing data in generated override')
    return bands,fields

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--workspace',type=Path,required=True,help='repository/workspace root')
    ap.add_argument('--output-dir',type=Path,required=True,help='new absent output directory')
    args=ap.parse_args(); root=args.workspace.resolve(); out=args.output_dir.resolve()
    if out.exists(): raise SystemExit(f'refusing to overwrite existing preparation directory: {out}')
    export_gz=root/'build/udm37-cf0-cu-replay-pr-work/validation/rrtmgp37/rrtmg4-same-call-attribution/exports/rrtmg4_d01_i24_j55_step2161_sw.txt.gz'
    trace_dir=root/'build/udm37-cf0-cu-replay-pr-work/validation/rrtmgp37/rrtmg4-same-call-attribution/traces/NEW_ON'
    input_path=trace_dir/'sw_000001.input'; raw_path=trace_dir/'sw_000001.raw'
    baseline_path=root/'build/udm37-cf0-retained-cu-runtime-v1/run-v1/outputs/baseline-sw.result'
    execution_path=root/'build/udm37-cf0-retained-cu-runtime-v1/run-v1/execution.json'
    coeff_path=root/'build/cf0-cu-src-v1/WRF/run/rrtmgp-gas-sw-g112.nc'
    coeff_copy_path=root/'build/udm37-cf0-cu-replay-pr-work/WRF/run/rrtmgp-gas-sw-g112.nc'
    export_parser=root/'build/udm37-cf0-cu-replay-pr-work/validation/rrtmgp37/rrtmg4-same-call-attribution/parser/read_export.py'
    result_parser=root/'build/udm37-cf0-cu-replay-pr-work/WRF/test/rrtmgp/compare_column_replay.py'
    legacy_source=root/'build/udm37-current-rrtmg4-optics-export-work/WRF/phys/module_ra_rrtmg_sw.F'
    compiled_legacy_source=root/'build/cf0-cu-src-v1/WRF/phys/module_ra_rrtmg_sw.F'
    publication_legacy_source=root/'build/udm37-cf0-cu-replay-pr-work/WRF/phys/module_ra_rrtmg_sw.F'
    replay_source=root/'build/cf0-cu-src-v1/WRF/test/rrtmgp/reference_column.f90'
    reference_exe=root/'build/cf0-cu-build-v1/cmake-build/reference_column'
    for p in (export_gz,input_path,raw_path,baseline_path,execution_path,coeff_path,coeff_copy_path,export_parser,result_parser,legacy_source,compiled_legacy_source,publication_legacy_source,replay_source,reference_exe):
        if not p.is_file(): raise PrepError(f'missing pinned source input: {p}')
    pins={label:pin(p,root) for label,p in {
      'legacy_export_gzip':export_gz,'new_on_trace_input':input_path,'new_on_trace_raw':raw_path,
      'same_executable_baseline_result':baseline_path,'baseline_execution_receipt':execution_path,'sw_gas_coefficients_executed_tree':coeff_path,
      'sw_gas_coefficients_publication_copy':coeff_copy_path,'export_parser':export_parser,'result_parser':result_parser,
      'capture_legacy_sw_source':legacy_source,'reference_build_legacy_sw_source':compiled_legacy_source,'publication_legacy_sw_source':publication_legacy_source,
      'executed_reference_source':replay_source,'executed_reference_executable':reference_exe}.items()}
    if len(input_path.read_text().splitlines())<2 or input_path.read_text().splitlines()[:2]!=['RRTMGP_REPLAY_V11','SW 1 45 2 1762397950 4']:
        raise PrepError('SW V11 input identity/header differs from expected selected capture')
    if raw_path.read_text().splitlines()[:2]!=['RRTMGP_RAW_V1','SW 24 55 44']:
        raise PrepError('SW raw identity/header differs from selected point/native44 contract')
    if sha(reference_exe)!='353333cc96bce44d26c02ca7585c0ddef8996fc74a05904220fba83db76cd97f': raise PrepError('reference executable differs from approved eight-call build identity')
    if sha(coeff_path)!=sha(coeff_copy_path): raise PrepError('executed and publication SW coefficient files differ')
    execution=json.loads(execution_path.read_text())
    baseline_calls=[c for c in execution.get('calls',[]) if c.get('case_id')=='baseline-sw']
    if execution.get('status')!='ALL_EIGHT_CALLS_VALIDATED' or len(baseline_calls)!=1: raise PrepError('baseline execution receipt is not terminal PASS with one baseline-sw call')
    baseline_call=baseline_calls[0]
    if baseline_call.get('returncode')!=0 or baseline_call.get('status')!='CALL_VALIDATED' or baseline_call.get('timed_out'): raise PrepError('baseline SW execution was not validated')
    if baseline_call.get('output_pin',{}).get('sha256')!=sha(baseline_path) or baseline_call.get('command',[None])[0]!=str(reference_exe): raise PrepError('baseline result is not bound to the pinned reference executable/output')
    if len(baseline_call.get('command',[]))<4 or hashlib.sha256(Path(baseline_call['command'][2]).read_bytes()).hexdigest()!=pins['new_on_trace_input']['sha256']:
        raise PrepError('baseline execution input does not match the selected captured SW V11 input')
    result_mod=load_module('compare_column_replay',result_parser)
    input_plev=read_text_section(input_path,'PLEV',2).reshape(-1)
    input_play=read_text_section(input_path,'PLAY',2).reshape(-1)
    input_cf=read_text_section(input_path,'CF',2).reshape(-1)
    raw_dp=read_text_section(raw_path,'DP_HPA',1).reshape(-1)
    raw_cf=read_text_section(raw_path,'CF',1).reshape(-1)
    if input_plev.shape!=(46,) or input_play.shape!=(45,) or input_cf.shape!=(45,) or raw_dp.shape!=(44,) or raw_cf.shape!=(44,): raise PrepError('pressure/cloud-fraction layer dimensions do not match native44 / engine45 contract')
    if not np.all(np.diff(input_plev)<0) or not np.all(np.diff(input_play)<0) or not np.all(raw_dp>0): raise PrepError('captured pressure interfaces are not strictly decreasing or native pressure thickness is nonpositive')
    if not np.array_equal(raw_dp,input_plev[:44]-input_plev[1:45]): raise PrepError('native DP_HPA does not exactly match first44 bottom-up input pressure intervals')
    if not np.array_equal(raw_cf,input_cf[:44]): raise PrepError('native CF trace does not exactly match first44 replay-input cloud fractions')
    validate_layer_set(EXPECTED_LAYERS)
    for layer in EXPECTED_LAYERS:
        if input_cf[layer-1]!=1.0 or raw_cf[layer-1]!=1.0: raise PrepError(f'native layer {layer} is not CF=1 in replay input and raw trace')
    base=result_mod.read_result(baseline_path)
    if base['phase']!='SW' or base['nc']!=1 or base['nl']!=45: raise PrepError('baseline result must be SW 1-column, 45 engine layers')
    for field in ('PREPARED_TAU','PREPARED_SSA','PREPARED_G','MASK'):
        if field not in base['sections']: raise PrepError(f'baseline missing {field}')
    tau0=np.asarray(base['sections']['PREPARED_TAU'],dtype=np.float64).copy()
    ssa0=np.asarray(base['sections']['PREPARED_SSA'],dtype=np.float64).copy()
    asym0=np.asarray(base['sections']['PREPARED_G'],dtype=np.float64).copy()
    gp_mask=np.asarray(base['sections']['MASK'],dtype=np.float64)
    if tau0.shape!=(1,45,14) or ssa0.shape!=tau0.shape or asym0.shape!=tau0.shape or gp_mask.shape!=(1,45,112):
        raise PrepError(f'unexpected baseline prepared/mask shapes {tau0.shape}/{ssa0.shape}/{asym0.shape}/{gp_mask.shape}')
    with netCDF4.Dataset(coeff_path) as nc:
        gp_bounds=np.asarray(nc.variables['bnd_limits_wavenumber'][:],dtype=np.float64)
        gp_gpts=np.asarray(nc.variables['bnd_limits_gpt'][:],dtype=np.int64)
    if gp_bounds.shape!=(14,2) or gp_gpts.shape!=(14,2): raise PrepError('unexpected pinned SW coefficient band table dimensions')
    with tempfile.TemporaryDirectory(prefix='exact-band-swap-') as td:
        plain=Path(td)/'sw-export.txt'
        with gzip.open(export_gz,'rb') as src: plain.write_bytes(src.read())
        export_mod=load_module('same_call_export_parser',export_parser)
        exp=export_mod.read_export(plain,expected_phase='SW')
    meta=exp['metadata']
    if meta!={'phase':'SW','domain':1,'step':2161,'source_seconds':129600.0,'i':24,'j':55}:
        raise PrepError(f'wrong selected export source: {meta}')
    F=exp['fields']
    if not np.array_equal(np.asarray(F['INPUT','PLEV'].values,dtype=np.float64),input_plev): raise PrepError('legacy export PLEV differs bitwise from SW V11 replay input')
    if not np.array_equal(np.asarray(F['INPUT','PLAY'].values,dtype=np.float64),input_play): raise PrepError('legacy export PLAY differs bitwise from SW V11 replay input')
    required=[('CLOUD',n) for n in ('BAND_INDEX','GPOINT_TO_BAND','BAND_WAVENUM_LO','BAND_WAVENUM_HI','MCICA_MASK','CLDPRMC_TAU','CLDPRMC_SSA','CLDPRMC_ASM')]
    if any(k not in F for k in required):raise PrepError('legacy export missing one of the required physical band/mask/optics records')
    for key,shape in {('CLOUD','BAND_INDEX'):(14,),('CLOUD','GPOINT_TO_BAND'):(112,),('CLOUD','BAND_WAVENUM_LO'):(14,),('CLOUD','BAND_WAVENUM_HI'):(14,),('CLOUD','MCICA_MASK'):(112,45),('CLOUD','CLDPRMC_TAU'):(112,45),('CLOUD','CLDPRMC_SSA'):(112,45),('CLOUD','CLDPRMC_ASM'):(112,45)}.items():
        require_shape('/'.join(key),F[key].shape,shape)
    require_shape('INPUT/PLEV',F['INPUT','PLEV'].shape,(46,))
    require_shape('INPUT/PLAY',F['INPUT','PLAY'].shape,(45,))
    band_index=np.asarray(F['CLOUD','BAND_INDEX'].values,dtype=np.float64)
    legacy_bounds=np.column_stack((F['CLOUD','BAND_WAVENUM_LO'].values,F['CLOUD','BAND_WAVENUM_HI'].values)).astype(np.float64)
    map_legacy=np.asarray(F['CLOUD','GPOINT_TO_BAND'].values,dtype=np.float64)
    if band_index.shape!=(14,) or legacy_bounds.shape!=(14,2) or map_legacy.shape!=(112,):raise PrepError('unexpected legacy SW dimensions')
    if not np.array_equal(np.asarray([int(x) for x in gp_gpts[:,0]]),np.asarray([1,11,19,30,38,47,57,68,72,81,90,97,103,110])):raise PrepError('pinned GP gpoint lower limits changed')
    if not np.array_equal(np.asarray([int(x) for x in gp_gpts[:,1]]),np.asarray([10,18,29,37,46,56,67,71,80,89,96,102,109,112])):raise PrepError('pinned GP gpoint upper limits changed')
    joins=exact_band_map(legacy_bounds,gp_bounds)
    if len(joins)!=12 or [b for b,_ in joins]!=list(range(2,14)):
        raise PrepError(f'expected exact joined GP bands 3–14 only; got {[(g+1,l+1) for g,l in joins]}')
    validate_layer_set(EXPECTED_LAYERS)
    metrics=[]; tau1=tau0.copy();ssa1=ssa0.copy();asym1=asym0.copy()
    tau_l=np.asarray(F['CLOUD','CLDPRMC_TAU'].values,dtype=np.float64).reshape((112,45),order='F')
    ssa_l=np.asarray(F['CLOUD','CLDPRMC_SSA'].values,dtype=np.float64).reshape((112,45),order='F')
    asym_l=np.asarray(F['CLOUD','CLDPRMC_ASM'].values,dtype=np.float64).reshape((112,45),order='F')
    mask_l=np.asarray(F['CLOUD','MCICA_MASK'].values,dtype=np.float64).reshape((112,45),order='F')
    for gp_band,legacy_band in joins:
        lo,hi=gp_bounds[gp_band]
        target_gpts=np.arange(int(gp_gpts[gp_band,0])-1,int(gp_gpts[gp_band,1]),dtype=int)
        legacy_band_code=band_index[legacy_band]
        legacy_gpts=np.where(map_legacy==legacy_band_code)[0]
        for layer in EXPECTED_LAYERS:
            k=layer-1
            validate_mask(mask_l[:,k].tolist(),f'legacy mask all112 g points layer {layer}')
            validate_mask(gp_mask[0,k,:].tolist(),f'GP mask all112 g points layer {layer}')
            vals={}
            for name,arr in (('TAU',tau_l),('SSA',ssa_l),('ASYM',asym_l)):
                val=exact_constant(arr[legacy_gpts,k].tolist(),f'{name} band {lo:g}-{hi:g} layer {layer}')
                vals[name]=val
            if not (vals['TAU']>0 and 0<=vals['SSA']<=1 and -1<=vals['ASYM']<=1):
                raise PrepError(f'out-of-contract legacy optics in band {lo:g}-{hi:g}, layer {layer}: {vals}')
            tau1[0,k,gp_band]=vals['TAU']; ssa1[0,k,gp_band]=vals['SSA']; asym1[0,k,gp_band]=vals['ASYM']
            metrics.append({'native_layer_1based':layer,'gp_band_1based':gp_band+1,'legacy_band_1based':legacy_band+1,
              'legacy_band_code':int(legacy_band_code),'bounds_cm-1':[float(lo),float(hi)],
              'gp_gpoint_bounds_1based_inclusive':[int(gp_gpts[gp_band,0]),int(gp_gpts[gp_band,1]),
              ],'gp_gpoint_count':int(target_gpts.size),'legacy_gpoint_count':int(legacy_gpts.size),'mask_all_one_both_engines':True,
              'legacy_values_exactly_constant_across_all_legacy_gpoints':True,'legacy_values':vals})
    # Assert no array coordinate changed outside the exact requested band/layer mask.
    allowed={(0,layer-1,gp_band) for gp_band,_ in joins for layer in EXPECTED_LAYERS}
    tau0bits=tau0.view(np.uint64); ssa0bits=ssa0.view(np.uint64); asym0bits=asym0.view(np.uint64)
    tau1bits=tau1.view(np.uint64); ssa1bits=ssa1.view(np.uint64); asym1bits=asym1.view(np.uint64)
    changed={(c,k,b) for c in range(1) for k in range(45) for b in range(14)
             if (tau1bits[c,k,b]!=tau0bits[c,k,b] or ssa1bits[c,k,b]!=ssa0bits[c,k,b] or asym1bits[c,k,b]!=asym0bits[c,k,b])}
    ensure_change_scope(changed,allowed)
    if any((tau1bits[c,k,b]==tau0bits[c,k,b] and ssa1bits[c,k,b]==ssa0bits[c,k,b] and asym1bits[c,k,b]==asym0bits[c,k,b]) for c,k,b in allowed):
        raise PrepError('at least one eligible matched cloud optics group did not change')
    # Offline negative controls, no compiled calls.
    negatives={}
    bad=gp_bounds.copy();bad[2,1]+=1.0
    try: exact_band_map(legacy_bounds,bad) if len(exact_band_map(legacy_bounds,bad))==12 else (_ for _ in ()).throw(PrepError('wrong edge still joined'))
    except PrepError: negatives['wrong_physical_band_edge_rejected']=True
    try: validate_layer_set((29,30,31))
    except PrepError: negatives['wrongly_included_layer_rejected']=True
    else: raise PrepError('wrong layer negative control passed')
    bgi,li=joins[0]; gpt0=np.where(map_legacy==band_index[li])[0]; vals=tau_l[gpt0,29].copy(); vals[-1]=np.nextafter(vals[-1],np.inf)
    try: exact_constant(vals.tolist(),'synthetic nonconstant TAU')
    except PrepError: negatives['nonconstant_legacy_gpoints_rejected']=True
    else: raise PrepError('nonconstant gpoint negative control passed')
    try: validate_mask([1.0,0.0,1.0],'synthetic missed cloudy sample')
    except PrepError: negatives['missed_cloudy_mask_rejected']=True
    else: raise PrepError('missed-mask negative control passed')
    try: require_shape('synthetic transposed optics',(45,112),(112,45))
    except PrepError: negatives['swapped_export_axes_rejected']=True
    else: raise PrepError('swapped-axis negative control passed')
    try: ensure_change_scope({(0,28,0)},allowed)
    except PrepError: negatives['out_of_scope_layer_band_change_rejected']=True
    else: raise PrepError('out-of-scope optics mutation negative control passed')
    # New unique output path; write baseline-shaped control and targeted legacy swap.
    out.mkdir(parents=True)
    (out/'inputs').mkdir()
    control=out/'inputs/sw-optics-control-full-prepared.optics';variant=out/'inputs/sw-optics-legacy-exact-band-k30-32.optics'
    make_override(control,gp_bounds.T,tau0,ssa0,asym0);make_override(variant,gp_bounds.T,tau1,ssa1,asym1)
    # Prove text serialization round-trips every REAL64 payload exactly.
    for p,expected in ((control,(tau0,ssa0,asym0)),(variant,(tau1,ssa1,asym1))):
        read_bands,read_fields=read_override(p)
        if not np.array_equal(read_bands,gp_bounds.T): raise PrepError(f'{p.name}: band bounds changed in writer round-trip')
        for key,want in zip(('TAU','SSA','ASYM'),expected):
            if read_fields[key].tobytes(order='F')!=np.asarray(want,dtype=np.float64).tobytes(order='F'): raise PrepError(f'{p.name}: {key} changed at IEEE binary64 bit level in writer round-trip')
    generated={name:{'path':p.relative_to(root).as_posix(),'sha256':sha(p),'size_bytes':p.stat().st_size}
               for name,p in [('full_baseline_prepared_control',control),('legacy_exact_common_band_swap',variant)]}
    # Verify immutable inputs stayed at their initial pins after parsing/writing.
    if any(sha(root/x['path'])!=x['sha256'] for x in pins.values()):raise PrepError('source input changed during preparation')
    source=out/'generate.py';source.write_bytes(Path(__file__).read_bytes())
    plan={'schema':SCHEMA,'status':'PREPARED_OFFLINE_NO_SOLVER_CALLS','scope':{'point':{'domain':1,'i':24,'j':55,'step':2161,'source_seconds':129600.0},'phase':'SW','native_layers_1based':[30,31,32],
       'operator':'replace PREPARED TAU/SSA/G only in exact physical band-bound matches (12 of 14 bands) and native layers 30–32 with legacy CLDPRMC values',
       'baseline_context':'same-captured column baseline PREPARED optics include native cloud, retained CU/snow and precipitation contributions; control override is a full copy of that prepared state and is checked IEEE-binary64 bitwise against the baseline arrays',
       'interpretation_limit':'This is a combined prepared-cloud sensitivity. It is not a pure engine or PSD test: gas/state/solar/surface, retained CU, native hydrometeors, precipitation, masks, and unmatched bands remain as captured. No solver has been invoked.'},
      'pins':pins,'band_contract':{'gas_table_bands_cm-1':gp_bounds.tolist(),'gas_table_gpoint_bounds_1based_inclusive':gp_gpts.tolist(),
       'legacy_band_bounds_cm-1':legacy_bounds.tolist(),'exact_matches':[{'gp_band_1based':g+1,'legacy_band_1based':l+1,'bounds_cm-1':gp_bounds[g].tolist()} for g,l in joins],
       'unmatched_gp_band_indices_1based':[1,2],'gpoint_matching':'Use only exact physical band bounds and each engine native gpoint-to-band map; quadrature counts may differ, no positional cross-engine g-point matching or averaging.'},
      'eligibility':{'native_layers_1based':list(EXPECTED_LAYERS),'native_layer_contract':'Native pressure layers are bottom-first: the captured input has 46 PLEV interfaces and raw/input DP_HPA exactly equals the first44 interface differences; engine has45 layers, with one upper extension beyond native44.','cloud_fraction':{'input_CF_layers30_32_exactly_one':True,'raw_CF_layers30_32_exactly_one':True,'raw_CF_equals_input_CF_native_prefix':True},'band_layer_cells':len(metrics),'expected_band_layer_cells':36,'property_assignments':3*len(metrics),'expected_property_assignments':108,'mask_all_one_for_all112_gpoints_both_engines':True,'legacy_export_pressure_interfaces_and_layer_means_match_replay_input_bitwise':True,
       'legacy_optics_constant_per_exact_band_and_layer':True,'metrics':metrics},
      'generated_overrides':generated,'offline_negative_controls':negatives,
      'provenance':{'source_note':'module_ra_rrtmg_sw.F cldprmc_sw outputs TAU/SSA/ASM after its delta-M transforms (not raw input optics); reference_column.f90 applies the override after prepared native/CU/precip composition and before mask generation. Raw state and input/component diagnostics are held, but the selected combined prepared native+CU+snow optical tuple is replaced; CU optics are therefore not retained in the RTE at those selected layer-band cells.',
       'relevant_source_paths':{'legacy_cloud_optics':'build/udm37-current-rrtmg4-optics-export-work/WRF/phys/module_ra_rrtmg_sw.F','reference_override':'build/udm37-cf0-cu-replay-pr-work/WRF/test/rrtmgp/reference_column.f90'},
       'source_location_note':'Current source reviewed around cldprmc_sw call/export, 9440-series; cldprmc_sw delta-M transform near 2187–2196; independent replay override application near 915–934 and parser near 1214–1288. Line numbers are locator hints, source contents must be verified using pinned hashes.',
       'direct_beam_caveat':'The override replaces prepared optical arrays; raw cloud/direct-beam bookkeeping remains a distinct path. Treat this as prepared-array sensitivity, not a fully consistent direct-beam attribution. The raw state and separately exported component diagnostics remain baseline, but the combined prepared native+CU+precip tuple is replaced at selected cells; CU optics are not retained in the RTE there.'},
      'outputs':generated,'generator_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
      'software':{'python':sys.version.split()[0],'numpy':np.__version__,'netCDF4':netCDF4.__version__}}
    (out/'plan-inputs.json').write_text(json.dumps(plan,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':plan['status'],'groups':len(metrics),'joined_bands':len(joins),'negative_controls':negatives,'outputs':generated},sort_keys=True))

if __name__=='__main__':main()
