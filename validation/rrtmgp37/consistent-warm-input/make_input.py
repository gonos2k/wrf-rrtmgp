"""Narrow research producer: canonical all-warm SCM + explicit condensate.

Never relabel a legacy number checkpoint. Reconstruct pressure/alpha/Phi using
WRF's discrete hydrostatic initializer, including declared condensate loading.
Only 2x2x59, terrain-following, theta_m ideal seed is supported.
"""
import argparse,hashlib,json,shutil
from pathlib import Path
import netCDF4
import numpy as np

def generate(seed,output,receipt):
    seed=Path(seed);output=Path(output)
    if output.exists():raise ValueError('output already exists')
    with netCDF4.Dataset(seed) as d:
        if (len(d.dimensions['west_east']),len(d.dimensions['south_north']),len(d.dimensions['bottom_top']))!=(2,2,59):raise ValueError('research SCM dimensions required')
        if d.getncattr('USE_THETA_M')!=1 or d.getncattr('HYBRID_OPT')!=0:raise ValueError('theta_m terrain-following seed required')
        state={n:np.asarray(d[n][0],dtype=np.float64) for n in ['MU','MUB','C1H','C2H','C1F','C2F','DNW','DN','T','THM','AL','ALB','PH','PHB','P','PB','QVAPOR','QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL','T_BASE','Z_BASE']}
    s=state;g=float(np.float32(9.81));rd=float(np.float32(287.));rv=float(np.float32(461.6));cp=float(np.float32(1004.5));qv=s['QVAPOR'];theta=s['T']+300;P=s['P']+s['PB'];temp=theta*(P/1e5)**(rd/cp)
    if not all(np.isfinite(a).all() for a in s.values()) or temp.min()<285 or temp.max()>305:raise ValueError('finite all-warm canonical seed required')
    if any(np.any(s[n]!=0) for n in ['QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL']):raise ValueError('unmodified clear canonical ideal seed required')
    mu=s['MU']+s['MUB'];alpha=s['AL']+s['ALB'];md=-(s['C1H'][:,None,None]*mu+s['C2H'][:,None,None])*s['DNW'][:,None,None]/g
    phi=s['PH']+s['PHB'];geom=np.diff(phi,axis=0)/g
    seed_ratio=geom/alpha/md
    if np.max(abs(seed_ratio-1))>1e-5:raise ValueError('seed pressure mass/geometry inconsistent')
    zc=(phi[:-1]+phi[1:])/(2*g);active=zc<1500.;qc=np.where(active,1e-5,0.);qr=np.where(active,2e-4,0.);qt=qv+qc+qr
    # Same downward discrete pressure integration as module_initialize_scm_xy,
    # replacing vapor-only loading by the explicitly declared total water.
    pert=np.empty_like(P);f=qt[-1]/(1+qt[-1]);f2=1/(1+qt[-1]);pert[-1]=-.5*(s['C1F'][-1]*s['MU']+f*(s['C1F'][-1]*s['MUB']+s['C2F'][-1]))*s['DNW'][-1]/f2
    for k in range(57,-1,-1):
        q=.5*(qt[k]+qt[k+1]);f=q/(1+q);f2=1/(1+q)
        pert[k]=pert[k+1]-(s['C1F'][k+1]*s['MU']+f*(s['C1F'][k+1]*s['MUB']+s['C2F'][k+1]))*s['DN'][k+1]/f2
    alpha=(rd/1e5)*theta*(1+rv/rd*qv)*((pert+s['PB'])/1e5)**(-(cp-rd)/cp)
    phi=np.concatenate([phi[:1],phi[:1]+np.cumsum(md*alpha*g,axis=0)])
    rho=1/alpha
    shutil.copy2(seed,output)
    with netCDF4.Dataset(output,'r+') as d:
        for n,a in [('P',pert),('AL',alpha-s['ALB']),('PH',phi-s['PHB']),('QCLOUD',qc),('QRAIN',qr)]:d[n][0]=a
        for n,nv in [('QNCCN',1e8),('QNCLOUD',5e7),('QNRAIN',2e4)]:d[n][0]=nv/rho if n=='QNCCN' else np.where(active,nv/rho,0.)
        # Rayleigh damper acts on theta_m: its reference must use that representation.
        d['T_BASE'][0]=s['THM'][:,0,0];d['Z_BASE'][0]=(phi[1:,0,0]+phi[:-1,0,0])/(2*g)
        d.setncattr('UDM_NUMBER_POLICY',np.int32(1));d.setncattr('UDM_POPULATION_POLICY',np.int32(2))
        d.setncattr('RESEARCH_INPUT_DEFINITION','warm-SCM-discrete-hydrostatic-liquid-v1; explicit new eta values; theta_m reference; not general real/boundary support')
    report={'seed_sha256':hashlib.sha256(seed.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'seed_native_mass_ratio_min':float(seed_ratio.min()),'seed_native_mass_ratio_max':float(seed_ratio.max()),'new_number_definition':'eta=n_volume/rho_d; n free/cloud/rain=1e8/5e7/2e4 m-3','water_perturbation':'qc=1e-5 qr=2e-4 below original 1500m; condensate-loading pressure and EOS/Phi reconstructed','production_accepted':False}
    Path(receipt).write_text(json.dumps(report,indent=2)+'\n')
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--canonical-ideal-seed',required=True);p.add_argument('--output',required=True);p.add_argument('--receipt',required=True);a=p.parse_args();print(json.dumps(generate(a.canonical_ideal_seed,a.output,a.receipt)))
