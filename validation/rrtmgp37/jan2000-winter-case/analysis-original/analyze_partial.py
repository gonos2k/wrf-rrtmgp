#!/usr/bin/env python3
"""Read-only statistics from the preserved January paired forecast artifacts."""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[4]
PAIR = ROOT / "build/udm-alternate-jan2000-data/paired-forecast-v2"
OUT = Path(__file__).resolve().parent
FATAL = "LW i=17 j=58: RRTMGP_INPUT_UDM_QI_NEGATIVE value_kgkg=-5.623554244493789E-008 limit_kgkg= 9.999999960041972E-013 layer=7"
FATAL_TIME = "2000-01-24_14:50:00"
SUSPECT = {"i_fortran":17,"j_fortran":58,"k_fortran":7}
QFIELDS = ["QCLOUD","QICE","QRAIN","QSNOW","QGRAUP","QHAIL"]
NFILES = ["QNCCN","QNCLOUD","QNRAIN"]
G = 9.81

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()

def read_times(ds):
 return [b''.join(np.asarray(row).tolist()).decode('ascii').rstrip('\x00 ') for row in ds['Times'][:]]

def record_stats(ds, qname, ti, dm):
 a=np.asarray(ds[qname][ti])
 neg=a<0
 where=np.argwhere(neg)
 minloc=None
 if where.size:
  k,j,i=map(int,where[np.argmin(a[neg])])
  minloc={'i_fortran':i+1,'j_fortran':j+1,'k_fortran':k+1,'value_kgkg':float(a[k,j,i]),'drymass_kg_m2':float(dm[k,j,i]),'grid_path_g_m2':float(a[k,j,i]*dm[k,j,i]*1000.)}
 neg_path=np.abs(a[neg]*dm[neg]*1000.)
 return {'negative_cells':int(neg.sum()),'minimum_kgkg':float(np.min(a)),'maximum_kgkg':float(np.max(a)),
         'maximum_absolute_kgkg':float(np.max(np.abs(a))),'minimum_location':minloc,
         'negative_gridcell_path_abs_sum_g_m2_unweighted':float(np.sum(neg_path)),
         'negative_gridcell_path_abs_max_g_m2':float(np.max(neg_path)) if neg_path.size else 0.0}

def drymass_reconstruction(ds,ti):
 # Same hybrid-coordinate identity used at the real radiation call:
 # -DNW(k)*(C1H(k)*MUT(i,j)+C2H(k))/g. At archived history timestamps,
 # reconstruct MUT as MU+MUB. This is a snapshot estimate, not the exact
 # intermediate MUT buffer from the 14:50 radiation call.
 dnw=np.asarray(ds['DNW'][ti],dtype=np.float64)
 c1=np.asarray(ds['C1H'][ti],dtype=np.float64)
 c2=np.asarray(ds['C2H'][ti],dtype=np.float64)
 mu=np.asarray(ds['MU'][ti],dtype=np.float64)
 mub=np.asarray(ds['MUB'][ti],dtype=np.float64)
 dm=-dnw[:,None,None]*(c1[:,None,None]*(mu+mub)[None,:,:]+c2[:,None,None])/G
 closure=dm.sum(axis=0)/((mu+mub)/G)
 return dm, {'min_kg_m2':float(dm.min()),'max_kg_m2':float(dm.max()),
              'column_closure_ratio_median':float(np.median(closure)),
              'column_closure_ratio_max_abs_error':float(np.max(np.abs(closure-1.0))),
              'formula':'-DNW*(C1H*(MU+MUB)+C2H)/9.81; approximates timestep MUT by saved MU+MUB'}

