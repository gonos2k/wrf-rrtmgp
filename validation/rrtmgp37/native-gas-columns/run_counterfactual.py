#!/usr/bin/env python3
"""Re-run V6 replay captures with native versus pressure-derived dry columns."""
from __future__ import annotations
import argparse, hashlib, json, math, pathlib, subprocess, sys
import numpy as np


def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def read_input(path):
    lines=path.read_text(encoding='ascii').splitlines(keepends=True)
    if len(lines)<2 or lines[0].strip()!='RRTMGP_REPLAY_V6':
        raise ValueError(f'{path}: expected RRTMGP_REPLAY_V6')
    head=lines[1].split()
    if len(head)!=6: raise ValueError(f'{path}: malformed V6 phase header')
    phase,nc,nl= head[0],int(head[1]),int(head[2])
    if phase not in ('LW','SW') or nc<1 or nl<1: raise ValueError(f'{path}: bad phase/dimensions')
    out=[lines[0].replace('RRTMGP_REPLAY_V6','RRTMGP_REPLAY_V5',1),lines[1]]
    preserved=[lines[1]]
    i=2; seen=[]; native=None
    while i<len(lines):
        fields=lines[i].split()
        if not fields: raise ValueError(f'{path}: blank record header at line {i+1}')
        if fields[0].upper()=='NATIVE_DRY_LAYER_MASS_KG_M2':
            if native is not None or len(fields)!=3: raise ValueError(f'{path}: invalid/duplicate native mass section')
            nrow,ncol=map(int,fields[1:3]); count=nrow*ncol
            block=lines[i+1:i+1+count]
            if len(block)!=count: raise ValueError(f'{path}: truncated native mass section')
            vals=np.array([float(z.split()[0]) for z in block],dtype=np.float64)
            if not np.all(np.isfinite(vals)) or np.any(vals<=0): raise ValueError(f'{path}: invalid native masses')
            native={'rows':nrow,'columns':ncol,'values':vals}
            i += 1+count
            continue
        # Records are NAME rows columns followed by exactly rows*columns values.
        if len(fields)!=3:
            raise ValueError(f'{path}: malformed section at line {i+1}: {lines[i].strip()}')
        name=fields[0]; nr,nc2=map(int,fields[1:3]); count=nr*nc2
        if nr<1 or nc2<1 or i+1+count>len(lines): raise ValueError(f'{path}: invalid section size for {name}')
        seen.append(name.upper())
        preserved.extend(lines[i:i+1+count])
        out.extend(lines[i:i+1+count]); i += 1+count
    if native is None: raise ValueError(f'{path}: V6 native mass section missing')
    if native['rows']!=nc or native['columns']>nl: raise ValueError(f'{path}: native mass shape inconsistent with replay header')
    if 'GRAVITY' not in seen or 'CP_DRY' not in seen or 'MOL_WEIGHT_DRY' not in seen:
        raise ValueError(f'{path}: V6 lacks V5 host-constant metadata')
    if ''.join(preserved)!=''.join(out[1:]):
        raise AssertionError('V6->V5 mutation changed bytes outside magic and native mass section')
    return ''.join(out), dict(phase=phase,ncol=nc,nlay=nl,native_layers=native['columns'],native_mass=native['values'],section_names=seen,
      mutation_proof={'only_magic_and_native_mass_changed':True,
        'preserved_input_records_sha256':hashlib.sha256(''.join(preserved).encode('ascii')).hexdigest(),
        'counterfactual_preserved_records_sha256':hashlib.sha256(''.join(out[1:]).encode('ascii')).hexdigest()})

def read_result(path):
    lines=pathlib.Path(path).read_text(encoding='ascii').splitlines()
    if len(lines)<2 or lines[0].strip()!='RRTMGP_RESULT_V1': raise ValueError(f'{path}: bad result magic')
    h=lines[1].split(); phase,nc,nl=h[0],int(h[1]),int(h[2]); arrays={}; i=2
    while i<len(lines):
        h=lines[i].split()
        if len(h)!=4: raise ValueError(f'{path}: malformed result record line {i+1}')
        name=h[0].upper(); shape=tuple(map(int,h[1:4])); count=math.prod(shape); i+=1
        vals=[]
        while len(vals)<count and i<len(lines):
            vals.extend(map(float,lines[i].split())); i+=1
        if len(vals)!=count: raise ValueError(f'{path}: truncated {name} record')
        arrays[name]=np.asarray(vals,dtype=np.float64).reshape(shape,order='F')
    return dict(phase=phase,ncol=nc,nlay=nl,arrays=arrays)

def compare_field(a,b):
    if a.shape!=b.shape: raise ValueError(f'shape mismatch {a.shape} vs {b.shape}')
    d=np.asarray(a,dtype=np.float64)-np.asarray(b,dtype=np.float64)
    denom=np.maximum(np.abs(b),np.finfo(np.float64).tiny)
    return dict(max_abs=float(np.max(np.abs(d))),mean_abs=float(np.mean(np.abs(d))),
                max_relative=float(np.max(np.abs(d)/denom)))

