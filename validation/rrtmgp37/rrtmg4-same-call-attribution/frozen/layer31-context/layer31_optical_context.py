#!/usr/bin/env python3
"""Bounded layer 30-32 radiative input inventory from existing RRTMG4/GP captures."""
import hashlib, importlib.util, json, math, subprocess, sys
from pathlib import Path
import numpy as np
from netCDF4 import Dataset
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'build/udm37-current-rrtmg4-optics-export-work'
RUN=ROOT/'build/udm37-rrtmg4-export-runtime-v1/NEW_ON'
RUNTIME=ROOT/'build/udm37-rrtmg4-export-runtime-v4'
ANALYSIS=ROOT/'build/udm37-current-rrtmg4-optics-export-analysis-v1'
LAYER_IDS=(29,30,31) # zero-based; centre is model layer 31

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def loadmod(name,path):
    sys.path.insert(0,str(Path(path).parent)); spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
ex=loadmod('exp_l31',ROOT/'build/udm37-rrtmg4-export-analysis-v1/read_export.py')
sys.path.insert(0,str(WORK/'WRF/test/rrtmgp'))
rp=loadmod('replay_l31',WORK/'WRF/test/rrtmgp/test_column_replay.py')

def parse_records(path,skip=2):
    lines=Path(path).read_text(encoding='ascii').splitlines(); rec={};i=skip
    while i<len(lines):
        h=lines[i].split();i+=1
        if not h:continue
        name=h[0].upper();shape=tuple(int(x) for x in h[1:]); n=math.prod(shape);vals=[]
        while len(vals)<n:
            if i>=len(lines):raise ValueError(f'truncated {name}')
            vals.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split());i+=1
        if len(vals)!=n or name in rec or not np.isfinite(vals).all():raise ValueError(f'bad {path}:{name}')
        rec[name]=np.asarray(vals,dtype=np.float64).reshape(shape,order='F')
    return lines,rec

def field(e,stage,name):
    x=e['fields'][stage,name]
    return np.asarray(x.values,dtype=np.float64).reshape(x.shape,order='F')

def summary(x):
    a=np.asarray(x,dtype=np.float64).reshape(-1)
    nz=a[a!=0]
    return {'count':int(a.size),'nonzero_count':int(nz.size),'unique_count':int(np.unique(a).size),
            'min_nonzero':float(nz.min()) if nz.size else None,'max_nonzero':float(nz.max()) if nz.size else None}

def scalar_at(a,k):
    v=np.asarray(a).reshape(-1)
    return float(v[k]) if k<len(v) else None

def raw_record_summary(raw,k):
    one_layer=['QC','QI','QR','QS','QG','QH','RHO','T','P_HPA','SOURCE_T','SOURCE_P_PA','AMD_W','QV',
               'CF','RAD_CF_SOURCE','UDM_CF_USED','UDM_CF_RECOMPUTED','UDM_CF_SOURCE_STEP','UDM_CF_TOP',
               'HAS_REQC','HAS_REQI','HAS_REQS','ICLOUD','SOURCE_RE_CLOUD','SOURCE_RE_ICE','SOURCE_RE_SNOW',
               'REL','REI','RES','CU_REL_RAW','CU_REI_RAW','CU_POPULATION_POLICY','CU_RADIUS_POLICY','CU_OCCURRENCE_POLICY',
               'PI','DRY_MASS_KG_M2','NATIVE_QC','NATIVE_QI','CU_QC','CU_QI','DP_CU','SH_CU','CF_CU',
               'CU_ACCEPTED_GRID_LWP','CU_ACCEPTED_GRID_IWP','CU_REJECTED_GRID_LWP','CU_REJECTED_GRID_IWP',
               'CU_OMITTED_CF0_LWP','CU_OMITTED_CF0_IWP','LWP_GRID','LWP_RADIATION','LWP_OMITTED',
               'IWP_GRID','IWP_RADIATION','IWP_OMITTED','RWP_GRID','RWP_RADIATION','RWP_OMITTED',
               'SWP_GRID','SWP_RADIATION','SWP_OMITTED','GWP_GRID','GWP_RADIATION','GWP_OMITTED',
               'HWP_GRID','HWP_RADIATION','HWP_OMITTED','FROZEN_LAMBDA_G_M-1','FROZEN_LAMBDA_H_M-1']
    out={}
    for n in one_layer:
        if n not in raw:continue
        a=np.asarray(raw[n]).reshape(-1)
        if len(a)>k:out[n]=float(a[k])
    return out

