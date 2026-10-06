#!/usr/bin/env python3
"""Compare generated frozen-table artifacts; kernel binary identity is reported, not cross-run required."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
PLAN=json.loads((HERE/'plan.json').read_text())
TOOL=Path(PLAN['source_checkout'])/'tools/udm_frozen_optics'
sys.path.insert(0,str(TOOL))
import compare
from lookup import FrozenTable
MOMENTS=compare.MOMENTS


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def array_sha(a): return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--expanded',type=Path,required=True)
    ap.add_argument('--direct',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args()
    if a.output.exists(): ap.error('Output exists; preserving previous evidence')
    ea,ev,er,eh=compare.load(a.expanded)
    da,dv,dr,dh=compare.load(a.direct)
    old=Path(PLAN['old_generation']['path'])
    oa,ov,orr,oh=compare.load(old)
    expected_t=np.asarray(PLAN['proposed_temperature_axis_K'],dtype=np.float64)
    expected_l=np.asarray(PLAN['old_generation']['lambda_m_inv'],dtype=np.float64)
    if not np.array_equal(ea['temperature'],expected_t) or not np.array_equal(ea['lambda'],expected_l):
        raise ValueError('Expanded axes do not match reviewed plan')
    if not np.array_equal(da['temperature'],np.asarray([179.996])) or not np.array_equal(da['lambda'],expected_l):
        raise ValueError('Direct artifact axes are not the planned 179.996 K and fixed lambda grid')
    for name in ('input_sources','gas_data_sha256','generator_sha256','kernel_source_sha256','kernel_source_adaptation','numerical_packages','compiler','kernel_flags','quadrature_algorithm','quadrature_nodes_weights_sha256','order','max_spectral_step_cm_inv','workers','spectral_chunk_size','max_terms','quadrature_area_weight_pruning_threshold'):
        if er[name]!=orr[name] or dr[name]!=orr[name]:
            raise ValueError(f'Generation provenance/control mismatch in {name}')
    results={'status':'NUMERICAL_DIAGNOSTIC_NO_ACCURACY_THRESHOLD','expanded_receipt_sha256':eh,'expanded_table_sha256':er['table_sha256'],
             'kernel_binary_identity':{'expanded_sha256':er['kernel_binary_sha256'],'direct_sha256':dr['kernel_binary_sha256'],
                                      'identical_bytes':er['kernel_binary_sha256']==dr['kernel_binary_sha256'],
                                      'comparison_policy':'Each local binary is verified against its own generation receipt by compare.load; binaries from different output directories are reported but not required byte-identical. Source/adaptation/compiler/flags remain strict.'},
             'direct_receipt_sha256':dh,'direct_table_sha256':dr['table_sha256'],'old_receipt_sha256':oh,'old_table_sha256':orr['table_sha256'],
             'provenance_controls_equal':True,'axis_contract':{'temperature_K':ea['temperature'].tolist(),'lambda_m_inv':ea['lambda'].tolist()},
             'old_knot_checks':{},'boundary_checks':{},'direct_179_996_metrics':{},
             'interpretation':'A numerical interpolation comparison at the listed slopes and bands; not material or forecast accuracy.'}
    failures=[]
    old_t=oa['temperature']
    for temp in [180.,233.,250.,300.]:
        oi=int(np.flatnonzero(old_t==temp)[0]); ei=int(np.flatnonzero(ea['temperature']==temp)[0])
        group={}
        orows={(row['phase'],row['slope'],row['band']):row for row in orr['rows']}
        erows={(row['phase'],row['slope'],row['band']):row for row in er['rows']}
        for moment in MOMENTS:
            key='lw_'+moment+'_times_density'
            left=ov[key][:,oi,:]; right=ev[key][:,ei,:]
            same=bool(np.array_equal(left,right)); group[moment]={'exact_array_equal':same,'old_sha256':array_sha(left),'expanded_sha256':array_sha(right)}
            if not same: failures.append(f'LW common knot {temp} {moment}')
        source_equal=True
        for slope in expected_l:
            for band in range(16):
                ok=np.array_equal(np.asarray(orows[('LW',float(slope),band)]['source_integral'])[oi:oi+1],np.asarray(erows[('LW',float(slope),band)]['source_integral'])[ei:ei+1])
                source_equal=source_equal and bool(ok)
        group['source_integral_exact_all_lambda_bands']=source_equal
        if not source_equal: failures.append(f'LW source integrals at common knot {temp}')
        results['old_knot_checks'][str(temp)]=group
    for moment in MOMENTS:
        key='sw_'+moment+'_times_density'
        same=bool(np.array_equal(ov[key],ev[key]))
        results['old_knot_checks'].setdefault('SW',{})[moment]={'exact_array_equal':same,'old_sha256':array_sha(ov[key]),'expanded_sha256':array_sha(ev[key])}
        if not same: failures.append(f'SW {moment}')
    sw_sources=True
    orows={(row['phase'],row['slope'],row['band']):row for row in orr['rows']}
    erows={(row['phase'],row['slope'],row['band']):row for row in er['rows']}
    for slope in expected_l:
        for band in range(14):
            if not np.array_equal(np.asarray(orows[('SW',float(slope),band)]['source_integral']),np.asarray(erows[('SW',float(slope),band)]['source_integral'])):
                sw_sources=False
    results['old_knot_checks']['SW']['source_integral_exact_all_lambda_bands']=sw_sources
    if not sw_sources: failures.append('SW source integrals')
    table=FrozenTable(a.expanded)
    old_table=FrozenTable(old)
    try:
        old_table.moments('LW',expected_l,np.full(expected_l.shape,179.996))
    except ValueError as exc:
        results['boundary_checks']['old_table_179.996']={'rejected':True,'reason':str(exc)}
    else:
        failures.append('Old 180 K-minimum table accepted 179.996 K')
    query179=table.moments('LW',expected_l,np.full(expected_l.shape,179.996))
    finite179=all(bool(np.all(np.isfinite(x))) for x in query179.values())
    results['boundary_checks']['expanded_table_179.996']={'accepted':True,'moments_finite':finite179}
    if not finite179: failures.append('Expanded table returned nonfinite 179.996 K interpolation')
    for temp in (150.,330.):
        query=table.moments('LW',expected_l,np.full(expected_l.shape,temp))
        finite=all(bool(np.all(np.isfinite(x))) for x in query.values())
        results['boundary_checks'][str(temp)]={'accepted':True,'moments_finite':finite}
        if not finite: failures.append(f'Nonfinite boundary interpolation at {temp}')
    for temp in (149.999,330.001):
        try: table.moments('LW',expected_l,np.full(expected_l.shape,temp))
        except ValueError as exc: results['boundary_checks'][str(temp)]={'rejected':True,'reason':str(exc)}
        else: failures.append(f'Out-of-range temperature {temp} was accepted')
    direct_sw_checks={}
    for moment in MOMENTS:
        key='sw_'+moment+'_times_density'
        same=bool(np.array_equal(ev[key],dv[key]))
        direct_sw_checks[moment]={'exact_array_equal':same,'expanded_sha256':array_sha(ev[key]),'direct_sha256':array_sha(dv[key])}
        if not same: failures.append(f'Direct SW {moment} differs from expanded table')
    direct_sw_source=True
    for slope in expected_l:
        for band in range(14):
            if not np.array_equal(np.asarray(erows[('SW',float(slope),band)]['source_integral']),np.asarray({(row['phase'],row['slope'],row['band']):row for row in dr['rows']}[('SW',float(slope),band)]['source_integral'])):
                direct_sw_source=False
    direct_sw_checks['source_integral_exact_all_lambda_bands']=direct_sw_source
    if not direct_sw_source: failures.append('Direct SW source integrals differ from expanded table')
    results['direct_SW_invariant_checks']=direct_sw_checks
    direct_i=int(np.flatnonzero(da['temperature']==179.996)[0])
    lookup=table.moments('LW',expected_l,np.full(expected_l.shape,179.996))
    for moment in MOMENTS:
        key='lw_'+moment+'_times_density'
        truth=dv[key][:,direct_i,:]
        interp=np.asarray(lookup[moment])
        diff=np.abs(interp-truth)
        ext=dv['lw_extinction_times_density'][:,direct_i,:]
        norm=diff/np.maximum(ext,1e-300)
        by_band=[]
        for il,lam in enumerate(expected_l):
            for band in range(16):
                by_band.append({'lambda_m_inv':float(lam),'band_index_zero_based':band,
                                'direct_m_inv':float(truth[il,band]),'lookup_m_inv':float(interp[il,band]),
                                'absolute_difference_m_inv':float(diff[il,band]),
                                'extinction_normalized_difference':float(norm[il,band])})
        results['direct_179_996_metrics'][moment]={
          'max_absolute_difference_m_inv':float(np.max(diff)),
          'max_absolute_difference_index_lambda_band':[int(x) for x in np.unravel_index(np.argmax(diff),diff.shape)],
          'max_extinction_normalized_difference':float(np.max(norm)),
          'max_extinction_normalized_index_lambda_band':[int(x) for x in np.unravel_index(np.argmax(norm),norm.shape)],
          'direct_values_sha256':array_sha(truth),'lookup_values_sha256':array_sha(interp),'per_lambda_band':by_band}
    results['status']='STRUCTURAL_FAILURES' if failures else results['status']
    results['structural_failures']=failures
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps({'status':results['status'],'structural_failures':failures,'metrics':results['direct_179_996_metrics']}))
    return 1 if failures else 0

if __name__=='__main__': raise SystemExit(main())
