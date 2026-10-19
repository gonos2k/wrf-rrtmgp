"""Read-only sustained-run analysis. Replay stdlib packets, not rounded flux re-differencing."""
import importlib.util
import json
import math
from pathlib import Path
import re
import struct
ROOT = Path(__file__).resolve().parents[3]

def load(p, name):
    s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
pack=load(ROOT/'validation/rrtmgp37/policy2-budget-optics/analyze_saved.py','sustained_packets')
parser=load(ROOT/'validation/rrtmgp37/radiation-occurrence-runtime/verify_saved.py','sustained_capture')

def require(ok,msg):
    if not ok: raise ValueError(msg)

def analyze(read):
    inputs=json.loads(read('input/identity.json'))
    require(inputs['00']['physical_arrays']==inputs['11']['physical_arrays'],'physical initial arrays differ')
    require(inputs['00']['policies']==[0,0] and inputs['11']['policies']==[1,1],'input policy tags differ')
    def hist(name):
        return pack.History(json.loads(read('host/'+name+'.json')), read('host/'+name+'.bin'))
    def times(h):
        return [h.values('Times')[i:i+19].decode() for i in range(0,len(h.values('Times')),19)]
    def finite(h):
        return all(math.isfinite(x) for n,r in h.rows.items() if r['dtype'][1:2] in 'fi' for x in h.values(n))
    cases={}
    for name in ('hour_00','hour_11','day_00','day_11'):
        h=hist(name);ts=times(h);nt=len(ts)
        require(finite(h),'nonfinite history '+name)
        for n in ('QVAPOR','QCLOUD','QRAIN','QNCCN','QNCLOUD','QNRAIN'):
            require(min(h.values(n))>=0, 'negative state '+name+'/'+n)
        require(h.index['attrs']['UDM_NUMBER_POLICY']==1 and h.index['attrs']['UDM_POPULATION_POLICY']==2,'population selection changed')
        choice=int(name[-1]);require(h.index['attrs']['RRTMGP_CAPACITY_POLICY']==h.index['attrs']['RRTMGP_LIQUID_SIZE_POLICY']==choice,'research choice differs')
        def area(n,t):
            return sum(h.at(n,t,j,i)*h.at('AREA2D',t,j,i) for j in range(2) for i in range(2))/sum(h.at('AREA2D',t,j,i) for j in range(2) for i in range(2))
        W=[pack.water_inventory(h,t) for t in range(nt)]
        P=[sum(area(n,t)-area(n,0) for n in ('RAINC','RAINNC')) for t in range(nt)]
        E=[(area('ACLHF',t)-area('ACLHF',0))/2501000. for t in range(nt)]
        residual=[w-W[0]+p-e for w,p,e in zip(W,P,E)]
        air=[];thm_error=[];reff=[];zero=positive=up=down=0
        for t in range(nt):
            for k in range(59):
                for j in range(2):
                    for i in range(2):
                        theta=h.at('T',t,k,j,i)+300.
                        pressure=h.at('P',t,k,j,i)+h.at('PB',t,k,j,i)
                        require(pressure>0,'nonpositive total pressure')
                        air.append(theta*(pressure/1.e5)**(287./1004.5))
                        qv=h.at('QVAPOR',t,k,j,i)
                        thm_error.append((1+parser.f32(parser.f32(461.6)/parser.f32(287.))*qv)*theta-300-h.at('THM',t,k,j,i))
                        qc=h.at('QCLOUD',t,k,j,i);nr=h.at('QNRAIN',t,k,j,i);qr=h.at('QRAIN',t,k,j,i)
                        f=h.at('UDM_CLDFRA',t,k,j,i)
                        if t>0:
                            if qr>0:zero+=f==0;positive+=f>0
                            before=h.at('UDM_CLDFRA',t-1,k,j,i)
                            up+=qr>0 and before==0 and f>0;down+=qr>0 and before>0 and f==0
                        eta=h.at('QNCLOUD',t,k,j,i)
                        if qc>0 and eta>0:
                            rv=(3*qc/(4*math.pi*1000*eta))**(1/3)
                            reff.append(rv*(100/(8*9))**(1/3)*1.e6)
        # History solar fields are held diagnostics; exclude the uninitialized time zero.
        day_indices=[t for t in range(1,nt) if max(h.at('COSZEN',t,j,i) for j in range(2) for i in range(2))>0]
        night_indices=[t for t in range(1,nt) if max(h.at('COSZEN',t,j,i) for j in range(2) for i in range(2))<=0]
        log=read('logs/'+name+'.stdout').decode(errors='replace')
        require('SUCCESS COMPLETE WRF' in log and 'FATAL CALLED' not in log,'integration not complete '+name)
        source=[float(x) for x in re.findall(r'LW RRTMGP_UDM_PHASE_PATH phase=LIQ .*?source_time_seconds=([0-9.E+\-]+)',log)]
        duration=3600 if name.startswith('hour') else 86400
        require(source==list(range(0,duration,30)),'actual LW call phase changed '+name)
        if duration==86400:
            require(day_indices and night_indices,'day/night not both exercised')
            require(ts[-1]=='1999-10-23_19:00:00','24-hour window truncated')
        cases[name]={
            'history_records':nt,'start':ts[0],'end':ts[-1],'actual_LW_calls':len(source),
            'actual_LW_source_first_last_s':[source[0],source[-1]],
            'air_temperature_from_dry_theta_pressure_K':[min(air),max(air)],
            'max_abs_THM_reconstruction_K':max(map(abs,thm_error)),
            'water_inventory_kg_m2':W,'accumulated_total_precip_kg_m2':P,'surface_evaporation_from_ACLHF_kg_m2':E,
            'inventory_plus_precip_minus_evap_kg_m2':residual,
            'water_budget_approved':False,'water_note':'History inventory/ACLHF ledger; common PBL/PD actual-source contribution not re-instrumented. This is not closed-host-budget approval.',
            'sampled_CF0_rain_cells':zero,'sampled_positive_CF_rain_cells':positive,
            'sampled_CF0_to_positive_rain':up,'sampled_positive_to_CF0_rain':down,
            'daylight_history_records':len(day_indices),'night_history_records':len(night_indices),
            'night_SWdown_max_W_m2':max((h.at('SWDOWN',t,j,i) for t in night_indices for j in range(2) for i in range(2)),default=None),
            'Gamma8_reff_diagnosed_from_history_um':[min(reff),max(reff)],
            'Gamma8_outside_liquid_LUT_sample_count':sum(x<2.5 or x>21.5 for x in reff),
            'history_radius_is_optical_consumption_proof':False}
    a,b=hist('day_11'),hist('resumed_11');ta,tb=times(a),times(b)
    require(tb[0]=='1999-10-23_01:00:10','restart not between calls')
    common=sorted(set(ta)&set(tb));require(len(common)==216,'restart history overlap incomplete')
    ia=[ta.index(t) for t in common];ib=[tb.index(t) for t in common];eq=[]
    for n,row in a.rows.items():
        require(n in b.rows and row['shape'][1:]==b.rows[n]['shape'][1:],'restart schema differs '+n)
        aa=read('host/day_11.bin')[row['offset']:row['offset']+row['bytes']]
        z=b.rows[n];bb=read('host/resumed_11.bin')[z['offset']:z['offset']+z['bytes']]
        stride=row['bytes']//len(ta)
        require(all(aa[i*stride:(i+1)*stride]==bb[j*stride:(j+1)*stride] for i,j in zip(ia,ib)),'restart overlap differs '+n)
        eq.append(n)
    cp=hist('checkpoint21610')
    for n in ('RTHRATEN','RTHRATLW','RTHRATSW','RTHRATLWC','RTHRATSWC','STEPRA'):
        require(cp.values(n)==b.values(n)[:len(cp.values(n))],'checkpoint held field lost '+n)
    require(cp.values('STEPRA')==(3,),'checkpoint interval changed')
    log=read('logs/resumed_11.stdout').decode(errors='replace')
    calls=[float(x) for x in re.findall(r'LW RRTMGP_UDM_PHASE_PATH phase=LIQ .*?source_time_seconds=([0-9.E+\-]+)',log)]
    require(calls==list(range(21630,86400,30)),'restart call phase changed')
    original=hist('attempt_restart');to=times(original)
    original_common=sorted(set(ta)&set(to))
    require(len(original_common)==8,'original timer deviation coverage changed')
    for n,row in a.rows.items():
        u=a.values(n);v=original.values(n);stride=math.prod(row['shape'][1:])
        require(all(u[ta.index(t)*stride:(ta.index(t)+1)*stride]==v[to.index(t)*stride:(to.index(t)+1)*stride] for t in original_common),'original common state differs '+n)
    probe=times(hist('attempt_restart-timers'))
    require(probe==['1999-10-23_01:00:10','1999-10-23_01:05:00','1999-10-23_01:10:00'],'output timer probe changed')
    capacity={}
    for name in ('day_00','day_11','resumed_11'):
        capacity[name]={}
        for ph in (('lw',) if name=='resumed_11' else ('lw','sw')):
            z={k:parser.trace(read(f'capture/{name}/{ph}.{k}'),k)[1] for k in ('raw','input','result')}
            v=lambda k,n:z[k][n]['values']
            expect=21630 if name=='resumed_11' else 1800
            require(v('raw','SOURCE_TIME_SECONDS')==[expect],'capture source clock differs')
            cap=int(name.endswith('11'))
            require(v('raw','RRTMGP_RESEARCH_POLICIES')==[cap,cap],'capture choices differ')
            if cap:
                C=v('result','NATIVE_CAPACITY_J_M2_K');m=v('raw','DRY_LAYER_MASS_KG_M2');qv=v('raw','SOURCE_QV')
                require(C==[x*1004.5*(1+parser.f32(parser.f32(461.6)/parser.f32(287.))*q) for x,q in zip(m,qv)],'capacity inputs changed')
                up,dn,heat=[v('result',n) for n in ('UP_WP','DN_WP','HEAT_WP_K_S')]
                errors=[]
                for k,c in enumerate(C):
                    Q=dn[k+1]-up[k+1]-dn[k]+up[k]
                    errors.append(c*heat[k]-Q)
                    bound=32*2**-52*max(abs(dn[k+1])+abs(up[k+1])+abs(dn[k])+abs(up[k]),1.)
                    require(abs(errors[-1])<=bound,'capacity source closure outside arithmetic bound')
                capacity[name][ph]={'source_seconds':expect,'native_layers':len(C),'max_abs_layer_capacity_residual_W_m2':max(map(abs,errors))}
            else: require('NATIVE_CAPACITY_J_M2_K' not in z['result'],'00 acquired research capacity')
            if cap:
                rho,qc,eta,cf=[v('raw',n) for n in ('SOURCE_DRY_RHO','SOURCE_QC','SOURCE_QNC','CF')]
                rel=v('input','REL');count=0
                for k,q in enumerate(qc):
                    if q<=0:continue
                    f=cf[k] if cf[k]>0 else 1.;M0=rho[k]*eta[k]/f;M3=3*rho[k]*q/(4*math.pi*1000*f)
                    lam=(M0*8*9*10/M3)**(1/3);M2=M0*8*9/lam**2
                    require(parser.f32(M3/M2*1e6)==rel[k],'same-call Gamma optical input differs')
                    count+=1
                capacity[name][ph]['positive_cloud_consumed_layers']=count
    return {'status':'PASS_SCOPED_SUSTAINED_AND_RESTART','production_accepted':False,
            'preregistered_full_validation_passed':False,
            'protocol_coverage_notes':['The hour 1810 s checkpoint was written but not separately replayed; the longer 21610 s checkpoint was replayed instead.','The initial full restart failed the requested output cadence; its original record and the output-only amendment/probe are preserved.','Water inventories and captured source contracts are evaluated; exact long-run source/energy accounting was not newly instrumented.'],
            'science_gates_closed':False,'cases':cases,'captured_source_contract':capacity,
            'output_timer_deviation':{'stock_restart_interval_s':290,'requested_interval_s':300,'common_times_before_override':len(original_common),'all_common_arrays_equal':214,'fixed_by_existing_namelist_only':True,'override_restart_timers':True,'history_begin_s':290,'production_source_modified':False},
            'restart':{'checkpoint_seconds':21610,'first_next_radiation_seconds':21630,'overlap_times':len(common),'byte_equal_Time_arrays':len(eq),'last_time':common[-1]},
            'full_host_water_budget_approved':False,'long_run_actual_applied_energy_budget':'NOT_ASSESSED_NO_NEW_ACOUSTIC_OBSERVER',
            'reference_FAILs_overridden':False,'new_solver_runs_in_replay':0}
