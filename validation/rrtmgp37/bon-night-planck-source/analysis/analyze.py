"""Independent finite-band SI Planck integrals; no radiation transport calls."""
from pathlib import Path
import hashlib, importlib.util, json, math, sys
import numpy as np
from netCDF4 import Dataset
from scipy.special import roots_legendre

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj

def metric(actual, reference):
    actual, reference = np.asarray(actual), np.asarray(reference)
    delta = actual-reference
    return {'max_abs': float(np.max(np.abs(delta))),
            'max_relative': float(np.max(np.abs(delta/reference))),
            'delta': delta.tolist()}

def interpolate(table, temperatures, offset, delta):
    # Exact production interpolate1D index/fraction convention (one -> zero based).
    val0 = (np.asarray(temperatures)-offset)/delta
    integers = np.trunc(val0).astype(int)
    fraction = val0-integers
    index = np.minimum(table.shape[1]-2, np.maximum(0, integers))
    return table[:,index] + fraction[None,:]*(table[:,index+1]-table[:,index])

def interpolate_legacy(table, temperatures):
    # RRTMG setcoef clamps the integer index BEFORE calculating its fraction.
    coordinate = np.asarray(temperatures)-159.
    index = np.minimum(180, np.maximum(1, np.trunc(coordinate).astype(int)))
    fraction = coordinate-index
    return table[:,index-1] + fraction[None,:]*(table[:,index]-table[:,index-1])

