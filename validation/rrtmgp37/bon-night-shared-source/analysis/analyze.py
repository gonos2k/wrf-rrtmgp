"""Held-column Planck-envelope and layer-face fraction counterfactuals."""
from pathlib import Path
import hashlib,importlib.util,json,math,sys
import numpy as np
from scipy.special import roots_jacobi

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);obj=importlib.util.module_from_spec(spec)
    sys.modules[name]=obj;spec.loader.exec_module(obj);return obj

def main():
    out=Path(__file__).resolve().parent
    if (out/'result.json').exists():raise ValueError('refuse overwrite')
    plan=json.loads((out/'plan.json').read_text());pins=plan['pins']
    for name,pin in pins.items():
        if sha(pin['path'])!=pin['sha256'] or Path(pin['path']).stat().st_size!=pin['bytes']:
            raise ValueError('changed pin '+name)
    a=load('source_parser',pins['angular_helper']['path'])
    l=load('source_legacy_parser',pins['legacy_helper']['path'])
    e=load('source_emission',pins['common_angle_helper']['path'])
    pkt=l.read_packet(Path(pins['packet']['path']))
    def f(stage,name):return pkt['fields'][(stage,name)].array()
    _,inp=a.read_sections(Path(pins['input']['path']))
    _,gp=a.read_sections(Path(pins['gp_result']['path']))
    _,src=a.read_sections(Path(pins['gp_source']['path']))
    fracdoc=json.loads(Path(pins['independent_pfrac']['path']).read_text())
    blackbody=json.loads(Path(pins['independent_Planck']['path']).read_text())
    prior=json.loads(Path(pins['common_angle_result']['path']).read_text())
    for doc,key in [(fracdoc,'held_input'),(blackbody,'input')]:
        if doc['pins'][key]['sha256']!=pins['input']['sha256']:raise ValueError('input provenance join')
    if fracdoc['pins']['production_coefficients']['sha256']!=blackbody['pins']['coefficients']['sha256']:
        raise ValueError('coefficient provenance join')
    state_t=np.concatenate((inp['TLAY'][0],inp['TLEV'][0],inp['TSFC'][0]))
    if len(state_t)!=92:raise ValueError('temperature ordering')
    for name in ('MCICA_MASK','RRTMG_INPUT_CLOUD_MASK'):
        if np.any(f('CLOUD',name)):raise ValueError('legacy optical clear only')
    gtau=gp['TOTAL_TAU'][0]
    if not np.array_equal(gtau,gp['GAS_TAU_RAW'][0]) or not np.array_equal(gtau,gp['GAS_TAU'][0]):
        raise ValueError('GP transported opacity differs from gas-only opacity')
    if np.any(gp['DN'][0,-1]) or np.any(f('GAS','RTE_BAND_DN_NATIVE')[:,-1]):
        raise ValueError('nonzero incident TOA')
    otau=f('GAS','TAUTOTAL_GAS_PLUS_AEROSOL_CLOUD_EXCLUDED').T
    pf=np.asarray(fracdoc['independent_pfrac'],dtype=float)
    if pf.shape!=(45,128) or np.any(pf<0):raise ValueError('GP fraction shape/range')
    lower_pf=np.vstack((pf[:1],np.sqrt(pf[:-1]*pf[1:])))
    oldmap=f('CLOUD','GPOINT_TO_BAND').astype(int);of=f('GAS','RTE_PLANCK_FRACTIONS').T
    bounds=src['BAND_LIMITS_GPOINT'][:,:,0].astype(int)
    wave=src['BAND_LIMITS_WAVENUMBER'][:,:,0]
    oldwave=np.array([f('CLOUD','BAND_WAVENUM_LO'),f('CLOUD','BAND_WAVENUM_HI')])
    if not np.array_equal(oldwave[:,2:13],wave[:,2:13]):raise ValueError('common edges')
    width=f('GAS','RTE_DELWAVE');scale=width*float(f('GAS','RTE_WTDIFF').item())*float(f('GAS','RTE_FLUXFAC').item())/math.pi
    matrices=[];rows=[];source_error=0.;fraction_sums=[]
    for row in blackbody['bands']:
        b=row['band']-1
        if not 2<=b<13 or not np.array_equal(np.asarray(row['temperature_K']),state_t):raise ValueError('shared Planck ordering/band')
        if not np.array_equal(np.asarray(row['limits_cm_inverse']),wave[:,b]):raise ValueError('shared Planck edges')
        si=np.asarray(row['SI_direct_band_radiance']);bg=np.asarray(row['GP_LUT_band_radiance'])
        if si.shape!=(92,) or np.any(si<=0):raise ValueError('SI source envelope')
        lo,hi=bounds[:,b];s=slice(lo-1,hi);m=oldmap==b+1
        # Own gpoint arrays never exchange places or normalize fraction sums.
        ogl=f('GAS','RTE_PLANCK_LAYER_NATIVE')[b,:,None]*scale[b]*of[:,m]
        ogd=f('GAS','RTE_PLANCK_LEVEL_NATIVE')[b,:-1,None]*scale[b]*of[:,m]
        ggl=bg[:45,None]*pf[:,s];ggd=bg[45:90,None]*lower_pf[:,s]
        source_error=max(source_error,float(np.max(np.abs(ggl-src['SOURCE_LAYER'][0,:,s]))),
                         float(np.max(np.abs(ggd-src['SOURCE_LEVEL'][0,:-1,s]))))
        common_old_l=si[:45,None]*of[:,m];common_old_d=si[45:90,None]*of[:,m]
        common_gp_l=si[:45,None]*pf[:,s];common_gp_geo=si[45:90,None]*lower_pf[:,s]
        common_gp_local=si[45:90,None]*pf[:,s]
        cases=[((otau[:,m],ogl,ogd),(gtau[:,s],ggl,ggd)),
               ((otau[:,m],common_old_l,common_old_d),(gtau[:,s],common_gp_l,common_gp_geo)),
               ((otau[:,m],common_old_l,common_old_d),(gtau[:,s],common_gp_l,common_gp_local)),
               ((otau[:,m],common_old_l,common_old_l),(gtau[:,s],common_gp_l,common_gp_l))]
        matrices.append(cases);rows.append(row['band'])
        fraction_sums.append((of[:,m].sum(axis=1),pf[:,s].sum(axis=1)))
    if rows!=list(range(3,14)) or source_error>plan['source_reconstruction_tolerance']:raise ValueError('source reconstruction')
    previous=None;convergence=[];final=None
    for order in plan['quadrature_orders']:
        x,w=roots_jacobi(order,0,1);mus=(x+1.)/2.;weights=w/2.
        value=np.zeros((4,2,11,45))
        for bi,cases in enumerate(matrices):
            for mu,weight in zip(mus,weights):
                for pol,pair in enumerate(cases):
                    for eng,case in enumerate(pair):value[pol,eng,bi]+=weight*e.emission(float(mu),*case)
        if previous is None:change=None
        else:
            delta=value-previous
            change={'emitters':float(np.max(np.abs(delta))),
                'bands':float(np.max(np.abs(delta.sum(axis=3)))),
                'common_total':float(np.max(np.abs(delta.sum(axis=(2,3)))))}
        convergence.append({'order':order,'weights_sum':float(weights.sum()),'successive_max_abs_Wm2':change})
        if change is not None and max(change.values())<=plan['quadrature_tolerance_Wm2']:final=value;break
        previous=value
    if final is None:raise ValueError('quadrature did not converge')
    old_reference=np.array([r['legacy_integral_emitter_contribution_Wm2'] for r in prior['bands'][2:13]])
    gp_reference=np.array([r['GP_integral_emitter_contribution_Wm2'] for r in prior['bands'][2:13]])
    reproduction_error=max(float(np.max(np.abs(final[0,0]-old_reference))),float(np.max(np.abs(final[0,1]-gp_reference))))
    if reproduction_error>plan['closure_tolerance_Wm2']:raise ValueError('prior emitter reference')
    if not np.array_equal(final[1,0],final[2,0]):raise ValueError('unchanged legacy face policy')
    bottom_face_delta=final[1,1,:,0]-final[2,1,:,0]
    if np.any(bottom_face_delta!=0):raise ValueError('surface-layer face unexpectedly changes')
    contrast=final[:,1]-final[:,0];band_delta=contrast.sum(axis=2);totals=band_delta.sum(axis=1)
    pieces={'native_envelope_minus_shared_SI':totals[0]-totals[1],
            'native_face_policy_minus_both_layer_local':totals[1]-totals[2],
            'shared_SI_layer_local_residual':totals[2]}
    if abs(sum(pieces.values())-totals[0])>plan['closure_tolerance_Wm2']:raise ValueError('telescoping closure')
    profiles=[]
    for pol,name in enumerate(plan['policies']):
        profiles.append({'policy':name,'legacy_surface_DN_Wm2':float(final[pol,0].sum()),
            'GP_surface_DN_Wm2':float(final[pol,1].sum()),'delta_GP_minus_legacy_Wm2':float(totals[pol]),
            'by_band_delta_Wm2':band_delta[pol].tolist(),
            'legacy_emitter_contributions_Wm2':final[pol,0].tolist(),
            'GP_emitter_contributions_Wm2':final[pol,1].tolist(),
            'emitter_delta_Wm2':contrast[pol].sum(axis=0).tolist()})
    # Bound only: no fractions or transport inputs are rescaled. In the
    # layer-local case each emitter is linear in its own layer's weights.
    # A hypothetical unit-sum rescaling changes c by c*(1-1/sum(weights)).
    weight_bounds=np.zeros((2,11,45))
    for bi,pair in enumerate(fraction_sums):
        for eng,sums in enumerate(pair):
            active=sums>0
            if np.any(final[2,eng,bi,~active]!=0):raise ValueError('zero weight sum has nonzero emitter')
            weight_bounds[eng,bi,active]=np.abs(final[2,eng,bi,active])*np.abs((sums[active]-1.)/sums[active])
    bound={'legacy_Wm2':float(weight_bounds[0].sum()),'GP_Wm2':float(weight_bounds[1].sum()),
           'engine_difference_Wm2':float(weight_bounds.sum()),'per_engine_band_layer_Wm2':weight_bounds.tolist(),
           'meaning':'Triangle bound on changing raw within-band weight sums to unit sum in the shared-SI/layer-local diagnostic only; no normalization is performed.'}
    result={'schema':'udm37-bon-night-shared-source-attribution-v1','status':'PASS_SCOPED',
        'plan_sha256':sha(out/'plan.json'),'script_sha256':sha(__file__),'pins':pins,
        'source_reconstruction_max_abs_radiance':source_error,'prior_emitter_reproduction_max_abs_Wm2':reproduction_error,
        'convergence':convergence,'common_bands':rows,'policies':profiles,
        'three_term_shared_angle_attribution_Wm2':{k:float(v) for k,v in pieces.items()},
        'linear_weight_sum_effect_upper_bound':bound,
        'surface_layer_face_policy_delta_exact_zero':bool(np.all(bottom_face_delta==0)),
        'fraction_sums_unchanged':True,'scope':plan['scope'],'limitations':plan['limitations'],
        'new_WRF_forecasts':0,'new_builds':0,'new_compiled_RTE_or_replays':0,'new_SI_integrations':0}
    for pin in pins.values():
        if sha(pin['path'])!=pin['sha256']:raise ValueError('post-run changed pin')
    (out/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':result['status'],'three_term_attribution_Wm2':result['three_term_shared_angle_attribution_Wm2'],
        'policy_delta_Wm2':[p['delta_GP_minus_legacy_Wm2'] for p in profiles],'result_sha256':sha(out/'result.json')}))

if __name__=='__main__':main()
