#!/usr/bin/env python3
"""Read-only analysis of one selected actual RRTMG4/UDM37 same-call export pair."""
import csv, hashlib, importlib.util, json, math, sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]

def loadmod(name,path):
    sys.path.insert(0,str(Path(path).parent)); s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
ex=loadmod('ex_v2',ROOT/'build/udm37-rrtmg4-export-analysis-v1/read_export.py')
rp=loadmod('rp_v2',ROOT/'build/udm37-current-rrtmg4-optics-export-work/WRF/test/rrtmgp/test_column_replay.py')

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def parse(path,skip=2):
    lines=Path(path).read_text(encoding='ascii').splitlines(); rec={};i=skip
    while i<len(lines):
        h=lines[i].split();i+=1
        if not h:continue
        name=h[0].upper();shape=tuple(map(int,h[1:]));n=math.prod(shape);v=[]
        while len(v)<n:
            v += [float(x.replace('D','E').replace('d','e')) for x in lines[i].split()];i+=1
        if name in rec or len(v)!=n or not np.isfinite(v).all(): raise ValueError(f'bad record {path} {name}')
        rec[name]=np.asarray(v,dtype=np.float64).reshape(shape,order='F')
    return lines,rec

def vec(x): return np.asarray(x,dtype=np.float64).reshape(-1)
def compare(a,b):
    a,b=vec(a),vec(b)
    if a.shape!=b.shape:return {'same_shape':False,'shape_a':list(a.shape),'shape_b':list(b.shape)}
    d=a-b
    return {'same_shape':True,'bitwise_equal':bool(np.array_equal(a,b)),'max_abs':float(np.max(np.abs(d))) if d.size else 0.,'mean_abs':float(np.mean(np.abs(d))) if d.size else 0.,'count_nonzero':int(np.count_nonzero(d)),'shape':list(a.shape)}
def desc(x):
    a=np.asarray(x,dtype=np.float64)
    return {'shape':list(a.shape),'min':float(a.min()),'max':float(a.max()),'sum':float(a.sum()),'count_positive':int((a>0).sum()),'count_zero':int((a==0).sum())}
def profile_diff(a,b,pressure):
    a,b=vec(a),vec(b);n=min(len(a),len(b),len(pressure));d=a[:n]-b[:n]
    k=int(np.argmax(np.abs(d)))
    return {'mapping':'bottom-up layer order; layer k matches PLAY[k] (hPa)','compared_layers':n,'max_abs':float(abs(d[k])),'mean_abs':float(np.mean(np.abs(d))),'count_nonzero':int(np.count_nonzero(d)),'max_abs_layer_zero_based':k,'max_abs_pressure_hpa':float(pressure[k]),'legacy_at_max':float(a[k]),'gp_at_max':float(b[k]),'legacy_minus_gp_at_max':float(d[k])}