def series(path,mode):
 records=[]
 with Dataset(path) as ds:
  times=read_times(ds)
  for ti,t in enumerate(times):
   dm,dmstat=drymass_reconstruction(ds,ti)
   entry={'time':t,'dry_layer_mass_reconstruction':dmstat,'species':{}}
   for qn in QFIELDS:
    entry['species'][qn]=record_stats(ds,qn,ti,dm)
   for qn in NFILES:
    a=np.asarray(ds[qn][ti]); neg=a<0
    loc=None
    if np.any(neg):
     idx=np.argwhere(neg)[np.argmin(a[neg])]; k,j,i=map(int,idx)
     loc={'i_fortran':i+1,'j_fortran':j+1,'k_fortran':k+1,'value':float(a[k,j,i])}
    entry['species'][qn]={'negative_cells':int(neg.sum()),'minimum':float(np.min(a)),'maximum':float(np.max(a)),'minimum_location':loc}
   if t=='2000-01-25_12:00:00' or mode=='ra37':
    entry['fatal_neighborhood_14_00'] = None
   records.append(entry)
  # last available state before the fatal: 14:00 history, no 14:50 history exists.
  target='2000-01-24_14:00:00'
  if target in times:
   ti=times.index(target); dm,_=drymass_reconstruction(ds,ti)
   values={}
   j0=SUSPECT['j_fortran']-1; i0=SUSPECT['i_fortran']-1; k0=SUSPECT['k_fortran']-1
   for qn in QFIELDS+NFILES+['QVAPOR','CLDFRA','T','P','PB','MU','MUB']:
    if qn not in ds.variables: continue
    v=np.asarray(ds[qn][ti])
    if v.ndim==3:
     values[qn]={'at_fatal_cell_last_output':float(v[k0,j0,i0]),
                 '3x3_k7_one_based':[{ 'i':i+1,'j':j+1,'v':float(v[k0,j,i])}
                    for j in range(max(0,j0-1),min(v.shape[1],j0+2))
                    for i in range(max(0,i0-1),min(v.shape[2],i0+2))]}
    elif v.ndim==2:
     values[qn]={'at_fatal_cell_last_output':float(v[j0,i0]),
                 '3x3':[{ 'i':i+1,'j':j+1,'v':float(v[j,i])}
                    for j in range(max(0,j0-1),min(v.shape[0],j0+2))
                    for i in range(max(0,i0-1),min(v.shape[1],i0+2))]}
   entry={'history_time':'2000-01-24_14:00:00','relative_to_fatal_time':'50 minutes before failure; not contemporaneous with fatal input',
          'fatal_cell':SUSPECT,'variables':values}
   records[times.index(target)]['fatal_neighborhood_14_00']=entry
  return {'history_path':str(path),'history_sha256':sha(path),'times':times,'records':records}

def parse_corrected_logs():
 pat=re.compile(r'^(LW|SW) RRTMGP_UDM_NEGATIVE_INPUT_CORRECTED species=(\w+) layers=(\d+) sum_grid_correction_g_m2=\s*([+-]?\d+(?:\.\d*)?[Ee][+-]?\d+) max_abs_q_kgkg=\s*([+-]?\d+(?:\.\d*)?[Ee][+-]?\d+) limit_kgkg=\s*([+-]?\d+(?:\.\d*)?[Ee][+-]?\d+)')
 agg={}
 fatal=[]
 for p in sorted((PAIR/'ra37').glob('rsl.error.*')):
  text=p.read_text(errors='replace')
  for line_no,line in enumerate(text.splitlines(),1):
   m=pat.match(line)
   if m:
    phase,sp,lay,path,mx,lim=m.groups(); key=f'{phase}_{sp}'; d=agg.setdefault(key,{'messages':0,'reported_layers_sum':0,'grid_correction_sum_g_m2_sum_of_column_messages':0.0,'max_abs_q_kgkg':0.0,'limit_kgkg':float(lim),'max_ratio_to_limit':0.0})
    d['messages']+=1;d['reported_layers_sum']+=int(lay);d['grid_correction_sum_g_m2_sum_of_column_messages']+=float(path);d['max_abs_q_kgkg']=max(d['max_abs_q_kgkg'],float(mx));d['max_ratio_to_limit']=max(d['max_ratio_to_limit'],float(mx)/float(lim))
   if 'RRTMGP_INPUT_UDM_QI_NEGATIVE' in line:
    prev=text.splitlines()[line_no-2] if line_no>=2 else ''
    fatal.append({'rank_log':p.name,'line_number':line_no,'fatal_line':line,'previous_log_line':prev,'log_sha256':sha(p)})
 return agg,fatal

r4path=next((PAIR/'ra4').glob('wrfout_d01_*'))
r37path=next((PAIR/'ra37').glob('wrfout_d01_*'))
ra4=series(r4path,'ra4'); ra37=series(r37path,'ra37')
corrections,fatals=parse_corrected_logs()
# Find exact modeled timestamp adjacent to fatal from rank 2's log.
r2=(PAIR/'ra37/rsl.error.0002').read_text(errors='replace')
idx=r2.find('RRTMGP_INPUT_UDM_QI_NEGATIVE')
before=r2[:idx].splitlines()[-5:]
# Combine only contemporaneous last saved state at 14:00 for machine-readable comparison.
def findrec(case,t):return next(x for x in case['records'] if x['time']==t)
comp={}
for qn in QFIELDS+NFILES:
 comp[qn]={'ra4_14_00':findrec(ra4,'2000-01-24_14:00:00')['species'][qn],
          'ra37_14_00':findrec(ra37,'2000-01-24_14:00:00')['species'][qn]}
