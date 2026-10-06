#!/usr/bin/env python3
"""Compare completed historical output to retained controls, without reruns."""
from pathlib import Path
import csv, hashlib, json
import numpy as np
from netCDF4 import Dataset

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CURRENT=ROOT/'build/udm37-rfmip-residual-next-diagnostic-v5/execution-v5/old_solar'
REFERENCE=ROOT/'build/official-rrtmgp-reference/data/examples/rfmip-clear-sky/reference'

def pin(p):
    p=Path(p);data=p.read_bytes()
    return {'path':str(p),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}

def metrics(x,y):
    if x.shape!=y.shape or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Shape/nonfinite mismatch')
    delta=x.astype(np.float64)-y.astype(np.float64)
    return {'shape':list(x.shape),'dtype_x':str(x.dtype),'dtype_y':str(y.dtype),
            'values':int(x.size),'exact_values':int(np.count_nonzero(x==y)),
            'bitwise_equal':x.dtype==y.dtype and x.tobytes()==y.tobytes(),
            'max_abs':float(np.max(np.abs(delta))),
            'mean_abs':float(np.mean(np.abs(delta))),
            'failed_cells_at_1e_5':int(np.count_nonzero(np.abs(delta)>1e-5))}

def capture(path,count):
    dtype=np.dtype([('ids','<i4',(2,)),('data','<f8',(count,))])
    if path.stat().st_size != 135*dtype.itemsize:
        raise ValueError('Capture size/schema mismatch: '+str(path))
    data=np.fromfile(path,dtype=dtype)
    if len(data)!=135 or len(set(map(tuple,data['ids'])))!=135 or not np.isfinite(data['data']).all():
        raise ValueError('Capture count/uniqueness/finiteness failure')
    return data

def read(path,var):
    with Dataset(path) as ds:
        x=np.asarray(ds.variables[var][:])
        if x.shape!=(18,100,61) or x.dtype!=np.dtype('float32'):
            raise ValueError('RFMIP output shape/type changed')
        return x

def ulps(x,y):
    # Monotone sign-aware ordering for IEEE float32, including signed values.
    x=np.asarray(x,dtype=np.float32).view(np.uint32).astype(np.int64)
    y=np.asarray(y,dtype=np.float32).view(np.uint32).astype(np.int64)
    order=lambda a:np.where(a & 0x80000000,0x80000000-(a & 0x7fffffff),0x80000000+a)
    distances=np.abs(order(x)-order(y))
    values,counts=np.unique(distances,return_counts=True)
    return {str(int(v)):int(c) for v,c in zip(values,counts)}