def one(phase):
    dat=ROOT/'build/udm37-rrtmg4-export-runtime-v1/NEW_ON'; expfile=dat/'export'/f'rrtmg4_d01_i24_j55_step2161_{phase.lower()}.txt'
    e=ex.read_export(expfile,expected_phase=phase); f=e['fields']; L={(s,n):np.asarray(z.values,dtype=np.float64).reshape(z.shape,order='F') for (s,n),z in f.items()}
    trace=dat/'trace'; stem=phase.lower()+'_000001'; il,ip=parse(trace/(stem+'.input')); rl,rpout=parse(trace/(stem+'.result')); raw=trace/(stem+'.raw'); _,i,j,rawr=rp.read_raw(raw)
    p={k:v[0] if v.ndim>=1 and v.shape[0]==1 else v for k,v in ip.items()}
    g={k:v[0] if v.ndim>=1 and v.shape[0]==1 else v for k,v in rpout.items()}
    nlay=int(e['fields'][('INPUT','PLAY')].shape[0]); play=np.asarray(e['fields'][('INPUT','PLAY')].values).reshape(-1)
    # All comparing records are intentionally sliced/flattened only after validating their known column dimensions.
    checks={}
    profile_fields=('PLAY','PLEV','TLAY','TLEV','TSFC') if phase=='LW' else ('PLAY','PLEV','TLAY')
    for nm in profile_fields:
        if ('INPUT',nm) in L and nm in p:
            checks[nm]=compare(L['INPUT',nm],p[nm])
    gasmap={'H2O_VMR':'H2O','O3_VMR':'O3','CO2_VMR':'CO2','CH4_VMR':'CH4','N2O_VMR':'N2O','O2_VMR':'O2'}
    if phase=='LW':gasmap.update({'CFC11_VMR':'VMR_CFC11','CFC12_VMR':'VMR_CFC12','CFC22_VMR':'VMR_CFC22','CCl4_VMR':'VMR_CCL4'})
    for a,b in gasmap.items(): checks[a+'='+b]=compare(L['INPUT',a],p[b])
    extras={}
    if phase=='LW':
        extras['surface_emissivity=EMIS']=compare(L['INPUT','SURFACE_EMISSIVITY'],p['EMIS'])
    else:
        for a,b in [('ALBEDO_VIS_DIRECT','AVDIR'),('ALBEDO_VIS_DIFFUSE','AVDIF'),('ALBEDO_NIR_DIRECT','ANDIR'),('ALBEDO_NIR_DIFFUSE','ANDIF'),('COSZEN','MU0')]: extras[a+'='+b]=compare(L['INPUT',a],p[b])
    # Dry gas column is a distinct representation; keep units explicit and compare only if values are directly equal.
    coldry_name=next(n for n in ('COLDry','COLDRY') if ('INPUT',n) in L)
    drylegacy=vec(L['INPUT',coldry_name]); drygp=vec(g['GAS_COL_DRY']); dryrel=(drygp-drylegacy)/drylegacy; drymax=int(np.argmax(np.abs(dryrel))); drycol={'same_unit':'molecules cm-2 (RRTMGP gas_dry_column documents conversion to this; native dry-mass override is applied)','max_abs_relative_difference':float(np.max(np.abs(dryrel))),'mean_abs_relative_difference':float(np.mean(np.abs(dryrel))),'max_layer_zero_based':drymax,'legacy_at_max':float(drylegacy[drymax]),'gp_at_max':float(drygp[drymax]),'relative_gp_minus_legacy_at_max':float(dryrel[drymax]),'pressure_hpa_at_max':float(play[drymax]),'native44_max_abs_relative':float(np.max(np.abs(dryrel[:int(rawr['DP_HPA'].size)]))),'extension_max_abs_relative':float(np.max(np.abs(dryrel[int(rawr['DP_HPA'].size):]))) if len(dryrel)>int(rawr['DP_HPA'].size) else None}
    # Flux and heating. Legacy LW htr(0:nlayers) maps to WRF hr(1:nlayers)=htr(0:nlayers-1), as confirmed in adapter source.
    fluxnames={'UP_FLUX':'UP','DOWN_FLUX':'DN','UP_CLEAR_FLUX':'UPC','DOWN_CLEAR_FLUX':'DNC'}
    if phase=='SW':fluxnames.update({'DOWN_DIRECT':'DIRECT','DOWN_DIFFUSE':'DIFFUSE','UP_CLEAR_FLUX':'UPC','DOWN_CLEAR_FLUX':'DNC'})
    flux={}
    for a,b in fluxnames.items():
        if ('RESULT',a) not in L or b not in g:continue
        x=vec(L['RESULT',a]);y=vec(g[b]);n=min(x.size,y.size);d=x[:n]-y[:n];k=int(np.argmax(np.abs(d)))
        flux[a]={'legacy_surface':float(x[0]),'gp_surface':float(y[0]),'surface_gp_minus_legacy':float(y[0]-x[0]),'legacy_toa':float(x[n-1]),'gp_toa':float(y[n-1]),'toa_gp_minus_legacy':float(y[n-1]-x[n-1]),'profile':{'compared_levels':n,'max_abs':float(abs(d[k])),'mean_abs':float(np.mean(np.abs(d))),'max_level_index_zero_based':k,'legacy_at_max':float(x[k]),'gp_at_max':float(y[k]),'legacy_minus_gp_at_max':float(d[k])}}
    heat=np.asarray(L['RESULT','HEATING']).reshape(-1)
    if phase=='LW':heat=heat[:nlay]
    gpheat=vec(g['HR']); nnative=int(rawr['DP_HPA'].size)
    heating={'all_solver_layers':profile_diff(heat,gpheat,play),'native_shared_layers':profile_diff(heat[:nnative],gpheat[:nnative],play[:nnative]),'legacy_layers':int(heat.size),'gp_solver_layers':int(gpheat.size),'wrf_native_layers':nnative,'extra_adapter_layers':int(max(0,gpheat.size-nnative)),'note':'Native comparison uses raw DP_HPA extent only; appended solver layers reported separately.'}
    # Cloud paths are intentionally different stochastic representations: legacy values are per sampled g-point; GP input is grid/in-cloud layer state.
    paths={}
    for lname,gname in [('CLDPRMC_LWP','LWP'),('CLDPRMC_IWP','IWP'),('CLDPRMC_SWP','SWP')]:
        ar=L['CLOUD',lname]; gpv=vec(p[gname]);
        perlayer={'legacy_positive_gpoints':[],'legacy_positive_path_sum_g_m2_sampled':[]}
        for k in range(ar.shape[1]):
            x=ar[:,k]; perlayer['legacy_positive_gpoints'].append(int((x>0).sum()));perlayer['legacy_positive_path_sum_g_m2_sampled'].append(float(x.sum()))
        paths[lname]={'legacy_shape_gpoint_by_layer':list(ar.shape),'legacy_units':'g m-2 per cloud/g-point sample as written by rrtmg4 adapter','legacy_total_sampled_path_sum':float(ar.sum()),'legacy_positive_entries':int((ar>0).sum()),'legacy_by_layer':perlayer,'gp_input_shape_col_squeezed':list(np.asarray(p[gname]).shape),'gp_input_units_contract':'g m-2 grid/in-cloud path as replay input','gp_input':desc(gpv),'direct_equality_comparison':'not valid: different stochastic path representation/g-point counts and masks'}
    radii={}
    for a,b in [('CLDPRMC_RELIQ','REL'),('CLDPRMC_REICE','REI'),('CLDPRMC_RESNOW','RES')]:
        radii[a+'='+b]={'stats':compare(L['CLOUD',a],p[b]),'legacy':desc(L['CLOUD',a]),'gp':desc(p[b])}
    mask=np.asarray(g.get('MASK'))
    if mask.ndim==2 and mask.shape[0]==1:mask=mask[0]
    # legacy sampling masks are gpoint x layer; GP masks are gpoint x layer after input-column squeeze.
    lm=np.asarray(L['CLOUD','MCICA_MASK'])
    bands={'legacy_bounds_low_cm1':vec(L['CLOUD','BAND_WAVENUM_LO']).tolist(),'legacy_bounds_high_cm1':vec(L['CLOUD','BAND_WAVENUM_HI']).tolist(),'legacy_band_index':vec(L['CLOUD','BAND_INDEX']).astype(int).tolist(),'legacy_ngpt':int(L['CLOUD','GPOINT_TO_BAND'].size)}
    if 'BAND_LIMS_WAVENUMBER' in p:bands['gp_band_lims_wavenumber_2_by_nband']=np.asarray(p['BAND_LIMS_WAVENUMBER']).tolist()
    gpt={'legacy':int(L['CLOUD','GPOINT_TO_BAND'].size),'gp':int(np.asarray(rpout['GAS_TAU']).shape[-1]),'note':'g-point coefficient/mask spaces differ; no positional g-point matching'}
    # Source call explicitly forwards all optional CFC VMR arrays through set_gases_lw; only LW has them.
    return {'metadata':e['metadata'],'legacy_export_sha256':e['sha256'],'gp_files':{x:sha(trace/(stem+'.'+x)) for x in ('input','raw','result')},'point':{'i':i,'j':j,'ncol':1,'legacy_nlay':nlay,'gp_nlay':int(p['PLAY'].size),'wrf_native_nlay':int(rawr['DP_HPA'].size),'gp_overlap':int(il[1].split()[3]),'gp_seed':int(il[1].split()[4]),'gp_iceflag':int(il[1].split()[5])},'input_state_checks_bitwise':checks,'surface_solar_checks_bitwise':extras,'dry_gas_column':{'legacy_name':coldry_name,'legacy_units':f['INPUT',coldry_name].units,'gp_output':'GAS_COL_DRY','comparison':drycol,'legacy':desc(L['INPUT',coldry_name]),'gp':desc(g['GAS_COL_DRY'])},'flux_profiles':flux,'heating_profile':heating,'cloud_path_representations':paths,'cloud_radii':radii,'legacy_final_flags':{n:vec(L['CLOUD',n]).astype(int).tolist() for n in ('INFLAG','ICEFLAG','LIQFLAG','ICLD')},'gpoints':gpt,'bands':bands,'sw_only_note':('TLEV and TSFC are exported as zero GP replay inputs in SW and are not used as SW thermal boundary inputs; do not interpret as state mismatch.' if phase=='SW' else None),'mask_sampling':{'legacy_mask_shape':list(lm.shape),'legacy_mask_cloudy_fraction_by_layer':np.mean(lm,axis=0).tolist(),'gp_mask_shape':list(mask.shape),'gp_mask_cloudy_fraction_by_layer':np.mean(mask,axis=-1).tolist() if mask.ndim==2 else None,'note':'distinct seed/engine realization; not a same-mask check'},'radiative_context':{'gp_cf':desc(p['CF']),'mu0':float(vec(p['MU0'])[0]) if 'MU0' in p else None,'legacy_coszen':float(vec(L['INPUT','COSZEN'])[0]) if ('INPUT','COSZEN') in L else None,'gp_solar':desc(p['SOLAR']) if 'SOLAR' in p else None,'legacy_solar_constant':desc(L['INPUT','SOLAR_CONSTANT']) if ('INPUT','SOLAR_CONSTANT') in L else None,'solar_flux_toa_down_legacy':float(vec(L['RESULT','DOWN_FLUX'])[-1]) if phase=='SW' else None,'solar_flux_toa_down_gp':float(vec(g['DN'])[-1]) if phase=='SW' else None},'native_extent':{'raw_native_layer_count':int(rawr['DP_HPA'].size),'raw_source_pressure_hpa':desc(rawr['SOURCE_P_PA']) if 'SOURCE_P_PA' in rawr else None,'adapter_engine_layers':int(nlay),'adapter_only_layer_count':int(max(0,nlay-int(rawr['DP_HPA'].size)))},'snow_radius_mismatch_layers_zero_based':[int(k) for k in np.where(np.abs(vec(L['CLOUD','CLDPRMC_RESNOW'])-vec(p['RES']))>0)[0]],'snow_radius_vs_snow_path_at_mismatch': [{'layer_zero_based':int(k),'legacy_resnow_um':float(vec(L['CLOUD','CLDPRMC_RESNOW'])[k]),'gp_res_um':float(vec(p['RES'])[k]),'legacy_positive_gpoints':int((L['CLOUD','CLDPRMC_SWP'][:,k]>0).sum()),'gp_swp_g_m2':float(vec(p['SWP'])[k])} for k in np.where(np.abs(vec(L['CLOUD','CLDPRMC_RESNOW'])-vec(p['RES']))>0)[0]] }