def band_property(arr,band_gp,layer):
    # g-point-first legacy properties: counts/ranges only, never an average.
    x=np.asarray(arr,dtype=np.float64)[band_gp,layer]
    nz=x[x!=0]
    return {'sample_count':int(x.size),'nonzero_count':int(nz.size),'distinct_value_count':int(np.unique(x).size),
            'nonzero_min':float(nz.min()) if nz.size else None,'nonzero_max':float(nz.max()) if nz.size else None}

def gp_band_values(result,phase,band_index,gpt_indices,layer):
    # Cloud/precip components are band-resolved; final optical fields are g-point-resolved.
    band_fields=['NATIVE_CLOUD_TAU','CU_CLOUD_TAU','PRECIP_TAU','CLOUD_TAU','PREPARED_TAU','FROZEN_TAU',
                 'GRAUPEL_TAU_EXT','HAIL_TAU_EXT','GRAUPEL_TAU_ABS','HAIL_TAU_ABS']
    if phase=='SW':
        band_fields += ['NATIVE_CLOUD_SSA','NATIVE_CLOUD_G','CU_CLOUD_SSA','CU_CLOUD_G','PRECIP_SSA','PRECIP_G',
                        'CLOUD_SSA','CLOUD_G','PREPARED_SSA','PREPARED_G','FROZEN_SSA','FROZEN_G',
                        'GRAUPEL_TAU_SCA','GRAUPEL_TAU_SCA_G','HAIL_TAU_SCA','HAIL_TAU_SCA_G']
    out={}
    for n in band_fields:
        if n not in result:continue
        a=np.asarray(result[n])
        if a.ndim==3 and a.shape[0]==1 and a.shape[1]>layer and a.shape[2]>band_index:
            out[n]={'value':float(a[0,layer,band_index])}
    for n in ['GAS_TAU','TOTAL_TAU'] + (['GAS_SSA','GAS_G','TOTAL_SSA','TOTAL_G'] if phase=='SW' else []):
        if n not in result:continue
        a=np.asarray(result[n])
        if a.ndim==3 and a.shape[0]==1 and a.shape[1]>layer and a.shape[2]>max(gpt_indices):
            out[n]=summary(a[0,layer,gpt_indices])
    mask=np.asarray(result['MASK'])
    if mask.ndim==3 and mask.shape[0]==1 and mask.shape[1]>layer:
        vals=mask[0,layer,gpt_indices]
        out['MASK']={'gpoint_count':int(vals.size),'hit_count':int((vals>0.5).sum())}
    return out

result={'schema':'layer31-optical-context-v1','scope':{'point':[24,55],'domain':1,'step':2161,'source_time_seconds':129600,
 'central_native_layer_one_based':31,'examined_native_layers_one_based':[30,31,32],
 'method':'read-only parsing of existing RRTMG4 exports and GP V10 trace files; no model/solver/build execution',
 'limits':['one selected point and timestep','not a flux attribution or accuracy result','no g-point positional pairing or unweighted g-point averages','only exact physical band bounds are joined; unmatched band edges remain separate']},'provenance':{},
 'units_contract':{'raw_qc_qi_qr_qs_qg_qh':'kg kg-1 (as captured in native raw trace)','raw_rho':'kg m-3','raw_p_hpa':'hPa','raw_source_p_pa':'Pa','raw_temperature':'K',
 'raw_SOURCE_RE_CLOUD_SOURCE_RE_ICE_SOURCE_RE_SNOW':'m','GP_REL_REI_RES_and_used_radius_fields':'micrometres',
 'IWP_LWP_RWP_SWP_GWP_HWP_paths':'g m-2','DRY_MASS_KG_M2':'kg m-2','GAS_COL_DRY':'dry-air molecular column cm-2',
 'optical_depth':'dimensionless','SSA_g':'dimensionless','wavenumber_bounds':'cm-1'},
 'band_join_contract':'Exact legacy-export bound pair is matched against pinned GP cloud-coefficient bnd_limits_wavenumber. GP result optical fields are g-point arrays; their bands are selected using the matching pinned gas-table bnd_limits_gpt. No positional cross-engine g-point pairing or unweighted spectral mean.',
 'sampling_contract':'Trace contains pre-sampling RAW/NATIVE/CU/PRECIP/PREPARED component optics, the sampled MASK, and final TOTAL solver optics. It does not expose a distinct sampled-cloud-optics bundle, so that intermediate is not independently reconstructed or asserted.'}
