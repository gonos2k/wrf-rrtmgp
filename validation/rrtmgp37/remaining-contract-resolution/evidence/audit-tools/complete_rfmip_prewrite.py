#!/usr/bin/env python3
"""One immutable historical-candidate run for eight uncaptured strict failures.

Reuse the authenticated diagnostic executable with an external profile selector.
Do not rewrite archives, change the comparator, or claim publisher provenance.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import numpy as np
from netCDF4 import Dataset

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'build/udm37-rfmip-historical-source-experiment-v1'
WORK=ROOT/'build/udm37-remaining-resolution-v1/rfmip-prewrite-eight-v1'


def pin(path):
    path=Path(path);raw=path.read_bytes()
    return {'path':str(path.resolve()),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}


def require(ok,message):
    if not ok:raise ValueError(message)


def check(rec):
    got=pin(rec['path'])
    require(got['sha256']==rec['sha256'] and got['bytes']==rec.get('bytes',rec.get('size',rec.get('size_bytes'))),
            'immutable pin differs: '+rec['path'])


def array(path,var):
    with Dataset(path) as ds:
        v=ds.variables[var];v.set_auto_maskandscale(False);a=np.asarray(v[:])
        require(a.dtype==np.dtype('float32') and a.shape==(18,100,61),'unexpected published/candidate storage')
        require(np.all(np.isfinite(a)) and np.all(np.abs(a)<1.e19),'nonfinite/fill data')
        return a


def main():
    WORK.mkdir(exist_ok=False)
    plan=json.loads((OLD/'plan.json').read_text());built=json.loads((OLD/'build-receipt.json').read_text())
    residual_path=OLD/'residual-details.json';details=json.loads(residual_path.read_text())
    selected=[r for r in details['residual_cells'] if not r['profile_captured']]
    require(len(selected)==8,'uncaptured failure cell roster changed')
    profiles=sorted({tuple(r['index0_experiment_site_level'][:2]) for r in selected})
    for rec in [*plan['source_files'],*plan['pins'].values()]:check(rec)
    exe=Path(built['executable']['path']);check(built['executable'])
    for rec in built['runtime_closure'].values():check(rec)
    env={**os.environ,**built['controlled_environment'],'LC_ALL':'C'}
    linked=subprocess.check_output(['/usr/bin/ldd',str(exe)],env=env,text=True)
    require('not found' not in linked,'missing linked runtime')
    actual_paths=set()
    for line in linked.splitlines():
        match=re.match(r'\s*(?:\S+\s+=>\s+)?(/\S+)\s+\(',line)
        if match:actual_paths.add(str(Path(match[1]).resolve()))
    require(actual_paths=={str(Path(r['path']).resolve()) for r in built['runtime_closure'].values()},
            'resolved shared-library roster changed')
    helper=ROOT/'build/udm37-remaining-contracts-pr-work/WRF/test/rrtmgp/test_netcdf_zz.py'
    spec=importlib.util.spec_from_file_location('rfmip_eight_runner',helper)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    runner=module.Runner(WORK,300,env,2)
    run=WORK/'run';run.mkdir()
    selector=run/'profiles.txt';selector.write_text(''.join(f'{e+1} {s+1}\n' for e,s in profiles))
    for key,name in [('input','input.nc'),('coefficient','coeff.nc')]:
        (run/name).symlink_to(plan['pins'][key]['path'])
    (run/'multiple_input4MIPs_radiation_RFMIP_UColorado-RFMIP-1-2_none.nc').symlink_to(plan['pins']['input']['path'])
    refroot=ROOT/'build/official-rrtmgp-reference/data/examples/rfmip-clear-sky/reference'
    names={v:f'{v}_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc' for v in ('rsd','rsu')}
    original_arrays={};reference_arrays={};inputpins=[]
    for var,name in names.items():
        ref=refroot/name;old=OLD/'run'/name
        check(details['pins']['reference_'+var]);check(details['pins']['historical_'+var])
        reference_arrays[var]=array(ref,var);original_arrays[var]=array(old,var)
        inputpins.extend([pin(ref),pin(old)]);shutil.copy2(ref,run/name)
    report={'schema':'UDM37_RFMIP_EIGHT_MISSING_PREWRITE_V1','status':'PREPARED',
            'scope':'Historical candidate serialization only; exact publisher generation remains unauthenticated',
            'compiler_calls':0,'new_SW_standalone_calls':0,'WRF_calls':0,'LBLRTM_calls':0,
            'source_commit':plan['source_commit'],'executable':pin(exe),
            'plan':pin(OLD/'plan.json'),'build_receipt':pin(OLD/'build-receipt.json'),
            'residuals':pin(residual_path),'selector':pin(selector),'input_pins':inputpins,
            'profiles':profiles,'strict_atol':1.e-5,'strict_rtol':0,
            'production_accepted':False,'physical_reference_accepted':False}
    def save():
        report['processes']=runner.commands;module.write_json(WORK/'result.json',report)
    save()
    try:
        report['new_SW_standalone_calls']=1;save()
        log=runner.run([exe,'8','input.nc','coeff.nc','1','diag','profiles.txt'],run,'historical_SW_diagnostic')
        require(not any(t in log.read_text() for t in ['stopping','unblock_and_write:','write_field:']),
                'legacy driver reported an error with RC0')
        captures={}
        for key,n in {'source_pre':224,'source_post':224,'optics':60*224*3,'flux_solver':61*2,'flux_written':61*2}.items():
            p=run/f'diag_{key}.bin';require(p.stat().st_size==len(profiles)*(8+n*8),'capture roster/length differs')
            captures[key]=pin(p)
        outputs={};failure_counts={}
        for var,name in names.items():
            data=array(run/name,var)
            require(np.array_equal(data.view('u4'),original_arrays[var].view('u4')),'selector changed candidate flux bits')
            failure_counts[var]=int(np.count_nonzero(np.abs(data.astype('f8')-reference_arrays[var].astype('f8'))>1.e-5))
            outputs[var]=pin(run/name)
        require(failure_counts=={'rsd':13,'rsu':8},'unchanged strict result differs')
        raw=(run/'diag_flux_written.bin').read_bytes();step=8+61*2*8;captured={}
        for i in range(0,len(raw),step):
            e,s=struct.unpack_from('<ii',raw,i);key=(e-1,s-1)
            require(key not in captured,'duplicate prewrite profile')
            captured[key]=np.frombuffer(raw,dtype='<f8',count=122,offset=i+8).copy()
        require(set(captured)==set(profiles),'prewrite profile identities differ')
        rows=[]
        for r in selected:
            var=r['variable'];e,s,k=r['index0_experiment_site_level']
            value=float(captured[(e,s)][k+(61 if var=='rsd' else 0)])
            target=reference_arrays[var][e,s,k];stored=original_arrays[var][e,s,k]
            cast=np.float32(value)
            require(cast.view('u4')==stored.view('u4'),'prewrite cast does not reproduce candidate output')
            low=(float(np.nextafter(target,np.float32(-np.inf)))+float(target))/2.
            high=(float(np.nextafter(target,np.float32(np.inf)))+float(target))/2.
            rows.append({'variable':var,'index0_experiment_site_level':[e,s,k],
                         'prewrite_W_m2':value,'reference_stored_W_m2':float(target),
                         'candidate_stored_W_m2':float(stored),'prewrite_minus_reference':value-float(target),
                         'reference_rounding_interval':[low,high],
                         'prewrite_outside_closed_reference_rounding_interval':not(low<=value<=high),
                         'prewrite_strict_fail':abs(value-float(target))>1.e-5,
                         'cast_equals_saved_candidate_bits':True})
        for rec in [*plan['source_files'],*plan['pins'].values()]:check(rec)
        check(built['executable'])
        for rec in built['runtime_closure'].values():check(rec)
        report.update(status='PASS_SCOPED_MISSING_PREWRITE_COVERAGE_STRICT_FAIL_PRESERVED',
            captures=captures,outputs=outputs,candidate_all_flux_bits_unchanged=True,
            strict_failure_counts=failure_counts,rows=rows,
            newly_captured_cells=8,previously_captured_cells=13,full_strict_cell_prewrite_coverage=21,
            new_prewrite_failures=sum(r['prewrite_strict_fail'] for r in rows),
            new_outside_rounding_intervals=sum(r['prewrite_outside_closed_reference_rounding_interval'] for r in rows),
            missing_authority='Exact publisher source/build/compiler/libraries/inputs/coefficients and pre-cast fluxes remain unknown')
        save();print(json.dumps({k:report[k] for k in ['status','strict_failure_counts','newly_captured_cells','new_prewrite_failures','new_outside_rounding_intervals']}))
        return 0
    except BaseException as error:
        report.update(status='FAIL_PRESERVED_STOPPED',error=type(error).__name__+': '+str(error));save()
        print(json.dumps({'status':report['status'],'error':report['error']}));return 1


if __name__=='__main__':raise SystemExit(main())