root=ROOT/'build/udm37-rrtmg4-export-runtime-v1/NEW_ON'; out={
 'schema':'actual-rrtmg4-vs-udm37-same-call-v2','status':'READ_ONLY_OBSERVER_COMPARISON_NOT_ACCURACY_VALIDATION','runtime':{},'phases':{},'scope_limits':['One selected column, one call per phase, one WRF timestep.','This compares two operational engine configurations on the same captured thermodynamic/gas/path state; cloud masks and band/g-point discretizations differ.','It does not isolate a pure engine effect, establish an accuracy ranking, or validate a forecast.','GP 128 LW/112 SW g-points and legacy RRTMG 140 LW/112 SW g-points are not positionally aligned; SW first shared band boundary is 2600 cm-1 in RRTMG4 versus 2680 cm-1 in RRTMGP (80 cm-1 index-match approximation).']}
for phase in ('LW','SW'):out['phases'][phase]=one(phase)
# CSV observer cross-check for the same selected call.
csvp=root/'audit/same_state.csv'; rows=list(csv.DictReader(csvp.open())); selected=[]
for row in rows:
 if (row['i'].strip(),row['j'].strip())==('24','55') and (row['metric'] in ('SURFACE_DOWN','TOA_UP','SURFACE_DIRECT','SURFACE_DIFFUSE') or row['metric'].startswith('HEAT_')):
  selected.append({k:row[k].strip() for k in ('phase','domain','step','source_seconds','i','j','metric','value37','value4','mean37','mean4','sample_count')})
