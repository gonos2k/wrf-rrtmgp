#!/usr/bin/env python3
"""Report direct-vs-interpolated LW moments at every temperature midpoint."""
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

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def bytes_sha(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--expanded',type=Path,required=True)
    ap.add_argument('--direct',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args()
    if a.output.exists():ap.error('Output exists; preserve prior evidence')
    ea,ev,er,eh=compare.load(a.expanded); da,dv,dr,dh=compare.load(a.direct)
    expected_t=np.asarray(PLAN['expanded_reference']['expected_temperatures_K'],dtype=np.float64)
    expected_l=np.asarray(PLAN['expanded_reference']['expected_lambda_m_inv'],dtype=np.float64)
    mids=np.asarray(PLAN['midpoint_temperatures_K'],dtype=np.float64)
    if not np.array_equal(ea['temperature'],expected_t) or not np.array_equal(ea['lambda'],expected_l):raise ValueError('Expanded axes mismatch')
    if not np.array_equal(da['temperature'],mids) or not np.array_equal(da['lambda'],expected_l):raise ValueError('Direct midpoint axes mismatch')
    for key in ('input_sources','gas_data_sha256','generator_sha256','kernel_source_sha256','kernel_source_adaptation','numerical_packages','compiler','kernel_flags','quadrature_algorithm','quadrature_nodes_weights_sha256','order','max_spectral_step_cm_inv','workers','spectral_chunk_size','max_terms','quadrature_area_weight_pruning_threshold'):
        if er[key]!=dr[key]:raise ValueError(f'Generation controls/provenance differ: {key}')
    binary_identity={'expanded_sha256':er['kernel_binary_sha256'],'direct_sha256':dr['kernel_binary_sha256'],
                     'identical_bytes':er['kernel_binary_sha256']==dr['kernel_binary_sha256'],
                     'policy':'compare.load validates each local binary against its own receipt; cross-generation binary byte equality is not required.'}
    table=FrozenTable(a.expanded)
    detail=[]; maxima={m:{'max_absolute_difference_m_inv':0.0,'max_extinction_normalized_difference':0.0} for m in MOMENTS}
    for it,temp in enumerate(mids):
        q=table.moments('LW',expected_l,np.full(expected_l.shape,temp))
        for moment in MOMENTS:
            key=f'lw_{moment}_times_density'
            direct=dv[key][:,it,:]; interp=np.asarray(q[moment])
            if not np.all(np.isfinite(direct)) or not np.all(np.isfinite(interp)):raise ValueError(f'Nonfinite value at T={temp} for {moment}')
            diff=np.abs(interp-direct)
            ext=dv['lw_extinction_times_density'][:,it,:]
            norm=diff/np.maximum(ext,1e-300)
            maxima[moment]['max_absolute_difference_m_inv']=max(maxima[moment]['max_absolute_difference_m_inv'],float(diff.max()))
            maxima[moment]['max_extinction_normalized_difference']=max(maxima[moment]['max_extinction_normalized_difference'],float(norm.max()))
            for il,lam in enumerate(expected_l):
                for band in range(16):
                    detail.append({'temperature_K':float(temp),'lambda_m_inv':float(lam),'band_index_zero_based':band,'moment':moment,
                                   'direct_m_inv':float(direct[il,band]),'lookup_m_inv':float(interp[il,band]),
                                   'absolute_difference_m_inv':float(diff[il,band]),
                                   'extinction_normalized_difference':float(norm[il,band])})
    result={'status':'NUMERICAL_INTERPOLATION_DIAGNOSTIC_NO_ACCEPTANCE_THRESHOLD','expanded_receipt_sha256':eh,
            'expanded_table_sha256':er['table_sha256'],'direct_receipt_sha256':dh,'direct_table_sha256':dr['table_sha256'],
            'kernel_binary_identity':binary_identity,
            'temperature_midpoints_K':mids.tolist(),'lambda_m_inv':expected_l.tolist(),'band_count':16,'moment_names':list(MOMENTS),
            'sample_count_per_moment':len(mids)*len(expected_l)*16,'maximum_differences_by_moment':maxima,
            'per_temperature_lambda_band_moment_differences':detail,
            'scope':'Sampled numerical interpolation differences under one static material, kernel, PSD, and numerical-control set; no physical accuracy or forecast validation.'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'samples_per_moment':result['sample_count_per_moment'],'maxima':maxima}))
    return 0
if __name__=='__main__':raise SystemExit(main())
