"""Path-weighted LUT exposure, fixed-state attribution and a bounded source ledger.

All replay reads sealed artifacts. Component removal measures contribution, never
clipping error. The stored history is not a record of every radiation call.
"""
import datetime as dt
import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]

def load(p,name):
    s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
pack=load(ROOT/'validation/rrtmgp37/policy2-budget-optics/analyze_saved.py','exposure_packets')
parser=load(ROOT/'validation/rrtmgp37/radiation-occurrence-runtime/verify_saved.py','exposure_trace')

def require(ok,msg):
    if not ok:raise ValueError(msg)

def history_exposure(h,tables):
    times=[h.values('Times')[i:i+19].decode() for i in range(0,len(h.values('Times')),19)]
    clocks=[dt.datetime.strptime(x,'%Y-%m-%d_%H:%M:%S') for x in times]
    seconds=[int((x-clocks[0]).total_seconds()) for x in clocks]
    require(seconds==list(range(0,86401,300)),'history sampling clock differs')
    weights=[(seconds[min(i+1,len(seconds)-1)]-seconds[max(i-1,0)])/2 for i in range(len(seconds))]
    cats=('low','high','in','undefined');totals={n:0. for n in cats};counts={n:0 for n in cats};rows=[]
    optical={ph:{n:[[0.,0.,0.,0.] for _ in tables[ph]['arrays']['extliq']] for n in ('ext','sca','abs','sca_g')} for ph in tables}
    for t,time in enumerate(times):
        area=sum(h.at('AREA2D',t,j,i) for j in range(2) for i in range(2));paths={n:0. for n in cats};columns=[]
        for j in range(2):
            for i in range(2):
                cp={n:0. for n in cats};A=h.at('AREA2D',t,j,i)
                for k in range(59):
                    q=h.at('QCLOUD',t,k,j,i);eta=h.at('QNCLOUD',t,k,j,i)
                    if q<=0:continue
                    path=h.mass(t,k,j,i)*q;require(path>=0,'negative liquid path')
                    if eta>0:
                        r=(3*q/(4*math.pi*1000*eta))**(1/3)*(100/72)**(1/3)*1.e6
                        cat='low' if r<2.5 else 'high' if r>21.5 else 'in'
                    else:r=None;cat='undefined'
                    counts[cat]+=1;totals[cat]+=A*weights[t]*path;paths[cat]+=A*path;cp[cat]+=path*1000
                    if r is None:continue
                    ci=cats.index(cat);rr=min(max(r,2.5),21.5)
                    for ph,table in tables.items():
                        arrays=table['arrays'];n=len(arrays['extliq'][0]);step=19/(n-1)
                        ii=min(int((rr-2.5)/step),n-2);fraction=(rr-2.5)/step-ii
                        for band in range(len(arrays['extliq'])):
                            def lut(name):
                                v=arrays[name][band];return v[ii]+fraction*(v[ii+1]-v[ii])
                            ext=lut('extliq');ssa=lut('ssaliq');g=lut('asyliq')
                            for moment,value in [('ext',ext),('sca',ext*ssa),('abs',ext*(1-ssa)),('sca_g',ext*ssa*g)]:
                                optical[ph][moment][band][ci]+=A*weights[t]*path*1000*value
                columns.append({'i':i+1,'j':j+1,'path_g_m2':cp})
        mean={n:paths[n]/area*1000 for n in cats}
        rows.append({'seconds':seconds[t],'time':time,'mean_grid_LWP_g_m2':mean,'COSZEN_max':max(h.at('COSZEN',t,j,i) for j in range(2) for i in range(2)),'columns':columns})
    total=sum(totals.values());require(total>0 and counts['undefined']==0,'undefined positive-cloud population')
    summaries={n:{'samples':counts[n],'path_time_fraction':totals[n]/total} for n in cats}
    require(abs(sum(v['path_time_fraction'] for v in summaries.values())-1)<1.e-12,'path partition does not close')
    optical_fraction={ph:{moment:[{'low':v[0]/sum(v) if sum(v) else 0.,'high':v[1]/sum(v) if sum(v) else 0.} for v in bands] for moment,bands in moments.items()} for ph,moments in optical.items()}
    def peak(key,eligible=lambda x:True):return max((x for x in rows if eligible(x)),key=lambda x:x['mean_grid_LWP_g_m2'][key])
    night=peak('high',lambda x:x['COSZEN_max']<=0);day=peak('high',lambda x:x['COSZEN_max']>0);low=peak('low')
    selected={}
    for name,row,cat in [('night_peak',night,'high'),('day_peak',day,'high'),('low_peak',low,'low')]:
        col=max(row['columns'],key=lambda x:x['path_g_m2'][cat]);selected[name]={'seconds':row['seconds'],'time':row['time'],'i':col['i'],'j':col['j'],'selected_column_path_g_m2':col['path_g_m2'],'mean_grid_LWP_g_m2':row['mean_grid_LWP_g_m2']}
    # Existing source/inventory ledger, resolved only at its saved cadence.
    inventory=[pack.water_inventory(h,t) for t in range(len(times))]
    def mean(n,t):return sum(h.at(n,t,j,i)*h.at('AREA2D',t,j,i) for j in range(2) for i in range(2))/sum(h.at('AREA2D',t,j,i) for j in range(2) for i in range(2))
    precip=[sum(mean(n,t)-mean(n,0) for n in ('RAINC','RAINNC')) for t in range(len(times))]
    evap=[(mean('ACLHF',t)-mean('ACLHF',0))/2501000 for t in range(len(times))]
    residual=[w-inventory[0]+p-e for w,p,e in zip(inventory,precip,evap)]
    intervals=[{'start_s':seconds[i],'end_s':seconds[i+1],'delta_residual_kg_m2':residual[i+1]-residual[i],'delta_inventory_kg_m2':inventory[i+1]-inventory[i],'precip_kg_m2':precip[i+1]-precip[i],'evap_ACLHF_kg_m2':evap[i+1]-evap[i],'COSZEN_at_end':rows[i+1]['COSZEN_max']} for i in range(len(times)-1)]
    return {'categories':summaries,'time_integration':'Trapezoidal history quadrature (300 s sampling), including half-weight endpoints; not every radiation call','path_definition':'same-time host dry mass * qc; AREA2D weighting; grid path, no division by CF','history_is_actual_clipping_count':False,'clamped_LUT_optical_moment_exposure_fraction_by_band':optical_fraction,'optical_proxy_is_flux_or_error':False,'selected_windows':selected,'water_residual_end_kg_m2':residual[-1],'water_largest_absolute_increments':sorted(intervals,key=lambda x:abs(x['delta_residual_kg_m2']),reverse=True)[:10],'water_series':residual,'water_intervals':intervals}

