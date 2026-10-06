"""Compare engine-native band sources/fluxes; never pair correlated-k points."""
from pathlib import Path
import hashlib, importlib.util, json, math, sys
import numpy as np
from scipy.special import roots_jacobi

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec); sys.modules[name]=mod
    spec.loader.exec_module(mod); return mod
def metrics(actual, baseline):
    delta=np.asarray(actual)-np.asarray(baseline)
    return {'max_abs':float(np.max(np.abs(delta))), 'rms':float(np.sqrt(np.mean(delta*delta))),
            'delta':delta.tolist()}

def main():
    out=Path(__file__).resolve().parent
    if (out/'result.json').exists(): raise ValueError('refusing result overwrite')
    plan=json.loads((out/'plan.json').read_text()); pins=plan['pins']
    for pin in pins.values():
        if sha(pin['path'])!=pin['sha256']: raise ValueError('changed pin '+pin['path'])
    a=module('angular',pins['angular_helper']['path'])
    legacy=module('legacy',pins['legacy_helper']['path'])
    packet=legacy.read_packet(Path(pins['packet']['path']))
    _,inp=a.read_sections(Path(pins['input']['path']))
    _,src=a.read_sections(Path(pins['gp_source']['path']))
    _,res=a.read_sections(Path(pins['gp_result']['path']))
    def field(stage,name): return packet['fields'][(stage,name)].array()
    for name,gpname in [('PLAY','PLAY'),('PLEV','PLEV'),('TLAY','TLAY'),('TLEV','TLEV'),('TSFC','TSFC'),('SOLVER_SEMISS','EMIS')]:
        if not np.array_equal(field('INPUT',name),inp[gpname].reshape(-1)): raise ValueError('state mismatch '+name)
    for name in ('MCICA_MASK','RRTMG_INPUT_CLOUD_MASK'):
        if np.any(field('CLOUD',name)): raise ValueError('clear-only scope')
    oldmap=field('CLOUD','GPOINT_TO_BAND').astype(int)
    bounds=src['BAND_LIMITS_GPOINT'][:,:,0].astype(int)
    oldedges=np.array([field('CLOUD','BAND_WAVENUM_LO'),field('CLOUD','BAND_WAVENUM_HI')])
    gpedges=src['BAND_LIMITS_WAVENUMBER'][:,:,0]
    if not np.array_equal(oldedges[:,2:13],gpedges[:,2:13]): raise ValueError('common edges mismatch')
    fractions=field('GAS','RTE_PLANCK_FRACTIONS')
    width=field('GAS','RTE_DELWAVE')
    fluxfac=float(field('GAS','RTE_FLUXFAC').item())
    weight=float(field('GAS','RTE_WTDIFF').item())
    if weight!=0.5: raise ValueError('unsupported weight')
    unit_factor=width*weight*fluxfac/math.pi
    oldlay=field('GAS','RTE_PLANCK_LAYER_NATIVE')
    oldlev=field('GAS','RTE_PLANCK_LEVEL_NATIVE')
    oldsurf=field('GAS','RTE_PLANCK_SURFACE_NATIVE')
    oldup=field('GAS','RTE_BAND_UP_NATIVE')*width[:,None]*fluxfac
    olddn=field('GAS','RTE_BAND_DN_NATIVE')*width[:,None]*fluxfac
    tau=res['TOTAL_TAU'][0]; lay=src['SOURCE_LAYER'][0]; lev=src['SOURCE_LEVEL'][0]
    surf=src['SOURCE_SURFACE'][0,0]; emis=inp['EMIS'][0]
    if tau.shape!=(45,128) or fractions.shape!=(140,45): raise ValueError('shape mismatch')
    slices=[slice(lo-1,hi) for lo,hi in bounds.T]
    if not np.array_equal(np.concatenate([np.arange(128)[s] for s in slices]),np.arange(128)): raise ValueError('bad gpoint coverage')
    def calc(nodes,weights):
        up=np.zeros((16,46)); dn=np.zeros_like(up)
        for b,s in enumerate(slices):
            for mu,w in zip(nodes,weights):
                u,d=a.transfer(float(mu),tau[:,s],lay[:,s],lev[:,s],surf[s],np.full(s.stop-s.start,emis[b]))
                up[b]+=w*u; dn[b]+=w*d
        return up,dn
    gpup,gpdn=calc(*a.POLICIES[1])
    reproduction={}
    for name,arr in [('UP',gpup),('DN',gpdn)]:
        error=float(np.max(np.abs(arr.sum(axis=0)-res[name][0,:,0])))
        if error>1e-10: raise ValueError('GP broadband mismatch '+name)
        reproduction[name]=error
    # New band-specific convergence check, rather than assuming broadband convergence.
    previous=None; convergence=[]; integral=None
    for order in plan['quadrature_orders']:
        x,w=roots_jacobi(order,0,1); value=calc((x+1)/2,w/2)
        error=None if previous is None else max(float(np.max(np.abs(v-p))) for v,p in zip(value,previous))
        convergence.append({'order':order,'weights_sum':float((w/2).sum()),'max_abs_all_band_UP_DN_change_Wm2':error})
        if error is not None and error<=1e-9: integral=value; break
        previous=value
    if integral is None: raise ValueError('band quadrature did not converge')
    bands=[]
    for b in range(16):
        s=slices[b]; mask=oldmap==b+1; fsum=fractions[mask].sum(axis=0)
        ls=oldlay[b]*fsum*unit_factor[b]
        ld=oldlev[b,:-1]*fsum*unit_factor[b]
        lu=oldlev[b,1:]*fsum*unit_factor[b]
        ss=float(oldsurf[b]*fsum[0]*unit_factor[b])
        gl=lay[:,s].sum(axis=1); ge=lev[:,s].sum(axis=1)
        gs=float((surf[s]*emis[b]).sum())
        band={'band':b+1,'paired_exact_physical_edges':2<=b<13,
              'legacy_edges_cm-1':oldedges[:,b].tolist(),'gp_edges_cm-1':gpedges[:,b].tolist(),
              'legacy_fraction_sum_min_max':[float(fsum.min()),float(fsum.max())],
              'legacy_UP_Wm2':oldup[b].tolist(),'legacy_DN_Wm2':olddn[b].tolist(),
              'gp_policy1_UP_Wm2':gpup[b].tolist(),'gp_policy1_DN_Wm2':gpdn[b].tolist(),
              'gp_integral_UP_Wm2':integral[0][b].tolist(),'gp_integral_DN_Wm2':integral[1][b].tolist(),
              'legacy_layer_source_Wm2sr':ls.tolist(),'legacy_layer_lower_face_source_Wm2sr':ld.tolist(),
              'legacy_layer_upper_face_source_Wm2sr':lu.tolist(),'legacy_emitted_surface_source_Wm2sr':ss,
              'gp_layer_source_Wm2sr':gl.tolist(),'gp_level_source_Wm2sr':ge.tolist(),
              'gp_emitted_surface_source_Wm2sr':gs}
        if 2<=b<13:
            band['comparison']={'layer_source':metrics(gl,ls),'lower_face_source':metrics(ge[:-1],ld),
                'upper_face_source':metrics(ge[1:],lu),'surface_emitted_source_delta_Wm2sr':gs-ss,
                'surface_DN_policy1_delta_Wm2':float(gpdn[b,0]-olddn[b,0]),
                'surface_DN_integral_delta_Wm2':float(integral[1][b,0]-olddn[b,0]),
                'TOA_UP_policy1_delta_Wm2':float(gpup[b,-1]-oldup[b,-1]),
                'TOA_UP_integral_delta_Wm2':float(integral[0][b,-1]-oldup[b,-1])}
        bands.append(band)
    def totals(indices):
        return {'legacy_surface_DN_Wm2':float(olddn[indices,0].sum()),
                'gp_policy1_surface_DN_Wm2':float(gpdn[indices,0].sum()),
                'gp_integral_surface_DN_Wm2':float(integral[1][indices,0].sum()),
                'legacy_TOA_UP_Wm2':float(oldup[indices,-1].sum()),
                'gp_policy1_TOA_UP_Wm2':float(gpup[indices,-1].sum()),
                'gp_integral_TOA_UP_Wm2':float(integral[0][indices,-1].sum())}
    result={'schema':'BON_COMMON_BAND_SOURCE_MATH_V1','status':'PASS_SCOPED_COMMON_BAND_COMPARISON',
            'plan_sha256':sha(out/'plan.json'),'gp_same_engine_broadband_reproduction_max_abs_Wm2':reproduction,
            'quadrature_convergence':convergence,'bands':bands,
            'totals_common_3_13':totals(list(range(2,13))),
            'totals_unpaired_engine_native':totals([0,1,13,14,15]),
            'totals_all_engine_native':totals(list(range(16))),
            'legacy_conversion':{'WTDIFF':weight,'FLUXFAC':fluxfac,'source_formula':'native Planck * fraction sum * DELWAVE * WTDIFF * FLUXFAC / mathematical pi',
                'native_band_flux_formula':'native band flux * DELWAVE * FLUXFAC; WTDIFF already applied',
                'relative_rounding_vs_10000_factor':weight*fluxfac/math.pi/10000-1},
            'limits':plan['limits'],'new_WRF_calls':0,'new_builds':0,'new_RTE_executable_calls':0}
    for pin in pins.values():
        if sha(pin['path'])!=pin['sha256']: raise ValueError('post-run changed pin')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'common':result['totals_common_3_13'],
                     'all':result['totals_all_engine_native'],'order':order,'result_sha256':sha(out/'result.json')}))

if __name__=='__main__': main()
