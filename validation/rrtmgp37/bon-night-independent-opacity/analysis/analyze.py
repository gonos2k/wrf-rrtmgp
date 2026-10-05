"""LW major/minor absorption reconstructed from input and coefficient tables only."""
from pathlib import Path
import hashlib,importlib.util,json,math,sys
import numpy as np
from netCDF4 import Dataset,chartostring

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def module(path):
    spec=importlib.util.spec_from_file_location('opacity_parser',path)
    obj=importlib.util.module_from_spec(spec);sys.modules[spec.name]=obj;spec.loader.exec_module(obj)
    return obj

def main():
    out=Path(__file__).resolve().parent
    if (out/'result.json').exists():raise ValueError('refuse overwrite')
    plan=json.loads((out/'plan.json').read_text());pins=plan['pins']
    for key,pin in pins.items():
        if sha(pin['path'])!=pin['sha256'] or Path(pin['path']).stat().st_size!=pin['bytes']:
            raise ValueError('changed pin '+key)
    parser=module(pins['parser']['path'])
    _,inp=parser.read_sections(Path(pins['held_input']['path']))
    _,saved=parser.read_sections(Path(pins['captured_n2_result']['path']))
    if inp['TLAY'].shape!=(1,45) or saved['GAS_TAU_RAW'].shape!=(1,45,128):
        raise ValueError('unexpected diagnostic shape')
    with Dataset(pins['production_coefficients']['path']) as ds:
        def get(name,dtype=float):
            a=ds[name][:]
            if np.any(np.ma.getmaskarray(a)):raise ValueError('masked table '+name)
            return np.asarray(a,dtype=dtype)
        def strings(name):return [str(x).strip() for x in chartostring(ds[name][:])]
        names=strings('gas_names');gas_minor=strings('gas_minor');identifiers=strings('identifier_minor')
        keys=get('key_species',int);vmr_ref=get('vmr_ref');pref=get('press_ref');tref=get('temp_ref')
        ptrop=float(get('press_ref_trop'));major_table=get('kmajor');bounds=get('bnd_limits_gpt',int)
        rayleigh_names=[x for x in ds.variables if 'rayl' in x]
        if rayleigh_names:raise ValueError('audit is restricted to no-Rayleigh LW table')
        rawminor={}
        for regime in ['lower','upper']:
            rawminor[regime]={'table':get('kminor_'+regime),'ids':strings('minor_gases_'+regime),
                'scaling':strings('scaling_gas_'+regime),'bounds':get('minor_limits_gpt_'+regime,int),
                'density':get('minor_scales_with_density_'+regime,int),
                'complement':get('scale_by_complement_'+regime,int),'start':get('kminor_start_'+regime,int)}
        expected_dims={'kmajor':['temperature','pressure_interp','mixing_fraction','gpt'],
            'vmr_ref':['temperature','absorber_ext','atmos_layer'],'key_species':['bnd','atmos_layer','pair'],
            'kminor_lower':['temperature','mixing_fraction','contributors_lower'],
            'kminor_upper':['temperature','mixing_fraction','contributors_upper']}
        if any(list(ds[k].dimensions)!=v for k,v in expected_dims.items()):raise ValueError('coefficient axes')
    reduced=[n for n in names if n in plan['available_gases']]
    reference=vmr_ref[:,[0]+[names.index(n)+1 for n in reduced],:]
    rewritten=np.empty_like(keys);flavors=[]
    for b in range(16):
        for atm in range(2):
            pair=tuple(0 if i==0 else reduced.index(names[int(i)-1])+1 for i in keys[b,atm])
            if pair==(0,0):pair=(2,2)
            rewritten[b,atm]=pair
            if pair not in flavors:flavors.append(pair)
    gpoint_flavor=np.empty((2,128),dtype=int)
    for b,(lo,hi) in enumerate(bounds):
        for atm in range(2):gpoint_flavor[atm,lo-1:hi]=flavors.index(tuple(rewritten[b,atm]))
    dry=inp['NATIVE_DRY_LAYER_MASS_KG_M2'][0]*plan['avogadro']/(float(inp['MOL_WEIGHT_DRY'][0,0])*10000.)
    colgas=np.empty((45,len(reduced)+1));colgas[:,0]=dry
    for j,name in enumerate(reduced,1):
        vmr=np.full(45,plan['n2_override']) if name=='n2' else inp[plan['input_gas_sections'][name]][0]
        colgas[:,j]=vmr*dry
    dry_error=float(np.max(np.abs(dry/saved['GAS_COL_DRY'][0,:,0]-1)))
    if dry_error>plan['dry_column_max_relative']:raise ValueError('dry column')
    p=inp['PLAY'][0]*100.;t=inp['TLAY'][0]
    dt=float((tref[-1]-tref[0])/(len(tref)-1));logs=np.log(pref)
    dp=float((math.log(pref[-1])-math.log(pref[0]))/(len(pref)-1))
    jt=np.clip(np.trunc((t-(tref[0]-dt))/dt).astype(int),1,len(tref)-1)
    ft=(t-tref[jt-1])/dt;lp=1.+(np.log(p)-logs[0])/dp
    jp=np.clip(np.trunc(lp).astype(int),1,len(pref)-1);fp=lp-jp
    atmosphere=np.where(np.log(p)>math.log(ptrop),0,1)
    nf=len(flavors);je=np.empty((45,nf,2),dtype=int);mix=np.empty((45,nf,2))
    fm=np.empty((45,nf,2,2));fw=np.empty((45,nf,2,2,2))
    for f,(g1,g2) in enumerate(flavors):
        for k in range(45):
            atm=atmosphere[k]
            for plane in range(2):
                temp=jt[k]-1+plane;ratio=reference[temp,g1,atm]/reference[temp,g2,atm]
                cm=colgas[k,g1]+ratio*colgas[k,g2];mix[k,f,plane]=cm
                eta=colgas[k,g1]/cm if cm>2*np.finfo(float).tiny else .5
                loceta=eta*(major_table.shape[2]-1);je[k,f,plane]=min(math.trunc(loceta)+1,major_table.shape[2]-1)-1
                feta=math.fmod(loceta,1.);tf=1.-ft[k] if plane==0 else ft[k]
                fm[k,f,0,plane]=(1.-feta)*tf;fm[k,f,1,plane]=feta*tf
                fw[k,f,:,0,plane]=(1.-fp[k])*fm[k,f,:,plane]
                fw[k,f,:,1,plane]=fp[k]*fm[k,f,:,plane]
    tau_major=np.zeros((45,128))
    for b,(lo,hi) in enumerate(bounds):
        sl=slice(lo-1,hi)
        for k in range(45):
            f=int(gpoint_flavor[atmosphere[k],lo-1]);pr=int(jp[k]+atmosphere[k]-1);planes=[]
            for plane in range(2):
                e=je[k,f,plane];tt=jt[k]-1+plane;w=fw[k,f,:,:,plane]
                partial=(w[0,0]*major_table[tt,pr,e,sl]+w[1,0]*major_table[tt,pr,e+1,sl]+
                         w[0,1]*major_table[tt,pr+1,e,sl]+w[1,1]*major_table[tt,pr+1,e+1,sl])
                planes.append(mix[k,f,plane]*partial)
            tau_major[k,sl]=planes[0]+planes[1]
    # Source MINLOC/MAXLOC gives the first matching index and zero if its mask is empty.
    top_at_1=bool(p[0]<p[-1]);lower=np.flatnonzero(atmosphere==0);upper=np.flatnonzero(atmosphere==1)
    low_edge=int(lower[np.argmin(p[lower])])+1 if len(lower) else 0
    up_edge=int(upper[np.argmax(p[upper])])+1 if len(upper) else 0
    limits={'lower':[low_edge,45] if top_at_1 else [1,low_edge],
            'upper':[1,up_edge] if top_at_1 else [up_edge,45]}
    total=tau_major.copy();partials={};metadata=[];by_identifier={};h2o=reduced.index('h2o')+1
    for atm,regime in enumerate(['lower','upper']):
        raw=rawminor[regime];rows=[];pieces=[];removed=0;cursor=0;source_cursor=0
        for i,identifier in enumerate(raw['ids']):
            idx=identifiers.index(identifier);gas=gas_minor[idx];lo,hi=raw['bounds'][i];width=int(hi-lo+1)
            start=int(raw['start'][i])-1
            if start!=source_cursor:raise ValueError('noncontiguous source minor contributors')
            source_cursor+=width
            if gas not in plan['available_gases']:
                removed+=width;continue
            redstart=start-removed
            if redstart!=cursor:raise ValueError('filtered minor start remap')
            cursor+=width;pieces.append(raw['table'][:,:,start:start+width])
            scaling_name=raw['scaling'][i]
            rows.append({'original_interval':i+1,'original_start_Fortran':start+1,
              'reduced_start_Fortran':redstart+1,'identifier':identifier,'gas':gas,
              'gas_index_Fortran':reduced.index(gas)+1,'scaling_gas':scaling_name,
              'scaling_index_Fortran':reduced.index(scaling_name)+1 if scaling_name in reduced else -1,
              'density':bool(raw['density'][i]),'complement':bool(raw['complement'][i]),
              'gpoint_bounds':[int(lo),int(hi)]})
        if source_cursor!=raw['table'].shape[2]:raise ValueError('source contributor extent')
        table=np.concatenate(pieces,axis=2) if pieces else np.empty((14,9,0))
        contribution=np.zeros((45,128));a,z=limits[regime];layer_range=range(a-1,z) if a>0 else range(0)
        for row in rows:
            lo,hi=row['gpoint_bounds'];sl=slice(lo-1,hi);cs=slice(row['reduced_start_Fortran']-1,row['reduced_start_Fortran']+hi-lo)
            f=int(gpoint_flavor[atm,lo-1]);increments=[]
            group=by_identifier.setdefault(row['identifier'],np.zeros((45,128)))
            for k in layer_range:
                if atmosphere[k]!=atm:raise ValueError('regime window does not match layer mask')
                scaling=colgas[k,row['gas_index_Fortran']]
                if row['density']:
                    scaling=scaling*(.01*p[k]/t[k])
                    if row['scaling_index_Fortran']>0:
                        vmr_fact=1./colgas[k,0];dry_fact=1./(1.+colgas[k,h2o]*vmr_fact)
                        fraction=colgas[k,row['scaling_index_Fortran']]*vmr_fact*dry_fact
                        scaling=scaling*(1.-fraction if row['complement'] else fraction)
                tt=jt[k]-1;e0,e1=je[k,f];m=fm[k,f]
                coefficient=(m[0,0]*table[tt,e0,cs]+m[1,0]*table[tt,e0+1,cs]+
                             m[0,1]*table[tt+1,e1,cs]+m[1,1]*table[tt+1,e1+1,cs])
                value=scaling*coefficient
                total[k,sl]+=value;contribution[k,sl]+=value;group[k,sl]+=value
                increments.append({'layer':k+1,'scaling':float(scaling),'sum_tau':float(value.sum()),'max_tau':float(value.max())})
            row['layer_contributions']=increments
        partials[regime]=contribution
        metadata.append({'regime':regime,'original_intervals':len(raw['ids']),'retained_intervals':len(rows),
            'original_contributors':raw['table'].shape[2],'retained_contributors':table.shape[2],
            'layer_limits_Fortran':limits[regime],'intervals':rows})
    # Saved opacity is not used until reconstruction has completed.
    target=saved['GAS_TAU_RAW'][0];delta=total-target
    allowed=plan['tau_atol']+plan['tau_rtol']*np.abs(target)
    if not np.all(np.isfinite(total)) or np.any(total<0):raise ValueError('invalid reconstructed absorption')
    errors={'max_abs':float(np.max(np.abs(delta))),
        'max_normalized_by_gate':float(np.max(np.abs(delta)/allowed)),
        'max_relative_nonzero':float(np.max(np.abs(delta[target!=0]/target[target!=0]))),
        'dry_column_max_relative':dry_error,'different_zero_mask_count':int(np.count_nonzero((total==0)!=(target==0)))}
    if np.any(np.abs(delta)>allowed) or errors['different_zero_mask_count']:
        raise ValueError('opacity mapping failure '+json.dumps(errors))
    band_metrics=[]
    for b,(lo,hi) in enumerate(bounds):
        sl=slice(lo-1,hi)
        band_metrics.append({'band':b+1,'gpoint_bounds':[int(lo),int(hi)],
            'max_abs_error':float(np.max(np.abs(delta[:,sl]))),
            'max_normalized_error':float(np.max(np.abs(delta[:,sl])/allowed[:,sl])),
            'major_sum_tau':float(tau_major[:,sl].sum()),
            'minor_lower_sum_tau':float(partials['lower'][:,sl].sum()),
            'minor_upper_sum_tau':float(partials['upper'][:,sl].sum())})
    result={'schema':'udm37-bon-night-independent-opacity-result-v1','status':'PASS_SCOPED',
        'plan_sha256':sha(out/'plan.json'),'script_sha256':sha(__file__),'pins':pins,
        'scope':plan['scope'],'nonclaims':plan['nonclaims'],'errors':errors,
        'available_gases':plan['available_gases'],'reduced_gases':reduced,'flavors_Fortran':[list(x) for x in flavors],
        'jtemp_Fortran':jt.tolist(),'jpress_Fortran':jp.tolist(),'atmosphere_Fortran':(atmosphere+1).tolist(),
        'top_at_1':top_at_1,'minor_loader_and_contributions':metadata,'band_metrics':band_metrics,
        'tau_major':tau_major.tolist(),'tau_minor_lower':partials['lower'].tolist(),
        'tau_minor_upper':partials['upper'].tolist(),'tau_total':total.tolist(),
        'tau_by_minor_identifier':{k:v.tolist() for k,v in by_identifier.items()},
        'component_sum_closure_max_abs':float(np.max(np.abs(tau_major+partials['lower']+partials['upper']-total))),
        'no_Rayleigh_table':True,'units':'Optical depth dimensionless; gas columns molecules/cm^2.'}
    (out/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':result['status'],'errors':errors,'intervals':[{k:x[k] for k in ['regime','retained_intervals','retained_contributors','layer_limits_Fortran']} for x in metadata],'result_sha256':sha(out/'result.json')}))

if __name__=='__main__':main()