def main():
    out=HERE/'analysis.json'
    if out.exists():raise FileExistsError('Refusing to overwrite completed analysis')
    execution=json.loads((HERE/'execution.json').read_text())
    if execution['status']!='COMPLETE_ONE_HISTORICAL_STANDALONE_NOT_ACCURACY_VERDICT':
        raise ValueError('Historical run incomplete')
    old=HERE/'run'
    result={'schema':'udm37-historical-source-analysis-v1','status':'COMPLETE_DIAGNOSTIC_NOT_ACCURACY_VERDICT',
            'scope':'Historical v1.0 + authenticated coefficient candidate versus published SW and completed current-source/old-solar control. Not authenticated as the original CMIP6 generator.',
            'new_solver_calls_in_analysis':0,'threshold':{'atol':1e-5,'rtol':0},
            'pins':{'execution':pin(HERE/'execution.json'),'plan':pin(HERE/'plan.json'),
                    'analyzer':pin(HERE/'analyze.py'),
                    'retained_current_execution':pin(ROOT/'build/udm37-rfmip-residual-next-diagnostic-v5/execution-v5/execution.json'),
                    'loader_equivalence':pin(ROOT/'build/udm37-rfmip-historical-source-plan-v1/loader-equivalence-v1.json')},
            'capture_comparison':{},'full_outputs':{},'selected_failures':{}}
    specs={'source_pre':224,'source_post':224,'optics':60*224*3,'flux_solver':122,'flux_written':122}
    captured={}
    expected_ids=np.loadtxt(old/'profiles.txt',dtype=np.int32)
    for name,size in specs.items():
        a=capture(old/f'diag_{name}.bin',size);b=capture(CURRENT/f'diag_{name}.bin',size)
        if not np.array_equal(a['ids'],b['ids']) or not np.array_equal(a['ids'],expected_ids):
            raise ValueError('Observer profile ordering differs: '+name)
        result['capture_comparison'][name]={'historical_pin':pin(old/f'diag_{name}.bin'),
            'current_pin':pin(CURRENT/f'diag_{name}.bin'),'metrics':metrics(a['data'],b['data'])}
        if name=='optics':
            result['capture_comparison'][name]['fields']={field:metrics(a['data'][:,i*60*224:(i+1)*60*224],b['data'][:,i*60*224:(i+1)*60*224]) for i,field in enumerate(['tau','ssa','g'])}
        captured[name]=(a,b)
    with Dataset(old/'coeff.nc') as ds:
        spectrum=np.asarray(ds.variables['solar_source'][:],dtype=np.float64)
    raw=captured['source_pre'][0]['data']
    if not np.array_equal(raw,np.broadcast_to(spectrum,raw.shape)):
        raise ValueError('Historical gas-optics raw spectrum is not exact promoted solar_source')
    result['raw_historical_source_exact_to_promoted_coefficient']=True
    failed=list(csv.DictReader((ROOT/'build/udm37-rfmip-residual-next-diagnostic-v4/failed_points.csv').open()))
    if len(failed)!=155:raise ValueError('Inherited failure selector changed')
    for var,offset in [('rsu',0),('rsd',61)]:
        filename=f'{var}_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc'
        h=read(old/filename,var);c=read(CURRENT/filename,var);r=read(REFERENCE/filename,var)
        result['full_outputs'][var]={'historical_pin':pin(old/filename),'current_pin':pin(CURRENT/filename),
            'reference_pin':pin(REFERENCE/filename),'historical_vs_reference':metrics(h,r),
            'current_old_solar_vs_reference':metrics(c,r),'historical_vs_current_old_solar':metrics(h,c),
            'historical_vs_reference_ULP_histogram':ulps(h,r)}
        # Verify both retained and new casts, rather than assume observers prove file writing.
        for label,array,cap in [('historical',h,captured['flux_written'][0]),('current',c,captured['flux_written'][1])]:
            sample=array[cap['ids'][:,0]-1,cap['ids'][:,1]-1,:]
            cast=cap['data'][:,offset:offset+61].astype(np.float32)
            if not np.array_equal(sample,cast):raise ValueError(f'Written-output cast mismatch: {label} {var}')
        sel=[x for x in failed if x['variable']==var]
        inds=tuple(np.array([int(row[key]) for row in sel]) for key in ['expt_index0','site_index0','level_index0'])
        result['selected_failures'][var]={'cells':len(sel),'historical_vs_reference':metrics(h[inds],r[inds]),
            'current_old_solar_vs_reference':metrics(c[inds],r[inds]),
            'historical_vs_current_old_solar':metrics(h[inds],c[inds]),
            'historical_vs_reference_ULP_histogram':ulps(h[inds],r[inds])}
    result['written_casts_exact_for_both_135_profile_captures']=True
    result['historical_full_strict_failures']=sum(x['historical_vs_reference']['failed_cells_at_1e_5'] for x in result['full_outputs'].values())
    result['retained_current_old_solar_full_strict_failures']=sum(x['current_old_solar_vs_reference']['failed_cells_at_1e_5'] for x in result['full_outputs'].values())
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':result['status'],'historical_full_strict_failures':result['historical_full_strict_failures'],
                     'retained_current_old_solar_full_strict_failures':result['retained_current_old_solar_full_strict_failures'],
                     'capture_bitwise_equal':{k:v['metrics']['bitwise_equal'] for k,v in result['capture_comparison'].items()},
                     'selected_failures':{k:v['historical_vs_reference']['failed_cells_at_1e_5'] for k,v in result['selected_failures'].items()}},sort_keys=True))

if __name__=='__main__':main()
