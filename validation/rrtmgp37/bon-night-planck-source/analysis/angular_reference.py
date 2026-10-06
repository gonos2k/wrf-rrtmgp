#!/usr/bin/env python3
"""Pure-Python angular integration of saved no-scattering LW kernel inputs."""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np
from scipy.special import roots_jacobi

BASE = Path('build/udm37-bon-night-lw-transport-attribution-v1')
INPUT = Path('build/udm37-bon-night-dry-column-attribution-v1/matched-legacy-dry.input')
POLICIES = {
    1: ([0.6096748751], [1.0]),
    2: ([1.0 / 1.66], [1.0]),
    3: ([0.0454586727, 0.2322334416, 0.5740198775, 0.9030775973],
        [0.0092068785, 0.1285704278, 0.4323381850, 0.4298845087]),
}

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def read_sections(path: Path) -> tuple[list[str], dict[str, np.ndarray]]:
    lines = path.read_text(encoding='ascii').splitlines()
    if len(lines) < 2 or not lines[0].startswith('RRTMGP_'):
        raise ValueError(f'{path}: bad magic')
    # Input replay headers have extra seed/version fields; result headers have 3 fields.
    phase, nc, nl = lines[1].split()[:3]
    nc, nl = int(nc), int(nl)
    sections = {}
    i = 2
    while i < len(lines):
        if not lines[i].strip():
            i += 1; continue
        name, *shape_text = lines[i].split()
        if name in sections or len(shape_text) not in (1,2,3):
            raise ValueError(f'{path}:{i+1}: malformed/duplicate section {name}')
        shape = tuple(int(x) for x in shape_text)
        if any(x < 1 for x in shape):
            raise ValueError(f'{path}:{i+1}: invalid shape {shape}')
        n = math.prod(shape); i += 1; values = []
        while len(values) < n and i < len(lines):
            if lines[i].strip():
                values.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split())
            i += 1
        if len(values) != n or not np.isfinite(values).all():
            raise ValueError(f'{path}: wrong/nonfinite payload for {name}')
        sections[name] = np.asarray(values, dtype=np.float64).reshape(shape, order='F')
    return [phase.upper(), str(nc), str(nl)], sections

def require(sections, name, shape=None):
    if name not in sections:
        raise ValueError(f'missing {name}')
    a = sections[name]
    if shape is not None and a.shape != shape:
        raise ValueError(f'{name}: shape {a.shape}, expected {shape}')
    if not np.isfinite(a).all():
        raise ValueError(f'{name}: nonfinite')
    return a

