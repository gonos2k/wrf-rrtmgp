"""Replay integrated research boundaries using captured arrays; no model execution."""
from pathlib import Path
import hashlib,importlib.util,json,math,struct
ROOT=Path(__file__).resolve().parents[3]
def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
parser=load(ROOT/'validation/rrtmgp37/radiation-occurrence-runtime/verify_saved.py','capture_parser')
pack=load(ROOT/'validation/rrtmgp37/policy2-budget-optics/analyze_saved.py','packet_parser')
f32=parser.f32
require=parser.require

def analyze(read):
    def capture(name,ph):
        return {kind:parser.trace(read(f'host/{name}/capture/{ph}.{kind}'),kind)[1] for kind in ('input','raw','result')}
    def history(name):return pack.History(json.loads(read('host/'+name+'.json')),read('host/'+name+'.bin'))
    cloud={}
    for cap,size in [(0,0),(0,1),(1,0),(1,1)]:
        name=f'cloud_{cap}{size}';cloud[name]={}
        for ph in ['lw','sw']:
            z=capture(name,ph);raw,inp,res=[z[k] for k in ['raw','input','result']]
            v=lambda d,n:d[n]['values']
            require(v(raw,'SOURCE_TIME_SECONDS')==[10.],'wrong positive-cloud source time')
            require(v(raw,'RRTMGP_RESEARCH_POLICIES')==[float(cap),float(size)],'wrong executed options')
            rho,qc,eta,cf=[v(raw,n) for n in ['SOURCE_DRY_RHO','SOURCE_QC','SOURCE_QNC','CF']]
            md,qv=v(raw,'DRY_LAYER_MASS_KG_M2'),v(raw,'SOURCE_QV');rel=v(inp,'REL');rows=[];closure=[]
            if cap:
                C=v(res,'NATIVE_CAPACITY_J_M2_K')
                expected=[m*1004.5*(1.+f32(f32(461.6)/f32(287.))*q) for m,q in zip(md,qv)]
                require(C==expected,'same-call capacity mismatch')
                up,dn,heat=[v(res,n) for n in ['UP_WP','DN_WP','HEAT_WP_K_S']]
                for k,c in enumerate(C):
                    Q=dn[k+1]-up[k+1]-dn[k]+up[k]
                    delta=c*heat[k]-Q;require(abs(delta)<1e-10,'native layer capacity closure')
                    closure.append(delta)
                # Clear/allsky use the same denominator; account for exported REAL32 flux/HR.
                up,dn,hr=[v(res,n) for n in ['UPC','DNC','HRC']]
                for k,c in enumerate(C):
                    Q=dn[k+1]-up[k+1]-dn[k]+up[k];delta=c*hr[k]/86400.-Q
                    bound=8*2**-24*(abs(up[k])+abs(up[k+1])+abs(dn[k])+abs(dn[k+1])+abs(c*hr[k]/86400.))
                    require(abs(delta)<=bound,'clear capacity closure outside export rounding bound')
            else:require('NATIVE_CAPACITY_J_M2_K' not in res,'legacy column received capacity')
            table=json.loads(read('coefficients/'+ph+'.json'));optical_error=0.
            for k,(rh,q,n,f) in enumerate(zip(rho,qc,eta,cf)):
                if q<=0:continue
                require(n>0 and rh>0,'invalid positive-cloud population')
                foot=f if f>0 else 1.;M0=rh*n/foot;M3=3*rh*q/(4*math.pi*1000*foot)
                lam=(M0*8*9*10/M3)**(1/3);M2=M0*8*9/lam**2;reff=M3/M2*1e6
                if size:require(f32(reff)==rel[k],'Gamma8 optical radius mismatch')
                lo,hi=table['radliq_lwr'],table['radliq_upr'];require(lo<rel[k]<hi,'liquid LUT clipping active')
                grid=len(table['arrays']['extliq'][0]);step=(hi-lo)/(grid-1)
                ii=min(math.floor((rel[k]-lo)/step),grid-2);frac=(rel[k]-lo)/step-ii
                for band in range(len(table['arrays']['extliq'])):
                    def lut(n):
                        a=table['arrays'][n][band];return a[ii]+frac*(a[ii+1]-a[ii])
                    tau=v(inp,'LWP')[k]*lut('extliq');index=band*inp['LWP']['shape'][1]+k
                    if ph=='sw':a=f32(tau);o=v(inp,'RAW_CLOUD_TAU')[index]
                    else:a=tau-tau*lut('ssaliq')+v(res,'PRECIP_TAU')[index];o=v(res,'CLOUD_TAU')[index]
                    require(math.isclose(a,o,rel_tol=3e-7,abs_tol=1e-12),'optical LUT consumption mismatch')
                    optical_error=max(optical_error,abs(a-o))
                rows.append({'k':k+1,'qc':q,'eta':n,'rho_d':rh,'footprint':foot,'M0':M0,'M2':M2,'M3':M3,'Gamma8_reff_um':reff,'consumed_REL_um':rel[k]})
            require(len(rows)>0,'positive cloud absent')
            # Captured source10 qv is exactly the history state10. Reconstruct Exner
            # from exported T/theta_m, allowing REAL32 state/export rounding.
            h=history(name);theta_errors=[]
            for k in range(59):
                q=qv[k];require(q==h.at('QVAPOR',1,k,0,0),'source/history clock differs')
                theta=(h.at('THM',1,k,0,0)+300.)/(1.+f32(f32(461.6)/f32(287.))*q)
                Pi=v(raw,'SOURCE_T')[k]/theta
                pred=f32(v(res,'HR')[k]/86400.)/Pi
                lw=h.at('RTHRATLW',2,k,0,0)
                actual=h.at('RTHRATLW' if ph=='lw' else 'RTHRATSW',2,k,0,0)
                bound=8*2**-24*(abs(pred)+abs(lw))+1e-14
                require(abs(pred-actual)<=bound,'actual host theta source differs')
                theta_errors.append(abs(pred-actual))
            cloud[name][ph]={'max_abs_actual_host_theta_reconstruction_K_s':max(theta_errors),'positive_layers':rows,'max_abs_layer_capacity_residual_W_m2':max(map(abs,closure),default=0.),'max_abs_LUT_consumption_error':optical_error}
    # Same initial arrays, distinct metadata. Signed interactions are on matching elements.
    hs={n:history(n) for n in cloud};interactions={}
    for n in ['T','QVAPOR','QCLOUD','QRAIN','QNCLOUD','QNRAIN','RTHRATEN','RTHRATLW','RTHRATSW','SWDOWN','GLW']:
        vs={k:h.values(n) for k,h in hs.items()};shape=hs['cloud_00'].rows[n]['shape']
        require(all(h.rows[n]['shape']==shape for h in hs.values()),'interaction shape differs')
        signed=[d-c-b+a for a,b,c,d in zip(vs['cloud_00'],vs['cloud_01'],vs['cloud_10'],vs['cloud_11'])]
        require(all(math.isfinite(x) for x in signed),'nonfinite interaction')
        i=max(range(len(signed)),key=lambda k:abs(signed[k]));ind=[];j=i
        for dim in reversed(shape):ind.insert(0,j%dim);j//=dim
        interactions[n]={'shape':shape,'signed_values':signed,'max_abs':abs(signed[i]),'signed_at_max':signed[i],'index_zero_based':ind}
    # Restart between radiation calls: compare all common records from 20s onward.
    held,resumed=history('held_11'),history('resumed_11');eq=[]
    for n,z in held.rows.items():
        p=resumed.rows[n];require(z['shape'][1:]==p['shape'][1:],'restart shape differs')
        a=read('host/held_11.bin')[z['offset']:z['offset']+z['bytes']]
        b=read('host/resumed_11.bin')[p['offset']:p['offset']+p['bytes']]
        count=math.prod(z['shape'][1:]);record=z['bytes']//z['shape'][0]
        require(a[2*record:]==b,'restart overlap differs '+n);eq.append(n)
    held_vars=['RTHRATEN','RTHRATLW','RTHRATLWC','RTHRATSW','RTHRATSWC']
    cp=history('checkpoint20')
    require(cp.index['attrs']['RRTMGP_CAPACITY_POLICY']==cp.index['attrs']['RRTMGP_LIQUID_SIZE_POLICY']==1,'checkpoint identity lost')
    require(cp.values('STEPRA')==(3,),'checkpoint radiation interval changed')
    for n in held_vars:
        count=math.prod(held.rows[n]['shape'][1:])
        require(held.values(n)[2*count:3*count]==cp.values(n),'held checkpoint field differs '+n)

    require(all(n in eq for n in held_vars+['STEPRA']),'missing held state')
    for n in held_vars:require(any(x!=0 for x in held.values(n)),'empty held tendency '+n)
    for ph in ['lw','sw']:
        a=capture('held_11',ph);b=capture('resumed_11',ph)
        require(a['raw']['SOURCE_TIME_SECONDS']['values']==b['raw']['SOURCE_TIME_SECONDS']['values']==[30.],'restart changed radiation call phase')
        for kind in a:require(a[kind]==b[kind],'post-restart radiation capture differs '+kind)
    for ph in ['lw','sw']:
        z=capture('audit_11',ph)
        require(z['raw']['RRTMGP_RESEARCH_POLICIES']['values']==[1.,1.],'diagnostic lost research choices')
        require('NATIVE_CAPACITY_J_M2_K' in z['result'],'diagnostic reverted to legacy heat')
        qc=z['raw']['SOURCE_QC']['values'];eta=z['raw']['SOURCE_QNC']['values'];rho=z['raw']['SOURCE_DRY_RHO']['values'];cf=z['raw']['CF']['values']
        for k,q in enumerate(qc):
            if q<=0:continue
            f=cf[k] if cf[k]>0 else 1.;M0=rho[k]*eta[k]/f;M3=3*rho[k]*q/(4*math.pi*1000*f)
            lam=(M0*8*9*10/M3)**(1/3);M2=M0*8*9/lam**2
            require(f32(M3/M2*1e6)==z['input']['REL']['values'][k],'diagnostic reverted to native liquid radius')
    return {'status':'PASS_SCOPED_INTEGRATED_RESEARCH','production_accepted':False,'science_gates_closed':False,
            'cloud':cloud,'same_initial_state_signed_interactions':interactions,
            'restart':{'checkpoint_seconds':20,'next_actual_radiation_source_seconds':30,'overlap_arrays_bit_identical':len(eq),'held_fields':held_vars,'post_restart_raw_input_result_equal':True},
            'research_definitions':{'capacity':'native-constant-kappa-source-v1','liquid':'final-liquid-gamma-veff-0p1-v1'},
            'whole_energy_and_observation_accuracy_approved':False,'new_solver_runs_in_replay':0}
