"""Bind one retained research configuration; never authorize physical production."""
from pathlib import Path
import argparse,hashlib,json,math,struct,importlib.util
B=Path(__file__).resolve().parent
ROOT=B.parents[2]
_h=importlib.util.spec_from_file_location('historical_source',ROOT/'validation/rrtmgp37/historical-source/binding.py')
historical=importlib.util.module_from_spec(_h);_h.loader.exec_module(historical)
GATES=('PHY-NC','PHY-SIZE','PHY-OCCURRENCE','REF-RFMIP','REF-LBL','FINAL-IDENTITY','FINAL-FORECAST')
MASS=('QCLOUD','QICE','QRAIN','QSNOW','QGRAUP','QHAIL')
def require(ok,msg):
    if not ok:raise ValueError(msg)
def load(p):return json.loads(p.read_text())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def validate_profile(p):
    require(p['purpose']=='RESEARCH_ONLY' and p['production_accepted'] is False and p['scientific_acceptance'] is False,'research-only profile cannot approve physics')
    expected={'mp_physics':27,'ra_lw_physics':37,'ra_sw_physics':37,'scalar_adv_opt':0,'rk_ord':3,'h_sca_adv_order':5,'v_sca_adv_order':3,'periodic_x':True,'periodic_y':True,'max_dom':1,'cldovrlp':2,'ccn_conc_raw':1e8,'frozen_optics_mode':0,'ice_roughness':1}
    require(all(p['resolved_configuration'].get(k)==v for k,v in expected.items()),'resolved configuration outside frozen v1 profile')
    n=p['number_policy'];require(n['cold_start']=='legacy_constant_before_first_UDM' and n['encoding']=='UNRESOLVED_NATIVE_RAW','unapproved number relabeling or initialization change')
    require(n['external_QNN_preservation_supported'] is False and n['dry_mass_denominator_approved'] is False and n['population_approved'] is False and n['rho_or_CF_scaling_added'] is False,'unapproved number conversion/population')
    require(p['size_policy']['PSD_LUT_moment_approved'] is False and p['size_policy']['empirical_radius_multiplier'] is None,'unapproved optical-size conversion')
    require(p['occurrence_policy']['physical_occurrence_approved'] is False and p['resolved_configuration']['frozen_optics_mode']==0,'physical occurrence or frozen-profile promotion')

def decode_state(meta,raw):
    require(meta['variables']==['QNCCN','QNCLOUD','QNRAIN',*MASS,'CLDFRA'] and meta['shape_per_variable']==[59,2,2],'retained state layout')
    require(meta['encoding']=='IEEE little-endian binary32' and len(raw)==meta['extracted_bytes']==10*236*4,'state extent')
    require(hashlib.sha256(raw).hexdigest()==meta['extracted_sha256'],'state byte identity')
    vals=struct.unpack('<'+str(10*236)+'f',raw);require(all(math.isfinite(v) for v in vals),'finite recorded state')
    arrays={name:vals[k*236:(k+1)*236] for k,name in enumerate(meta['variables'])};cf=arrays['CLDFRA']
    require(all(0<=v<=1 for v in cf) and all(v>=0 for name in MASS for v in arrays[name]),'retained hydrometeor and CF range')
    counts={name:sum(v>0 for v in arrays[name]) for name in MASS}
    clear={name:sum(f==0 and v>0 for f,v in zip(cf,arrays[name])) for name in MASS}
    require(counts['QGRAUP']==counts['QHAIL']==0,'positive G/H outside this research profile')
    stamp=meta['UDM_CF_STEP_range'];diagnosed=stamp is not None and stamp[0]>=0
    return {'role':meta['role'],'cells':236,'positive_condensate_cells':counts,'CF0_positive_condensate_cells':clear,
      'CF0_counts_are_potential_snapshot_omission_not_measured_radiation_loss':True,'CF_diagnostic_stamp_nonnegative':diagnosed,
      'UDM_CF_STEP_range':stamp,'direct_radiation_call_state':False,
      'reported_number_units':{n:meta['reported_units_attributes'][n] for n in ('QNCCN','QNCLOUD','QNRAIN')},
      'number_unit_population_approved':False,
      'number_raw_ranges':{n:[min(arrays[n]),max(arrays[n])] for n in ('QNCCN','QNCLOUD','QNRAIN')}}

