#!/usr/bin/env python3
"""Portable integrity and semantic checks for the retained nested runtime evidence."""
import csv, hashlib, json, re
from pathlib import Path

def need(ok, msg):
    if not ok: raise ValueError(msg)

def safe(root, rel):
    p=Path(rel); need(not p.is_absolute() and '..' not in p.parts, 'unsafe path '+str(rel))
    q=root/p; need(q.is_file() and not q.is_symlink() and q.resolve().is_relative_to(root.resolve()), 'missing/escaping file '+str(rel))
    return q

def jload(root, rel): return json.loads(safe(root,rel).read_text())

def verify(root):
    root=Path(root).resolve(); m=jload(root,'artifact-manifest.json')
    need(m['schema']=='retained-sha256-manifest-v1','manifest schema')
    entries=m['files']; paths=[x['path'] for x in entries]
    need(len(paths)==len(set(paths)),'duplicate manifest path')
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name!='artifact-manifest.json' and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    need(actual==set(paths),'extra/missing packaged file')
    for x in entries:
        p=safe(root,x['path']); b=p.read_bytes()
        need(len(b)==x['size_bytes'] and hashlib.sha256(b).hexdigest()==x['sha256'],'payload hash/size '+x['path'])
        need(p.suffix.lower() not in {'.nc','.exe','.o','.so','.a'},'model/binary artifact included')
    ledger=jload(root,'runtime-ledger.json'); need(ledger['schema']=='udm37-ccn-nested-runtime-ledger-v1','ledger schema')
    need(ledger['publication_context']['pull_request']==50,'PR context')
    pre=jload(root,'receipts/runtime-preflight-final-v9.json'); stage=jload(root,'receipts/stage.json')
    pins=ledger['provenance']['static_runtime_pins']
    need(pre['source']['base_commit']==pins['source_base_commit']=='4394845667db52c258dab62719abc87402dd731f' and pre['status']=='PASS_POSTHOC_BUILD_IDENTITY' and pre['safety']['model_invocations']==0,'source/preflight provenance')
    srcbuild=jload(root,'reports/restart-root-report-v11.json')['runtime_integrity']['after']['integrity']['build']
    need(pins['source_manifest']==srcbuild['source_manifest'] and pins['wrf_executable']==srcbuild['binary'],'source manifest/executable pins')
    integrity=jload(root,'reports/restart-root-report-v11.json')['runtime_integrity']
    need(pins['resolved_library_file_count']==51 and pins['resolved_libraries_unchanged'] is True and integrity['resolved_libraries_unchanged'] is True and len(integrity['resolved_libraries_before'])==len(integrity['resolved_libraries_after'])==51 and integrity['resolved_libraries_before']==integrity['resolved_libraries_after'],'resolved runtime-library pins')
    stageassets=[{'name':Path(x['path']).name,'sha256':x['sha256'],'size_bytes':x['size_bytes']} for x in stage['runtime_assets']]
    stagecoeffs=[{'name':Path(x['path']).name,'sha256':x['sha256'],'size_bytes':x['size_bytes']} for x in stage['coefficients']]
    need(pins['runtime_assets']==stageassets and pins['coefficient_files']==stagecoeffs,'staged executable/input/coefficient pins')
    cont=jload(root,'reports/continuous-posthoc-v4.json'); omit=jload(root,'reports/continuous-omission-audit.json'); rpt=jload(root,'reports/restart-root-report-v11.json')
    need(ledger['provenance']['root_readback']['sha256']==hashlib.sha256(safe(root,'reports/restart-root-report-v11.json').read_bytes()).hexdigest(),'root v11 report pin')
    ce=jload(root,'receipts/continuous-execution.json'); rexe=jload(root,'receipts/restart-execution.json')
    need(ce['returncode']==0 and ce['all_rank_success'] and len(ce['rank_success'])==4 and all(ce['rank_success'].values()) and ce['model_invocations']==1 and not ce['fatal_present'] and ce['status']=='FAIL_PRESERVED','continuous original execution status')
    need(rexe['returncode']==0 and rexe['all_rank_success'] and len(rexe['rank_success'])==4 and all(rexe['rank_success'].values()) and rexe['model_invocations']==1 and not rexe['fatal_present'] and rexe['status']=='FAIL_PRESERVED','restart original execution status')
    need('RTHRATLW' in ce['error'] and 'RTHRATSW' in ce['error'],'continuous original strict failure')
    need('WRF_ALARM_SECS_TIL_NEXT_RING_51' in rexe['error'],'restart original strict failure')
    need(cont['status']=='PASS_POSTHOC_CONTINUOUS_READBACK' and cont['original_execution_status']=='FAIL_PRESERVED','continuous posthoc scope')
    need(omit['status']=='PASS_OUTPUT_OMISSION_ATTRIBUTION_ONLY' and omit['original_execution']['status']=='FAIL_PRESERVED','continuous omission attribution')
    need(rpt['status']=='PASS_SCOPED_RESTART_PARITY_WITH_INITIAL_DIAGNOSTIC_RESET_AND_FINAL_RESTART_ALARM_METADATA' and rpt['strict_restart_status']=='FAIL_PRESERVED','restart posthoc/original strict scope')
    need(rpt['counts']=={'final_checkpoint_pairs':2,'final_checkpoint_variables':{'d01':650,'d02':649},'history_exact_fields':2478,'history_pairs':12,'history_variables_by_domain':{'d01':209,'d02':205},'initial_diagnostic_resets':6},'restart comparison counts')
    freeze=jload(root,'receipts/root-attribution-freeze-v1.json')
    tool=safe(root,'tools/compare_restart_v11.py')
    need(freeze['status']=='ROOT_FROZEN_READ_ONLY_ATTRIBUTION_COMPARATOR' and hashlib.sha256(tool.read_bytes()).hexdigest()==freeze['comparator']['sha256']==rpt['analyzer']['sha256'],'v11 comparator freeze/pin')
    tool10=safe(root,'tools/compare_restart.py')
    need(hashlib.sha256(tool10.read_bytes()).hexdigest()==freeze['preserved_v10_comparator']['sha256'],'v10 comparator source pin for 13 controls')
    controls_result=jload(root,'receipts/negative-controls-v4.json')
    controls_script=safe(root,'tools/test_contract.py')
    need(controls_result['status']=='PASS' and len(controls_result['cases'])==13 and hashlib.sha256(controls_script.read_bytes()).hexdigest()=='5175c5b4cb53ddf4bf0d71995a12a1aa68cd8db85287c7c81ac1f9e4cfa742ba','v10 negative control source/result identity')
    controls=jload(root,'receipts/root-controls-v1.json'); need(controls['status']=='PASS' and len(controls['cases'])==13,'13 comparator controls')
    passed={q['name'] for q in controls['cases'] if not q['rejected']}; rejected={q['name'] for q in controls['cases'] if q['rejected']}
    need(passed=={'clean-history','valid-initial-diagnostic-reset','valid-final-checkpoint'} and len(rejected)==10,'3 accepted fixtures and 10 rejected mutations')
    quality=jload(root,'receipts/root-quality-controls-v1.json'); need(quality['status']=='PASS' and len(quality['cases'])==5 and all(q['status']=='REJECTED_AS_EXPECTED' for q in quality['cases']) and quality['comparator_sha256']==freeze['comparator']['sha256'],'five root-added numeric-quality controls against v11')
    # Validate variable-level hash rows directly against the frozen root report.
    def expected_rows():
        for q in rpt['history_pairs']+rpt['final_checkpoint_pairs']:
            for v in q['variables']:
                yield [q['kind'],str(q['domain']),q['timestamp'],v['name'],v['dtype'],json.dumps(v['shape'],separators=(',',':')),v['continuous_raw_sha256'],v['restart_raw_sha256'],str(v['raw_bytes_equal']).lower(),str(v['variable_attributes_equal']).lower(),v['variable_attributes_sha256'],v['classification']]
    p=safe(root,'reports/restart-variable-raw-hashes.csv')
    with p.open(newline='') as f: rows=list(csv.reader(f))
    header=['kind','domain','timestamp','variable','dtype','shape_json','continuous_raw_sha256','restart_raw_sha256','raw_bytes_equal','variable_attributes_equal','variable_attributes_sha256','classification']
    need(rows[0]==header and rows[1:]==list(expected_rows()),'raw variable hash CSV does not match report')
    need(len(rows)-1==3783,'raw variable hash row count')
    diffs=[r for r in rows[1:] if r[8]=='false']
    need(len(diffs)==6 and {r[3] for r in diffs}=={'UDM_CLDFRA','UDM_CF_STEP','UDM_CF_TOP'} and all(r[11]=='initial_restart_reset_to_minus_one' for r in diffs),'only documented initial diagnostic resets')
    need(all(r[9]=='true' for r in rows[1:]),'variable attribute mismatch')
    # File-level outputs inventory matches the two independent posthoc ledgers.
    with safe(root,'reports/external-output-inventory.csv').open(newline='') as f: inv=list(csv.DictReader(f))
    need(len(inv)==38,'output inventory row count')
    ci=[x for x in inv if x['run']=='continuous']; ri=[x for x in inv if x['run']=='restart']
    need(sum(x['kind']=='history' for x in ci)==20 and sum(x['kind']=='checkpoint' for x in ci)==4,'continuous output counts')
    need(sum(x['kind']=='history' for x in ri)==12 and sum(x['kind']=='checkpoint' for x in ri)==2,'restart output counts')
    need(all(re.fullmatch(r'[0-9a-f]{64}',x['sha256']) and int(x['size_bytes'])>0 for x in inv),'external output hash syntax')
    expected_outputs=[]
    for dom,items in cont['histories'].items():
        expected_outputs.extend(('continuous','history',dom,q['time'],q['path'],q['size_bytes'],q['sha256'],'true') for q in items)
    for group in ('checkpoints_0110','checkpoints_0200'):
        expected_outputs.extend(('continuous','checkpoint',dom,q['time'],q['path'],q['size_bytes'],q['sha256'],'true') for dom,q in cont[group].items())
    expected_outputs.extend(('restart','history',str(q['domain']),q['timestamp'],q['restart']['path'],q['restart']['size_bytes'],q['restart']['sha256'],'true') for q in rpt['history_pairs'])
    expected_outputs.extend(('restart','checkpoint',str(q['domain']),q['timestamp'],q['restart']['path'],q['restart']['size_bytes'],q['restart']['sha256'],'true') for q in rpt['final_checkpoint_pairs'])
    observed_outputs=[(x['run'],x['kind'],x['domain'],x['time'],x['external_path'],int(x['size_bytes']),x['sha256'],x['selected_for_comparison']) for x in inv]
    need(observed_outputs==expected_outputs,'external output inventory differs from reports')
    with safe(root,'reports/restart-input-checkpoint-links.csv').open(newline='') as f: links=list(csv.DictReader(f))
    expected_links=[]
    for q in rpt['restart_input_checkpoint_links']:
        match=re.search(r'wrfrst_(d\d+)_',q['path']); expected_links.append((match.group(1) if match else '',q['path'],q['target'],q['size_bytes'],q['sha256']))
    observed_links=[(x['domain'],x['external_path'],x['target_path'],int(x['size_bytes']),x['sha256']) for x in links]
    need(observed_links==expected_links and all('01:10:00' in x[1] and '01:10:00' in x[2] for x in observed_links),'restart input checkpoint link identity')
    sibling_att=root.parent/'udm-ccn-runtime/retained/udm37-ccn-tile-init-gnu-v1/posthoc-v3/posthoc-attestation-v3.json'
    if sibling_att.is_file():
        ref=ledger['provenance']['build_attestation_external']
        need(sibling_att.stat().st_size==ref['size_bytes'] and hashlib.sha256(sibling_att.read_bytes()).hexdigest()==ref['sha256'],'sibling PR50 build-attestation pin')
    # Check concrete configuration values in retained namelists and I/O field list.
    n1=safe(root,'inputs/continuous.namelist.input').read_text(); n2=safe(root,'inputs/restart.namelist.input').read_text()
    expected_namelists={'max_dom':r'2', 'mp_physics':r'27\s*,\s*27', 'ra_lw_physics':r'37\s*,\s*37', 'ra_sw_physics':r'37\s*,\s*37', 'cu_physics':r'1\s*,\s*0'}
    for n in (n1,n2):
        for key,value in expected_namelists.items():
            need(re.search(r'^\s*'+key+r'\s*=\s*'+value+r'\s*,?\s*(?:!.*)?$',n,re.I|re.M) is not None, 'namelist scope value mismatch: '+key)
    need(ledger['scope']['domains']['d01']['cu_physics']==1 and ledger['scope']['domains']['d02']['cu_physics']==0,'parent/child CU scope')
    need(ledger['external_model_output_inventory']['model_files_in_package'] is False and ledger['per_variable_hashes']['external_netcdf_arrays_in_package'] is False,'external model files disclosure')
    return {'status':'PASS_NESTED_RUNTIME_PACKAGE_INTEGRITY_AND_SCOPE','files':len(entries),'continuous_histories':20,'continuous_selected_checkpoints':4,'restart_histories':12,'restart_final_checkpoints':2,'restart_raw_variable_hash_rows':len(rows)-1,'restart_exact_rows':len(rows)-1-len(diffs),'documented_initial_reset_rows':len(diffs),'model_invocations':2,'strict_original_receipts_preserved_fail':2,'root_comparator_controls':13,'additional_quality_rejections':5}

if __name__=='__main__':
    import json
    print(json.dumps(verify(Path(__file__).parent),sort_keys=True))
