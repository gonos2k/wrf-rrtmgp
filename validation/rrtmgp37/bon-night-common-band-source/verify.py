#!/usr/bin/env python3
"""Portable integrity/profile verifier; no radiative-transfer recurrence."""
from __future__ import annotations
import argparse, gzip, hashlib, json, math
from pathlib import Path

def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def close(a, b, tol=1e-10):
    return math.isfinite(float(a)) and math.isfinite(float(b)) and abs(float(a)-float(b)) <= tol

def read_sections(data: bytes):
    lines=data.decode('ascii').splitlines()
    if len(lines)<3 or not lines[0].startswith('RRTMGP_'):
        raise ValueError('bad replay magic/header')
    h=lines[1].split()
    if len(h)<3: raise ValueError('bad replay dimensions')
    phase,nc,nl=h[0].upper(),int(h[1]),int(h[2])
    sections={}; i=2
    while i<len(lines):
        if not lines[i].strip(): i+=1; continue
        row=lines[i].split(); i+=1
        if len(row)<2: raise ValueError('bad section header')
        name=row[0]
        if name in sections: raise ValueError('duplicate section '+name)
        shape=tuple(map(int,row[1:])); n=math.prod(shape)
        vals=[]
        while len(vals)<n and i<len(lines):
            if lines[i].strip(): vals.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split())
            i+=1
        if len(vals)!=n or any(not math.isfinite(v) for v in vals): raise ValueError('bad values '+name)
        sections[name]=(shape,vals)
    return phase,nc,nl,sections

def read_legacy_inputs(data: bytes):
    lines=data.decode('ascii').splitlines()
    if not lines or lines[0].strip()!='RRTMG4_SELECTED_COLUMN_EXPORT_V1': raise ValueError('legacy packet magic')
    fields={}; stage=None; i=1
    while i<len(lines):
        row=lines[i].split(); i+=1
        if not row: continue
        if row[0]=='stage':
            if len(row)!=2: raise ValueError('bad legacy stage')
            stage=row[1]; continue
        if row[0] in {'phase','domain','step','source_seconds','i','j','layout'}: continue
        if stage!='INPUT': continue
        if len(row)<3: raise ValueError('bad legacy field header')
        name,units=row[:2]; shape=tuple(map(int,row[2:])); n=math.prod(shape); values=[]
        while len(values)<n and i<len(lines):
            if lines[i].strip(): values.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split())
            i+=1
        if len(values)!=n: raise ValueError('bad legacy input length '+name)
        if name in fields: raise ValueError('duplicate legacy field '+name)
        fields[name]=(units,shape,values)
    return fields

