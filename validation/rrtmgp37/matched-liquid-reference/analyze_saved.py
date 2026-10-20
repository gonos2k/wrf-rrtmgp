"""Replay executed component reference and direct target uncertainties, stdlib only."""
import importlib.util,json,math,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
s=importlib.util.spec_from_file_location('endpoint_analysis',ROOT/'validation/rrtmgp37/liquid-endpoint-optics/analyze_saved.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
require,close=a.require,a.close
M=a.MOMENTS;CASES=a.CASES;GRIDS=('fine','radius_half','spectral_half')

def axis_pass(grids,screen):
 f=grids['fine']
 return all(all(abs(f[k]-grids[x][k])<=screen['coefficient_relative_axis_change']*max(abs(f[k]),screen['coefficient_scale_floor_m2_g']) for k in M) and abs(f['g']-grids[x]['g'])<=screen['g_absolute_axis_change'] for x in GRIDS[1:])
def values(fields,native_top=59):
 require(native_top==59,'native-top boundary must be59, not extended TOA')
 u=fields['UP_WP']['values'];d=fields['DN_WP']['values'];net=[y-x for x,y in zip(u,d)]
 out={f'{boundary}_{name}_W_m2':[arr[k]] for boundary,k in [('surface',0),('native_top',native_top)] for name,arr in [('up',u),('down',d),('net_down',net)]}
 out['native_column_convergence_W_m2']=[net[native_top]-net[0]]
 out['native_heating_K_day']=[v*86400 for v in fields['HEAT_WP_K_S']['values'][:59]]
 return out

def difference(x,y):return [v-w for v,w in zip(x,y)]
def maximum(v):return max(map(abs,v))
def target_report(allvalues,old,plan):
 report={};ok=True
 for key,f in allvalues['fine'].items():
  diff={axis:difference(f,allvalues[axis][key]) for axis in GRIDS[1:]}
  threshold=plan['predeclared_numerical_screens']['transport_refinement_heating_K_day' if 'heating' in key else 'transport_refinement_flux_W_m2']
  passed=all(maximum(v)<=threshold for v in diff.values());ok=ok and passed
  report[key]={'fine':f,'method_correction_from_PR183':difference(f,old[key]),'signed_axis_changes':diff,'empirical_axis_sum_estimate':[sum(abs(diff[x][i]) for x in GRIDS[1:]) for i in range(len(f))],'max_axis_change':max(maximum(v) for v in diff.values()),'numerical_screen_passed':passed,'certified_true_error_bound':None}
 return report,ok

def analyze(read,prior,plan):
 ref=json.loads(read('mie/result.json'));controls=json.loads(read('mie/definition-controls.json'));cross=json.loads(read('mie/cross-result.json'))
 require(ref['completed'] and cross['completed'],'incomplete reference')
 require(ref['plan_sha256']==hashlib.sha256(read('executed/plan.json')).hexdigest(),'pre-execution plan binding')
 require(json.loads(read('mie/plan.json'))==plan,'declared definition changed')
 require(ref['water_sha256']==hashlib.sha256(read('water/Segelstein.yml')).hexdigest(),'material input changed')
 close(controls['density_only_actual_ratio_996_over1000'],1000/996,'density normalization control',1e-13)
 close(controls['matched_reconstructed_reff_um'],12.,'definition control reff',1e-12)
 require(controls['high_level_medium_API_matches_cross_sections'] and controls['no_constructor_projection'],'definition control failed')
 require(not controls['moment_g_control']['mean_g_is_used_in_reference'],'incorrect band g definition')
 require(abs(controls['moment_g_control']['sca_weighted']-controls['moment_g_control']['mean_g'])>1e-3,'ineffective g control')
 for ctrl in ref['medium_controls']:
  for x,y in zip(ctrl['high_level'],ctrl['relative_m_and_x']):close(x,y,'medium conventions',1e-12)
 records=ref['records'];require(len(records)==16 and len(cross['records'])==16,'selected reference coverage')
 require(sum(r['role']=='primary' for r in records)==14,'primary subset coverage')
 rows=[];index={};evals=0
 for row in records:
  key=(row['phase'],row['band'],row['reff_um']);require(key not in index,'duplicate reference entry');index[key]=row
  for level in row['levels']:
   require(set(level)==set(GRIDS),'independent quadrature axes missing')
   f=level['fine'];require(level['radius_half']['nr']*2==f['nr'] and level['radius_half']['ns']==f['ns'],'radius axis changes spectral grid')
   require(level['spectral_half']['nr']==f['nr'] and level['spectral_half']['ns']*2==f['ns'],'spectral axis changes radius grid')
   for v in level.values():
    evals+=1;require(all(v[k]>=0 and math.isfinite(v[k]) for k in M),'nonphysical moment')
    close(v['g'],v['sca_g']/v['sca'],'moment-based band g')
    require(v['same_node_relative_residual']<=1e-10,'number/area Gamma algebra')
    close(v['integrated_reff_um'],row['reff_um'],'integrated effective radius',1e-10)
    close(v['abs'],v['ext']-v['sca']+v['abs_ext_minus_sca_residual'],'absorption stage residual')
  ok=axis_pass(row['levels'][-1],plan['predeclared_numerical_screens']);require(ok==row['qualified_numerical_axes'],'qualification contradicts retained grids')
  f=row['levels'][-1]['fine'];c=next(v for v in cross['records'] if (v['phase'],v['band'],v['reff_um'])==key);old=row['original_PR183']
  require(c['nr']==f['nr'] and c['ns']==old['ns'],'crossed quadratures not matched')
  moments={}
  for m in M:
   radial=f[m]-row['levels'][-1]['radius_half'][m];spectral=f[m]-row['levels'][-1]['spectral_half'][m]
   radial_method=c[m]-old[m];spectral_method=f[m]-c[m];total=f[m]-old[m]
   close(total,radial_method+spectral_method,'signed method decomposition',1e-14)
   moments[m]={'fine_m2_g':f[m],'PR183_m2_g':old[m],'signed_radius_axis_change':radial,'signed_spectral_axis_change':spectral,'empirical_axis_sum_estimate_m2_g':abs(radial)+abs(spectral),'method_correction_from_PR183':total,'radial_method_correction_at_old_spectral_nodes':radial_method,'spectral_method_correction_at_new_radial_nodes':spectral_method,'relative_method_correction':total/max(abs(old[m]),1e-30)}
  rows.append({'phase':key[0],'band':key[1],'reff_um':key[2],'role':row['role'],'qualified_numerical_axes':ok,'fine_grid':[f['nr'],f['ns']],'moments':moments,'g':f['g']})
 qualified=sum(r['qualified_numerical_axes'] for r in rows);primary=sum(r['qualified_numerical_axes'] for r in rows if r['role']=='primary')
 receipt=json.loads(read('rte-journal/receipt.json'));require(len(receipt['runs'])==18 and len(receipt['commands'])==18,'actual RTE process coverage')
 require(all(c['actual_returncode']==0 and not c['timed_out'] for c in receipt['commands']),'failed RTE process')
 cases={};all_transport=True
 for case in CASES:
  ph=case.rsplit('_',1)[1];variants={};oldvalues={};counts={}
  for mode in ('B','C'):
   oldname=case+'_'+mode
   oldres=a.parser.trace(prior(oldname+'/'+ph+'.result'),'result')[1]
   oldinp=a.parser.trace(prior(oldname+'/'+ph+'.input'),'input')[1]
   cph,nl,nb,mask,basecoef=a.parse_coeff(prior(oldname+'/optics.dat'));oldvalues[mode]=values(oldres);variants[mode]={};counts[mode]=0
   require(cph==ph.upper() and sum(mask)==(2 if case.startswith('night') else 3),'source mask or phase changed')
   for grid in GRIDS:
    name=oldname+'_'+grid;res=a.parser.trace(read(name+'/'+ph+'.result'),'result')[1]
    inp=a.parser.trace(read(name+'/'+ph+'.input'),'input')[1]
    require(read(name+'/input.dat')==prior(oldname+'/input.dat'),'physical input changed')
    for field in oldinp:
     if field not in ('RAW_CLOUD_TAU','RAW_NATIVE_CLOUD_TAU'):require(inp[field]==oldinp[field],'input field changed '+field)
    for n in ('UPC','DNC','HRC','GAS_TAU','GAS_SSA','GAS_G','PRECIP_TAU','PRECIP_SSA','PRECIP_G','MASK','NATIVE_CAPACITY_J_M2_K','RL_USED'):
     if n in oldres:require(res[n]==oldres[n],'unselected control changed '+n)
    for n in oldres:
     if n.startswith(('UNIFORM_','ENDPOINT_UNIFORM_')):require(res[n]==oldres[n],'uniform component changed')
    ph2,nl2,nb2,mask2,coef=a.parse_coeff(read(name+'/optics.dat'));require((ph2,nl2,nb2,mask2)==(cph,nl,nb,mask),'layout or mask changed')
    changed=[]
    for band in range(1,nb+1):
     for k in range(nl):
      i=(band-1)*nl+k;radius=21.5 if mode=='B' else oldinp['REL']['values'][k]
      rec=index.get((ph,band,radius)) if mask[k] else None
      replace=rec is not None and rec['qualified_numerical_axes']
      expected=[rec['levels'][-1][grid][m] for m in M] if replace else basecoef[i]
      require(coef[i]==expected,'unqualified or unselected coefficient overwritten')
      if replace:changed.append({'layer':k+1,'band':band,'radius_um':radius})
      rawname='ENDPOINT_NATIVE_RAW_LIQUID_'+('ABS_TAU' if ph=='lw' else 'EXT_TAU')
      if not mask[k]:
       for n in (rawname,'CLOUD_TAU','CLOUD_SSA','CLOUD_G'):
        if n in res:require(res[n]['values'][i]==oldres[n]['values'][i],'unselected optical layer changed')
       continue
      ext,sca,ab,sg=coef[i];path=inp['LWP']['values'][k];tau=path*ext;ssa=sca/ext;g=sg/sca
      close(res[rawname]['values'][i],path*(ab if ph=='lw' else ext),'raw consumed moment')
      pt=res['PRECIP_TAU']['values'][i]
      if ph=='lw':close(res['CLOUD_TAU']['values'][i],path*ab+pt,'LW absorption consumption')
      else:
       close(res['ENDPOINT_NATIVE_RAW_LIQUID_SSA']['values'][i],ssa,'SW raw SSA');close(res['ENDPOINT_NATIVE_RAW_LIQUID_G']['values'][i],g,'SW raw g')
       d=1-ssa*g*g;td=tau*d;sd=ssa*(1-g*g)/d;gd=g/(1+g)
       ps=res['PRECIP_SSA']['values'][i];pg=res['PRECIP_G']['values'][i];total=td+pt;sct=td*sd+pt*ps
       close(res['CLOUD_TAU']['values'][i],total,'SW exactly one delta scale');close(res['CLOUD_SSA']['values'][i],sct/total,'scaled SSA');close(res['CLOUD_G']['values'][i],(td*sd*gd+pt*ps*pg)/sct,'scaled g')
    journal=next(r for r in receipt['runs'] if (r['case'],r['mode'],r['grid'])==(case,mode,grid));require(journal['changed_entries']==changed,'executed replacement receipt differs')
    counts[mode]=len(changed)
    net=[d-u for d,u in zip(res['DN_WP']['values'],res['UP_WP']['values'])];C=res['NATIVE_CAPACITY_J_M2_K']['values'];heat=res['HEAT_WP_K_S']['values']
    err=max(abs(C[k]*heat[k]-(net[k+1]-net[k])) for k in range(59));require(err<1e-10,'native capacity/flux relation')
    variants[mode][grid]=values(res)
  mode_reports={};mode_ok=True
  for mode in ('B','C'):
   mode_reports[mode],ok=target_report(variants[mode],oldvalues[mode],plan);mode_ok=mode_ok and ok
  radius={grid:{key:difference(variants['C'][grid][key],variants['B'][grid][key]) for key in variants['B'][grid]} for grid in GRIDS}
  oldradius={key:difference(oldvalues['C'][key],oldvalues['B'][key]) for key in oldvalues['B']}
  radius_report,ok=target_report(radius,oldradius,plan)
  all_transport=all_transport and mode_ok and ok
  cases[case]={'qualified_replaced_layer_band_entries':counts,'B_C_target_reports':mode_reports,'radius_effect_C_minus_B':radius_report,'all_unselected_controls_unchanged':True,'source_relation_checked_each_native_layer':True}
 return {'status':'EXECUTED_MATCHED_COMPONENT_REFERENCE','coefficient_scope':{'selected_combinations':len(rows),'qualified_primary':primary,'primary_total':14,'qualified_total':qualified,'excluded':[{k:r[k] for k in ('phase','band','reff_um')} for r in rows if not r['qualified_numerical_axes']],'axis_evaluations':evals,'crossed_method_evaluations':len(cross['records']),'rows':rows},'transport':{'actual_new_column_processes':18,'partial_band_substitutions_only':True,'axis_numerical_screen_passed':all_transport,'cases':cases},'reference_decision':{'conditional_reference':'QUALIFIED_FOR_LISTED_RADIUS_BAND_ENTRIES' if primary==14 else 'PARTIAL_QUALIFICATION_ONLY','claim':'Shared-kernel spherical Gamma8 numerical integration reference with matched definitions and empirical axis estimates. Not a second independent Mie kernel.','certified_numerical_error_bound':None,'physical_tolerance':None,'original_LUT_generation_definition_certified':False,'observed_PSD_or_occurrence_approved':False,'representativeness':'outside this conditional numerical claim; not assumed zero','existing_RFMIP_LBLRTM_FAIL':'PRESERVED','whole_host_water_energy_approval':False,'full_spectrum_physical_reference':False},'new_WRF_runs':0,'production_accepted':False}