def source_window(data,h):
    wq={};sq={};mb={}
    for line in data.decode().splitlines():
        w=line.split()
        if not w:continue
        if w[0].startswith('WQ_'):wq[(w[0],*map(int,w[1:6]))]=list(map(float,w[6:]))
        elif w[0].startswith('SQ_'):sq[(w[0],*map(int,w[1:7]))]=list(map(float,w[7:]))
        elif w[0] in ('MB_PRE','MB_POST'):mb[(w[0],*map(int,w[1:5]))]=list(map(float,w[5:]))
    require({key[1] for key in wq}==set(range(8491,8521)),'source window coverage differs')
    imids=sorted({key[3] for key in sq});require(len(imids)==3,'water species coverage differs')
    total={k:0. for k in ('QFX','PBL_dry_mass','PBL_total_pressure','PD_actual','PD_source','RK_arithmetic','scalar_advection','micro_residual')}
    for step in range(8491,8521):
        for j in (1,2):
            for i in (1,2):
                row=wq['WQ_PBL',step,1,i,j,1];total['QFX']+=row[8]*10/4
                for k in range(1,60):
                    a=wq['WQ_PBL',step,1,i,j,k]
                    total['PBL_dry_mass']+=a[2]*(a[6]+a[7])*10/4
                    total['PBL_total_pressure']+=(a[9]-a[10])/9.810000419616699*(a[6]+a[7])*10/4
                    for im in imids:
                        x=sq['SQ_PD_PRE',step,3,im,i,j,k];z=sq['SQ_PD_POST',step,3,im,i,j,k]
                        total['PD_actual']+=x[0]*(z[2]-x[2])/4;total['PD_source']+=x[8]*x[6]*x[4]/4
                        x=sq['SQ_PRE',step,3,im,i,j,k];z=sq['SQ_POST',step,3,im,i,j,k]
                        actual=x[1]*z[3]-x[0]*x[2];source=x[8]*x[6]*x[4];adv=x[8]*x[6]*x[5]*x[7]
                        total['RK_arithmetic']+=(actual-source-adv)/4;total['scalar_advection']+=adv/4
                    x=mb['MB_PRE',step,i,j,k];z=mb['MB_POST',step,i,j,k]
                    require(x[13]==z[13]==16000000.,'equal physical area assumption differs')
                    total['micro_residual']+=x[0]*(sum(z[4:7])-sum(x[4:7]))/4
                total['micro_residual']+=(mb['MB_POST',step,i,j,1][10]-mb['MB_PRE',step,i,j,1][10])/4
    # Inventory bridges use the actual recorded states, with mass and mixing-ratio
    # parts kept separate. They are accounting terms, not fitted corrections.
    bridges={n:{'carrier_mass':0.,'mixing_ratio':0.} for n in ('state_to_PD','PD_to_RK','RK_to_micro','between_steps')}
    native_start=native_end=0.;max_relative_carrier_gap=0.
    for step in range(8491,8521):
        for j in (1,2):
            for i in (1,2):
                for k in range(1,60):
                    a=wq['WQ_PBL',step,1,i,j,k];pre=mb['MB_PRE',step,i,j,k];post=mb['MB_POST',step,i,j,k]
                    if step==8491:native_start+=a[1]*sum(a[3:6])/4
                    if step==8520:native_end+=post[0]*sum(post[4:7])/4
                    for n,im in enumerate(imids):
                        pd0=sq['SQ_PD_PRE',step,3,im,i,j,k];pd1=sq['SQ_PD_POST',step,3,im,i,j,k]
                        rk0=sq['SQ_PRE',step,3,im,i,j,k];rk1=sq['SQ_POST',step,3,im,i,j,k]
                        pairs=[('state_to_PD',a[1],a[3+n],pd0[0],pd0[2]),('PD_to_RK',pd1[0],pd1[2],rk0[0],rk0[2]),('RK_to_micro',rk1[1],rk1[3],pre[0],pre[4+n])]
                        if step>8491:
                            prev=mb['MB_POST',step-1,i,j,k];pairs.append(('between_steps',prev[0],prev[4+n],a[1],a[3+n]))
                        for name,m0,q0,m1,q1 in pairs:
                            bridges[name]['carrier_mass']+=(m1-m0)*q0/4
                            bridges[name]['mixing_ratio']+=m1*(q1-q0)/4
                            max_relative_carrier_gap=max(max_relative_carrier_gap,abs(m1-m0)/max(abs(m0),abs(m1)))
    require(all(z['mixing_ratio']==0. for z in bridges.values()),'inventory bridge unexpectedly changes mixing ratio')
    require(max_relative_carrier_gap<=8*2**-23,'carrier bridge exceeds REAL32 arithmetic-scale bound')
    # Use the original same-time history inventory; diagnostic histories are byte-matched to it.
    area=lambda n,t:sum(h.at(n,t,j,i) for j in range(2) for i in range(2))/4
    E=(area('ACLHF',284)-area('ACLHF',283))/2501000
    P=sum(area(n,284)-area(n,283) for n in ('RAINC','RAINNC'))
    observed=pack.water_inventory(h,284)-pack.water_inventory(h,283)+P-E
    terms={'PBL_return_minus_QFX':total['PBL_dry_mass']-total['QFX'],'PD_application_minus_source':total['PD_actual']-total['PD_source'],'RK_arithmetic':total['RK_arithmetic'],'micro_residual':total['micro_residual'],'QFX_minus_ACLHF':total['QFX']-E,'net_scalar_advection':total['scalar_advection']}
    terms['PBL_to_PD_source_coupling']=total['PD_source']-total['PBL_dry_mass']
    terms['recorded_inventory_bridges']=sum(sum(z.values()) for z in bridges.values())
    terms['history_vs_recorded_endpoint_carrier']=(pack.water_inventory(h,284)-pack.water_inventory(h,283))-(native_end-native_start)
    reconstructed=sum(terms.values());unexplained=observed-reconstructed
    # Bound REAL64 reductions of recorded inventories, independent of the observed residual.
    arithmetic_bound=256*2**-52*30*(abs(native_start)+abs(native_end)+1.)
    require(abs(unexplained)<=arithmetic_bound,'bounded source ledger exceeds inventory reduction bound')
    return {'interval_seconds':[84900,85200],'actual_steps':30,'quantities_kg_m2':total,'terms_kg_m2':terms,'observed_history_delta_residual_kg_m2':observed,'reconstructed_kg_m2':reconstructed,'unexplained_kg_m2':unexplained,'inventory_reduction_bound_kg_m2':arithmetic_bound,'recorded_inventory_bridges_kg_m2':bridges,'max_relative_carrier_gap':max_relative_carrier_gap,'daily_residual_approved_or_corrected':False,'isolation':'Actual sources at each evolved state; not a same-state isolated radiation-error test'}

