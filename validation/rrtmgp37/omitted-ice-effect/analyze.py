#!/usr/bin/env python3
"""Stdlib replay of paired held-state sensitivity; no independent physics approval."""
import argparse,csv,gzip,hashlib,importlib.util,io,json,math,statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
PARENT=ROOT/'validation/rrtmgp37/radiation-occurrence-runtime'
spec=importlib.util.spec_from_file_location('parent_trace',PARENT/'verify_saved.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)


def require(condition,message):
    if not condition:raise ValueError(message)


def records(path):return v.trace(gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes(),'result')[1]


def recpath(run,phase):
    p=run/(phase+'.result')
    return p if p.is_file() else p.with_suffix('.result.gz')


def check_unchanged(Z,B,phase):
    names=('GAS_TAU','CLOUD_TAU','PREPARED_TAU','MASK','RL_USED','DI_USED','DS_USED','UPC','DNC','HRC')
    if phase=='sw':names+=('CLOUD_SSA','CLOUD_G','PREPARED_SSA','PREPARED_G','PRECIP_TAU','PRECIP_SSA','PRECIP_G')
    for name in names:require(Z[name]==B[name],'existing component changed '+name)


def check_scaling(tr,tt,sr,gr,ss,gg,phase):
    require(tr>=0 and 0<=sr<=1 and -1<=gr<=1,'invalid raw optics')
    if phase=='sw' and tr>0:
        f=gr*gr;den=1-sr*f
        require(abs(tt-tr*den)<=1e-14*max(tr,1e-30),'delta scaling count/tau')
        require(abs(ss-sr*(1-f)/den)<1e-13 and abs(gg-gr/(1+gr))<1e-13,'delta scaling moments')
    if phase=='lw':require(tr==tt,'LW opacity was scaled')


def analyze(runtime,band_map):
    groups=[];layer_rows=[];interface_rows=[];optical_rows=[]
    for prefix in sorted(runtime.glob('on-*')):
        case=prefix.name[:8];phase=prefix.name[9:11];offset=int(prefix.name.rsplit('-s',1)[1])
        Z=records(recpath(prefix/'Z',phase));B=records(recpath(prefix/'B',phase))
        reference=records(PARENT/'saved'/case/'capture'/(phase+'.result.gz'))
        require((prefix/'Z'/ (phase+'.input')).read_bytes()==(prefix/'B'/(phase+'.input')).read_bytes(),'pair input changed')
        _,inp=v.trace((prefix/'Z'/(phase+'.input')).read_bytes(),'input')
        nl=Z['TOTAL_TAU']['shape'][1];bounds=band_map[phase]
        bands=len(bounds);ngpt=Z['TOTAL_TAU']['shape'][2]
        if offset==0:
            A=records(recpath(prefix/'A',phase))
            require(all(A[k]==reference[k] for k in A if k in reference),'parent baseline replay mismatch')
            require(all(A[k]==Z[k] for k in A),'zero-addition control changed baseline')
        check_unchanged(Z,B,phase)
        raw=gzip.decompress((PARENT/'saved'/case/'capture'/(phase+'.raw.gz')).read_bytes())
        (_,rr)=v.trace(raw,'raw');positive=[k for k,x in enumerate(rr['IWP_OMITTED']['values']) if x>0]
        cf=inp['CF']['values']
        rawtau=B['ICE_EXTRA_TAU_RAW']['values'];tau=B['ICE_EXTRA_TAU']['values']
        require(B['ICE_EXTRA_TAU']['shape']==(1,nl,bands),'new component extent')
        require(all(Z['ICE_EXTRA_TAU']['values'][k]==0 for k in range(nl*bands)),'nonzero zero-control optics')
        maxima={'tau':0.,'scattering':0.,'asymmetry':0.}
        for b,(lo,hi) in enumerate(bounds):
            for k in range(nl):
                ix=k+nl*b;tr=rawtau[ix];tt=tau[ix]
                sr=B['ICE_EXTRA_SSA_RAW']['values'][ix] if phase=='sw' else 0.
                gr=B['ICE_EXTRA_G_RAW']['values'][ix] if phase=='sw' else 0.
                ss=B['ICE_EXTRA_SSA']['values'][ix] if phase=='sw' else 0.
                gg=B['ICE_EXTRA_G']['values'][ix] if phase=='sw' else 0.
                if k not in positive:
                    require(tr==tt==0.,'new optics outside omitted ice layers')
                else:
                    require(cf[k]==0 and tr>0 and tt>0,'missing or misplaced positive ice optics')
                check_scaling(tr,tt,sr,gr,ss,gg,phase)
                for g in range(lo-1,hi):
                    gi=k+nl*g
                    tz=Z['TOTAL_TAU']['values'][gi];tb=B['TOTAL_TAU']['values'][gi]
                    residual=tb-tz-tt;maxima['tau']=max(maxima['tau'],abs(residual))
                    require(abs(residual)<=1e-13*max(abs(tz),abs(tt),1e-20),'total tau component closure')
                    if phase=='sw':
                        sz=Z['TOTAL_SSA']['values'][gi];sb=B['TOTAL_SSA']['values'][gi]
                        gz=Z['TOTAL_G']['values'][gi];gb=B['TOTAL_G']['values'][gi]
                        e1=tb*sb-tz*sz-tt*ss;e2=tb*sb*gb-tz*sz*gz-tt*ss*gg
                        maxima['scattering']=max(maxima['scattering'],abs(e1));maxima['asymmetry']=max(maxima['asymmetry'],abs(e2))
                        require(abs(e1)<=2e-13*max(tz+tt,1e-20) and abs(e2)<=2e-13*max(tz+tt,1e-20),'total optical moment closure')
                if k in positive:
                    optical_rows.append({'case':case,'phase':phase,'seed_offset':offset,'level1':k+1,'band1':b+1,
                       'tau_raw':tr,'tau':tt,'tau_omega_raw':tr*sr,'tau_omega_g_raw':tr*sr*gr,
                       'tau_omega':tt*ss,'tau_omega_g':tt*ss*gg})
        delta={n:[b-a for a,b in zip(Z['ICE_DIAG_'+n+'64']['values'],B['ICE_DIAG_'+n+'64']['values'])] for n in ('UP','DN','HR')}
        pressure=inp['PLEV']['values'];gravity=inp['GRAVITY']['values'][0];cp=inp['CP_DRY']['values'][0]
        heat_residual=0.
        for k in range(nl):
            expected=gravity/cp*86400.*(delta['UP'][k+1]-delta['UP'][k]-delta['DN'][k+1]+delta['DN'][k])/((pressure[k+1]-pressure[k])*100.)
            heat_residual=max(heat_residual,abs(expected-delta['HR'][k]))
            require(abs(expected-delta['HR'][k])<1e-9,'flux/heating difference closure')
            layer_rows.append({'case':case,'phase':phase,'seed_offset':offset,'level1':k+1,'native_layer':k<59,'delta_heating_K_day':delta['HR'][k]})
        for k in range(nl+1):
            interface_rows.append({'case':case,'phase':phase,'seed_offset':offset,'interface1':k+1,
                    'delta_up_W_m2':delta['UP'][k],'delta_down_W_m2':delta['DN'][k],
                    'delta_net_down_W_m2':delta['DN'][k]-delta['UP'][k]})
        row={'case':case,'phase':phase,'seed_offset':offset,'backend_layers':nl,'component_closure_max':maxima,
             'surface_down_W_m2':delta['DN'][0],'surface_up_W_m2':delta['UP'][0],
             'solver_TOA_up_W_m2':delta['UP'][-1],'model_top_up_W_m2':delta['UP'][59],
             'max_abs_interface_flux_difference_W_m2':max(abs(x) for name in ('UP','DN') for x in delta[name]),
             'max_abs_native_heating_K_day':max(abs(x) for x in delta['HR'][:59]),
             'max_native_heating_layer1':max(range(59),key=lambda k:abs(delta['HR'][k]))+1,
             'flux_heating_closure_max_K_day':heat_residual,
             'maximum_native_export_heating_difference_WP64_K_day':max(abs((B['HR']['values'][k]-Z['HR']['values'][k])-delta['HR'][k]) for k in range(59))}
        if phase=='sw':
            delta_pred=[b-a for a,b in zip(Z['ICE_DIAG_PREDELTA64']['values'],B['ICE_DIAG_PREDELTA64']['values'])]
            delta_direct=[b-a for a,b in zip(Z['ICE_DIAG_DIRECT64']['values'],B['ICE_DIAG_DIRECT64']['values'])]
            row['surface_predelta_direct_delta_W_m2']=delta_pred[0]
            row['surface_diffuse_delta_W_m2']=delta['DN'][0]-delta_direct[0]
            row['surface_WRF_convention_SWDOWN_delta_W_m2']=delta_pred[0]+row['surface_diffuse_delta_W_m2']
            row['SWDOWN_is_held_state_reconstruction_not_WRF_run']=True
        groups.append(row)
    summary={}
    for phase in ('lw','sw'):
        p=[x for x in groups if x['phase']==phase]
        summary[phase]={'maximum_native_heating_K_day':max(x['max_abs_native_heating_K_day'] for x in p),
                        'maximum_interface_flux_W_m2':max(x['max_abs_interface_flux_difference_W_m2'] for x in p),
                        'surface_down_range_W_m2':[min(x['surface_down_W_m2'] for x in p),max(x['surface_down_W_m2'] for x in p)],
                        'solver_TOA_up_range_W_m2':[min(x['solver_TOA_up_W_m2'] for x in p),max(x['solver_TOA_up_W_m2'] for x in p)]}
        if phase=='sw':summary[phase]['surface_WRF_SWDOWN_range_W_m2']=[min(x['surface_WRF_convention_SWDOWN_delta_W_m2'] for x in p),max(x['surface_WRF_convention_SWDOWN_delta_W_m2'] for x in p)]
    uncertainty=[]
    for case in sorted({g['case'] for g in groups}):
        for phase in ('lw','sw'):
            r=[g for g in groups if g['case']==case and g['phase']==phase]
            require(len(r)==(3 if phase=='lw' else 35),'missing paired seed member')
            for metric in ('surface_down_W_m2','solver_TOA_up_W_m2','max_abs_native_heating_K_day'):
                values=[g[metric] for g in r]
                uncertainty.append({'case':case,'phase':phase,'metric':metric,'paired_seeds':len(r),'mean':statistics.mean(values),
                                    'sample_std':statistics.stdev(values),'empirical_standard_error':statistics.stdev(values)/math.sqrt(len(values)),'range':[min(values),max(values)],'confidence_interval_claimed':False})
    result={'status':'PASS_SCOPED_OMITTED_ICE_SENSITIVITY','final_public_column_processes':312,'initial_public_column_processes':80,
            'total_Fortran_processes':393,'successful_public_column_calls':392,'input_parse_failed_processes':1,'new_WRF_processes':0,'baseline_parent_and_zero_controls_exact':True,
            'common_CF_and_existing_mask_unchanged':True,'new_ice_occurrence':1,'extra_SW_scalings':1,'summary':summary,
            'paired_seed_diagnostics':uncertainty,'groups':groups,'physical_uncertainty_quantified':False,
            'sampling_range_is_not_a_general_error_bound':True,'production_accepted':False}
    return result,{'layers.csv':layer_rows,'interfaces.csv':interface_rows,'ice-optics.csv':optical_rows}


def emit_csv(rows):
    s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows);return s.getvalue()

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('runtime',type=Path);ap.add_argument('bandmap',type=Path);ap.add_argument('output',type=Path);a=ap.parse_args()
    result,tables=analyze(a.runtime,json.loads(a.bandmap.read_text()))
    a.output.mkdir(exist_ok=True)
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    for n,rows in tables.items():(a.output/n).write_text(emit_csv(rows))
    print(json.dumps(result['summary'],indent=2))
