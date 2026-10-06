#!/usr/bin/env python3
"""Read completed two-call outputs; no build/model/solver invocation path."""
from pathlib import Path
import json,hashlib,importlib.util,sys,datetime
import numpy as np
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
D=ROOT/'build/udm37-exact-band-cloud-swap-runtime-v2';R=D/'run-v1'
def pin(p):
    p=Path(p);b=p.read_bytes();return {'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'size_bytes':len(b)}
def loadmod(name,p):
    s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def req(x,label):
    if not x:raise ValueError(label)
def bits(a):return np.asarray(a,dtype=np.float64).tobytes(order='F')
def delta(a,b):
    d=b-a;return {'max_abs':float(abs(d).max()),'native44_max_abs':float(abs(d[:, :44, :]).max()) if d.shape[1] in (45,46) else None,'changed_bits':int(sum(x!=y for x,y in zip(np.asarray(a).ravel(order='F').view(np.uint64),np.asarray(b).ravel(order='F').view(np.uint64))))}
def main():
    out=HERE/'runtime-terminal-review-v1.json';req(not out.exists(),'review collision')
    ck=loadmod('terminal_independent_override',HERE/'check_overrides.py');rt=loadmod('terminal_readonly_live_snapshot',D/'run_two.py');ex=loadmod('terminal_original_export',ck.READER)
    receipt_path=R/'execution.json';receipt=json.loads(receipt_path.read_text());initial_receipt_pin=pin(receipt_path)
    req(receipt['status']=='TWO_CALLS_VALIDATED' and receipt['solver_invocations']==2 and receipt['model_invocations']==0,'actual terminal counts/status');req([c['case_id'] for c in receipt['calls']]==rt.CASE_ORDER,'call order');req(len({c['pid'] for c in receipt['calls']})==2,'unique PIDs')
    plan=json.loads((D/'plan.json').read_text());pp=json.loads(rt.PREP_PLAN.read_text());auth=json.loads((D/'root-execution-authorization-v2.json').read_text());req(receipt['authorization']==pin(D/'root-execution-authorization-v2.json'),'authorization pin');req(auth['max_solver_invocations']==2,'authorization cap');req(receipt['runner_sha256']==pin(D/'run_two.py')['sha256'] and receipt['plan_sha256']==pin(D/'plan.json')['sha256'],'actual runner/plan binds')
    req(receipt['initial_pins']==receipt['final_immutable_snapshot'] and receipt['final_pins_match_initial'],'original immutable snapshots');req(rt.fixed_snapshot(plan)==receipt['initial_pins'],'current protected pins match before/after snapshot')
    inp_path=Path(plan['fixed_pins']['capture_input']['path']);raw_path=Path(plan['fixed_pins']['capture_raw']['path']);_,inp=ck.records(inp_path);_,raw=ck.records(raw_path);_,baseline=ck.records(rt.BASE_RESULT);prepared=[ck.override(Path(c['override']['path'])) for c in plan['cases']]
    results=[];call_rows=[]
    for i,(call,cplan) in enumerate(zip(receipt['calls'],plan['cases'])):
        req(call['status']=='CALL_VALIDATED' and call['returncode']==0 and not call['timed_out'],'child failure');req(call['ended_unix']>=call['started_unix'] and call['ended_unix']-call['started_unix']<=rt.TIMEOUT,'child timing');req(call['command']==[str(rt.EXE),str(rt.DATA),cplan['input']['path'],cplan['output'],'1',cplan['override']['path']],'exact six-element argv with no audit sidecar')
        op=Path(cplan['output']);lp=Path(cplan['log']);req(pin(op)==call['output_pin'] and pin(lp)==call['log_pin'],'actual output/log pins');h,res=ck.records(op);req(h==['RRTMGP_RESULT_V1','SW 1 45'],'actual result header');req(set(res)==rt.BASELINE_SECTIONS and len(res)==54,'exact actual 54 section roster');req(all(v.shape==baseline[n].shape and np.isfinite(v).all() for n,v in res.items()),'result shapes/finiteness');results.append(res);call_rows.append({'case_id':call['case_id'],'pid':call['pid'],'returncode':call['returncode'],'timed_out':False,'duration_seconds':call['ended_unix']-call['started_unix'],'command':call['command'],'output':pin(op),'log':pin(lp)})
    control,variant=results;req(Path(plan['cases'][0]['output']).read_bytes()==rt.BASE_RESULT.read_bytes(),'control whole-file identity');req(all(bits(control[n])==bits(baseline[n]) for n in baseline),'all54 control section identity')
    export=ex.read_export(ck.ORIGINAL/'export/rrtmg4_d01_i24_j55_step2161_sw.txt',expected_phase='SW');F=export['fields'];field=lambda st,n:np.array(F[st,n].values).reshape(F[st,n].shape,order='F');legacy_bounds=np.column_stack([field('CLOUD','BAND_WAVENUM_LO'),field('CLOUD','BAND_WAVENUM_HI')]);codes=field('CLOUD','BAND_INDEX');map_legacy=field('CLOUD','GPOINT_TO_BAND')
    joins=ck.exact_bands(prepared[0]['BAND_LIMITS'],legacy_bounds);expected={'control':{p:baseline[n].copy() for p,n in zip(ck.PROPS,('PREPARED_TAU','PREPARED_SSA','PREPARED_G'))}};expected['variant']={p:a.copy() for p,a in expected['control'].items()};assignments=0
    for b,l in joins:
        indices=np.where(map_legacy==codes[l])[0]
        for k in (29,30,31):
            for p,n in zip(ck.PROPS,('CLDPRMC_TAU','CLDPRMC_SSA','CLDPRMC_ASM')):expected['variant'][p][0,k,b]=ck.constant(field('CLOUD',n),indices,k);assignments+=1
    ck.validate_scope(prepared[0],prepared[1],expected,prepared[0]['BAND_LIMITS']);req(assignments==108,'actual assignments');ck.cloudy(baseline['MASK']);req(all(inp['CF'][0,k]==raw['CF'][k]==1 for k in (29,30,31)),'CF1')
    for p,n in zip(ck.PROPS,('PREPARED_TAU','PREPARED_SSA','PREPARED_G')):req(bits(control[n])==bits(prepared[0][p]) and bits(variant[n])==bits(prepared[1][p]),'actual prepared values vs override')
    held=sorted(rt.BASELINE_SECTIONS-rt.RESPONSE);req(all(bits(variant[n])==bits(baseline[n]) for n in held),'all held sections')
    bnd=inp['BAND_LIMS_GPOINT'][0] if inp['BAND_LIMS_GPOINT'].ndim==3 else inp['BAND_LIMS_GPOINT'];req(bnd.shape==(2,14),'gpoint map axes');selection=np.zeros((1,45,112),dtype=bool);et=baseline['TOTAL_TAU'].copy();es=et*baseline['TOTAL_SSA'];eg=es*baseline['TOTAL_G']
    for b in range(2,14):
        sl=slice(int(bnd[0,b])-1,int(bnd[1,b]));selection[0,29:32,sl]=True
        for k in (29,30,31):
            ot,nt=control['PREPARED_TAU'][0,k,b],variant['PREPARED_TAU'][0,k,b];os,ns=control['PREPARED_SSA'][0,k,b],variant['PREPARED_SSA'][0,k,b];og,ng=control['PREPARED_G'][0,k,b],variant['PREPARED_G'][0,k,b]
            et[0,k,sl]+=nt-ot;es[0,k,sl]+=nt*ns-ot*os;eg[0,k,sl]+=nt*ns*ng-ot*os*og
    req(int(selection.sum())==282,'94 gpoints x3');moments={};actuals={'extinction':variant['TOTAL_TAU'],'scattering_optical_depth':variant['TOTAL_TAU']*variant['TOTAL_SSA'],'scattering_weighted_asymmetry':variant['TOTAL_TAU']*variant['TOTAL_SSA']*variant['TOTAL_G']};expects={'extinction':et,'scattering_optical_depth':es,'scattering_weighted_asymmetry':eg}
    for n,a in actuals.items():
        e=expects[n];resid=abs(a-e);bound=512*np.finfo(np.float64).eps*np.maximum(1,abs(e));req(np.all(resid<=bound),'total moment residual');moments[n]={'max_abs_residual':float(resid.max()),'selected_max_abs_residual':float(resid[selection].max()),'rounding_bound':'512*binary64epsilon*max(1,abs(expected))'}
    for n in ('TOTAL_TAU','TOTAL_SSA','TOTAL_G'):req(bits(variant[n][~selection])==bits(baseline[n][~selection]),'unselected TOTAL optics bit identity')
    g=float(inp['GRAVITY'].reshape(-1)[0]);cp=float(inp['CP_DRY'].reshape(-1)[0]);pl=inp['PLEV'][0];heating={}
    for label,result in zip(('control','variant'),results):
        heating[label]={}
        for sky,names in [('all_sky',('UP','DN','HR')),('clear_sky',('UPC','DNC','HRC'))]:
            u,d,h=(result[n][:,:,0] for n in names);expected_hr=np.empty((1,45))
            for k in range(45):expected_hr[0,k]=(((u[0,k+1]-u[0,k])-d[0,k+1])+d[0,k])*g/(cp*(pl[k+1]*100-pl[k]*100))*86400
            residual=float(abs(h-expected_hr).max());req(residual<=1e-9,'flux heating identity');heating[label][sky]=residual
    legacy_hr=field('RESULT','HEATING');req(legacy_hr.shape==(45,),'legacy heating layer shape');legacy_rows=[]
    for k in (29,30,31):
        old=float(control['HR'][0,k,0]);new=float(variant['HR'][0,k,0]);legacy=float(legacy_hr[k]);legacy_rows.append({'native_layer_one_based':k+1,'pressure_hpa':float(inp['PLAY'][0,k]),'legacy_HEATING_K_day_minus1_promoted_REAL32':legacy,'GP_control_HR_K_day_minus1':old,'GP_variant_HR_K_day_minus1':new,'variant_minus_control':new-old,'control_minus_legacy':old-legacy,'variant_minus_legacy':new-legacy})
    responses={n:delta(control[n],variant[n]) for n in sorted(rt.RESPONSE)};endpoints={}
    for endpoint,index in [('surface',0),('TOA',45)]:
        old={n:float(control[n][0,index,0]) for n in ('UP','DN','DIRECT','DIFFUSE')};new={n:float(variant[n][0,index,0]) for n in old};old['NET_DOWN_MINUS_UP']=old['DN']-old['UP'];new['NET_DOWN_MINUS_UP']=new['DN']-new['UP'];endpoints[endpoint]={'control':old,'variant':new,'variant_minus_control':{n:new[n]-old[n] for n in old}}
    hdiff=variant['HR']-control['HR'];preclaim=json.loads((D/'root-preclaim-format-rejection-v1.json').read_text());req(preclaim['solver_invocations']==0 and preclaim['status']=='REJECTED_BEFORE_EXECUTION_CLAIM' and preclaim['lock_absent'] and preclaim['run_directory_absent'],'preclaim failure scope')
    live=rt.fixed_snapshot(plan);req(live==receipt['initial_pins'] and initial_receipt_pin==pin(receipt_path),'unchanged protected/receipt after audit')
    review={'schema':'exact-band-cloud-swap-independent-terminal-review-v1','status':'PASS_SCOPED_EXACT_TWO_CALLS_HYBRID_ATTRIBUTION','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'reviewer_numerical_invocations':0,'actual_campaign':{'standalone_SW_calls':2,'WRF':0,'REAL':0,'build':0,'receipt':pin(receipt_path),'authorization':pin(D/'root-execution-authorization-v2.json'),'calls':call_rows},'original_preclaim_rejection':{'receipt':pin(D/'root-preclaim-format-rejection-v1.json'),'status':preclaim['status'],'standalone_calls':0,'cause':preclaim['cause']},'control_wholefile_and_all54_sections_baseline_identical':True,'exact54_roster_shapes_and_finite':True,'selected_prepared_cells':36,'selected_property_assignments':108,'selected_gpoints':282,'native_layers':44,'engine_layers':45,'all_selected_CF_and_all112_masks_one':True,'all_other_prepared_and_two_unmatched_bands_bit_identical':True,'all_unselected_TOTAL_optics_bit_identical':True,'held_section_count':len(held),'held_sections_all_bit_identical':held,'total_moment_residuals':moments,'flux_heating_residual_K_day_minus1':heating,'responses_vs_control':responses,'endpoints':endpoints,'native44_HR_max_abs_delta_K_day_minus1':float(abs(hdiff[0,:44,0]).max()),'upper_extension_HR_delta_K_day_minus1':float(hdiff[0,44,0]),'legacy_HEATING_descriptive_comparison':legacy_rows,'immutable_live_source_exe46libraries_SDK20_table_and_inputs_stable':True,'remaining_scope':['Hybrid replacement changes combined prepared native/CU/snow optics at36 cells, while their baseline component diagnostic records stay held. Not isolated engine/PSD/LUT/clipping accuracy.','Gas/clear/frozen/seed/mask/surface/solar and two unmatched bands held; exact shared physical bands do not equate correlated-k quadrature.','Ordinary four PREDELTA diagnostics are baseline/excluded. Actual RTE DIRECT/DIFFUSE/partition outputs are variant solver responses.','Layer31/control/variant/legacy heating comparison is descriptive; no winner or observational/forecast-accuracy conclusion.'],'helper_pin':pin(Path(__file__))}
    out.write_text(json.dumps(review,indent=2,allow_nan=False)+'\n');print(json.dumps({'review':pin(out),'status':review['status'],'endpoints':endpoints,'heating_legacy':legacy_rows,'moments':moments},indent=2))
if __name__=='__main__':main()
