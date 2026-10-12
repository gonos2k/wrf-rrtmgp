"""Analyze the full native window of the already executed PR165 grids."""
import csv,io,math,struct
TARGET=618.6133629315808
H=0.003941167029890377
RATIOS={'h':1,'half':2,'quarter':4}
def require(ok,msg):
    if not ok:raise ValueError(msg)
def same(a,b,msg):require(struct.pack('<d',a)==struct.pack('<d',b),msg)
def panel(header,payload,arm):
    require(len(header)==32,'actual panel header extent')
    lo,hi,dv,n,pad=struct.unpack('<dddii',header)
    same(dv,H/RATIOS[arm],'actual native grid step')
    require(n==2400 and pad==0 and len(payload)==8*n,'actual native payload extent')
    require(all(math.isfinite(x) for x in (lo,hi,dv)) and abs(hi-(lo+(n-1)*dv))<1e-7,'actual panel coordinates')
    return lo,hi,dv,n

def init_grid(trace,step):
    a=trace.splitlines()[0].split()
    require(a[0]=='INIT' and int(a[2])==21 and int(a[3])==1 and int(a[11])==4,'actual layer21 INIT origin')
    vft,dvr3=map(float,a[12:14]);same(dvr3,16*step,'actual R3 spacing from trace')
    require(math.isfinite(vft) and round((TARGET-vft)/step)%16==0,'chosen shared R3 target alignment')
    return vft

def extract(header,payload,trace,arm):
    ratio=RATIOS[arm];lo,hi,dv,n=panel(header,payload,arm);origin=init_grid(trace,dv);out=[]
    for k in range(80*ratio+1):
        nu=TARGET+(k-40*ratio)*dv;j=round((nu-lo)/dv)
        require(0<=j<n,'native window inside saved panel')
        actual=lo+j*dv;require(abs(actual-nu)<1e-7,'actual physical native coordinate')
        x=struct.unpack_from('<d',payload,8*j)[0];require(math.isfinite(x),'finite native OD')
        index0=round((actual-origin)/dv);require(abs(origin+index0*dv-actual)<1e-7,'INIT grid alignment')
        out.append({'arm':arm,'native_row0':k,'payload_index1':j+1,'planned_nu_cm1':nu,'actual_nu_cm1':actual,'OD':x,
          'INIT_grid_index0':index0,'R3_node':index0%16==0,'R2_node':index0%4==0,'R3_phase0':index0%16,'R2_phase0':index0%4,
          'distance_to_output_panel_edge_steps':min(j,n-1-j)})
    require(len(out)==80*ratio+1 and [r['payload_index1'] for r in out]==list(range(out[0]['payload_index1'],out[-1]['payload_index1']+1)),'complete consecutive native window')
    return out

def negative_runs(rows):
    result=[];start=None
    for k,r in enumerate(rows):
        if r['OD']<0 and start is None:start=k
        if start is not None and (r['OD']>=0 or k==len(rows)-1):
            end=k-1 if r['OD']>=0 else k
            result.append({'first_native_row0':start,'last_native_row0':end,'negative_samples':end-start+1,
             'first_negative_nu_cm1':rows[start]['actual_nu_cm1'],'last_negative_nu_cm1':rows[end]['actual_nu_cm1'],
             'left_adjacent_nonnegative_nu_cm1':rows[start-1]['actual_nu_cm1'] if start else None,
             'right_adjacent_nonnegative_nu_cm1':rows[end+1]['actual_nu_cm1'] if end+1<len(rows) else None,
             'truncated_at_left_window_edge':start==0,'truncated_at_right_window_edge':end==len(rows)-1})
            start=None
    return result

def summarize(rows,arm):
    i=min(range(len(rows)),key=lambda i:rows[i]['OD']);j=max(range(len(rows)),key=lambda i:rows[i]['OD']);dv=H/RATIOS[arm]
    # Finite-window numerical trapezoids are not band fluxes or truth errors.
    signed=sum((a['OD']+b['OD'])*.5*dv for a,b in zip(rows,rows[1:]))
    negative=sum((max(-a['OD'],0)+max(-b['OD'],0))*.5*dv for a,b in zip(rows,rows[1:]))
    extrema=[]
    for k in range(1,len(rows)-1):
        a,b,c=rows[k-1]['OD'],rows[k]['OD'],rows[k+1]['OD']
        if b<a and b<c:extrema.append({'type':'sampled_minimum','native_row0':k,'nu_cm1':rows[k]['actual_nu_cm1'],'OD':b})
        elif b>a and b>c:extrema.append({'type':'sampled_maximum','native_row0':k,'nu_cm1':rows[k]['actual_nu_cm1'],'OD':b})
    return {'native_samples':len(rows),'negative_samples':sum(r['OD']<0 for r in rows),'zero_samples':sum(r['OD']==0 for r in rows),
      'minimum':{'native_row0':i,'nu_cm1':rows[i]['actual_nu_cm1'],'OD':rows[i]['OD'],'at_window_edge':i in (0,len(rows)-1)},
      'maximum':{'native_row0':j,'nu_cm1':rows[j]['actual_nu_cm1'],'OD':rows[j]['OD'],'at_window_edge':j in (0,len(rows)-1)},
      'discrete_negative_runs':negative_runs(rows),'strict_sampled_local_extrema':extrema,
      'finite_window_signed_trapezoid_cm1':signed,'finite_window_negative_part_trapezoid_cm1':negative,
      'max_abs_requested_coordinate_residual_cm1':max(abs(r['planned_nu_cm1']-r['actual_nu_cm1']) for r in rows)}