def main():
    out = Path(__file__).resolve().parent
    if (out/'result.json').exists():
        raise ValueError('refuse overwrite of prior calculation')
    plan = json.loads((out/'plan.json').read_text()); pins = plan['pins']
    for key, pin in pins.items():
        if sha(pin['path']) != pin['sha256']:
            raise ValueError('changed pin '+key)
    a = module('planck_angular_parser', pins['angular_helper']['path'])
    legacy = module('planck_legacy_parser', pins['legacy_helper']['path'])
    packet = legacy.read_packet(Path(pins['packet']['path']))
    _, inp = a.read_sections(Path(pins['input']['path']))
    _, src = a.read_sections(Path(pins['gp_source']['path']))
    def field(stage, name):
        return packet['fields'][(stage,name)].array()
    for name, gpname in [('TLAY','TLAY'),('TLEV','TLEV'),('TSFC','TSFC'),('SOLVER_SEMISS','EMIS')]:
        if not np.array_equal(field('INPUT',name), inp[gpname].reshape(-1)):
            raise ValueError('state mismatch '+name)
    tl = inp['TLAY'][0]; te = inp['TLEV'][0]; ts = inp['TSFC'].reshape(-1)
    if (tl.shape, te.shape, ts.shape) != ((45,), (46,), (1,)):
        raise ValueError('unexpected temperature shapes')
    temperatures = np.concatenate((tl,te,ts))
    if np.any((temperatures < 160) | (temperatures > 340)):
        raise ValueError('outside legacy nonextrapolating temperature grid')
    bands = np.asarray(plan['common_bands'])-1
    edges = src['BAND_LIMITS_WAVENUMBER'][:,:,0].T
    oldedges = np.array([field('CLOUD','BAND_WAVENUM_LO'),field('CLOUD','BAND_WAVENUM_HI')]).T
    if not np.array_equal(edges[bands],oldedges[bands]):
        raise ValueError('unlike physical bands')
    bounds = src['BAND_LIMITS_GPOINT'][:,:,0].T.astype(int)
    if not np.array_equal(np.concatenate([np.arange(lo-1,hi) for lo,hi in bounds]),np.arange(128)):
        raise ValueError('gpoint coverage')
    with Dataset(pins['coefficients']['path']) as ds:
        def values(name):
            raw=ds[name][:]
            if np.any(np.ma.getmaskarray(raw)):
                raise ValueError('masked coefficient '+name)
            return np.asarray(raw,dtype=float)
        table = values('totplnk')
        tref = values('temp_ref')
        coordinate = values('temperature_Planck')
        if table.shape != (16,196) or not np.array_equal(coordinate,np.arange(196)):
            raise ValueError('unexpected coefficient grid')
        if not np.array_equal(values('bnd_limits_wavenumber'),edges):
            raise ValueError('sidecar/LUT edges differ')
        if not np.array_equal(values('bnd_limits_gpt'),bounds):
            raise ValueError('sidecar/LUT bounds differ')
        units={name:ds[name].getncattr('units') if 'units' in ds[name].ncattrs() else None
               for name in ('totplnk','plank_fraction')}
    offset=float(tref[0]); delta=float((tref[-1]-tref[0])/(table.shape[1]-1))
    if (offset,delta,float(tref[-1])) != (160.,1.,355.):
        raise ValueError('unexpected physical Planck axis')
    grid = offset+delta*np.arange(table.shape[1])
    h,c,k = (plan['constants_SI'][key] for key in ('h','c','k'))
    prefactor = 2*h*c*c; exponent = h*c/k
    sigma = 2*math.pi**5*k**4/(15*h**3*c**2)

    def integral(order, T, first=prefactor, second=exponent, cm_units=False):
        x,w = roots_legendre(order)
        limits=edges[bands] if cm_units else edges[bands]*100.
        wave=(limits[:,1,None]+limits[:,0,None])/2 + (limits[:,1,None]-limits[:,0,None])/2*x
        width=(limits[:,1]-limits[:,0])/2
        radiance=first*wave[:,:,None]**3/np.expm1(second*wave[:,:,None]/T[None,None,:])
        return np.einsum('bnt,n,b->bt',radiance,w,width)

    allT=np.concatenate((temperatures,grid))
    prior=None; convergence=[]
    for order in plan['quadrature_orders']:
        si=integral(order,allT)
        change=None if prior is None else float(np.max(np.abs(si-prior)))
        convergence.append({'order':order,'max_abs_radiance_change':change})
        prior=si
    if change is None or change>plan['convergence_max_abs_radiance']:
        raise ValueError('SI band quadrature not converged')
    direct=si[:,:92]; knots=si[:,92:]
    # Dimensionless full-spectrum control: truncation at x=80 is negligible.
    x,w=roots_legendre(plan['quadrature_orders'][-1]); x=(x+1)*40
    dimensionless=float(np.sum(w*40*x**3/np.expm1(x)))
    exact=math.pi**4/15
    rel=abs(dimensionless/exact-1)
    if rel>plan['stefan_boltzmann_max_relative']:
        raise ValueError('Stefan-Boltzmann integral control')
    gpraw=interpolate(table,temperatures,offset,delta)[bands]
    gpsamegrid=interpolate(knots,temperatures,offset,delta)
    oldraw=np.concatenate((field('GAS','RTE_PLANCK_LAYER_NATIVE'),
                           field('GAS','RTE_PLANCK_LEVEL_NATIVE'),
                           field('GAS','RTE_PLANCK_SURFACE_NATIVE')[:,None]),axis=1)[bands]
    emis=inp['EMIS'][0,bands]
    if np.any(emis<=0):
        raise ValueError('cannot unweight zero-emissivity surface')
    width=field('GAS','RTE_DELWAVE')[bands]
    if not np.array_equal(width,edges[bands,1]-edges[bands,0]):
        raise ValueError('legacy width mismatch')
    oldsi=oldraw*width[:,None]*1e4
    oldsi[:,-1]/=emis
    weight=float(field('GAS','RTE_WTDIFF').item())
    fluxfac=float(field('GAS','RTE_FLUXFAC').item())
    transport_factor=weight*fluxfac/(math.pi*1e4)
    oldtransport=oldsi*transport_factor
    oldgrid=np.arange(160.,341.)
    oldSIsamegrid=interpolate_legacy(integral(order,oldgrid),temperatures)
    # Source-declared cm radiation constants; values not fitted to saved data.
    legacy_formula=integral(order,oldgrid,1.191042722e-12,1.4387752,True)*1e4
    legacy_samegrid=interpolate_legacy(legacy_formula,temperatures)
    # Infer fractions from source values, ONLY for independent level/surface closure.
    raw_all=interpolate(table,temperatures,offset,delta)
    layer=src['SOURCE_LAYER'][0]; level=src['SOURCE_LEVEL'][0]
    surface=src['SOURCE_SURFACE'][0,0]
    inferred=np.empty_like(layer); inferred_sums=[]; level_errors=[]; surface_errors=[]
    oldmap=field('CLOUD','GPOINT_TO_BAND').astype(int)
    oldfrac=field('GAS','RTE_PLANCK_FRACTIONS')
    records=[]
    for pos,b in enumerate(bands):
        lo,hi=bounds[b]; sl=slice(lo-1,hi)
        fraction=layer[:,sl]/raw_all[b,:45,None]
        inferred[:,sl]=fraction
        predicted=np.empty_like(level[:,sl])
        predicted[0]=fraction[0]*raw_all[b,45]
        predicted[-1]=fraction[-1]*raw_all[b,90]
        predicted[1:-1]=np.sqrt(fraction[:-1]*fraction[1:])*raw_all[b,46:90,None]
        le=float(np.max(np.abs(predicted-level[:,sl])))
        se=float(np.max(np.abs(fraction[0]*raw_all[b,91]-surface[sl])))
        level_errors.append(le);surface_errors.append(se)
        if max(le,se)>plan['closure_max_abs']:
            raise ValueError('GP level/surface formula closure band '+str(b+1))
        fsum=fraction.sum(axis=1); inferred_sums.extend(fsum.tolist())
        records.append({'band':int(b+1),'limits_cm_inverse':edges[b].tolist(),
                        'temperature_K':temperatures.tolist(),
                        'SI_direct_band_radiance':direct[pos].tolist(),
                        'GP_LUT_band_radiance':gpraw[pos].tolist(),
                        'legacy_transport_equivalent_radiance_cm2_to_m2':oldsi[pos].tolist(),
                        'GP_minus_SI_direct':metric(gpraw[pos],direct[pos]),
                        'GP_minus_SI_same_grid':metric(gpraw[pos],gpsamegrid[pos]),
                        'legacy_minus_SI_direct':metric(oldsi[pos],direct[pos]),
                        'legacy_minus_SI_same_grid':metric(oldsi[pos],oldSIsamegrid[pos]),
                        'legacy_minus_declared_constants_same_grid':metric(oldsi[pos],legacy_samegrid[pos]),
                        'GP_inferred_fraction_sums':fsum.tolist(),
                        'legacy_saved_fraction_sums':oldfrac[oldmap==b+1].sum(axis=0).tolist(),
                        'GP_predicted_level_max_abs':le,'GP_predicted_surface_max_abs':se})
    def summary_diff(actual,ref):
        d=metric(actual,ref);d.pop('delta');return d
    result={'version':1,'plan_sha256':sha(out/'plan.json'),'script_sha256':sha(__file__),
            'scope':plan['scope'],'nonclaims':plan['nonclaims'],'pins':pins,
            'temperature_min_max_K':[float(temperatures.min()),float(temperatures.max())],
            'table_grid':{'physical_min_K':offset,'physical_max_K':float(tref[-1]),'delta_K':delta,
                          'stored_coordinate':'indices0..195, not temperature_K','units_attributes':units},
            'convergence':convergence,
            'Stefan_Boltzmann_control':{'dimensionless_numeric':dimensionless,'analytic_pi4_over15':exact,
                                       'max_relative':rel,'sigma_from_exact_SI':sigma},
            'legacy_transport_vs_cm2_factor':transport_factor,
            'summary':{'GP_vs_SI_direct':summary_diff(gpraw,direct),
                       'GP_vs_SI_same_grid':summary_diff(gpraw,gpsamegrid),
                       'GP_knots_vs_SI':summary_diff(table[bands],knots),
                       'legacy_vs_SI_direct':summary_diff(oldsi,direct),
                       'legacy_vs_SI_same_grid':summary_diff(oldsi,oldSIsamegrid),
                       'legacy_vs_declared_constants_same_grid':summary_diff(oldsi,legacy_samegrid),
                       'legacy_native_transport_vs_SI_direct':summary_diff(oldtransport,direct),
                       'GP_inferred_fraction_sum_min_max':[min(inferred_sums),max(inferred_sums)],
                       'GP_level_closure_max_abs':max(level_errors),'GP_surface_closure_max_abs':max(surface_errors)},
            'bands':records,
            'units':'Band-integrated radiance W m^-2 sr^-1; no RTE/WRF flux calculation.'}
    (out/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'result_sha256':sha(out/'result.json'),'summary':result['summary'],
                      'convergence':convergence,'Stefan_Boltzmann_control':result['Stefan_Boltzmann_control']}))

if __name__=='__main__':
    main()
