"""Saved-array/ledger audit only. Never imports or invokes reconstruction code."""
from pathlib import Path
import datetime, hashlib, json, math, struct
import numpy as np
from netCDF4 import Dataset

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
HERE = Path(__file__).resolve().parent
RUN = HERE.parent
OUT = RUN / 'output'
PLAN = ROOT / 'build/udm37-bon-night-opacity-independent-plan-v1/v3/plan.json'

def pin(path):
    path = Path(path)
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return dict(path=str(path), sha256=h.hexdigest(), size_bytes=path.stat().st_size)

def records(value, pointer=''):
    found=[]
    if isinstance(value, dict):
        if {'path','sha256','size_bytes'} <= value.keys():
            found.append(dict(json_pointer=pointer or '/',path=value['path'],sha256=value['sha256'],size_bytes=int(value['size_bytes'])))
        for k,v in value.items(): found += records(v,pointer+'/'+str(k).replace('~','~0').replace('/','~1'))
    elif isinstance(value,list):
        for k,v in enumerate(value): found += records(v,pointer+'/'+str(k))
    return found

def checked(rec):
    path=Path(rec['path']); path=path if path.is_absolute() else ROOT/path
    assert path.is_file() and not path.is_symlink()
    actual=pin(path)
    assert actual['sha256']==rec['sha256'] and actual['size_bytes']==rec['size_bytes'],str(path)
    return actual

def read_result(path):
    lines=Path(path).read_text().splitlines()
    assert lines[1].split()==['LW','1','45']
    sections={}; i=2
    while i<len(lines):
        if not lines[i].strip(): i+=1;continue
        fields=lines[i].split();i+=1
        assert len(fields)==4 and fields[0] not in sections
        shape=tuple(map(int,fields[1:]));assert all(n>0 for n in shape)
        values=[]
        while len(values)<math.prod(shape):
            values.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split());i+=1
        assert len(values)==math.prod(shape)
        a=np.asarray(values,dtype='f8').reshape(shape,order='F');assert np.isfinite(a).all()
        sections[fields[0]]=a
    return sections

def finite_json(v):
    if isinstance(v,float): assert math.isfinite(v);return 1
    if isinstance(v,dict): return sum(finite_json(x) for x in v.values())
    if isinstance(v,list): return sum(finite_json(x) for x in v)
    return 0

def exact(a,b):
    aa=np.asarray(a,dtype='f8');bb=np.asarray(b,dtype='f8')
    assert aa.shape==bb.shape and aa.tobytes()==bb.tobytes()

def order(x):
    b=struct.unpack('>Q',struct.pack('>d',float(x)))[0]
    return (~b)&((1<<64)-1) if b>>63 else b|(1<<63)

