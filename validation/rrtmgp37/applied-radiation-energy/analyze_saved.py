"""Replay native radiation energy, actual source adds, and frozen YSU columns.

Uses only Python standard library; no solver runs. The energy ledger is explicitly
cp_dry * temperature-equivalent heating, not a complete atmospheric energy budget.
"""
from pathlib import Path
import json,math,struct,collections,decimal
D=decimal.Decimal;decimal.getcontext().prec=65
f32=lambda x:struct.unpack('=f',struct.pack('=f',x))[0]
def records(data):
 out=collections.defaultdict(list)
 for line in data.decode().splitlines():
  a=line.split()
  if not a:continue
  n={'EI_LW':3,'EI_SW':3,'EA_RAW':5,'EA_DRY':5,'EA_MOIST':5,'EA_APPLY':6,'EA_ADD':4,'YS_MATRIX':3,'YS_RETURN':3}.get(a[0])
  if n is not None:
   if not all(math.isfinite(float(z)) for z in a[n+1:]):raise ValueError('nonfinite record')
   out[a[0]].append((tuple(map(int,a[1:n+1])),list(map(float,a[n+1:]))))
 return out

def analyze_host(data):
 r=records(data);out={'counts':{k:len(v) for k,v in r.items()}}
 if len(r['EA_RAW'])!=6*4*59 or len(r['YS_MATRIX'])!=12*2*59:raise ValueError('case coverage')
 raw={k:v for k,v in r['EA_RAW']};dry={k:v for k,v in r['EA_DRY']};moist={k:v for k,v in r['EA_MOIST']}
 internal={};max_mapping=0;max_heat=0;max_conv=0
 calls=max(k[0] for k,v in r['EI_SW'])
 if calls not in (8,24):raise ValueError('radiation call coverage')
 call_interval=6//(calls//4);coeff={}
 for phase in ('LW','SW'):
  rr=collections.defaultdict(dict)
  for (call,c,k),v in r['EI_'+phase]:rr[call,c][k]=v
  heat_err=[]; column=[]
  for (call,c),layers in rr.items():
   # scalar column calls in actual i-fastest, j-next order. LW extends 62 layers; SW extends 1.
   step=1+((call-1)//4)*call_interval; p=(call-1)%4;i=p%2+1;j=p//2+1
   selected=[layers[k] for k in range(1,60)]
   e=math.fsum((v[0]-v[1])/v[7]*v[8]*v[6] for v in selected)
   bottom=selected[0];top=selected[-1];boundary=(bottom[2]-bottom[4])-(top[3]-top[5])
   heat_err.append(e-boundary)
   if abs(e-boundary)>1e-9:raise ValueError('native flux heat closure')
   for k,v in enumerate(selected,1):
    a=raw[step,1,i,j,k];coeff[phase,step,i,j,k]=v;expected=f32(f32(f32(v[6]*86400.)/86400.)/a[3]);actual=a[0 if phase=='LW' else 1]

    if phase=='SW':expected=f32(f32(expected+a[0])-a[0])
    max_mapping=max(max_mapping,abs(expected-actual));
    if actual!=expected:raise ValueError(('HR mapping mismatch',phase,step,i,j,k,expected,actual))
    h=(v[3]-v[2]-v[5]+v[4])*v[7]/(v[8]*(v[1]-v[0]));max_heat=max(max_heat,abs(h-v[6]))
   internal[phase,step,i,j]=boundary
   column.append({'call':call,'step':step,'i':i,'j':j,'total_RTE_layers':len(layers),'native_layers':59,'native_boundary_flux_W_m2':boundary,'pressure_heat_W_m2':e,'residual_W_m2':e-boundary})
  out[phase]={'columns':column,'max_abs_native_telescoping_residual_W_m2':max(map(abs,heat_err))}
 # exact REAL32 arithmetic check of theta_m conversion, including moisture term separately from radiation.
 for key,a in dry.items():
  b=moist[key];t,qt,q,th,radc,rvrd=a
  factor=f32(1.+f32(rvrd*q));other=f32(f32(f32(rvrd*f32(th+300.))/factor)*qt)
  expected=f32(f32(factor*t)+other)
  max_conv=max(max_conv,abs(expected-b[0]))
  if expected!=b[0]:raise ValueError(('theta_m',key,expected,b[0]))
 # Actual accepted RK3 acoustic source-add interval. RK1/2 predictors explicitly excluded.
 radiation_rows=collections.defaultdict(lambda:collections.defaultdict(float))
 if len(r['EA_APPLY'])!=len(r['EA_ADD']):raise ValueError('source-add correspondence')
 duration=collections.defaultdict(float);maxround=0
 for (key,v),(akey,b) in zip(r['EA_APPLY'],r['EA_ADD']):
  step,rk,it,i,j,k=key
  if akey!=(it,i,j,k) or v[0]!=b[2] or v[3]!=b[4] or v[4]!=b[3]:raise ValueError('actual source add ledger alignment')
  # Actual total ft operation; inline read-only radiation ledger is an additive component, not full state difference.
  expected=f32(b[0]+f32(f32(b[3]*b[4])*b[2]))
  if expected!=b[1]:raise ValueError('actual source add arithmetic')
  maxround=max(maxround,abs((b[1]-b[0])-b[3]*b[4]*b[2]))
  if rk!=3:continue
  a=raw[step,1,i,j,k];factor=f32(1.+f32(a[10]*a[6]));expected_rad=f32(factor*f32(a[4]*a[2]));
  if v[1]!=expected_rad:raise ValueError('held radiation source changed')
  # Reversing current mass/theta_m conversion to its temperature-equivalent dry-air energy ledger.
  M=a[4];md=-M*a[5]/a[8];Tdot=v[1]/M/factor*a[3]
  if k==1:duration[step,i,j]+=v[3]
  source_step=1+((step-1)//call_interval)*call_interval
  cl=coeff['LW',source_step,i,j,k];cs=coeff['SW',source_step,i,j,k]
  if cl[:2]!=cs[:2] or cl[7:9]!=cs[7:9] or cl[7:9]!=[a[8],a[9]]:
   raise ValueError('LW SW native pressure or constants mismatch')
  mp=(cl[0]-cl[1])/cl[7]
  ep=mp*cl[8]*Tdot
  eh=mp*cl[8]*(cl[6]+cs[6])
  rr=radiation_rows[step,i,j];rr['current_dry_mass_applied_J_m2']+=md*a[9]*Tdot*v[3]
  # Local counterfactual source-add rounding diagnostic. It is not an independently evolved trajectory.
  no_rad_ft=f32(b[2]-f32(v[1]/v[4]));no_rad_t=f32(b[0]+f32(f32(b[3]*b[4])*no_rad_ft))
  marginal_T=(b[1]-no_rad_t)/M/factor*a[3]
  rr['local_REAL32_marginal_radiation_J_m2']+=md*a[9]*marginal_T
  bound=(abs(b[0])+abs(b[1])+abs(no_rad_t)+abs(b[3]*b[4]*b[2])+abs(b[3]*b[4]*no_rad_ft))*8*2**-24
  rr['local_source_add_rounding_envelope_J_m2']+=md*a[9]*bound/M/factor*a[3]
  rr['call_pressure_mass_applied_J_m2']+=ep*v[3]
  rr['RTE_internal_heat_J_m2']+=eh*v[3]
  if k==1:
   rr['source_step']=source_step;rr['duration_s']+=v[3]
   rr['native_boundary_flux_J_m2']+=(internal['LW',source_step,i,j]+internal['SW',source_step,i,j])*v[3]
   rr['pi_current_over_pi_call']=a[3]/raw[source_step,1,i,j,1][3]
 for key,dt in duration.items():
  step,i,j=key
  if abs(dt-raw[step,1,i,j,1][7])>1e-6:raise ValueError('RK3 accepted duration')
 rows=[{'step':st,'i':i,'j':j,**dict(v)} for (st,i,j),v in sorted(radiation_rows.items())]
 out['adapter']={'max_abs_kday_ks_theta_mapping_error':max_mapping,'max_abs_internal_heat_formula_error_K_s':max_heat,'max_abs_theta_m_REAL32_replay_error':max_conv,'max_abs_total_source_add_roundoff_coupled_theta':maxround,'accepted_RK3_rows':rows,'radiation_call_interval_steps':call_interval,'all_RK3_durations_s':sorted(set(duration.values())),'predictor_stages_counted_as_physical_time':False,'energy_definition':'dry layer mass * cp_dry * frozen-physics-Exner/qv temperature-equivalent radiation source component; excludes pressure work and whole thermodynamic energy'}
 # YSU captured coefficients use actual al storage k -> lower diagonal row k+1 (sequence association in tridin).
 matrices=collections.defaultdict(dict);returns=collections.defaultdict(dict)
 for (call,i,k),v in r['YS_MATRIX']:matrices[call,i][k]=v
 for (call,i,k),v in r['YS_RETURN']:returns[call,i][k]=v
 ys=[]
 for key,col in sorted(matrices.items()):
  v=[col[k] for k in sorted(col)];n=len(v);low=[D(0)]+[D.from_float(z[0]) for z in v[:-1]];diag=[D.from_float(z[1]) for z in v];up=[D.from_float(z[2]) for z in v];rhs=[D.from_float(z[3]) for z in v];q0=[D.from_float(z[4]) for z in v];w=[D.from_float(z[5])/D.from_float(z[7]) for z in v];dt2=D.from_float(v[0][6]);qfx=D.from_float(v[0][8]);g=D.from_float(v[0][7]);
  # Thomas solve of frozen REAL32 coefficients in 65-digit Decimal, independent of original Fortran solve.
  a=diag.copy();f=rhs.copy()
  for k in range(1,n):
   z=low[k]/a[k-1];a[k]-=z*up[k-1];f[k]-=z*f[k-1]
  x=[D(0)]*n;x[-1]=f[-1]/a[-1]
  for k in range(n-2,-1,-1):x[k]=(f[k]-up[k]*x[k+1])/a[k]
  # Replay original REAL32 Thomas operations too; Decimal changes solve precision only.
  au32=[0.]*n;f32x=[0.]*n
  fk=f32(1./float(diag[0]));au32[0]=f32(fk*float(up[0]));f32x[0]=f32(fk*float(rhs[0]))
  for kk in range(1,n):
   fk=f32(1./f32(float(diag[kk])-f32(float(low[kk])*au32[kk-1])))
   if kk<n-1:au32[kk]=f32(fk*float(up[kk]))
   f32x[kk]=f32(fk*f32(float(rhs[kk])-f32(float(low[kk])*f32x[kk-1])))
  for kk in range(n-2,-1,-1):f32x[kk]=f32(f32x[kk]-f32(au32[kk]*f32x[kk+1]))
  ret=[returns[key][k] for k in range(1,n+1)]
  if any(f32x[kk]!=ret[kk][0] for kk in range(n)):raise ValueError('YSU REAL32 solve replay')
  xr=[D.from_float(z[0]) for z in ret];tend=[D.from_float(z[1]) for z in ret]
  balance=[w[k]*(diag[k]-1)+(w[k-1]*up[k-1] if k else 0)+(w[k+1]*low[k+1] if k<n-1 else 0) for k in range(n)]
  source=sum(wk*(b-q) for wk,b,q in zip(w,rhs,q0))/dt2
  exact=sum(wk*(b-q) for wk,b,q in zip(w,x,q0))/dt2
  real=sum(wk*(b-q) for wk,b,q in zip(w,xr,q0))/dt2
  returned=sum(wk*t for wk,t in zip(w,tend))
  # analytic intended source w1 * g/del1 == 1 and sfk==vlk==1, no BEP in this case.
  wb=w[0]*g/D.from_float(v[0][5]);
  if any(z[9]!=0 or z[10]!=0 or z[11]!=0 or z[12]!=1 or z[13]!=1 for z in v):raise ValueError('outside non-BEP proof')
  predicted_operator=-sum(z*xx for z,xx in zip(balance,x))/dt2
  if abs((exact-source)-predicted_operator)>D('1e-55'):raise ValueError('weighted matrix defect identity')
  coefficient_envelope=[D.from_float(8*2**-24)*(abs(w[k]*diag[k])+abs(w[k])+(abs(w[k-1]*up[k-1]) if k else 0)+(abs(w[k+1]*low[k+1]) if k<n-1 else 0)) for k in range(n)]
  if any(abs(z)>bd for z,bd in zip(balance,coefficient_envelope)):raise ValueError('matrix outside local coefficient rounding envelope')
  ys.append({'call':key[0], 'predicted_frozen_operator_defect_kg_m2_s':float(predicted_operator),'coefficient_rounding_envelope_kg_m2':float(max(coefficient_envelope)),'i':key[1],'QFX_kg_m2_s':float(qfx),'wT_b':float(wb),'max_abs_wT_M_minus_w_kg_m2':float(max(map(abs,balance))),'RHS_minus_QFX_kg_m2_s':float(source-qfx),'frozen_matrix_minus_RHS_kg_m2_s':float(exact-source),'REAL32_solve_minus_decimal65_kg_m2_s':float(real-exact),'tendency_return_minus_REAL32_solution_kg_m2_s':float(returned-real),'total_pressure_source_minus_QFX_kg_m2_s':float(returned-qfx),'decimal_solution_max_abs_q_difference':float(max(abs(a-b) for a,b in zip(x,xr)))})
 # Cumulative pieces are for kernel water-vapor, with its own pressure at matrix assembly.
 # They do not silently replace host post-PBL qv+qc / later p8w inventories from PR177.
 out['YSU']={'columns':ys,'conservation_contract':'w=delta total pressure/g; ideal unrounded pairwise diffusion preserves w; captured REAL32 matrix, solver and return separately assessed','physical_dry_mass_approval':False,'temperature_and_cloud_equations_certified':False,'kernel_qv_only_not_PR177_total_qv_qc_pressure_inventory':True}
 return out


def analyze(read):
 out={'production_accepted':False,'physics_gates_closed':False,'host':{}}
 for name,idx in [('on',2),('held30s',3)]:
  a=analyze_host(read(f'host/command-{idx:02d}.stdout'))
  rows=a['adapter']['accepted_RK3_rows']
  keys=['native_boundary_flux_J_m2','RTE_internal_heat_J_m2','call_pressure_mass_applied_J_m2','current_dry_mass_applied_J_m2','local_REAL32_marginal_radiation_J_m2','local_source_add_rounding_envelope_J_m2']
  totals={k:math.fsum(z[k] for z in rows)/4 for k in keys}
  totals['pressure_adapter_minus_native_flux_J_m2']=totals['call_pressure_mass_applied_J_m2']-totals['native_boundary_flux_J_m2']
  totals['dry_mass_minus_call_pressure_mass_J_m2']=totals['current_dry_mass_applied_J_m2']-totals['call_pressure_mass_applied_J_m2']
  totals['local_marginal_minus_additive_ledger_J_m2']=totals['local_REAL32_marginal_radiation_J_m2']-totals['current_dry_mass_applied_J_m2']
  if abs(totals['local_marginal_minus_additive_ledger_J_m2'])>totals['local_source_add_rounding_envelope_J_m2']:raise ValueError('actual local source rounding exceeds conservative envelope')
  # This tolerance bounds observed REAL32 K/day/theta conversions only. It is not
  # permission to relabel the dry/pressure mass difference as roundoff.
  if name=='on' and abs(totals['pressure_adapter_minus_native_flux_J_m2'])>.0001:raise ValueError('adapter pressure reference closure')
  a['summary']=totals
  pieces=['RHS_minus_QFX_kg_m2_s','frozen_matrix_minus_RHS_kg_m2_s','REAL32_solve_minus_decimal65_kg_m2_s','tendency_return_minus_REAL32_solution_kg_m2_s','total_pressure_source_minus_QFX_kg_m2_s']
  a['YSU']['kernel_qv_60s_totals_kg_m2']={k:math.fsum(z[k] for z in a['YSU']['columns'])*10/4 for k in pieces}
  out['host'][name]=a
 # Reuse historical signed arrays. No Mie or RTE process is launched here.
 import importlib.util
 root=Path(__file__).resolve().parents[3]
 spec=importlib.util.spec_from_file_location('retained_trace',root/'validation/rrtmgp37/radiation-occurrence-runtime/verify_saved.py');parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
 states={}
 for shape in [8,16]:
  for mode in ['LUT','NIR_Mie']:
   _,states[shape,mode]=parser.trace(read(f'prior-PSD/sw-s{shape}-{mode}/sw.result'),'result')
 interaction={}
 for field in ['UP','DN','HR']:
  values={key:v[field]['values'] for key,v in states.items()}
  shapes=[v[field]['shape'] for v in states.values()]
  if any(s!=shapes[0] for s in shapes):raise ValueError('interaction shape')
  d=[(a-b)-(c-e) for a,b,c,e in zip(values[16,'NIR_Mie'],values[8,'NIR_Mie'],values[16,'LUT'],values[8,'LUT'])]
  idx=max(range(len(d)),key=lambda i:abs(d[i]))
  interaction[field]={'shape':list(shapes[0]),'interaction_signed':d,'max_abs':abs(d[idx]),'signed_at_max':d[idx],'fortran_flat_index_1based':idx+1,'units':'K/day' if field=='HR' else 'W/m2'}
 out['PSD_interaction']=interaction
 out['decisions']={
  'radiation_internal_native_flux_heating':'CLOSED_SCOPED_AT_WP_PRESSURE_MASS_CP_DRY',
  'Kday_theta_THM_RK_source_add':'CLOSED_SCOPED_EXACT_REAL32_REPLAY_WITH_ACCEPTED_STAGE_TIME_LEDGER',
  'dry_mass_temperature_equivalent_energy':'NOT_CLOSED_TOTAL_PRESSURE_HEATING_MASS_DIFFERS_FROM_WRF_DRY_MASS',
  'radiation_held_tendency':'THETA_TENDENCY_HELD_EXACTLY_TEMPERATURE_EQUIVALENT_CHANGES_WITH_PI',
  'production_heating_correction':'NOT_APPLIED_HEAT_CAPACITY_AND_ENERGY_CONTRACT_REQUIRES_EXPLICIT_DECISION',
  'YSU_fixed_column':'SCOPED_PRESSURE_WEIGHT_CONTRACT_AND_REAL32_MATRIX_SOLVE_RETURN_SEPARATED',
  'YSU_host_dry_water_physical_approval':False,
  'PSD':'RETAIN_GAMMA8_RESEARCH_BASE_GAMMA16_SENSITIVITY_ONLY',
  'PSD_optical_or_observational_approval':False,
  'full_atmospheric_energy':'OPEN',
  'RFMIP_LBLRTM':'EXISTING_FAIL_UNCHANGED'}
 return out

if __name__=='__main__':
 import gzip,json
 B=Path(__file__).resolve().parent
 def read(n):
  if n.startswith('prior-PSD/'):
   p=B.parent/'host-source-fixed-psd/saved/psd'/(n[len('prior-PSD/'):]+'.gz')
  else:p=B/'saved'/(n+'.gz')
  return gzip.decompress(p.read_bytes())
 print(json.dumps(analyze(read),indent=2))