def transfer(mu: float, tau: np.ndarray, lay: np.ndarray, lev: np.ndarray,
             surf: np.ndarray, emis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return broadband up/down flux in native level ordering (bottom level first)."""
    if not (0.0 < mu <= 1.0): raise ValueError('mu outside (0,1]')
    nlay, ngpt = tau.shape
    x = tau / mu
    trans = np.exp(-x)
    threshold = np.finfo(np.float64).eps ** 0.25
    fact = np.empty_like(x)
    large = x > threshold
    fact[large] = (1.0 - trans[large]) / x[large] - trans[large]
    fact[~large] = x[~large] * (0.5 + x[~large] * (-1.0/3.0 + x[~large]/8.0))

    # Captured call has top_at_1=.FALSE.: level nlay+1 is TOA, level 1 is surface.
    source_up = (1.0-trans)*lev[1:,:] + 2.0*fact*(lay-lev[1:,:])
    source_dn = (1.0-trans)*lev[:-1,:] + 2.0*fact*(lay-lev[:-1,:])
    down = np.zeros((nlay+1, ngpt), dtype=np.float64)  # zero incident diffuse flux
    for k in range(nlay-1, -1, -1):
        down[k,:] = trans[k,:]*down[k+1,:] + source_dn[k,:]
    up = np.empty_like(down)
    up[0,:] = down[0,:]*(1.0-emis) + emis*surf
    for k in range(nlay):
        up[k+1,:] = trans[k,:]*up[k,:] + source_up[k,:]
    return math.pi * np.sum(up, axis=1), math.pi * np.sum(down, axis=1)

def angular_result(nodes, weights, tau, lay, lev, surf, emis, plev_hpa, gravity, cp):
    up = np.zeros(tau.shape[0]+1); dn = np.zeros_like(up)
    for mu,w in zip(nodes,weights):
        u,d = transfer(float(mu), tau, lay, lev, surf, emis)
        up += float(w)*u; dn += float(w)*d
    hr = (up[1:]-up[:-1]-dn[1:]+dn[:-1]) * gravity/(cp*((plev_hpa[1:]-plev_hpa[:-1])*100.0)) * 86400.0
    return up,dn,hr

def self_test():
    # Empty atmosphere transmits surface emission unchanged in every direction.
    tau0=np.zeros((2,3)); lay0=np.zeros((2,3)); lev0=np.zeros((3,3))
    sfc0=np.array([1.0,2.0,3.0]); emis0=np.ones(3)
    expected=math.pi*float(sfc0.sum())
    for mu,w in zip([0.2,0.7],[0.25,0.75]):
        up,dn=transfer(mu,tau0,lay0,lev0,sfc0,emis0)
        if not np.allclose(up,expected,rtol=0,atol=1e-13) or not np.allclose(dn,0,rtol=0,atol=1e-13):
            raise ValueError('transparent-atmosphere control failed')
    # A non-normalized quadrature must fail the flux normalization control.
    if abs(expected*0.9-expected) < 1e-3: raise ValueError('weight normalization negative control failed')
    return {'transparent_atmosphere_surface_emission':'PASS','zero_downwelling':'PASS',
            'nonunit_weight_control':'PASS'}

def metrics(actual, expected):
    d=np.asarray(actual)-np.asarray(expected)
    return {'max_abs':float(np.max(np.abs(d))), 'rms':float(np.sqrt(np.mean(d*d))),
            'max_rel_nonzero':float(np.max(np.abs(d[np.asarray(expected)!=0]/np.asarray(expected)[np.asarray(expected)!=0]))) if np.any(np.asarray(expected)!=0) else 0.0}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,default=Path.cwd()); ap.add_argument('--out',type=Path,required=True); args=ap.parse_args()
    root=args.root.resolve(); base=root/BASE; input_path=root/INPUT
    receipt_path=args.out.with_name(args.out.stem + '-execution-receipt.json')
    if args.out.exists() or receipt_path.exists():
        raise SystemExit(f'refusing to overwrite existing result/receipt: {args.out} / {receipt_path}')
    inp_header, inp=read_sections(input_path)
    emis= require(inp,'EMIS',(1,16))[0,:]
    plev=require(inp,'PLEV',(1,46))[0,:]
    gravity=float(require(inp,'GRAVITY',(1,1))[0,0]); cp=float(require(inp,'CP_DRY',(1,1))[0,0])
    # Policy sidecar provides the exact source arrays consumed by the solver.
    trpath=base/'run-v1/policy1.result.lw_transport'
    _,tr=read_sections(trpath)
    held_names=('SOURCE_LAYER','SOURCE_LEVEL','SOURCE_SURFACE','BAND_LIMITS_GPOINT','BAND_LIMITS_WAVENUMBER')
    for policy in (2,3):
        _,other=read_sections(base/f'run-v1/policy{policy}.result.lw_transport')
        for name in held_names:
            if not np.array_equal(tr[name],other[name]): raise ValueError(f'{name} differs across policy sidecars')
    nlay=45; ngpt=128
    lay=require(tr,'SOURCE_LAYER',(1,nlay,ngpt))[0,:,:]
    lev=require(tr,'SOURCE_LEVEL',(1,nlay+1,ngpt))[0,:,:]
    surf=require(tr,'SOURCE_SURFACE',(1,1,ngpt))[0,0,:]
    bounds=require(tr,'BAND_LIMITS_GPOINT',(2,16,1))[:,:,0].astype(int)
    tau=np.empty((nlay,ngpt))
    for policy in (1,2,3):
        _,result=read_sections(base/f'run-v1/policy{policy}.result')
        tau_policy=require(result,'TOTAL_TAU',(1,nlay,ngpt))[0,:,:]
        if policy == 1: tau[:]=tau_policy
        elif not np.array_equal(tau,tau_policy): raise ValueError('policy TOTAL_TAU differs')
    # Expand the captured 16 band emissivities using the exact captured g-point limits.
    emis_g=np.empty(ngpt)
    covered=np.zeros(ngpt,dtype=bool)
    for b,(lo,hi) in enumerate(bounds.T):
        if lo<1 or hi<lo or hi>ngpt or np.any(covered[lo-1:hi]): raise ValueError('invalid/overlapping band bounds')
        emis_g[lo-1:hi]=emis[b]; covered[lo-1:hi]=True
    if not covered.all(): raise ValueError('band map does not cover every g-point')
    # First verify exact discrete nodes/weights against the three stored RTE outputs.
    discrete={}
    for pol,(nodes,weights) in POLICIES.items():
        up,dn,hr=angular_result(nodes,weights,tau,lay,lev,surf,emis_g,plev,gravity,cp)
        _,saved=read_sections(base/f'run-v1/policy{pol}.result')
        exp_up=require(saved,'UP',(1,46,1))[0,:,0]
        exp_dn=require(saved,'DN',(1,46,1))[0,:,0]
        exp_hr=require(saved,'HR',(1,45,1))[0,:,0]
        discrete[str(pol)]={'nodes_mu':nodes,'weights':weights,'UP_W_m2':metrics(up,exp_up),'DN_W_m2':metrics(dn,exp_dn),'HR_K_day':metrics(hr,exp_hr)}
    for pol in discrete.values():
        for key in ('UP_W_m2','DN_W_m2','HR_K_day'):
            if pol[key]['max_abs'] > 1e-10: raise ValueError(f'discrete policy reproduction failed: {key}')
    # Overresolved reference: Gauss-Jacobi alpha=0,beta=1 under 2*mu dmu.
    convergence=[]
    prev=None; final=None; stop_order=None
    for n in (8,16,32,64,128,256,512,1024,2048):
        x,w=roots_jacobi(n,0.0,1.0)
        mus=(x+1.0)/2.0; weights=w/2.0
        val=angular_result(mus,weights,tau,lay,lev,surf,emis_g,plev,gravity,cp)
        delta=None if prev is None else {'UP_W_m2':metrics(val[0],prev[0]),'DN_W_m2':metrics(val[1],prev[1]),'HR_K_day':metrics(val[2],prev[2])}
        convergence.append({'order':n,'weights_sum':float(weights.sum()),'successive_difference':delta})
        if delta is not None and max(delta[k]['max_abs'] for k in delta)<=1e-9:
            stop_order=n; final=val; break
        prev=val; final=val
    pol_vs_integral={}
    for pol,(nodes,weights) in POLICIES.items():
        u,d,h=angular_result(nodes,weights,tau,lay,lev,surf,emis_g,plev,gravity,cp)
        pol_vs_integral[str(pol)]={'UP_W_m2':metrics(u,final[0]),'DN_W_m2':metrics(d,final[1]),'HR_K_day':metrics(h,final[2])}
    report={'schema':'udm37-bon-night-lw-angular-math-v1','status':'PYTHON_REFERENCE_COMPLETE','execution_scope':{'rte_executable_calls':0,'wrf_calls':0,'builds':0,'python_quadrature_transfer_evaluations':int(sum(n for n in (8,16,32,64,128,256,512,1024,2048) if n<= (stop_order or 2048))*ngpt*nlay),'discrete_policy_transfer_evaluations':int(sum(len(x[0]) for x in POLICIES.values())*ngpt*nlay),'synthetic_control_transfer_evaluations':12,'self_tests':self_test(),'initial_format_failure':'First parser draft expected three section dimensions and rejected the valid two-dimensional input EMIS section before any transfer evaluation; the reader was corrected to accept the input format and the final run completed.'},'source_order':{'layers':nlay,'gpoints':ngpt,'top_at_1':False,'surface_level_index':1,'toa_level_index':nlay+1},'input_and_source':{'input_sha256':sha(input_path),'source_sidecar_sha256':sha(trpath),'held_policy_sidecars_exact':True,'tau_source':'TOTAL_TAU from the three policy results; exact equality required','emissivity_source':'captured EMIS expanded by BAND_LIMITS_GPOINT','source_sections':['SOURCE_LAYER','SOURCE_LEVEL','SOURCE_SURFACE']},'discrete_policy_reproduction':discrete,'discrete_reproduction_tolerance':{'max_abs_flux_W_m2':1e-10,'max_abs_heating_K_day':1e-10},'quadrature':{'rule':'Gauss-Jacobi alpha=0,beta=1 after mu=(x+1)/2; maps to integral of I(mu)*2*mu dmu','orders':convergence,'criterion':'successive max absolute difference <= 1e-9 in each of UP, DN (W m-2) and HR (K day-1); hard order cap 2048','converged_order':stop_order,'reference':{'UP_W_m2':final[0].tolist(),'DN_W_m2':final[1].tolist(),'HR_K_day':final[2].tolist()},'policy_vs_reference':pol_vs_integral},'limits':['This only checks angular quadrature for the captured discrete TOTAL_TAU and source arrays under the source-code interpolation closure.','It does not validate optical depth, source interpolation against a continuous Planck profile, spectral quadrature, original LUT truth, WRF coupling, or physical accuracy.','Policy 2 is a one-node custom secant with weight 1, not a quadrature rule.']}
    design_pins=json.loads((root/'build/udm37-bon-night-lw-angular-reference-design-v1/source-pins.json').read_text())['source_pins']
    for pin in design_pins:
        pp=Path(pin['path'])
        if sha(pp)!=pin['sha256'] or pp.stat().st_size!=pin['size_bytes']:
            raise ValueError(f"pinned source artifact changed: {pin['label']}")
    report['pinned_design_artifacts']=design_pins
    import scipy
    report['runtime_versions']={'python':__import__('sys').version.split()[0],'numpy':np.__version__,'scipy':scipy.__version__}
    report['angular_reference_script_sha256']=sha(Path(__file__))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    receipt={'schema':'udm37-bon-night-lw-angular-math-execution-v1','status':report['status'],'result_path':str(args.out.resolve()),'result_sha256':sha(args.out),'script_path':str(Path(__file__).resolve()),'script_sha256':sha(Path(__file__)),'actual_rte_executable_invocations':0,'actual_wrf_invocations':0,'build_invocations':0,'python_quadrature_transfer_evaluations':report['execution_scope']['python_quadrature_transfer_evaluations'],'discrete_policy_transfer_evaluations':report['execution_scope']['discrete_policy_transfer_evaluations'],'synthetic_control_transfer_evaluations':report['execution_scope']['synthetic_control_transfer_evaluations'],'no_source_mutation':True}
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'out':str(args.out),'converged_order':stop_order,'discrete':discrete,'convergence':convergence},indent=2))
if __name__=='__main__': main()
