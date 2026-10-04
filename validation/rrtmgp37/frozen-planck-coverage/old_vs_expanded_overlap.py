#!/usr/bin/env python3
"""Compare old/new lookup moments against saved direct midpoint artifacts; no generation."""
from __future__ import annotations
import hashlib,json,pathlib,sys
import numpy as np
ROOT=pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
PKG=ROOT/'build/udm37-frozen-planck-coverage-v1'
MID=ROOT/'build/udm37-frozen-planck-interknots-v1'
PLAN=json.loads((PKG/'plan.json').read_text())
sys.path.insert(0,str(pathlib.Path(PLAN['source_checkout'])/'tools/udm_frozen_optics'))
import compare
from lookup import FrozenTable

OLD=pathlib.Path(PLAN['old_generation']['path'])
NEW=pathlib.Path(PLAN['generation_runs'][0]['output_dir'])
DIRECT=MID/'runs/frozen-direct-interknots-v1'
OUT=PKG/'old-vs-expanded-overlap-diagnostic.json'
MD=PKG/'old-vs-expanded-overlap-diagnostic.md'

def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def hasharr(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def main():
    if OUT.exists() or MD.exists():raise FileExistsError('Diagnostic output exists; preserving prior evidence')
    ex=json.loads((PKG/'execution.json').read_text());mi=json.loads((MID/'execution.json').read_text())
    if ex.get('status')!='GENERATIONS_COMPLETE_DIAGNOSTICS_PENDING':raise ValueError('Expanded generation execution receipt is not complete')
    if mi.get('status')!='DIRECT_MIDPOINT_GENERATION_COMPLETE_DIAGNOSTICS_PENDING':raise ValueError('Midpoint generation execution receipt is not complete')
    before={str(p):sha(p) for p in [OLD/'result.json',OLD/'frozen-ice-psd-moments.nc',NEW/'result.json',NEW/'frozen-ice-psd-moments.nc',DIRECT/'result.json',DIRECT/'frozen-ice-psd-moments.nc']}
    oa,ov,orr,oh=compare.load(OLD); na,nv,nr,nh=compare.load(NEW); da,dv,dr,dh=compare.load(DIRECT)
    oldtable=FrozenTable(OLD);newtable=FrozenTable(NEW)
    mids=[float(t) for t in dr['temperatures_K'] if 180.0<=float(t)<=300.0]
    if not mids:raise ValueError('No direct midpoint samples overlap old coverage')
    lams=np.asarray(PLAN['old_generation']['lambda_m_inv'],dtype=np.float64)
    if not np.array_equal(oa['lambda'],na['lambda']) or not np.array_equal(oa['lambda'],da['lambda']) or not np.array_equal(oa['lambda'],lams):raise ValueError('Lambda grids differ')
    if not np.array_equal(da['temperature'],np.asarray(dr['temperatures_K'])):raise ValueError('Direct temperature axis inconsistent')
    strict=('input_sources','gas_data_sha256','generator_sha256','kernel_source_sha256','kernel_source_adaptation','numerical_packages','compiler','kernel_flags','quadrature_algorithm','quadrature_nodes_weights_sha256','order','max_spectral_step_cm_inv','workers','spectral_chunk_size','max_terms','quadrature_area_weight_pruning_threshold')
    for key in strict:
        if not (orr[key]==nr[key]==dr[key]):raise ValueError(f'Pinned control/provenance mismatch: {key}')
    rec={'status':'LOOKUP_DIAGNOSTIC_COMPLETE_NO_ACCEPTANCE_THRESHOLD','range_K':[180.0,300.0],
         'midpoint_temperatures_K':mids,'midpoint_count':len(mids),'lambda_m_inv':lams.tolist(),'band_count':16,
         'moment_names':list(compare.MOMENTS),'points_per_moment':len(mids)*len(lams)*16,
         'artifacts':{'old':{'result_sha256':oh,'table_sha256':orr['table_sha256']},
                      'expanded':{'result_sha256':nh,'table_sha256':nr['table_sha256']},
                      'direct_midpoints':{'result_sha256':dh,'table_sha256':dr['table_sha256']},
                      'expanded_generation_execution_sha256':sha(PKG/'execution.json'),
                      'midpoint_generation_execution_sha256':sha(MID/'execution.json')},
         'kernel_binaries':{'old_sha256':orr['kernel_binary_sha256'],'expanded_sha256':nr['kernel_binary_sha256'],
                            'midpoint_direct_sha256':dr['kernel_binary_sha256'],
                            'identical_bytes':orr['kernel_binary_sha256']==nr['kernel_binary_sha256']==dr['kernel_binary_sha256'],
                            'policy':'Each generation artifact validates its own local binary receipt. Cross-output-directory binary bytes are reported only; numerical comparisons require identical source/adaptation/compiler/flags and controls.'},
         'strict_common_provenance_keys':list(strict), 'metrics_by_moment':{}, 'full_point_metrics':[],
         'interpretation':'This compares interpolation under the same fixed numerical source/material contract. It is not a physical accuracy, forecast error, or universal interpolation bound.'}
    accum={m:{'old_abs':[],'new_abs':[],'new_minus_old_abs':[],'old_norm':[],'new_norm':[],'delta_norm':[],'new_error_lower_count':0,'equal_error_count':0} for m in compare.MOMENTS}
    dindex={float(t):i for i,t in enumerate(da['temperature'])}
    for t in mids:
        ii=dindex[t]
        qold=oldtable.moments('LW',lams,np.full(lams.shape,t))
        qnew=newtable.moments('LW',lams,np.full(lams.shape,t))
        for m in compare.MOMENTS:
            key='lw_'+m+'_times_density'
            direct=np.asarray(dv[key][:,ii,:]);old=np.asarray(qold[m]);new=np.asarray(qnew[m])
            if not all(np.all(np.isfinite(x)) for x in (direct,old,new)):raise ValueError(f'Nonfinite lookup at T={t} {m}')
            oldd=np.abs(old-direct);newd=np.abs(new-direct);delta=new-old
            ext=np.asarray(dv['lw_extinction_times_density'][:,ii,:])
            oldn=oldd/np.maximum(ext,1e-300);newn=newd/np.maximum(ext,1e-300);deltan=np.abs(delta)/np.maximum(ext,1e-300)
            a=accum[m];a['old_abs'].extend(oldd.ravel().tolist());a['new_abs'].extend(newd.ravel().tolist());a['new_minus_old_abs'].extend(np.abs(delta).ravel().tolist())
            a['old_norm'].extend(oldn.ravel().tolist());a['new_norm'].extend(newn.ravel().tolist());a['delta_norm'].extend(deltan.ravel().tolist())
            a['new_error_lower_count']+=int(np.count_nonzero(newd<oldd));a['equal_error_count']+=int(np.count_nonzero(newd==oldd))
            for il,lam in enumerate(lams):
                for band in range(16):
                    rec['full_point_metrics'].append({'temperature_K':t,'lambda_m_inv':float(lam),'band_index_zero_based':band,'moment':m,
                      'direct_m_inv':float(direct[il,band]),'old_lookup_m_inv':float(old[il,band]),'expanded_lookup_m_inv':float(new[il,band]),
                      'old_minus_direct_m_inv':float(old[il,band]-direct[il,band]),'expanded_minus_direct_m_inv':float(new[il,band]-direct[il,band]),
                      'expanded_minus_old_m_inv':float(delta[il,band]),'old_abs_extinction_normalized':float(oldn[il,band]),
                      'expanded_abs_extinction_normalized':float(newn[il,band]),'expanded_minus_old_abs_extinction_normalized':float(deltan[il,band])})
    for m,a in accum.items():
        def summarize(values):
            x=np.asarray(values,dtype=np.float64)
            return {'max':float(x.max()),'mean':float(x.mean()),'rms':float(np.sqrt(np.mean(x*x)))}
        rec['metrics_by_moment'][m]={
          'old_lookup_vs_direct_abs_m_inv':summarize(a['old_abs']),
          'expanded_lookup_vs_direct_abs_m_inv':summarize(a['new_abs']),
          'expanded_minus_old_abs_m_inv':summarize(a['new_minus_old_abs']),
          'old_lookup_vs_direct_abs_extinction_normalized':summarize(a['old_norm']),
          'expanded_lookup_vs_direct_abs_extinction_normalized':summarize(a['new_norm']),
          'expanded_minus_old_abs_extinction_normalized':summarize(a['delta_norm']),
          'new_error_lower_than_old_count':a['new_error_lower_count'],'equal_old_new_error_count':a['equal_error_count'],
          'sample_count':len(a['old_abs'])}
    after={str(p):sha(p) for p in [OLD/'result.json',OLD/'frozen-ice-psd-moments.nc',NEW/'result.json',NEW/'frozen-ice-psd-moments.nc',DIRECT/'result.json',DIRECT/'frozen-ice-psd-moments.nc']}
    if before!=after:raise RuntimeError('A source table/result artifact changed during read-only lookup analysis')
    rec['artifact_hashes_unchanged_after_read']=True
    OUT.write_text(json.dumps(rec,indent=2)+'\n')
    md=['# Old versus expanded frozen-optics lookup in the prior coverage range','',
        'This is a read-only lookup comparison against saved direct midpoint generation. No Mie build, generator, or model was run for this analysis. The numerical differences are diagnostics, not physical accuracy criteria or forecast errors.','',
        f"Coverage tested: {len(mids)} direct midpoint temperatures from {mids[0]} to {mids[-1]} K, restricted to the old 180–300 K range; {len(lams)} lambdas, 16 bands, four moments ({rec['points_per_moment']} samples per moment).",'',
        f"Old result/table SHA256: `{oh}` / `{orr['table_sha256']}`.",f"Expanded result/table SHA256: `{nh}` / `{nr['table_sha256']}`.",
        f"Direct-midpoint result/table SHA256: `{dh}` / `{dr['table_sha256']}`.",
        f"Kernel binaries (old/expanded/direct): `{orr['kernel_binary_sha256']}` / `{nr['kernel_binary_sha256']}` / `{dr['kernel_binary_sha256']}`. Each is checked against its own generation receipt; cross-directory byte identity is not required.",'',
        '| Moment | Old lookup max abs normalized | Expanded lookup max abs normalized | Change max abs normalized | New lookup error lower / equal |','|---|---:|---:|---:|---:|']
    for m,x in rec['metrics_by_moment'].items():md.append(f"| {m} | {x['old_lookup_vs_direct_abs_extinction_normalized']['max']:.9g} | {x['expanded_lookup_vs_direct_abs_extinction_normalized']['max']:.9g} | {x['expanded_minus_old_abs_extinction_normalized']['max']:.9g} | {x['new_error_lower_than_old_count']} / {x['equal_old_new_error_count']} |")
    md+=['','Absolute moment differences are also reported in m⁻¹; each moment’s maximum, mean, and RMS, and every per-temperature/lambda/band value are in [`old-vs-expanded-overlap-diagnostic.json`](old-vs-expanded-overlap-diagnostic.json).','',
         'The expanded axis changes interpolation inside the old range as well as adding low-temperature coverage. These measurements describe only the sampled lookup against the same numerical Mie reference. They do not validate the fixed refractive index, particle model, WRF response, or forecast accuracy.']
    MD.write_text('\n'.join(md)+'\n')
    print(json.dumps({'status':rec['status'],'points_per_moment':rec['points_per_moment'],'metrics_by_moment':{m:x['expanded_lookup_vs_direct_abs_extinction_normalized']['max'] for m,x in rec['metrics_by_moment'].items()}}))

if __name__=='__main__':main()
