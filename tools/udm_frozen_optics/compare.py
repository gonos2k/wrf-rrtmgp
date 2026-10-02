#!/usr/bin/env python3
"""Validate complete generation artifacts and report numerical differences.

No tolerance is promoted to a forecast-accuracy criterion. The output is a
convergence report; a caller may explicitly set --max-extinction-normalized-error.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from netCDF4 import Dataset
import generate as gen

MOMENTS = ('extinction','scattering','scatter_times_g','absorption')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(directory: Path):
    receipt_path = directory/'result.json'
    receipt = json.loads(receipt_path.read_text())
    require(receipt['status']=='COMPLETE_NUMERICAL_GENERATION_NOT_MODEL_VALIDATION','Incomplete generator receipt')
    require(receipt['generator_sha256']==gen.sha(gen.HERE/'generate.py'),'Generator source identity differs; use its matching checkout')
    require(receipt['input_sources']==gen.INPUTS,'Pinned input identities differ')
    source_files=[gen.HERE/'socrates'/p for p in ('realtype_rd.f90','def_std_io_icf.f90','error_pcf.f90','mie_scatter.f')]
    source_files += [gen.HERE/'mie_dynamic_api.f90',gen.HERE/'SOURCE.json',gen.HERE/'laguerre.py']
    expected_sources={str(p.relative_to(gen.ROOT)):gen.sha(p) for p in source_files}
    require(receipt['kernel_source_sha256']==expected_sources,'Kernel/source-manifest identities differ')
    manifest=json.loads((gen.HERE/'SOURCE.json').read_text())
    require(all(gen.sha(gen.HERE/'socrates'/name)==spec['sha256'] for name,spec in manifest['files'].items()),'Original vendor source pin differs')
    adapted=(gen.HERE/'socrates/mie_scatter.f').read_text()
    for operands in ('0.0_RealK, 0.0_RealK','psi_nm2, -chi_nm2','psi_nm1, -chi_nm1','psi_n, -chi_n'):
        adapted=adapted.replace('CMPLX('+operands+')','CMPLX('+operands+', KIND=RealK)')
    adaptation=receipt['kernel_source_adaptation']
    require(adaptation['original_sha256']==gen.sha(gen.HERE/'socrates/mie_scatter.f') and
            adaptation['compiled_mie_sha256']==hashlib.sha256(adapted.encode()).hexdigest() and
            adaptation['constructors']==4,'Compiled precision adaptation identity differs')
    library=directory/'kernel/libmie_dynamic.so'
    if library.exists():require(gen.sha(library)==receipt['kernel_binary_sha256'],'Local compiled library identity differs')
    local_adaptation=directory/'kernel/source-adaptation.json'
    if local_adaptation.exists():require(json.loads(local_adaptation.read_text())==adaptation,'Local adaptation manifest differs')
    table_path=directory/'frozen-ice-psd-moments.nc'
    require(gen.sha(table_path)==receipt['table_sha256'],'Table hash differs from receipt')
    axes, arrays = {}, {}
    with Dataset(table_path) as nc:
        require(nc.model=='EXPERIMENTAL_HOMOGENEOUS_ICE_EXPONENTIAL_PSD_V1','Different material/PSD model')
        require(nc.status=='NUMERICAL_GENERATION_ONLY_NOT_WRF_VALIDATED','Different table scope')
        for name,units in [('lambda','m-1'),('temperature','K'),('sw_bounds','cm-1'),('lw_bounds','cm-1')]:
            require(nc[name].units==units and nc[name].dtype==np.dtype('f8'),f'Wrong {name} units/dtype')
            data=nc[name][:]
            require(not np.any(np.ma.getmaskarray(data)),f'Masked {name}')
            axes[name]=np.asarray(data,dtype=float)
            require(np.all(np.isfinite(axes[name])) and np.all(axes[name]>0),f'Invalid {name}')
        for name in ('lambda','temperature'):
            require(axes[name].ndim==1 and axes[name].size>0 and np.all(np.diff(axes[name])>0),f'Wrong {name} axis')
        require(axes['lambda'].tolist()==receipt['lambda_grid_m_inv'],'Lambda axis/receipt mismatch')
        require(axes['temperature'].tolist()==receipt['temperatures_K'],'Temperature axis/receipt mismatch')
        for phase,nb in [('SW',14),('LW',16)]:
            require(np.array_equal(axes[phase.lower()+'_bounds'],gen.EXPECTED_BOUNDS[phase]),f'{phase} band contract')
            dims=('lambda','sw_band') if phase=='SW' else ('lambda','temperature','lw_band')
            shape=(len(axes['lambda']),nb) if phase=='SW' else (len(axes['lambda']),len(axes['temperature']),nb)
            for moment in MOMENTS:
                name=phase.lower()+'_'+moment+'_times_density'; variable=nc[name]
                require(variable.dimensions==dims and variable.shape==shape and variable.units=='m-1' and variable.dtype==np.dtype('f8'),f'{name} schema')
                data=variable[:]; require(not np.any(np.ma.getmaskarray(data)),f'Masked {name}')
                arrays[name]=np.asarray(data,dtype=float)
                require(np.all(np.isfinite(arrays[name])),f'Nonfinite {name}')
            ext,sca,sg,absorb=(arrays[phase.lower()+'_'+moment+'_times_density'] for moment in MOMENTS)
            require(np.all(ext>0) and np.all(sca>=0) and np.all(absorb>=0),'Negative optical moment')
            require(np.all(sca<=ext+1e-10) and np.all(np.abs(sg)<=sca+1e-10),'Scattering/asymmetry bound')
            require(np.allclose(ext,sca+absorb,rtol=1e-12,atol=1e-10),'Extinction=absorption+scattering closure')
    seen=set()
    for row in receipt['rows']:
        phase,band,slope=row['phase'],row['band'],row['slope']
        key=(phase,band,slope); require(key not in seen,'Duplicate spectral task receipt'); seen.add(key)
        require(phase in ('SW','LW') and slope in axes['lambda'] and
                isinstance(band,int) and 0<=band<(14 if phase=='SW' else 16),'Unknown spectral task')
        il=int(np.where(axes['lambda']==slope)[0][0]); values=np.asarray(row['moments'])
        nt=1 if phase=='SW' else len(axes['temperature'])
        require(values.shape==(4,nt),'Spectral receipt shape')
        for j,moment in enumerate(MOMENTS):
            actual=arrays[phase.lower()+'_'+moment+'_times_density'][il,...,band]
            require(np.array_equal(np.atleast_1d(actual),values[j]),'Table does not match task receipt')
        require(np.all(np.isfinite(row['source_integral'])) and np.all(np.asarray(row['source_integral'])>0),'Source integral')
        require(row['needed_terms_max']<=receipt['max_terms'] and row['needed_terms_max']>0,'Workspace bound')
        require(0<=row['dropped_mass_weight_fraction']<1e-12 and
                0<=row['dropped_area_weight_fraction']<1e-12,'Excessive quadrature pruning')
    require(len(seen)==30*len(axes['lambda']),'Missing spectral task receipt')
    receipt['_artifact_verification']={'local_sources_verified':True,
                                      'local_compiled_library_available_and_verified':library.exists(),
                                      'local_adaptation_manifest_available_and_verified':local_adaptation.exists(),
                                      'table_and_all_task_rows_verified':True}
    return axes,arrays,receipt,gen.sha(receipt_path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--max-extinction-normalized-error',type=float)
    parser.add_argument('--select-lambda',type=float,nargs='+',help='explicit common slopes to compare after validating each complete artifact')
    args=parser.parse_args()
    if args.output.exists(): parser.error('Use a new output file')
    tolerance=args.max_extinction_normalized_error
    if tolerance is not None and (not math.isfinite(tolerance) or tolerance<=0): parser.error('Tolerance must be positive finite')
    ca,c,cr,ch=load(args.candidate); ra,r,rr,rh=load(args.reference)
    if args.select_lambda is None:
        require(all(np.array_equal(ca[name],ra[name]) for name in ca),'Cannot compare different axes/bands')
        selected=ra['lambda']
    else:
        selected=np.asarray(args.select_lambda)
        require(np.all(np.isfinite(selected)) and np.all(selected>0) and np.all(np.diff(selected)>0),'Invalid selected slopes')
        require(all(np.array_equal(ca[name],ra[name]) for name in ca if name!='lambda'),'Cannot compare different temperatures/bands')
        require(all(value in ca['lambda'] and value in ra['lambda'] for value in selected),'Selected slope absent from a complete artifact')
        ci=[int(np.where(ca['lambda']==value)[0][0]) for value in selected]
        ri=[int(np.where(ra['lambda']==value)[0][0]) for value in selected]
        c={name:data[ci,...] for name,data in c.items()};r={name:data[ri,...] for name,data in r.items()}
    for name in ('input_sources','gas_data_sha256','generator_sha256','kernel_source_sha256','kernel_source_adaptation',
                 'numerical_packages','compiler','kernel_flags','quadrature_algorithm'):
        require(cr[name]==rr[name],f'{name} differs; comparison is not numerical controls alone')
    metrics={}
    for name in r:
        diff=np.abs(c[name]-r[name]); ext=r[name[:2]+'_extinction_times_density']
        scaled=diff/np.maximum(ext,1e-30); point=diff/np.maximum(np.abs(r[name]),1e-30)
        where=np.unravel_index(np.argmax(scaled),scaled.shape)
        metrics[name]=dict(max_absolute_times_density=float(np.max(diff)),
                           max_extinction_normalized_error=float(np.max(scaled)),
                           max_point_relative_error=float(np.max(point)),
                           worst_extinction_normalized_index=list(map(int,where)))
    maximum=max(x['max_extinction_normalized_error'] for x in metrics.values())
    passed=None if tolerance is None else maximum<=tolerance
    result=dict(status='NUMERICAL_DIFFERENCE_REPORT',candidate_receipt_sha256=ch,reference_receipt_sha256=rh,
                candidate_controls={k:cr[k] for k in ('order','max_spectral_step_cm_inv')},
                reference_controls={k:rr[k] for k in ('order','max_spectral_step_cm_inv')},
                compared_lambda_m_inv=selected.tolist(),compared_temperatures_K=ra['temperature'].tolist(),
                artifact_verification={'candidate':cr['_artifact_verification'],'reference':rr['_artifact_verification']},
                maximum_extinction_normalized_error=maximum,requested_tolerance=tolerance,
                requested_numerical_tolerance_pass=passed,metrics=metrics,
                scope='Numerical control comparison at sampled axes, not interpolation, material or forecast validation')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','maximum_extinction_normalized_error','requested_numerical_tolerance_pass')}))
    if passed is False: raise SystemExit(1)


if __name__=='__main__':
    main()