def main():
    execution=json.loads((RUN/'execution.json').read_text())
    assert pin(RUN/'execution.json')['sha256']=='0eeb0be1db2c30640a14d86d3d95f5184532549c6c488586fb9c9e8476cd866d'
    assert execution['actual_child_return_code']==0 and not execution['timed_out'] and execution['bounded_python_invocations']==1
    assert all(execution[k]==0 for k in ['new_WRF','new_RTE','new_REAL','new_builds'])
    plan=json.loads(PLAN.read_text());assert pin(PLAN)['sha256']=='21edb10d1af8cbc6b12f44e305572d49fa688d822644c49acb946246aa62d01e'
    auth=json.loads((RUN/'authorization.json').read_text())
    wanted=records(plan);assert len(wanted)==51
    sort=lambda a:sorted(a,key=lambda x:(x['json_pointer'],x['path']))
    assert sort(wanted)==sort(auth['artifact_pins'])
    assert auth['status']=='AUTHORIZED_DIAGNOSTIC_ONLY' and auth['plan_sha256']==pin(PLAN)['sha256']
    before=[checked(x) for x in wanted]
    auth_extra=[checked(auth[x]) for x in ['point_source','source_review']]
    source_review=json.loads(Path(auth_extra[1]['path']).read_text())
    assert source_review['status'].startswith('PASS_SCOPED')
    assert checked(execution['point_source'])==auth_extra[0]
    for k in ['runner_source','stdout','stderr']:checked(execution[k])
    invocation=json.loads((RUN/'invocation.json').read_text());checked(invocation['authorization']);checked(invocation['launcher'])
    cmd=invocation['command'];assert cmd[cmd.index('--point-source')+1]==auth_extra[0]['path'] and cmd[cmd.index('--out')+1]==str(OUT)
    construction_pin=pin(OUT/'construction.json')
    assert construction_pin['sha256']=='cda11a1a806f64629dd7c1468385b379bba4d3a1d5a9ab9430c796e63f7722a9' and construction_pin['size_bytes']==143183928
    assert pin(OUT/'diagnostic.json')['sha256']=='883e24459496877eace7300baf3240037afb2ff2a0fc31ddc44aa28c6e1629a7'
    with (OUT/'construction.json').open() as f: construction=json.load(f)
    receipt=json.loads((OUT/'construction-receipt.json').read_text())
    diagnostic=json.loads((OUT/'diagnostic.json').read_text())
    assert construction['status']=='POINT_ARRAYS_CONSTRUCTED_TARGETS_NOT_OPENED'
    ids=['n2-absent-baseline','n2-explicit-zero','n2-0p7808']
    assert [x['case_id'] for x in construction['cases']]==receipt['case_ids']==ids
    assert receipt['construction_sha256']==construction_pin['sha256']==diagnostic['construction_sha256']
    assert diagnostic['status']=='DIAGNOSTIC_COMPLETE_NO_NUMERICAL_VERDICT'
    assert diagnostic['authorization_sha256']==pin(RUN/'authorization.json')['sha256']
    assert diagnostic['point_source_sha256']==auth_extra[0]['sha256']
    numeric_count=finite_json(construction)
    table_path=ROOT/plan['pinned_artifacts']['lw_coefficients']['path']
    with Dataset(table_path) as ds:
        tables={name:np.asarray(ds[name][:]) for name in ['kmajor','kminor_lower','kminor_upper','bnd_limits_gpt']}
    case_reports=[];coefficient_refs=0;major_count=minor_count=0
    for case in construction['cases']:
        tau=np.asarray(case['tau_point'],dtype='f8');assert tau.shape==(45,128) and np.isfinite(tau).all()
        sections=read_result(ROOT/plan['pinned_artifacts'][case['result_target_pin_name']]['path'])
        for name in ['GAS_TAU_RAW','GAS_TAU']:
            t=sections[name];assert t.shape==(1,45,128);exact(tau,t[0])
            saved=next(x for x in diagnostic['comparisons'] if (x['case_id'],x['target_section'])==(case['case_id'],name))
            exact(saved['candidate_tau'],tau);exact(saved['target_tau'],t[0])
            delta=tau-t[0];exact(saved['signed_residual'],delta);exact(saved['absolute_residual'],np.abs(delta))
            ulps=[[order(tau[k,g])-order(t[0,k,g]) for g in range(128)] for k in range(45)]
            assert ulps==saved['signed_ordered_binary64_ulp_delta'] and all(n==0 for row in ulps for n in row)
            summary=saved['summary'];assert summary['max_absolute_residual']==summary['rms_residual']==summary['max_absolute_ordered_ulp_delta']==0
            assert summary['target_zero_cells']==int(np.count_nonzero(t==0)) and summary['numerical_gate']=='NONE_DIAGNOSTIC_ONLY'
            relative=saved['relative_residual_signed_target_denominator_null_at_zero']
            assert all(relative[k][g] is None if t[0,k,g]==0 else relative[k][g]==0 for k in range(45) for g in range(128))
        dry=sections['GAS_COL_DRY'];assert dry.shape==(1,45,1);exact(case['dry_column_molecule_cm2'],dry[0,:,0])
        saved=next(x for x in diagnostic['dry_column_crosschecks'] if x['case_id']==case['case_id'])
        exact(saved['reconstructed_molecule_cm2'],dry[0,:,0]);exact(saved['saved_GAS_COL_DRY_molecule_cm2'],dry[0,:,0])
        assert saved['summary']['max_absolute_residual']==saved['summary']['rms_residual']==0
        accumulated=np.zeros((45,128),dtype='f8');flavor={};mc=ic=0
        for term in case['major_terms_source_order']:
            k=term['layer_fortran']-1;g=term['gpoint_fortran']-1;assert (k,g) not in flavor
            flavor[k,g]=term['flavor_fortran']-1
            planes=[]
            for plane in term['planes']:
                coeff=[float(tables['kmajor'][tuple(i-1 for i in idx)]) for idx in plane['coefficient_indices_fortran_raw_netCDF_T_P_eta_gpt']]
                exact(coeff,plane['corner_coefficients_same_order']);coefficient_refs+=len(coeff)
                weights=plane['weights_eta_low_pressure_low__eta_high_pressure_low__eta_low_pressure_high__eta_high_pressure_high']
                weighted=[float(a)*float(b) for a,b in zip(weights,coeff)];exact(weighted,plane['weighted_corner_terms_same_order'])
                total=((weighted[0]+weighted[1])+weighted[2])+weighted[3];assert total==plane['weighted_corner_sum_left_associated']
                value=plane['col_mix']*total;assert value==plane['scaled_plane_value'];planes.append(value)
            value=planes[0]+planes[1];assert value==term['two_scaled_plane_sum']
            accumulated[k,g]+=value;assert accumulated[k,g]==term['tau_after_major_add'];mc+=1
        assert mc==5760
        intervals=case['discrete_context']['minor_intervals']
        for term in case['minor_terms_source_order']:
            k=term['layer_fortran']-1;g=term['gpoint_fortran']-1;suffix=term['atmosphere_lower_upper']
            matches=[row for row in intervals[suffix] if row['id']==term['interval_id'] and row['keep']
                     and row['gas']==term['absorber'] and row['lo']<=g+1<=row['hi']
                     and term['raw_contributor_index_fortran']==row['raw_start']+(g+1-row['lo'])
                     and term['packed_contributor_index_fortran']==row['packed_start']+(g+1-row['lo'])]
            assert len(matches)==1
            row=matches[0]
            offset=g+1-row['lo'];assert term['raw_contributor_index_fortran']==row['raw_start']+offset and term['packed_contributor_index_fortran']==row['packed_start']+offset
            context=case['discrete_context']['layer_flavor_state'][k]['flavors'][flavor[k,g]]['reference_planes']
            weights=list(context[0]['fminor'])+list(context[1]['fminor'])
            indices=term['coefficient_indices_fortran_raw_table_temp_eta_contributor']
            coefficients=[float(tables['kminor_'+suffix][tuple(i-1 for i in idx)]) for idx in indices];coefficient_refs+=4
            for raw,packed in zip(indices,term['coefficient_indices_fortran_packed_temp_eta_contributor']):assert raw[:2]==packed[:2] and packed[2]==term['packed_contributor_index_fortran']
            values=[float(a)*b for a,b in zip(weights,coefficients)];exact(values,term['minor_corner_terms_source_order'])
            interp=((values[0]+values[1])+values[2])+values[3];assert interp==term['interpolated_minor_coefficient_left_associated']
            scale=term['scaling_before_density']
            if term['density_factor'] is not None:scale*=term['density_factor']
            if term['scaling_gas_factor'] is not None:scale*=1-term['scaling_gas_factor'] if term['complement'] else term['scaling_gas_factor']
            assert scale==term['scaling_final'];added=scale*interp;assert added==term['scaled_minor_tau']
            accumulated[k,g]+=added;assert accumulated[k,g]==term['tau_after_minor_add'];ic+=1
        exact(accumulated,tau);major_count+=mc;minor_count+=ic
        case_reports.append(dict(case_id=case['case_id'],shape=[45,128],compared_sections=['GAS_TAU_RAW','GAS_TAU'],max_absolute_residual=0,maximum_ordered_binary64_ULP=0,dry_layers=45,dry_residual=0,major_terms=mc,minor_terms=ic,all_ledger_arithmetic_and_raw_coefficients_exact=True,target_pin=checked(plan['pinned_artifacts'][case['result_target_pin_name']])))
    context=json.loads((ROOT/plan['pinned_artifacts']['pfrac_result']['path']).read_text())
    positive=construction['cases'][2];discrete=positive['discrete_context'];saved=json.loads((OUT/'pfrac-context-crosscheck.json').read_text())
    pairs={'available_gases_vs_pfrac_reduced_gases':(positive['available_gases'],context['reduced_gases']),
           'key_species_rewritten':(discrete['key_species_reduced_ids'],context['key_species_rewritten']),
           'flavors_fortran_indices':(discrete['flavors_reduced_ids'],context['flavors_Fortran_indices']),
           'jtemp_fortran':(discrete['jtemp_fortran'],context['jtemp_Fortran']),
           'jpress_fortran':(discrete['jpress_fortran'],context['jpress_Fortran']),
           'atmosphere_fortran':([1 if x else 2 for x in discrete['tropopause_lower']],context['atmosphere_Fortran'])}
    for key,(a,b) in pairs.items():assert a==b and saved['exact_discrete_checks'][key]['exact_equal']
    differences={}
    for name in ['ftemp','fpress']:
        delta=np.asarray([x[name] for x in discrete['layer_flavor_state']])-np.asarray(context[name])
        exact(delta,saved['fraction_differences_diagnostic_only'][name+'_point_minus_pfrac'])
        differences[name+'_max_abs_difference']=float(np.max(np.abs(delta)))
        assert differences[name+'_max_abs_difference']==saved['fraction_differences_diagnostic_only'][name+'_max_abs_difference']
    times={name:(OUT/name).stat().st_mtime_ns/1e9 for name in ['construction.json','construction-receipt.json','pfrac-context-crosscheck.json','diagnostic.json']}
    assert execution['started_unix']<=min(times.values())<=max(times.values())<=execution['completed_unix']
    assert list(times.values())==sorted(times.values())
    after=[checked(x) for x in wanted];assert before==after
    report=dict(schema='UDM_BON_OPACITY_SAVED_EVIDENCE_TERMINAL_REVIEW_V1',status='PASS_SCOPED_SAVED_EVIDENCE',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),execution=pin(RUN/'execution.json'),invocation=pin(RUN/'invocation.json'),authorization=pin(RUN/'authorization.json'),plan=pin(PLAN),source_review=auth_extra[1],point_source=auth_extra[0],runner_source=checked(execution['runner_source']),construction=construction_pin,construction_receipt=pin(OUT/'construction-receipt.json'),diagnostic=pin(OUT/'diagnostic.json'),static_runner_review=pin(ROOT/'build/udm37-bon-night-opacity-runner-review-v1/review-v2.json'),artifact_pin_records_before_and_after_exact=before,case_reports=case_reports,ledger_checks=dict(all_JSON_float_fields_finite=numeric_count,major_terms=major_count,minor_terms=minor_count,raw_coefficient_references_checked=coefficient_refs,all_major_minor_coefficient_indices_values_products_and_source_order_sums_exact=True,all_minor_raw_packed_contributor_joins_exact=True),pfrac_context=dict(six_discrete_pairs_exact=True,**differences),file_time_order=times,original_invocations=dict(bounded_Python_reconstruction=1,actual_child_RC=0,timed_out=False,WRF=0,REAL=0,RTE=0,build=0),reviewer_invocations=dict(saved_target_array_ledger_readback=1,point_source_import=0,point_reconstruction=0,compiled_calls=0,WRF=0,REAL=0,RTE=0,build=0),limits=['Exact equality is a saved same-held-table diagnostic observation, not a tolerance-certified arithmetic verdict, coefficient-generation evidence or physical-accuracy validation.','All45 masses are the matched-legacy diagnostic carrier; not a normal32-native/13-extension production mass reconstruction.','Component ledgers have no independent gold component observer. Algebra/index/actual-table checks establish internal source-order bookkeeping only.','File mtime ordering corroborates persisted construction before context/diagnostic; static pinned runner code establishes parser-read ordering. Integrity hashing of target bytes was allowed before construction.','Pfrac fractions remain diagnostic; no new normalization, gas clipping, optical/transport calculation, numerical threshold or goal closure.'],blocking_findings=[])
    path=HERE/'review.json'
    with path.open('x') as f:json.dump(report,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
    print(json.dumps(dict(review=pin(path),ledger=report['ledger_checks'],pfrac=report['pfrac_context'],cases=case_reports),indent=2))

if __name__=='__main__':main()