csv_checks=[]
for row in rows:
    if (row['i'].strip(),row['j'].strip())!=('24','55') or row['metric'] not in ('SURFACE_DOWN','TOA_UP','HEAT_1','HEAT_31','HEAT_44'): continue
    phase=row['phase'].upper(); e=ex.read_export(root/'export'/f'rrtmg4_d01_i24_j55_step2161_{phase.lower()}.txt',expected_phase=phase)
    stem=phase.lower()+'_000001'; _,gprec=parse(root/'trace'/(stem+'.result'))
    if row['metric']=='SURFACE_DOWN': legacy_val=e['fields']['RESULT','DOWN_FLUX'].values[0]; gp_val=float(vec(gprec['DN'])[0])
    elif row['metric']=='TOA_UP': legacy_val=e['fields']['RESULT','UP_FLUX'].values[-1]; gp_val=float(vec(gprec['UP'])[-1])
    else:
        k=int(row['metric'].split('_')[1])-1
        # LW htr(0:nlayers) maps htr(k) to WRF hr(k+1); SW swhr(1:nlayers) maps index k directly.
        legacy_val=e['fields']['RESULT','HEATING'].values[k]; gp_val=float(vec(gprec['HR'])[k])
    v4=float(row['value4']);v37=float(row['value37'])
    csv_checks.append({'phase':phase,'metric':row['metric'],'csv_value4':v4,'export_value4':float(legacy_val),'value4_abs_difference':float(abs(v4-legacy_val)),'csv_value37':v37,'trace_result_value37':gp_val,'value37_abs_difference':float(abs(v37-gp_val))})