def verify_semantics(root: Path, manifest: dict):
    files={x['path']:x for x in manifest['payloads']}
    def load_json(name): return json.loads((root/name).read_text())
    plan=load_json('analysis/plan.json'); result=load_json('analysis/result.json'); summary=load_json('summary.json')
    if result.get('status')!='PASS_SCOPED_COMMON_BAND_COMPARISON': raise ValueError('analysis result status')
    if result.get('plan_sha256')!=files['analysis/plan.json']['sha256']: raise ValueError('result/plan hash mismatch')
    if len(result.get('bands',[]))!=16: raise ValueError('expected 16 bands')
    for i,b in enumerate(result['bands'],1):
        if b.get('band')!=i: raise ValueError('band labels/order changed')
        expected=(3<=i<=13)
        if b.get('paired_exact_physical_edges') is not expected: raise ValueError('paired-band label mismatch')
        le=b['legacy_edges_cm-1']; ge=b['gp_edges_cm-1']
        if expected and (len(le)!=2 or len(ge)!=2 or le!=ge): raise ValueError('common physical edges mismatch')
        for key in ('legacy_UP_Wm2','legacy_DN_Wm2','gp_policy1_UP_Wm2','gp_policy1_DN_Wm2','gp_integral_UP_Wm2','gp_integral_DN_Wm2'):
            if len(b[key])!=46 or any(not math.isfinite(float(x)) for x in b[key]): raise ValueError('bad profile '+key)
    # Recompute stored broadband sums from the saved per-band profiles only.
    def sums(idx):
        return {
          'legacy_surface_DN_Wm2':sum(result['bands'][i]['legacy_DN_Wm2'][0] for i in idx),
          'gp_policy1_surface_DN_Wm2':sum(result['bands'][i]['gp_policy1_DN_Wm2'][0] for i in idx),
          'gp_integral_surface_DN_Wm2':sum(result['bands'][i]['gp_integral_DN_Wm2'][0] for i in idx),
          'legacy_TOA_UP_Wm2':sum(result['bands'][i]['legacy_UP_Wm2'][-1] for i in idx),
          'gp_policy1_TOA_UP_Wm2':sum(result['bands'][i]['gp_policy1_UP_Wm2'][-1] for i in idx),
          'gp_integral_TOA_UP_Wm2':sum(result['bands'][i]['gp_integral_UP_Wm2'][-1] for i in idx)}
    for key,idx in [('common_bands_3_13',range(2,13)),('all_engine_native_totals',range(16)),('unpaired_engine_native_totals',(0,1,13,14,15))]:
        recorded=summary[key]; calc=sums(idx)
        for field,value in calc.items():
            if not close(recorded[field],value,1e-10) or not close(result['totals_common_3_13' if key=='common_bands_3_13' else 'totals_all_engine_native' if key=='all_engine_native_totals' else 'totals_unpaired_engine_native'][field],value,1e-10):
                raise ValueError('stored broadband sum mismatch '+key+'/'+field)
    if summary['status']!=result['status']: raise ValueError('summary status mismatch')
    if max(result['gp_same_engine_broadband_reproduction_max_abs_Wm2'].values())>1e-10: raise ValueError('GP saved broadband reproduction bound')
    if result['quadrature_convergence'][-1]['max_abs_all_band_UP_DN_change_Wm2']>1e-9: raise ValueError('saved band quadrature convergence bound')
    # Validate the once-only GP surface emissivity application from saved inputs.
    def unpack(key):
        rec=manifest['origins'][key]; b=(root/rec['package_path']).read_bytes()
        return gzip.decompress(b) if rec['encoding']=='gzip' else b
    iph,inc,inl,ins=read_sections(unpack('input'))
    sph,snc,snl,sources=read_sections(unpack('gp_source'))
    rph,rnc,rnl,rtes=read_sections(unpack('gp_result'))
    if iph!='LW' or (inc,inl)!=(1,45) or sph!='LW' or (snc,snl)!=(1,45) or rph!='LW' or (rnc,rnl)!=(1,45): raise ValueError('input/source/result scope dimensions')
    legacy=read_legacy_inputs(unpack('packet'))
    base_pairs=(('PLAY','PLAY'),('PLEV','PLEV'),('TLAY','TLAY'),('TLEV','TLEV'),('TSFC','TSFC'),('H2O_VMR','H2O'),('O3_VMR','O3'),('CO2_VMR','CO2'),('CH4_VMR','CH4'),('N2O_VMR','N2O'),('O2_VMR','O2'),('SURFACE_EMISSIVITY','EMIS'),('SOLVER_SEMISS','EMIS'))
    for old,new in base_pairs:
        if old not in legacy or new not in ins: raise ValueError('missing state field '+old+'/'+new)
        _unit,_shape,oldv=legacy[old]; newshape,newv=ins[new]
        if oldv!=newv: raise ValueError('state field mismatch '+old+'/'+new)
    for old,new in (('CFC11_VMR','VMR_CFC11'),('CFC12_VMR','VMR_CFC12'),('CFC22_VMR','VMR_CFC22'),('CCl4_VMR','VMR_CCL4')):
        if old not in legacy or new not in ins: raise ValueError('missing trace-gas state '+old+'/'+new)
        if legacy[old][2]!=ins[new][1]: raise ValueError('trace-gas VMR mismatch '+old+'/'+new)
    for req in ('EMIS',):
        if req not in ins: raise ValueError('missing input '+req)
    for req in ('SOURCE_SURFACE','BAND_LIMITS_GPOINT','BAND_LIMITS_WAVENUMBER'):
        if req not in sources: raise ValueError('missing source '+req)
    emis_shape,emis=ins['EMIS']; (bshape,bounds)=sources['BAND_LIMITS_GPOINT']; (eshape,edges)=sources['BAND_LIMITS_WAVENUMBER']; (ssshape,surface)=sources['SOURCE_SURFACE']
    if emis_shape!=(1,16) or bshape!=(2,16,1) or eshape!=(2,16,1) or ssshape!=(1,1,128): raise ValueError('emissivity/source mapping shape')
    # Recheck the recorded exact band/g-point map, without pairing individual
    # correlated-k indices across the two engines.
    next_gp=1
    for band in range(16):
        lo=int(bounds[2*band]); hi=int(bounds[2*band+1])
        if lo!=next_gp or hi<lo or hi>128: raise ValueError('invalid/noncontiguous GP band gpoint bounds')
        next_gp=hi+1
        if [edges[2*band],edges[2*band+1]]!=result['bands'][band]['gp_edges_cm-1']: raise ValueError('GP result/source band-edge mismatch')
        expected=sum(surface[lo-1:hi])*emis[band]
        actual=float(result['bands'][band]['gp_emitted_surface_source_Wm2sr'])
        if not close(actual,expected,1e-11): raise ValueError('emissivity application mismatch band '+str(band+1))
    if next_gp!=129: raise ValueError('GP gpoint map does not cover 1..128')
    # Optical-scope receipt: total extinction is exactly the saved gas field;
    # cloud, CU and precip fields are zero in this clear optical calculation.
    for name in ('TOTAL_TAU','GAS_TAU','GAS_TAU_RAW'):
        if name not in rtes or rtes[name][0]!=(1,45,128): raise ValueError('missing/misshaped '+name)
    if rtes['TOTAL_TAU'][1]!=rtes['GAS_TAU'][1] or rtes['TOTAL_TAU'][1]!=rtes['GAS_TAU_RAW'][1]: raise ValueError('total/gas optical-depth identity')
    for name in ('PRECIP_TAU','CLOUD_TAU','NATIVE_CLOUD_TAU','CU_CLOUD_TAU','MASK'):
        if name not in rtes or any(x!=0.0 for x in rtes[name][1]): raise ValueError('nonzero/missing clear-optics field '+name)
    # The fixed-policy 16-band profiles reconstruct saved GP broadband UP/DN.
    for flux in ('UP','DN'):
        if flux not in rtes or rtes[flux][0] not in ((1,46,1),(1,46)): raise ValueError('missing/misshaped saved GP '+flux)
        expected=rtes[flux][1]
        observed=[sum(result['bands'][i]['gp_policy1_'+flux+'_Wm2'][k] for i in range(16)) for k in range(46)]
        expected=expected if len(expected)==46 else expected[::1]
        if max(abs(a-b) for a,b in zip(observed,expected))>1e-10: raise ValueError('saved 16-band '+flux+' profile does not reconstruct GP output')
    if result.get('new_WRF_calls')!=0 or result.get('new_builds')!=0 or result.get('new_RTE_executable_calls')!=0: raise ValueError('result scope counters')
    return {'status':'PASS_PACKAGE_AND_STORED_PROFILE_CONTRACTS','payload_count':len(files),'band_count':16,'common_edge_bands':[3,13], 'emissivity_band_checks':16,'matched_legacy_state_fields':13,'matched_trace_gas_vmr_fields':4,'scope':'Integrity and arithmetic consistency checks over stored output; no recurrence or radiative-transfer engine rerun.'}

def verify_tree(root: Path):
    root=root.resolve(); manifest=json.loads((root/'manifest.json').read_text())
    expected={x['path']:x for x in manifest['payloads']}
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name!='manifest.json'}
    if actual!=set(expected): raise ValueError('closed roster mismatch: extra=%r missing=%r'%(sorted(actual-set(expected)),sorted(set(expected)-actual)))
    for rel,rec in expected.items():
        b=(root/rel).read_bytes()
        if len(b)!=rec['size_bytes'] or sha_bytes(b)!=rec['sha256']: raise ValueError('package hash mismatch '+rel)
    for key,rec in manifest['origins'].items():
        b=(root/rec['package_path']).read_bytes()
        if rec['encoding']=='gzip': b=gzip.decompress(b)
        if len(b)!=rec['origin_size_bytes'] or sha_bytes(b)!=rec['origin_sha256']: raise ValueError('original artifact pin mismatch '+key)
    return verify_semantics(root,manifest)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parent); ap.add_argument('--output',type=Path)
    a=ap.parse_args(); result=verify_tree(a.root)
    if a.output:
        if a.output.exists(): raise FileExistsError(a.output)
        a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,sort_keys=True))
if __name__=='__main__': main()