def csv_bytes(rows):
    out=io.StringIO(newline='');w=csv.DictWriter(out,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows);return out.getvalue().encode()

def comparisons(native):
    half=native['half'];fine=native['quarter'];shared=[]
    for j,a in enumerate(half):
        b=fine[2*j];same(a['planned_nu_cm1'],b['planned_nu_cm1'],'shared161 planned physical coordinate')
        require(abs(a['actual_nu_cm1']-b['actual_nu_cm1'])<1e-7,'shared161 actual coordinate')
        shared.append({'shared_row0':j,'planned_nu_cm1':a['planned_nu_cm1'],'half_actual_nu_cm1':a['actual_nu_cm1'],'quarter_actual_nu_cm1':b['actual_nu_cm1'],
          'half_OD':a['OD'],'quarter_OD':b['OD'],'signed_OD_difference':b['OD']-a['OD'],
          'half_payload_index1':a['payload_index1'],'quarter_payload_index1':b['payload_index1'],
          'half_R3_node':a['R3_node'],'quarter_R3_node':b['R3_node'],'half_R2_node':a['R2_node'],'quarter_R2_node':b['R2_node'],
          'half_R3_phase0':a['R3_phase0'],'quarter_R3_phase0':b['R3_phase0'],'half_R2_phase0':a['R2_phase0'],'quarter_R2_phase0':b['R2_phase0'],
          'half_panel_edge_distance_steps':a['distance_to_output_panel_edge_steps'],'quarter_panel_edge_distance_steps':b['distance_to_output_panel_edge_steps']})
    require(len(shared)==161,'complete shared161 grid')
    return shared

def difference_summary(rows):
    require(rows,'nonempty difference group');r=max(rows,key=lambda r:abs(r['signed_OD_difference']))
    return {'samples':len(rows),'maximum_abs_OD_difference':abs(r['signed_OD_difference']),'maximum_location':r,
      'mean_abs_OD_difference':sum(abs(r['signed_OD_difference']) for r in rows)/len(rows)}

def analyze(native,parent_result,parent_samples):
    require(set(native)==set(RATIOS),'three actual native grids')
    summaries={a:summarize(native[a],a) for a in RATIOS}
    for a,ratio in RATIOS.items():
        old=parent_samples[a];require(len(old)==81,'parent81 roster')
        for j,r in enumerate(old):same(native[a][ratio*j]['planned_nu_cm1'],r['nu'],'parent81 physical subset unchanged')
        same(min(native[a][ratio*j]['OD'] for j in range(81)),parent_result['arms'][a]['shared_window_min_OD'],'parent81 minimum preserved')
        require(sum(native[a][ratio*j]['OD']<0 for j in range(81))==parent_result['arms'][a]['shared_window_negative_samples'],'parent81 sign count unchanged')
        same(native[a][40*ratio]['OD'],parent_result['arms'][a]['target_OD'],'parent target unchanged')
    shared=comparisons(native);old=shared[::2];extra=shared[1::2]
    same(difference_summary(old)['maximum_abs_OD_difference'],parent_result['comparisons']['half->quarter']['max_shared_OD_abs_change'],'parent81 maximum preserved')
    groups={'half_R3_nodes':[r for r in shared if r['half_R3_node']],
      'half_R2_nodes_excluding_R3':[r for r in shared if r['half_R2_node'] and not r['half_R3_node']],
      'between_half_R2_nodes':[r for r in shared if not r['half_R2_node']]}
    missing=[r for r in native['quarter'] if r['native_row0']%4!=0]
    return {'status':'PASS_SCOPED_PR165_NATIVE_WINDOW_READBACK','layer':21,'IOD':2,'requested_window_cm1':[TARGET-40*H,TARGET+40*H],
      'native':summaries,'shared161_half_to_quarter':difference_summary(shared),'preserved_parent81':difference_summary(old),
      'additional_shared80':difference_summary(extra),'alignment_group_diagnostics':{k:difference_summary(v) for k,v in groups.items()},
      'quarter_points_not_in_parent81':{'samples':len(missing),'negative_samples':sum(r['OD']<0 for r in missing)},
      'max_shared_actual_coordinate_mismatch_cm1':max(abs(r['half_actual_nu_cm1']-r['quarter_actual_nu_cm1']) for r in shared),
      'fresh_solver_executions':0,'fresh_compiler_executions':0,'new_observer_insertions':0,'additional_comparison_interpolation':False,
      'direct_R1_R2_component_attribution':'NOT_ESTABLISHED_FROM_OD_ONLY',
      'boundary_claim':'Distances concern the saved OD output-panel edges; they do not independently certify every internal interpolation/carry path.',
      'negative_interval_endpoints_are_sample_brackets_not_root_estimates':True,'full_band_or_full_layer_reference_accepted':False,
      'formal_convergence_tolerance_defined':False,'physical_reference_accepted':False,'production_accepted':False},shared