def layer_slice(a,native_n):
    return a[:, :native_n, ...],a[:, native_n:, ...]

def find_repo_root(explicit):
    if explicit is not None:
        root=explicit.resolve()
        if not (root/'WRF/phys/module_ra_rrtmgp.F').is_file():
            raise ValueError(f'--repo-root does not contain WRF/phys/module_ra_rrtmgp.F: {root}')
        return root
    for candidate in pathlib.Path(__file__).resolve().parents:
        if (candidate/'WRF/phys/module_ra_rrtmgp.F').is_file():
            return candidate
    raise ValueError('cannot discover repository root; pass --repo-root')

def phase_metrics(capture,exe,data_dir,outdir,case,phase):
    cap=pathlib.Path(capture); inp=cap/f'{phase.lower()}.input'; actual_path=cap/f'{phase.lower()}.result'
    v5_text,meta=read_input(inp)
    if meta['phase']!=phase: raise ValueError(f'{inp}: phase mismatch')
    native_dir=outdir/case/phase.lower()/'native'; fallback_dir=outdir/case/phase.lower()/'fallback-v5'
    native_dir.mkdir(parents=True); fallback_dir.mkdir()
    v5_input=fallback_dir/'input-v5.txt'; v5_input.write_text(v5_text,encoding='ascii')
    # The native run is replayed from the exact captured V6 file; V5 only changes
    # the magic and deletes the single native-mass section.
    native_out=native_dir/'reference.result'; fallback_out=fallback_dir/'reference.result'
    subprocess.run([str(exe),str(data_dir),str(inp),str(native_out)],check=True,capture_output=True,text=True)
    subprocess.run([str(exe),str(data_dir),str(v5_input),str(fallback_out)],check=True,capture_output=True,text=True)
    native=read_result(native_out); fallback=read_result(fallback_out); actual=read_result(actual_path)
    if native['phase']!=phase or fallback['phase']!=phase or actual['phase']!=phase: raise ValueError('result phase mismatch')
    na=native['arrays']; fb=fallback['arrays']; ac=actual['arrays']; nn=meta['native_layers']; nl=meta['nlay']
    for result,label in ((native,'native replay'),(fallback,'fallback replay'),(actual,'SCM actual')):
        if result['nlay']!=nl or result['ncol']!=meta['ncol']: raise ValueError(f'{label} shape disagrees with input')
    for key in ('GAS_COL_DRY','GAS_TAU','UP','DN','HR'):
        if key not in na or key not in fb or key not in ac: raise ValueError(f'{phase}: missing required result {key}')
    coln=na['GAS_COL_DRY'][:,:,0]; colf=fb['GAS_COL_DRY'][:,:,0]
    cola=ac['GAS_COL_DRY'][:,:,0]
    extn=coln[:,nn:]; extf=colf[:,nn:]
    tau_n=na['GAS_TAU']; tau_f=fb['GAS_TAU']; tau_a=ac['GAS_TAU']
    # Gas optics layer tau must also be unchanged in the pressure-extension layers.
    ext_tau_n=tau_n[:,nn:,:]; ext_tau_f=tau_f[:,nn:,:]
    if not np.array_equal(extn,extf): raise AssertionError(f'{phase}: dry-column extension changed outside native prefix')
    if not np.array_equal(ext_tau_n,ext_tau_f): raise AssertionError(f'{phase}: gas tau extension changed outside native prefix')
    flux={}
    for key in ('UP','DN'):
        a=ac[key][:,:,0]; f=fb[key][:,:,0]; nr=na[key][:,:,0]
        flux[key]={'surface_actual_native_scm':a[:,0].tolist(),'surface_pressure_fallback':f[:,0].tolist(),
                   'surface_delta_actual_minus_fallback':(a[:,0]-f[:,0]).tolist(),
                   'toa_actual_native_scm':a[:,-1].tolist(),'toa_pressure_fallback':f[:,-1].tolist(),
                   'toa_delta_actual_minus_fallback':(a[:,-1]-f[:,-1]).tolist(),
                   'all_interfaces_actual_vs_fallback':compare_field(a,f),
                   'surface_native_reference':nr[:,0].tolist(),'surface_delta_native_reference_minus_fallback':(nr[:,0]-f[:,0]).tolist(),
                   'toa_native_reference':nr[:,-1].tolist(),'toa_delta_native_reference_minus_fallback':(nr[:,-1]-f[:,-1]).tolist(),
                   'all_interfaces_native_reference_vs_fallback':compare_field(nr,f)}
    hr_n=na['HR']; hr_f=fb['HR']; hr_a=ac['HR']
    metrics={'phase':phase,'input':str(inp),'ncol':meta['ncol'],'total_layers':nl,'native_layers':nn,
      'native_extension_layer_count':nl-nn,'native_mass_sha256':sha(inp),
      'native_column':{'min_kg_m2':float(np.min(meta['native_mass'])),'max_kg_m2':float(np.max(meta['native_mass']))},
      'mutation_proof':meta['mutation_proof'],
      'dry_column_actual_scm_native_vs_pressure_fallback':compare_field(cola,colf),
      'dry_column_actual_scm_native_prefix_first_native_layers':compare_field(cola[:,:nn],colf[:,:nn]),
      'dry_column_native_reference_vs_pressure':compare_field(coln,colf),
      'dry_column_extension_exact_zero':bool(np.array_equal(extn,extf)),
      'dry_column_extension_max_abs':float(np.max(np.abs(extn-extf))) if extn.size else 0.0,
      'gas_tau_actual_scm_native_vs_pressure_fallback':compare_field(tau_a,tau_f),
      'gas_tau_actual_scm_native_prefix_first_native_layers':compare_field(tau_a[:,:nn,:],tau_f[:,:nn,:]),
      'gas_tau_native_reference_vs_pressure':compare_field(tau_n,tau_f),
      'gas_tau_extension_exact_zero':bool(np.array_equal(ext_tau_n,ext_tau_f)),
      'gas_tau_extension_max_abs':float(np.max(np.abs(ext_tau_n-ext_tau_f))) if ext_tau_n.size else 0.0,
      'surface_toa_flux':flux,'heating_rate_actual_scm_native_vs_pressure_fallback':compare_field(hr_a,hr_f),
      'heating_rate_native_reference_vs_pressure':compare_field(hr_n,hr_f),
      'heating_rate_max_abs_actual_minus_fallback':float(np.max(np.abs(hr_a-hr_f))),
      'actual_scm_vs_native_reference':{k:compare_field(na[k],ac[k]) for k in ('GAS_COL_DRY','GAS_TAU','UP','DN','HR')},
      'artifacts':{'source_v6_sha256':sha(inp),'source_actual_result_sha256':sha(actual_path),
        'native_replay_result_sha256':sha(native_out),'fallback_v5_input_sha256':sha(v5_input),
        'fallback_v5_result_sha256':sha(fallback_out)}}
    return metrics

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--reference',required=True,type=pathlib.Path)
    ap.add_argument('--data',required=True,type=pathlib.Path)
    ap.add_argument('--control-capture',required=True,type=pathlib.Path)
    ap.add_argument('--mixed-capture',required=True,type=pathlib.Path)
    ap.add_argument('--out-dir',required=True,type=pathlib.Path)
    ap.add_argument('--repo-root',type=pathlib.Path,
                    help='repository root; discovered from this script path when omitted')
    args=ap.parse_args()
    exe=args.reference.resolve(); data=args.data.resolve(); control=args.control_capture.resolve(); mixed=args.mixed_capture.resolve(); out=args.out_dir.resolve()
    repo=find_repo_root(args.repo_root)
    if not exe.is_file() or not os.access(exe,os.X_OK): raise SystemExit(f'not executable: {exe}')
    if not data.is_dir() or not control.is_dir() or not mixed.is_dir(): raise SystemExit('data/capture directory missing')
    if out.exists(): raise SystemExit(f'refusing to overwrite existing output directory: {out}')
    out.mkdir(parents=True,exist_ok=False)
    result={'scope':'Same captured V6 SCM states replayed with native dry-mass columns and a V5 pressure/VMR counterfactual. Only V6 magic and NATIVE_DRY_LAYER_MASS_KG_M2 are removed for V5; all other input record bytes are preserved.',
      'environment':{'reference_executable':str(exe),'reference_sha256':sha(exe),'runner_sha256':sha(pathlib.Path(__file__).resolve()),'repo_root':str(repo),'data_dir':str(data),
       'reference_source_sha256':sha(repo/'WRF/test/rrtmgp/reference_column.f90'),
       'gas_backend_source_sha256':sha(repo/'WRF/phys/module_ra_rrtmgp.F'),
       'capture_trace_source_sha256':sha(repo/'WRF/phys/module_ra_rrtmgp_trace.F'),
       'gas_cloud_data_sha256':{n:sha(data/n) for n in ('rrtmgp-gas-lw-g128.nc','rrtmgp-gas-sw-g112.nc','rrtmgp-clouds-lw-bnd.nc','rrtmgp-clouds-sw-bnd.nc')},
       'git_head':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()},
      'cases':{}}
    for name,cap in (('control',control),('mixed',mixed)):
      result['cases'][name]={phase:phase_metrics(cap,exe,data,out,name,phase) for phase in ('LW','SW')}
    p=out/'receipt.json'; p.write_text(json.dumps(result,indent=2)+'\n')
    print(p)

if __name__=='__main__':
    import os
    main()