source_files=[WORK/'WRF/phys/module_ra_rrtmgp.F',WORK/'WRF/phys/module_ra_rrtmg_lw.F',WORK/'WRF/phys/module_ra_rrtmg_sw.F',
              RUN/'export/rrtmg4_d01_i24_j55_step2161_lw.txt',RUN/'export/rrtmg4_d01_i24_j55_step2161_sw.txt',
              RUN/'trace/lw_000001.raw',RUN/'trace/lw_000001.input',RUN/'trace/lw_000001.result',
              RUN/'trace/sw_000001.raw',RUN/'trace/sw_000001.input',RUN/'trace/sw_000001.result',
              WORK/'WRF/run/rrtmgp-clouds-lw-bnd.nc',WORK/'WRF/run/rrtmgp-clouds-sw-bnd.nc',
              WORK/'WRF/run/rrtmgp-gas-lw-g128.nc',WORK/'WRF/run/rrtmgp-gas-sw-g112.nc',
              RUNTIME/'execution.json',RUNTIME/'plan.json']
# Actual loader files are copied in the staged source run used by runtime; use plan receipt to locate/check as relevant.
for p in source_files:
    if not p.exists(): raise FileNotFoundError(p)
result['provenance']['files']={str(p.relative_to(ROOT)):{'sha256':sha(p),'size_bytes':p.stat().st_size} for p in source_files}
result['provenance']['runtime_build_source_commit']=json.loads((RUNTIME/'plan.json').read_text())['build_provenance']['commit']
result['provenance']['analysis_checkout_commit']=subprocess.check_output(['git','-C',str(WORK),'rev-parse','HEAD'],text=True).strip()
result['provenance']['wrf_git_tree']=subprocess.check_output(['git','-C',str(WORK),'rev-parse','HEAD:WRF'],text=True).strip()
result['provenance']['execution_receipt_sha256']=sha(RUNTIME/'execution.json')

# Exact cloud-band bounds loaded from the pinned GP cloud-band NetCDFs.
gp_bounds={}
gp_gpt_bounds={}
gp_gas_bounds={}
for phase,filename in [('LW','rrtmgp-clouds-lw-bnd.nc'),('SW','rrtmgp-clouds-sw-bnd.nc')]:
    p=WORK/'WRF/run'/filename
    with Dataset(p) as ds: gp_bounds[phase]=np.asarray(ds.variables['bnd_limits_wavenumber'][:],dtype=np.float64)
    gasfile=WORK/'WRF/run'/('rrtmgp-gas-lw-g128.nc' if phase=='LW' else 'rrtmgp-gas-sw-g112.nc')
    with Dataset(gasfile) as ds:
        gp_gpt_bounds[phase]=np.asarray(ds.variables['bnd_limits_gpt'][:],dtype=np.int64)
        gp_gas_bounds[phase]=np.asarray(ds.variables['bnd_limits_wavenumber'][:],dtype=np.float64)
    if not np.array_equal(gp_bounds[phase],gp_gas_bounds[phase]):
        raise ValueError(f'{phase}: cloud and gas coefficient band edges disagree')