def analyze(read,prior):
    def h(name):return pack.History(json.loads(prior('host/'+name+'.json')),prior('host/'+name+'.bin'))
    tables={ph:json.loads(prior('coefficients/'+ph+'.json')) for ph in ('lw','sw')}
    exposure={name:history_exposure(h(name),tables) for name in ('day_00','day_11')}
    for name,row in exposure.items():row['Gamma8_is_selected']=name=='day_11'
    selected=exposure['day_11']['selected_windows'];optics={}
    for target,ph in [('night_peak','lw'),('day_peak','lw'),('day_peak','sw'),('low_peak','lw'),('low_peak','sw')]:
        source={kind:parser.trace(read(f'capture/{target}/{ph}.{kind}'),kind)[1] for kind in ('raw','input','result')}
        raw,inp,original=[source[k] for k in ('raw','input','result')]
        require(raw['SOURCE_TIME_SECONDS']['values']==[selected[target]['seconds']],'selected capture clock differs')
        require(raw['RRTMGP_RESEARCH_POLICIES']['values']==[1.,1.],'wrong executed policy')
        variants={mode:parser.trace(read(f'attribution/{target}_{ph}_{mode}/{ph}.result'),'result')[1] for mode in ('baseline','omit_high','omit_low')}
        base=variants['baseline']
        for n in ('UP','DN','HR','UPC','DNC','HRC','UP_WP','DN_WP','HEAT_WP_K_S','MASK','RL_USED','CLOUD_TAU','CLOUD_SSA','CLOUD_G'):
            if n in original:require(base[n]==original[n],'public column baseline differs from actual capture '+n)
        nl=inp['LWP']['shape'][1];nn=59;rel=inp['REL']['values'];used=original['RL_USED']['values'];cf=inp['CF']['values']
        for k,q in enumerate(raw['SOURCE_QC']['values']):
            if q<=0:continue
            rho=raw['SOURCE_DRY_RHO']['values'][k];eta=raw['SOURCE_QNC']['values'][k]
            f=cf[k] if cf[k]>0 else 1.;M0=rho*eta/f;M3=3*rho*q/(4*math.pi*1000*f)
            lam=(M0*720/M3)**(1/3);M2=M0*72/lam**2
            require(parser.f32(M3/M2*1.e6)==rel[k],'same-call final Gamma8 radius differs')
        C=original['NATIVE_CAPACITY_J_M2_K']['values']
        expected=[md*1004.5*(1+parser.f32(parser.f32(461.6)/parser.f32(287.))*q) for md,q in zip(raw['DRY_LAYER_MASS_KG_M2']['values'],raw['SOURCE_QV']['values'])]
        require(C==expected,'same-call native capacity differs')

        for k in range(nl):require(used[k]==min(max(rel[k],2.5),21.5),'consumed radius is not the declared endpoint clamp')
        groups={}
        for mode,predicate in [('omit_high',lambda x:x>21.5),('omit_low',lambda x:x<2.5)]:
            z=variants[mode];_,changed=parser.trace(read(f'attribution/{target}_{ph}_{mode}/{ph}.input'),'input')
            levels=[k for k in range(nn) if predicate(rel[k])]
            for field,v in inp.items():
                if field=='LWP':
                    require(changed[field]['values']==[0. if k in levels else x for k,x in enumerate(v['values'])],'liquid removal scope differs')
                elif field=='EMIS':
                    # The diagnostic public API uses its supported grey input;
                    # the actual WRF band vector is exactly grey in these captures.
                    require(all(x==changed[field]['values'][0] for x in v['values']),'grey emissivity is not equivalent to captured band input')
                elif field in ('RAW_CLOUD_TAU','RAW_UNIFORM_TAU'):
                    # Generated cloud optics recorded in the replay bundle,
                    # not an independently prescribed physical input.
                    require(changed[field]['shape']==v['shape'],'raw cloud diagnostic shape changed')
                else:require(changed[field]==v,'unselected public input changed '+field)
            require(z['MASK']==base['MASK'],'component attribution changed sampling')
            for n in ('UPC','DNC','HRC','GAS_TAU','GAS_COL_DRY','PRECIP_TAU','PRECIP_SSA','PRECIP_G','RL_USED'):
                if n in base:require(z[n]==base[n],'component attribution changed unrelated input/result '+n)
            def max_delta(n):
                signed=[y-x for x,y in zip(base[n]['values'],z[n]['values'])];i=max(range(len(signed)),key=lambda k:abs(signed[k]));return {'max_abs':abs(signed[i]),'signed_at_max':signed[i],'flat_index':i}
            path=raw['LWP_GRID']['values'];outside=sum(path[k] for k in levels)
            prepared_moments={}
            for moment in ('ext','sca','abs','sca_g'):
                def values(v):
                    tau=v['TOTAL_TAU']['values']
                    if ph=='lw':return tau if moment in ('ext','abs') else [0.]*len(tau)
                    omega=v['TOTAL_SSA']['values'];gg=v['TOTAL_G']['values']
                    if moment=='ext':return tau
                    if moment=='sca':return [x*y for x,y in zip(tau,omega)]
                    if moment=='abs':return [x*(1-y) for x,y in zip(tau,omega)]
                    return [x*y*z for x,y,z in zip(tau,omega,gg)]
                dd=[y-x for x,y in zip(values(base),values(z))]
                prepared_moments[moment]=max(map(abs,dd))
            groups[mode]={'removed_native_levels_one_based':[k+1 for k in levels],'affected_grid_LWP_g_m2':outside,'input_REL_um':[rel[k] for k in levels],'consumed_RL_USED_um':[used[k] for k in levels],'CF':[cf[k] for k in levels],'prepared_total_gpoint_optical_moment_max_abs_change':prepared_moments,'optical_moment_stage':'LW absorption / SW prepared delta-scaled total optics; not raw single-particle optics','deltas':{n:max_delta(n) for n in ('UP','DN','HR','CLOUD_TAU','TOTAL_TAU','UNIFORM_CF0_TAU') if n in base},'not_clipping_error':True}
        optics[target+'_'+ph]={'source_seconds':selected[target]['seconds'],'groups':groups,'native_layer_count':nn,'baseline_actual_capture_equal':True}
    water={name:source_window(read('water/'+name+'.stdout'),h('day_'+name[-2:])) for name in ('window_00','window_11')}
    original=read('source/WRF/dyn_em/solve_em.F')
    for version in ('v1','v2'):
        observer=read('observer/'+version+'/solve_em.F')
        stripped=re.sub(rb'! BUDGET_OBSERVER_BEGIN\n.*?! BUDGET_OBSERVER_END\n',b'',observer,flags=re.S)
        require(stripped==original,'observer modifies code outside read-only blocks')
    passivity={}
    for name in ('night_peak','day_peak','low_peak','window_00','window_11'):
        captured=pack.History(json.loads(read('history/'+name+'.json')),read('history/'+name+'.bin'))
        baseline=h('day_00' if name=='window_00' else 'day_11')
        def clock(x):return [x.values('Times')[i:i+19] for i in range(0,len(x.values('Times')),19)]
        a,b=clock(baseline),clock(captured);common=sorted(set(a)&set(b));require(common,'missing original trajectory overlap')
        count=0
        for n,row in baseline.rows.items():
            other=captured.rows[n];require(row['shape'][1:]==other['shape'][1:],'observer/capture changed history shape')
            va=baseline.payload[row['offset']:row['offset']+row['bytes']];vb=captured.payload[other['offset']:other['offset']+other['bytes']];stride=row['bytes']//len(a)
            for time in common:
                i,j=a.index(time),b.index(time)
                require(va[i*stride:(i+1)*stride]==vb[j*stride:(j+1)*stride],'observer/capture changed physical history '+n)
            count+=1
        require(count==214,'history comparison roster differs')
        passivity[name]={'common_times':len(common),'Time_arrays_equal':count}
    return {'status':'PASS_SCOPED_LUT_CONTRIBUTION_AND_SOURCE_WINDOW','production_accepted':False,'new_model_runs_in_replay':0,'exposure':exposure,'fixed_state_optical_attribution':optics,'bounded_source_windows':water,'capture_and_observer_passivity':passivity,'decisions':{'numerical_endpoint_clamp':'RETAIN_EXISTING_RESEARCH_GUARD_NO_DEFAULT_CHANGE','outside_LUT_accuracy':'NOT_APPROVED_SIGNIFICANT_CONTRIBUTING_POPULATIONS','scientific_application_scope':'Keep in-range optical definition separate; matching-PSD independent extension or validated fallback required to claim accuracy outside [2.5,21.5] um. No extension numbers or new policy added.','component_removal':'Diagnostic attribution only; never delete these clouds in production or call the difference a clipping-error estimate.','water':'Close the selected source-attribution subtask; retain whole-day water conservation OPEN, do not extrapolate a five-minute correction.','science_gates':'Original seven conditions unchanged; no RFMIP/LBLRTM FAIL overwritten.'}}
