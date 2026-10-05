"""Reconstruct LW Planck fractions from held state and tables; no RTE/model calls."""
import hashlib, importlib.util, json, math, sys
from pathlib import Path
import numpy as np
from netCDF4 import Dataset, chartostring

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def interp(table, temperatures, offset, delta):
    v=(temperatures-offset)/delta
    i=np.trunc(v).astype(int); f=v-i
    i=np.clip(i,0,table.shape[1]-2)
    return (table[:,i]+f[None,:]*(table[:,i+1]-table[:,i])).T

def main():
    out=Path(__file__).resolve().parent
    if (out/'result.json').exists():
        raise ValueError('refuse overwrite')
    plan=json.loads((out/'plan.json').read_text()); pins=plan['pins']
    for key,p in pins.items():
        if sha(p['path'])!=p['sha256']:
            raise ValueError('changed pin '+key)
    spec=importlib.util.spec_from_file_location('pfrac_parser',pins['parser']['path'])
    helper=importlib.util.module_from_spec(spec); sys.modules[spec.name]=helper;spec.loader.exec_module(helper)
    _,inp=helper.read_sections(Path(pins['held_input']['path']))
    _,src=helper.read_sections(Path(pins['captured_n2_sidecar']['path']))
    _,saved=helper.read_sections(Path(pins['captured_n2_result']['path']))
    if inp['TLAY'].shape!=(1,45) or inp['TLEV'].shape!=(1,46):
        raise ValueError('unexpected diagnostic-column shape')
    with Dataset(pins['production_coefficients']['path']) as ds:
        def get(k,dtype=float):
            raw=ds[k][:]
            if np.any(np.ma.getmaskarray(raw)): raise ValueError('masked table '+k)
            return np.asarray(raw,dtype=dtype)
        names=[str(x).strip() for x in chartostring(ds['gas_names'][:])]
        ks=get('key_species',int); vref=get('vmr_ref'); pref=get('press_ref')
        tref=get('temp_ref'); ptrop=float(get('press_ref_trop'))
        pf=get('plank_fraction'); bp=get('totplnk'); bounds=get('bnd_limits_gpt',int)
        edges=get('bnd_limits_wavenumber')
        dims={k:list(ds[k].dimensions) for k in ['key_species','vmr_ref','plank_fraction']}
    if pf.shape!=(14,60,9,128) or dims!={'key_species':['bnd','atmos_layer','pair'],
        'vmr_ref':['temperature','absorber_ext','atmos_layer'],
        'plank_fraction':['temperature','pressure_interp','mixing_fraction','gpt']}:
        raise ValueError('table shape/axis contract')
    if not np.array_equal(bounds,src['BAND_LIMITS_GPOINT'][:,:,0].T) or not np.array_equal(edges,src['BAND_LIMITS_WAVENUMBER'][:,:,0].T):
        raise ValueError('sidecar band contract')
    available=plan['available_gases']
    reduced=[x for x in names if x in available]
    indices=[0]+[names.index(x)+1 for x in reduced]
    vr=vref[:,indices,:]
    kr=np.empty_like(ks)
    for index in np.ndindex(ks.shape):
        val=int(ks[index])
        kr[index]=0 if val==0 else reduced.index(names[val-1])+1
    # Only (0,0) is rewritten to (2,2); a single-gas (g,0) keeps dry-air index0.
    rewritten=kr.copy(); flavors=[]
    for b in range(16):
        for atm in range(2):
            pair=tuple(int(x) for x in kr[b,atm])
            if pair==(0,0): pair=(2,2)
            rewritten[b,atm]=pair
            if pair not in flavors: flavors.append(pair)
    mass=inp['NATIVE_DRY_LAYER_MASS_KG_M2'][0]
    moldry=float(inp['MOL_WEIGHT_DRY'][0,0])
    dry=mass*(plan['avogadro']/(moldry*10000.))
    colgas=np.empty((45,len(reduced)+1));colgas[:,0]=dry
    for j,name in enumerate(reduced,1):
        vmr=np.full(45,plan['n2_override']) if name=='n2' else inp[plan['input_gas_sections'][name]][0]
        colgas[:,j]=vmr*dry
    dryerr=float(np.max(np.abs(dry/saved['GAS_COL_DRY'][0,:,0]-1)))
    if dryerr>plan['dry_column_max_relative']:raise ValueError('dry column contract')
    dt=float((tref[-1]-tref[0])/(len(tref)-1))
    logs=np.log(pref); dp=float((math.log(pref[-1])-math.log(pref[0]))/(len(pref)-1))
    t=inp['TLAY'][0]; p=inp['PLAY'][0]*100.
    jt=np.clip(np.trunc((t-(tref[0]-dt))/dt).astype(int),1,len(tref)-1)
    ft=(t-tref[jt-1])/dt
    lp=1.+(np.log(p)-logs[0])/dp
    jp=np.clip(np.trunc(lp).astype(int),1,len(pref)-1);fp=lp-jp
    atmosphere=np.where(np.log(p)>math.log(ptrop),0,1)
    fractions=np.empty((45,128)); metadata=[]
    for b,(lo,hi) in enumerate(bounds):
        sl=slice(lo-1,hi); rows=[]
        for k in range(45):
            atm=int(atmosphere[k]); g1,g2=rewritten[b,atm]
            # Fortran jpress argument is jp + itropo, itropo=atm+1.
            # Lower/upper zero-based pressure indices are jp+atm-1 / jp+atm.
            pressure=int(jp[k]+atm-1)
            temp=int(jt[k]-1); planes=[]; record=[]
            for plane in range(2):
                ratio=vr[temp+plane,g1,atm]/vr[temp+plane,g2,atm]
                cm=colgas[k,g1]+ratio*colgas[k,g2]
                eta=colgas[k,g1]/cm if cm>2*np.finfo(float).tiny else .5
                le=eta*(pf.shape[2]-1); je=min(math.trunc(le)+1,pf.shape[2]-1)
                fe=math.fmod(le,1.)
                tf=(1.-ft[k]) if plane==0 else ft[k]
                fm0=(1.-fe)*tf;fm1=fe*tf
                w00=(1.-fp[k])*fm0;w10=(1.-fp[k])*fm1
                w01=fp[k]*fm0;w11=fp[k]*fm1
                e=je-1;tt=temp+plane
                val=(w00*pf[tt,pressure,e,sl]+w10*pf[tt,pressure,e+1,sl]+
                     w01*pf[tt,pressure+1,e,sl]+w11*pf[tt,pressure+1,e+1,sl])
                planes.append(val)
                record.append({'eta':float(eta),'jeta_Fortran':je,
                    'weights_eta_pressure':[float(w00),float(w10),float(w01),float(w11)]})
            fractions[k,sl]=planes[0]+planes[1]
            rows.append({'layer':k+1,'atmosphere_Fortran':atm+1,'flavor_Fortran':flavors.index(tuple(rewritten[b,atm]))+1,'planes':record})
        metadata.append({'band':b+1,'gpoint_range':bounds[b].tolist(),'layers':rows})
    # Fraction reconstruction above has never read SOURCE_LAYER/LEVEL/SURFACE.
    temps=np.concatenate((t,inp['TLEV'][0],inp['TSFC'].ravel()))
    raw=interp(bp,temps,float(tref[0]),float((tref[-1]-tref[0])/(bp.shape[1]-1)))
    layer=np.empty((45,128));level=np.empty((46,128));surface=np.empty(128)
    inferred=np.empty_like(fractions);sums=[]; band_errors=[]
    for b,(lo,hi) in enumerate(bounds):
        sl=slice(lo-1,hi); f=fractions[:,sl]
        layer[:,sl]=f*raw[:45,b,None]
        level[0,sl]=f[0]*raw[45,b];level[-1,sl]=f[-1]*raw[90,b]
        level[1:-1,sl]=np.sqrt(f[:-1]*f[1:])*raw[46:90,b,None]
        surface[sl]=f[0]*raw[91,b]
        inferred[:,sl]=src['SOURCE_LAYER'][0,:,sl]/raw[:45,b,None]
        sums.append(f.sum(axis=1).tolist())
        band_errors.append({'band':b+1,'source_layer_max_abs':float(np.max(np.abs(layer[:,sl]-src['SOURCE_LAYER'][0,:,sl])))})
    errors={'dry_column_max_relative':dryerr,'fraction_vs_inferred_max_abs':float(np.max(np.abs(fractions-inferred))),
      'layer_source_max_abs':float(np.max(np.abs(layer-src['SOURCE_LAYER'][0]))),
      'level_source_max_abs':float(np.max(np.abs(level-src['SOURCE_LEVEL'][0]))),
      'surface_source_max_abs':float(np.max(np.abs(surface-src['SOURCE_SURFACE'][0,0])))}
    if errors['fraction_vs_inferred_max_abs']>plan['fraction_max_abs'] or max(errors[x] for x in ['layer_source_max_abs','level_source_max_abs','surface_source_max_abs'])>plan['source_max_abs']:
        raise ValueError('mapped source tolerance failed '+json.dumps(errors))
    result={'schema':'udm37-bon-night-independent-pfrac-result-v1','status':'PASS_SCOPED',
        'plan_sha256':sha(out/'plan.json'),'script_sha256':sha(__file__),'pins':pins,
        'scope':plan['scope'],'nonclaims':plan['nonclaims'],'errors':errors,
        'available_gases':available,'reduced_gases':reduced,'key_species_reduced':kr.tolist(),
        'key_species_rewritten':rewritten.tolist(),'flavors_Fortran_indices':[list(x) for x in flavors],
        'jtemp_Fortran':jt.tolist(),'jpress_Fortran':jp.tolist(),'ftemp':ft.tolist(),'fpress':fp.tolist(),
        'atmosphere_Fortran':(atmosphere+1).tolist(),'fraction_sums_by_band':sums,
        'fraction_sum_min_max':[float(np.min(sums)),float(np.max(sums))],
        'independent_pfrac':fractions.tolist(),'interpolation':metadata,'band_errors':band_errors}
    (out/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':result['status'],'errors':errors,'fraction_sum_min_max':result['fraction_sum_min_max'],'result_sha256':sha(out/'result.json')}))

if __name__=='__main__':main()