for phase in ('LW','SW'):
    exp_path=RUN/'export'/f'rrtmg4_d01_i24_j55_step2161_{phase.lower()}.txt'
    e=ex.read_export(exp_path,expected_phase=phase)
    stem=phase.lower()+'_000001'; ipath=RUN/'trace'/(stem+'.input');rawpath=RUN/'trace'/(stem+'.raw');respath=RUN/'trace'/(stem+'.result')
    il,inp=parse_records(ipath);rl,res=parse_records(respath);_,i,j,raw=rp.read_raw(rawpath)
    # Squeeze only the known single leading column dimension.
    header=il[1].split()
    # Replay header is PHASE ncol nlay overlap seed iceflag.
    input_ncol,input_nlay=int(header[1]),int(header[2])
    inputs={k:(v[0] if v.ndim>=1 and v.shape[0]==1 else v) for k,v in inp.items()}
    nlay=inputs['PLAY'].size; native_layers=raw['DP_HPA'].size
    center_pressure=float(inputs['PLAY'][30])
    assert native_layers==44 and abs(center_pressure-160.3939666748047)<1e-5
    result.setdefault('phases',{})
    phaseout={'native_layers':int(native_layers),'solver_layers':int(nlay),'center_layer':{'one_based':31,'pressure_hpa':center_pressure,
        'adjacent_native_pressures_hpa':{str(k+1):float(inputs['PLAY'][k]) for k in LAYER_IDS}},
        'raw_udm_native_context':{str(k+1):raw_record_summary(raw,k) for k in LAYER_IDS},
        'gp_inputs':{},'gp_optics':{},'gp_gas_separate':{},'legacy_cloud_by_bound':{},'band_joins':[]}
    input_keys=['CF','LWP','IWP','RWP','SWP','GWP','HWP','REL','REI','RES','NATIVE_DRY_LAYER_MASS_KG_M2','FROZEN_MODE','FROZEN_OCCURRENCE']
    for k in input_keys:
        if k in inputs:
            a=np.asarray(inputs[k])
            if a.ndim==1 and a.size==nlay:
                phaseout['gp_inputs'][k]={str(lev+1):float(a[lev]) for lev in LAYER_IDS}
            else:phaseout['gp_inputs'][k]=a.reshape(-1).tolist()
    optics=['NATIVE_CLOUD_TAU','NATIVE_CLOUD_SSA','NATIVE_CLOUD_G','CU_CLOUD_TAU','CU_CLOUD_SSA','CU_CLOUD_G',
            'CU_RL_USED','CU_DI_USED','PRECIP_TAU','PRECIP_SSA','PRECIP_G','CLOUD_TAU','CLOUD_SSA','CLOUD_G',
            'PREPARED_TAU','PREPARED_SSA','PREPARED_G','RL_USED','DI_USED','DS_USED','MASK','FROZEN_TAU','FROZEN_SSA','FROZEN_G',
            'GRAUPEL_TAU_EXT','GRAUPEL_TAU_SCA','GRAUPEL_TAU_SCA_G','GRAUPEL_TAU_ABS','HAIL_TAU_EXT','HAIL_TAU_SCA','HAIL_TAU_SCA_G','HAIL_TAU_ABS','TOTAL_TAU','TOTAL_SSA','TOTAL_G']
    # Include unique values / hit counts per selected layer, without averaging g-point spectra.
    for n in optics:
        if n not in res:continue
        a=np.asarray(res[n])
        if n=='MASK' and a.ndim==3 and a.shape[0]==1 and a.shape[1]>31:
            phaseout['gp_optics'][n]={str(k+1):{'gpoint_count':int(a.shape[2]),'hit_count':int((a[0,k,:]>0.5).sum()),'hit_indices_zero_based':np.where(a[0,k,:]>0.5)[0].astype(int).tolist()} for k in LAYER_IDS}
        elif n in ('CU_RL_USED','CU_DI_USED','RL_USED','DI_USED','DS_USED') and a.ndim==3 and a.shape[0]==1 and a.shape[2]==1 and a.shape[1]>31:
            phaseout['gp_optics'][n]={str(k+1):float(a[0,k,0]) for k in LAYER_IDS}
        elif a.ndim==3 and a.shape[0]==1 and a.shape[1]>31:
            vals={}
            for k in LAYER_IDS:
                v=a[0,k,:]
                vals[str(k+1)]={'shape':list(v.shape),'nonzero_count':int((v!=0).sum()),'unique_value_count':int(np.unique(v).size),
                   'min':float(v.min()),'max':float(v.max()),'values_by_band':v.tolist()}
            phaseout['gp_optics'][n]=vals
    for n in ('GAS_TAU','GAS_TAU_RAW','GAS_COL_DRY'):
        if n in res:
            a=np.asarray(res[n]);
            if a.ndim==3 and a.shape[0]==1 and a.shape[2]==1:
                phaseout['gp_gas_separate'][n]={str(k+1):float(a[0,k,0]) for k in LAYER_IDS}
            elif a.ndim==3 and a.shape[0]==1:
                phaseout['gp_gas_separate'][n]={str(k+1):summary(a[0,k,:]) for k in LAYER_IDS}
    # RRTMG4 per-gpoint stochastic fields; map each gpoint to band index then by exact cm-1 bounds.
    L={(st,n):np.asarray(f.values,dtype=np.float64).reshape(f.shape,order='F') for (st,n),f in e['fields'].items()}
    layer_context={}
    for n in ('CLDPRMC_LWP','CLDPRMC_IWP','CLDPRMC_SWP','CLDPRMC_TAU','CLDPRMC_RELIQ','CLDPRMC_REICE','CLDPRMC_RESNOW',
              'RRTMG_INPUT_CLOUD_MASK','RRTMG_INPUT_CLOUD_TAU','RRTMG_INPUT_CLOUD_SSA','RRTMG_INPUT_CLOUD_ASM'):
        if ('CLOUD',n) not in L:continue
        a=L['CLOUD',n]
        if a.ndim==1:
            layer_context[n]={str(k+1):float(a[k]) for k in LAYER_IDS}
        elif a.ndim==2:
            layer_context[n]={str(k+1):summary(a[:,k]) for k in LAYER_IDS}
    phaseout['legacy_cloud_layer_context']=layer_context
    phaseout['legacy_cloud_layer_units']={n:e['fields']['CLOUD',n].units for n in layer_context if ('CLOUD',n) in e['fields']}
    legacy_lows=L['CLOUD','BAND_WAVENUM_LO'];legacy_highs=L['CLOUD','BAND_WAVENUM_HI'];legacy_bandids=L['CLOUD','BAND_INDEX'].astype(int)
    gpt_band=L['CLOUD','GPOINT_TO_BAND'].astype(int)
    legacy_bounds=[(float(legacy_lows[b]),float(legacy_highs[b])) for b in range(len(legacy_lows))]
    exact_gp_map={}
    for idx,(lo,hi) in enumerate(gp_bounds[phase]):exact_gp_map[(float(lo),float(hi))]=idx
    for lbi,(lo,hi) in enumerate(legacy_bounds):
        gpg=exact_gp_map.get((lo,hi)); bandid=int(legacy_bandids[lbi]); gpidx=np.where(gpt_band==bandid)[0]
        entry={'legacy_band_index':bandid,'bounds_cm-1':[lo,hi],'legacy_gpoint_count':int(gpidx.size),'exact_gp_band_index_zero_based':gpg,
               'exact_physical_band_match':gpg is not None,'legacy_properties':{},'gp_band_optics':None}
        layer=30
        for name in ('MCICA_MASK','CLDPRMC_TAU','CLDPRMC_LWP','CLDPRMC_IWP','CLDPRMC_SWP'):
            if ('CLOUD',name) not in L:continue
            arr=L['CLOUD',name]
            entry['legacy_properties'][name]=band_property(arr,gpidx,layer)
        if phase=='SW':
            for name in ('CLDPRMC_SSA','CLDPRMC_ASM','CLDPRMC_FSF','CLDPRMC_TAUOR'):
                if ('CLOUD',name) in L:entry['legacy_properties'][name]=band_property(L['CLOUD',name],gpidx,layer)
        if gpg is not None:
            first,last=gp_gpt_bounds[phase][gpg]
            gp_indices=np.arange(int(first)-1,int(last))
            entry['gp_band_optics']=gp_band_values(res,phase,gpg,gp_indices,layer)
        phaseout['legacy_cloud_by_bound'][f'{lo:g}-{hi:g}'] = entry
        phaseout['band_joins'].append({'legacy_bounds_cm-1':[lo,hi],'legacy_index':bandid,'gp_index_zero_based':gpg,'exact':gpg is not None})
    # Gas tau inventories are separately summarized over gpoints; no spectral position matching.
    gasname='TAUGAS' if ('GAS','TAUGAS') in L else None
    if gasname:
        gas=L['GAS',gasname]
        phaseout['legacy_gas_tau_separate']={str(k+1):summary(gas[:,k]) for k in LAYER_IDS}
    phaseout['actual_gp_header']={'input_ncol':input_ncol,'input_solver_layer_count':int(input_nlay),'raw_i':i,'raw_j':j,
       'iceflag':int(header[5]),'seed':int(header[4]),'overlap':int(header[3])}
    phaseout['legacy_final_flags']={n:int(L['CLOUD',n].reshape(-1)[0]) for n in ('INFLAG','ICEFLAG','LIQFLAG','ICLD')}
    phaseout['legacy_gpoint_count']=int(gpt_band.size)
    phaseout['gp_gpoint_count']=int(res['GAS_TAU'].shape[-1])
    phaseout['gp_band_count']=int(gp_bounds[phase].shape[0])
    result['phases'][phase]=phaseout

out=ROOT/'build/udm37-rrtmg4-layer31-optical-context-v1/layer31-optical-context.json'
out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
print(out)
for ph,d in result['phases'].items():
 print(ph,'raw',d['raw_udm_native_context']['31'])
 print('matched physical bands',sum(x['exact'] for x in d['band_joins']),'/',len(d['band_joins']))
 print('gpoints legacy/gp',d['legacy_gpoint_count'],d['gp_gpoint_count'],'bands GP',d['gp_band_count'])