# Compact whole-record summaries retain each hourly (RA4) and partial (RA37) record above.
def all_record_summary(case):
    result={}
    for qn in QFIELDS+NFILES:
        vals=[rec['species'][qn] for rec in case['records']]
        mins=[float(v['minimum_kgkg'] if 'minimum_kgkg' in v else v['minimum']) for v in vals]
        maxabs=[float(v['maximum_absolute_kgkg']) if 'maximum_absolute_kgkg' in v else max(abs(float(v['minimum'])),abs(float(v['maximum']))) for v in vals]
        imin=int(np.argmin(mins))
        result[qn]={
          'record_count':len(vals),
          'times':case['times'],
          'negative_cells_each_record':[v['negative_cells'] for v in vals],
          'total_negative_cell_records':int(sum(v['negative_cells'] for v in vals)),
          'minimum_over_records':mins[imin],
          'maximum_absolute_over_records':float(max(maxabs)),
          'minimum_record_and_location':{'time':case['records'][imin]['time'],'location':vals[imin]['minimum_location']}
        }
    return result

source_root=ROOT/'build/udm-frozen-runtime-wrf/source/WRF'
source_files=[source_root/'dyn_em/solve_em.F',source_root/'dyn_em/module_first_rk_step_part1.F',source_root/'phys/module_mp_udm.F',source_root/'phys/module_ra_rrtmgp_input.F',source_root/'phys/module_ra_rrtmg_lw.F']
source_hashes={str(p.relative_to(ROOT)):sha(p) for p in source_files}
ra37_target=findrec(ra37,'2000-01-24_14:00:00')['fatal_neighborhood_14_00']
ra4_target=findrec(ra4,'2000-01-24_14:00:00')['fatal_neighborhood_14_00']
def cell_mass_near(target):
    q=target['variables']['QICE']['at_fatal_cell_last_output']
    # Approximate path uses the 14:00 archived dry-layer mass at the fatal location,
    # not a reconstruction of the unavailable 14:50 radiation input.
    record=findrec(ra37,'2000-01-24_14:00:00')
    # Locate matching per-column reconstructed mass from history directly.
    with Dataset(r37path) as ds:
        ti=read_times(ds).index('2000-01-24_14:00:00')
        dm,_=drymass_reconstruction(ds,ti)
        k,j,i=SUSPECT['k_fortran']-1,SUSPECT['j_fortran']-1,SUSPECT['i_fortran']-1
        d=float(dm[k,j,i])
    return {'qice_14_00_kgkg':q,'estimated_dry_layer_mass_14_00_kg_m2':d,'estimated_grid_path_from_saved14_00_state_g_m2':q*d*1000.0,'fatal_value_times_saved14_00_dry_mass_g_m2':-5.623554244493789e-8*d*1000.0,'warning':'14:00 q and reconstructed 14:00 dry mass; not the unavailable 14:50 fatal-call state'}
