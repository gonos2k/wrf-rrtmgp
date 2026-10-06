"""Own-spectrum LW emission/angle attribution; no cross-engine gpoint pairing."""
from pathlib import Path
import hashlib, importlib.util, json, math, sys
import numpy as np
from scipy.special import roots_jacobi

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name,p):
    spec=importlib.util.spec_from_file_location(name,p)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod
    spec.loader.exec_module(mod);return mod

def emission(mu,tau,lay,lower):
    """Surface downwelling contribution from each emitter, bottom-first order."""
    x=tau/mu;tr=np.exp(-x);om=-np.expm1(-x)
    fact=np.empty_like(x);large=x>np.finfo(float).eps**.25
    fact[large]=om[large]/x[large]-tr[large]
    fact[~large]=x[~large]*(.5+x[~large]*(-1./3.+x[~large]/8.))
    src=om*lower+2.*fact*(lay-lower)
    below=np.vstack((np.zeros((1,tau.shape[1])),np.cumsum(tau[:-1],axis=0)))
    return math.pi*np.sum(src*np.exp(-below/mu),axis=1)

def main():
    out=Path(__file__).resolve().parent
    if (out/'result.json').exists():raise ValueError('refuse result overwrite')
    plan=json.loads((out/'plan.json').read_text());pins=plan['pins']
    for pin in pins.values():
        if sha(pin['path'])!=pin['sha256'] or Path(pin['path']).stat().st_size!=pin['bytes']:
            raise ValueError('changed pin '+pin['path'])
    a=load('angle_parser',pins['angular_helper']['path'])
    l=load('legacy_parser',pins['legacy_helper']['path'])
    packet=l.read_packet(Path(pins['packet']['path']))
    def field(stage,name):return packet['fields'][(stage,name)].array()
    _,inp=a.read_sections(Path(pins['input']['path']))
    _,gp=a.read_sections(Path(pins['gp_result']['path']))
    _,gs=a.read_sections(Path(pins['gp_source']['path']))
    common=json.loads(Path(pins['common_result']['path']).read_text())
    for old,new in [('PLAY','PLAY'),('PLEV','PLEV'),('TLAY','TLAY'),('TLEV','TLEV')]:
        if not np.array_equal(field('INPUT',old),inp[new].reshape(-1)):raise ValueError('state mismatch '+old)
    for name in ('MCICA_MASK','RRTMG_INPUT_CLOUD_MASK'):
        if np.any(field('CLOUD',name)):raise ValueError('clear only')
    oldmap=field('CLOUD','GPOINT_TO_BAND').astype(int)
    bounds=gs['BAND_LIMITS_GPOINT'][:,:,0].astype(int)
    oldedges=np.array([field('CLOUD','BAND_WAVENUM_LO'),field('CLOUD','BAND_WAVENUM_HI')])
    newedges=gs['BAND_LIMITS_WAVENUMBER'][:,:,0]
    if not np.array_equal(oldedges[:,2:13],newedges[:,2:13]):raise ValueError('common physical edges mismatch')
    frac=field('GAS','RTE_PLANCK_FRACTIONS')
    otau=field('GAS','TAUTOTAL_GAS_PLUS_AEROSOL_CLOUD_EXCLUDED').T
    gtau=gp['TOTAL_TAU'][0]
    if not np.array_equal(gtau,gp['GAS_TAU_RAW'][0]) or not np.array_equal(gtau,gp['GAS_TAU'][0]):
        raise ValueError('captured GP assembled opacity is not exactly gas only')
    width=field('GAS','RTE_DELWAVE');fluxfac=float(field('GAS','RTE_FLUXFAC').item())
    weight=float(field('GAS','RTE_WTDIFF').item())
    if weight!=.5 or otau.shape!=(45,140) or gtau.shape!=(45,128):raise ValueError('unsupported shape/unit')
    scale=width*weight*fluxfac/math.pi
    secdiff=field('GAS','RTE_SECDIFF')
    olddn=field('GAS','RTE_BAND_DN_NATIVE')*width[:,None]*fluxfac
    cases=[];oldnative=[];gp_native=[];gp_check=[]
    for b,(lo,hi) in enumerate(bounds.T):
        oldmask=oldmap==b+1;s=slice(lo-1,hi)
        of=frac[oldmask].T
        ol=field('GAS','RTE_PLANCK_LAYER_NATIVE')[b,:,None]*scale[b]*of
        od=field('GAS','RTE_PLANCK_LEVEL_NATIVE')[b,:-1,None]*scale[b]*of
        gl=gs['SOURCE_LAYER'][0,:,s];gd=gs['SOURCE_LEVEL'][0,:-1,s]
        cases.append(((otau[:,oldmask],ol,od),(gtau[:,s],gl,gd)))
        oldnative.append(emission(1./secdiff[b],*cases[-1][0]))
        gp_native.append(emission(a.POLICIES[1][0][0],*cases[-1][1]))
        _,d=a.transfer(a.POLICIES[1][0][0],gtau[:,s],gl,gs['SOURCE_LEVEL'][0,:,s],
                       gs['SOURCE_SURFACE'][0,0,s],np.full(hi-lo+1,inp['EMIS'][0,b]))
        gp_check.append(abs(float(np.sum(gp_native[-1]))-float(d[0])))
    oldnative=np.array(oldnative);gp_native=np.array(gp_native)
    gp_saved=np.array([x['gp_policy1_DN_Wm2'][0] for x in common['bands']])
    err=max(float(np.max(np.abs(gp_native.sum(axis=1)-gp_saved))),max(gp_check))
    if err>plan['closure_tolerance_Wm2']:raise ValueError('GP emitter decomposition closure '+str(err))
    if float(np.min(gtau))<0 or float(np.min(otau))<0:raise ValueError('negative tau')
    # Meaningful analytic limiting control, independent of the saved column.
    z=np.zeros((2,3));ones=np.ones((2,3))
    if np.any(emission(.6,z,ones,ones)!=0):raise ValueError('transparent control')
    iso=emission(.6,ones,ones,ones).sum()
    if abs(iso-3.*math.pi*(-math.expm1(-2./.6)))>1e-12:raise ValueError('isothermal slab control')
    previous=None;convergence=[];final=None
    for order in plan['quadrature_orders']:
        x,w=roots_jacobi(order,0,1);mu=(x+1.)/2.;w=w/2.
        value=np.zeros((2,16,45))
        for b,pair in enumerate(cases):
            for direction,angle_weight in zip(mu,w):
                for engine,case in enumerate(pair):value[engine,b]+=angle_weight*emission(float(direction),*case)
        if previous is None:
            changes=None
        else:
            delta=value-previous
            changes={'emitters':float(np.max(np.abs(delta))),
                'bands':float(np.max(np.abs(delta.sum(axis=2)))),
                'common_3_13':float(np.max(np.abs(delta[:,2:13].sum(axis=(1,2))))),
                'all_engine_native':float(np.max(np.abs(delta.sum(axis=(1,2)))))}
        convergence.append({'order':order,'weights_sum':float(w.sum()),'successive_max_abs_Wm2':changes})
        if changes is not None and max(changes.values())<=plan['quadrature_tolerance_Wm2']:final=value;break
        previous=value
    if final is None:raise ValueError('emitter quadrature did not converge')
    oldint=final[0].sum(axis=1);gpint=final[1].sum(axis=1)
    oldexact=oldnative.sum(axis=1);gpactual=gp_native.sum(axis=1)
    prior_gp=np.array([b['gp_integral_DN_Wm2'][0] for b in common['bands']])
    if np.max(np.abs(gpint-prior_gp))>plan['closure_tolerance_Wm2']:raise ValueError('prior GP integral mismatch')
    terms={'GP_native_minus_integral':gpactual-gpint,
           'own_spectrum_common_angle_residual':gpint-oldint,
           'legacy_integral_minus_exact_native_angle':oldint-oldexact,
           'legacy_exact_minus_captured_approximation':oldexact-olddn[:,0]}
    closure=sum(terms.values())-(gpactual-olddn[:,0])
    if np.max(np.abs(closure))>plan['closure_tolerance_Wm2']:raise ValueError('attribution closure')
    rows=[]
    for b in range(16):
        rows.append({'band':b+1,'exact_common_physical_edges':2<=b<13,
            'legacy_edges_cm-1':oldedges[:,b].tolist(),'GP_edges_cm-1':newedges[:,b].tolist(),
            'legacy_captured_DN':float(olddn[b,0]),'legacy_exact_native_angle_DN':float(oldexact[b]),
            'legacy_integral_DN':float(oldint[b]),'GP_native_DN':float(gpactual[b]),'GP_integral_DN':float(gpint[b]),
            'legacy_native_mu':float(1./secdiff[b]),'terms':{k:float(v[b]) for k,v in terms.items()},
            'legacy_integral_emitter_contribution_Wm2':final[0,b].tolist(),
            'GP_integral_emitter_contribution_Wm2':final[1,b].tolist(),
            'own_spectrum_emitter_delta_Wm2':(final[1,b]-final[0,b]).tolist()})
    def totals(indices):
        return {'terms':{k:float(v[indices].sum()) for k,v in terms.items()},
            'captured_engine_difference_Wm2':float((gpactual-olddn[:,0])[indices].sum()),
            'legacy_integral_DN_Wm2':float(oldint[indices].sum()),'GP_integral_DN_Wm2':float(gpint[indices].sum()),
            'own_spectrum_emitter_delta_Wm2':(final[1,indices].sum(axis=0)-final[0,indices].sum(axis=0)).tolist()}
    result={'schema':'udm37-bon-night-common-angle-attribution-v1','status':'PASS_SCOPED',
        'plan_sha256':sha(out/'plan.json'),'script_sha256':sha(__file__),'pins':pins,
        'GP_native_emitter_closure_max_abs_Wm2':err,'prior_GP_integral_max_abs_Wm2':float(np.max(np.abs(gpint-prior_gp))),
        'attribution_closure_max_abs_Wm2':float(np.max(np.abs(closure))),'convergence':convergence,
        'bands':rows,'common_bands_3_13':totals(list(range(2,13))),
        'all_engine_native_bands_unpaired_edges':totals(list(range(16))),
        'scope':plan['scope'],'limitations':plan['limitations'],
        'new_WRF_forecasts':0,'new_builds':0,'new_compiled_RTE_or_replays':0}
    for pin in pins.values():
        if sha(pin['path'])!=pin['sha256']:raise ValueError('post-run changed pin')
    (out/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':result['status'],'common_terms':result['common_bands_3_13']['terms'],
                      'all_terms':result['all_engine_native_bands_unpaired_edges']['terms'],'result_sha256':sha(out/'result.json')}))

if __name__=='__main__':main()