def audit(repo,profile,case,namelist,purpose='research',number_policy='legacy_constant',source_scope='current'):
    validate_profile(profile)
    require(case in profile['namelist_bindings'],'unknown retained configuration')
    require(number_policy=='legacy_constant','external preservation conflicts with this implemented cold-start policy')
    binding=profile['namelist_bindings'][case];require(len(namelist)==binding['bytes'] and hashlib.sha256(namelist).hexdigest()==binding['sha256'],'configuration outside exact retained profile; new binding required')
    for r in profile['source_pins']:
        require(source_scope in ('current','retained'),'unknown source scope')
        raw=(repo/r['path']).read_bytes() if source_scope=='current' else historical.historical_bytes(repo,r['path'],r['sha256'])
        require(len(raw)==r['bytes'] and hashlib.sha256(raw).hexdigest()==r['sha256'],'source changed; revise profile and its evidence')
    closure=load(B/'closure-conditions.json');require({r['id'] for r in closure['items']}==set(GATES),'fixed seven closure conditions')
    check=load(repo/'validation/rrtmgp37/acceptance/review-resolution-checklist.json');items={r['id']:r for r in check['items']}
    for r in closure['items']:require(items[r['id']]['completion_condition']==r['completion_condition'],'closure condition changed; explicit version review required')
    meta=load(B/'state-readback.json');states=[decode_state(r,(B/r['extracted_path']).read_bytes()) for r in meta['states']]
    unresolved=[{'id':i,'status':items[i]['integrated_validation'],'completion_condition':items[i]['completion_condition']} for i in GATES if items[i]['integrated_validation'] not in ('PASS_PHYSICAL','PASS_FINAL_ACCEPTANCE')]
    require(purpose in ('research','physical'),'unknown audit purpose')
    return {'status':'PASS_SCOPED_RETAINED_RESEARCH_PROFILE' if purpose=='research' else 'REJECT_PHYSICAL_ACCEPTANCE',
      'profile_id':profile['profile_id'],'purpose':purpose,'case':case,'number_policy':'legacy_constant',
      'configuration_binding':'exact retained namelist bytes; not a generic Fortran namelist parser',
      'configuration':profile['resolved_configuration'],'selection_status':profile['selection_status'],
      'retained_case_observed_first_reset':binding['cold_start'],'restart_claim':'tested native checkpoint path only',
      'source_files_bound':len(profile['source_pins']),'checked_snapshots':states,'unresolved_required_gates':unresolved,
      'research_only_profile_blocks_physical_use_even_if_documentary_gates_retagged':True,
      'scientific_acceptance':False,'production_accepted':False,'fresh_model_executions':0,
      'operating_system_execution_identity_certified':False,'coefficient_bytes_reauthenticated':False,
      'limits':'No every-timestep admission, actual radiation omission budget, external input authority, other transport/parallel configuration, independent reference or final forecast approval.'}

def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--source-scope',choices=('current','retained'),default='current');a.add_argument('--source',type=Path,default=ROOT);a.add_argument('--case',choices=('warm-cloud-on','restart-on'),default='warm-cloud-on');a.add_argument('--namelist',type=Path);a.add_argument('--purpose',choices=('research','physical'),default='research');a.add_argument('--number-policy',choices=('legacy_constant','preserve_external'),default='legacy_constant');a.add_argument('--output',type=Path)
    args=a.parse_args();profile=load(B/'profile.json');path=args.namelist or args.source/profile['namelist_bindings'][args.case]['path']
    try:r=audit(args.source,profile,args.case,path.read_bytes(),args.purpose,args.number_policy,args.source_scope)
    except (ValueError,OSError) as exc:r={'status':'REJECT_PROFILE_BINDING','reason':str(exc),'production_accepted':False};rc=2
    else:rc=0 if args.purpose=='research' else 2
    text=json.dumps(r,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(text)
    print(text,end='');return rc
if __name__=='__main__':raise SystemExit(main())