run_receipt_path=PAIR/'run-receipt.json'
run_receipt=json.loads(run_receipt_path.read_text())
pair_plan=json.loads((PAIR/'pair-plan.json').read_text())
summary={'status':'READ_ONLY_FATAL_CAUSALITY_ANALYSIS','forecast_claim':'RA4 completed; RA37 partial and failed; no physical accuracy comparison implied',
 'fatal':{'exact_line':FATAL,'rank':'rsl.error.0002','model_time_from_driver_log':FATAL_TIME,'failure_after_minutes_from_start':170,
          'fatal_species':'QICE (builder label QI)','fatal_cell_fortran_1based':SUSPECT,
          'fatal_mixing_ratio_kgkg':-5.623554244493789e-8,'allowed_native_negative_only_limit_kgkg':9.999999960041972e-13,
          'fatal_magnitude_over_limit':5.623554244493789e4,'latest_hourly_state_before_fatal':'2000-01-24_14:00:00'},
 'time_14_00_all_species_comparison':comp,
 'whole_run_species_summary':{'ra4':all_record_summary(ra4),'ra37_partial':all_record_summary(ra37)},
 'fatal_cell_nearest_saved_state':{'ra37':cell_mass_near(ra37_target),'ra4_14_00':ra4_target['variables']['QICE']['at_fatal_cell_last_output']},
 'source_sha256':source_hashes,
 'experiment_provenance':{'run_receipt_sha256':sha(run_receipt_path),'run_status':run_receipt.get('status'),'errors':run_receipt.get('errors'), 'arms':{name:{'status':data.get('status'),'returncode':data.get('returncode'),'fatal_marker':data.get('fatal_marker'),'success_ranks':data.get('success_ranks')} for name,data in run_receipt.get('arms',{}).items()},'wrf_executable_sha256':pair_plan.get('wrf_executable_sha256'),'source_commit':pair_plan.get('source_commit'),'common_input_sha256':run_receipt.get('input_sha256',{}).get('ra4',{}).get('wrfinput'),'common_boundary_sha256':run_receipt.get('input_sha256',{}).get('ra4',{}).get('wrfbdy'),'engine_specific_namelist_sha256':{name:data.get('namelist') for name,data in run_receipt.get('input_sha256',{}).items()},'table_sha256':next((v for k,v in run_receipt.get('pins_before',{}).items() if k.endswith('frozen-ice-psd-moments.nc')),None)},
 'ra4':ra4,'ra37_partial':ra37,
 'ra37_correction_log_summary':corrections,
 'fatal_log_rows':fatals,'rank2_log_lines_before_fatal':before,
 'field_semantics':{'QFIELDS':'WRF hydrometeor mass mixing ratios kg water per kg dry air; the radiation builder validates these directly before path conversion.','number_fields':{'QNCCN':'Registry unit # kg(-1), CCN scalar passed directly to UDM','QNCLOUD':'Registry unit # kg(-1), scalar passed directly to UDM','QNRAIN':'Registry unit # kg(-1), scalar passed directly to UDM'},'number_handling':'UDM local ncr uses nonnegative clamping, with CCN bounds; adjust_number_concent uses den in the size relation. The RRTMGP cloud builder does not take number concentrations; do not infer or silently convert stored number-field units from this QI failure.'},
 'source_order':{'radiation_call':'WRF/phys/module_first_rk_step_part1.F; called from solve_em.F in first non-timesplit physics step around line 812.','microphysics_call':'solve_em.F around line 3881 calls microphysics_driver later in the timestep. Thus the failing radiation input is the current prognostic state before this timestep\'s UDM microphysics clipping; this locates the guard relative to microphysics but does not assign the negative to a unique dynamical process.','UDM_microphysics_negative_handling':'module_mp_udm.F flgzero=.true. and comments that dynamics-generated negatives are padded to zero in udm2d local qci/qrs arrays; it copies max(q,0) before microphysical calculations and writes updated local fields back. This occurs after the radiation call in the per-step order.', 'radiation_contract':'module_ra_rrtmgp_input.F applies strict negative input checks by species, with bounded correction only for q in (-limit,0); observed QI magnitude is far outside 1e-12. Radiation builder receives copied hydrometeor arrays; it cannot correct or mutate the host prognostic q.'},
 'dry_layer_mass_estimate':{'source_formula_file_line':'WRF/dyn_em/module_first_rk_step_part1.F:285-286','source_formula':'udm_dry_layer_mass = -DNW*(C1H*MUT + C2H)/g; archived reconstruction uses MU+MUB for MUT and g=9.81, validated by column-sum closure ratio near 1.','caveat':'The 14:50 intermediate MUT buffer and QI are not written to hourly history. Hourly outputs provide the immediately prior 14:00 state only; use for neighborhood/statistical context, not exact fatal-input reconstruction.'},
 'artifacts':{'analysis_script_sha256':sha(Path(__file__)), 'ra4_history_sha256':sha(r4path),'ra37_partial_history_sha256':sha(r37path),'ra4_rank_log_sha256':{p.name:sha(p) for p in sorted((PAIR/'ra4').glob('rsl.error.*'))},'ra37_rank_log_sha256':{p.name:sha(p) for p in sorted((PAIR/'ra37').glob('rsl.error.*'))},'run_receipt_sha256':sha(PAIR/'run-receipt.json')},
 'interpretation':'This is a pre-microphysics radiation-input failure at 14:50, after prior integration updates, not evidence that radiation created the negative QI. The preceding 14:00 archived state and earlier within-limit radiation corrections do not identify the process that produced the 14:50 value. No threshold or physics setting was altered.'}
(OUT/'causality-analysis.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
print(json.dumps({'status':summary['status'],'ra4_times':len(ra4['times']),'ra37_times':len(ra37['times']),'fatal_rows':len(fatals),'correction_groups':len(corrections),'json':str(OUT/'causality-analysis.json')},indent=2))