out['csv_observer']={'path':str(csvp.resolve()),'sha256':sha(csvp),'selected_rows':selected,'exact_value_checks':csv_checks}
# Provenance pins
paths=[ROOT/'build/udm37-rrtmg4-export-runtime-v4/execution.json',ROOT/'build/udm37-rrtmg4-export-runtime-v1/NEW_ON/export/rrtmg4_d01_i24_j55_step2161_lw.txt',ROOT/'build/udm37-rrtmg4-export-runtime-v1/NEW_ON/export/rrtmg4_d01_i24_j55_step2161_sw.txt',ROOT/'build/udm37-current-rrtmg4-optics-export-work/WRF/phys/module_ra_rrtmg_lw.F',ROOT/'build/udm37-current-rrtmg4-optics-export-work/WRF/phys/module_ra_rrtmg_sw.F',ROOT/'build/udm37-current-rrtmg4-optics-export-work/WRF/phys/module_ra_rrtmgp.F']
out['provenance']={'pins':{str(p.relative_to(ROOT)):sha(p) for p in paths},'gp_source_commit':__import__('subprocess').check_output(['git','-C',str(ROOT/'build/udm37-current-rrtmg4-optics-export-work'),'rev-parse','HEAD'],text=True).strip(),'export_source_observations':'RRTMG4 LW exports htr(0:nlayers); immediately after export, source maps htr(k) to WRF hr(k+1) for k=0..nlayers-1, so comparison uses first nlay values. SW exports swhr(1:nlayers), directly layer-indexed; source explicitly resets swhr(nlayers)=0 after calculating the loop, so the SW top-layer difference is reported separately. GP LW calls set_gases_lw with all four optional CFC arrays; those VMRs are supplied to the 10-gas LW setter, not merely trace-only fields. SW calls the six-gas setter.'}
# Distinguish the source used to build/run the executable from this later checkout.
plan=json.loads((ROOT/'build/udm37-rrtmg4-export-runtime-v4/plan.json').read_text())
executed_commit=plan['build_provenance']['commit']
analysis_commit=__import__('subprocess').check_output(['git','-C',str(ROOT/'build/udm37-current-rrtmg4-optics-export-work'),'rev-parse','HEAD'],text=True).strip()
executed_tree=__import__('subprocess').check_output(['git','-C',str(ROOT/'build/udm37-rrtmg4-export-serial-build-v1/source'),'rev-parse','HEAD:WRF'],text=True).strip()
analysis_tree=__import__('subprocess').check_output(['git','-C',str(ROOT/'build/udm37-current-rrtmg4-optics-export-work'),'rev-parse','HEAD:WRF'],text=True).strip()
if executed_tree != analysis_tree: raise RuntimeError('WRF source tree differs between runtime build and analysis checkout')
out['provenance']['executed_runtime_source_commit']=executed_commit
out['provenance']['analysis_checkout_commit']=analysis_commit
out['provenance']['executed_WRF_git_tree']=executed_tree
out['provenance']['analysis_WRF_git_tree']=analysis_tree
out['provenance']['source_commit_distinction']='RRTMG4/GP executable was built from executed_runtime_source_commit; analysis parser/source inspection used analysis_checkout_commit. These commits differ, but their WRF subtrees have the exact same Git tree object.'
out['schema']='actual-rrtmg4-vs-udm37-same-call-v3'
out['csv_observer']['metric_row_count']=len(out['csv_observer']['exact_value_checks'])
out['csv_observer']['engine_value_comparisons']=2*len(out['csv_observer']['exact_value_checks'])
for phase, d in out['phases'].items():
    d['dry_gas_column']['comparison']['mean_abs_relative_difference_extent_solver_layers']=int(d['dry_gas_column']['legacy']['shape'][0])
outpath=ROOT/'build/udm37-current-rrtmg4-optics-export-analysis-v1/actual-same-call-comparison-v3.json'
outpath.write_text(json.dumps(out,indent=2,sort_keys=True,allow_nan=False)+'\n')
print(outpath)
for phase,d in out['phases'].items():
 print('\n'+phase,'state bitwise all',all(x['bitwise_equal'] for x in list(d['input_state_checks_bitwise'].values())+list(d['surface_solar_checks_bitwise'].values())))
 print('drycolumn',d['dry_gas_column']['comparison'])
 print('flags',d['legacy_final_flags'],'gp iceflag',d['point']['gp_iceflag'],'gpoints',d['gpoints'])
 print('flux')
 for name,x in d['flux_profiles'].items(): print(name,x['surface_gp_minus_legacy'],x['toa_gp_minus_legacy'],'profile max',x['profile']['max_abs'])
 print('heating-native',d['heating_profile']['native_shared_layers'],'heating-all',d['heating_profile']['all_solver_layers'])
