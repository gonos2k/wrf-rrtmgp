from pathlib import Path
import json,hashlib,re
ROOT=Path(__file__).resolve().parents[2]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def pin(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p),'size_bytes':p.stat().st_size}
baseline=ROOT/'build/udm37-lblrtm-held-state-continuum-od-run-v1'
bprep=json.loads((baseline/'runs/od-v1/prepared.json').read_text());bp=json.loads((baseline/'od-parse-v1.json').read_text())
rows=[]
for name,folder,sample,coupled in [('coupled_sample8','udm37-lblrtm-held-state-sample8-od-run-v1',8,True),('nocpl_sample4','udm37-lblrtm-held-state-nocpl-od-run-v1',4,False),('nocpl_sample8','udm37-lblrtm-held-state-nocpl-sample8-od-run-v1',8,False)]:
 d=ROOT/'build'/folder;rd=d/'runs/od-v1';e=json.loads((rd/'execution.json').read_text());pe=json.loads((d/'parser-execution-v1.json').read_text());assert e['actual_child_returncode']==pe['actual_child_returncode']==0 and not e['timed_out']
 prep=json.loads((rd/'prepared.json').read_text());assert prep['executable']==bprep['executable'];assert sha(Path(prep['executable']['path']))==prep['executable']['sha256']
 current=[]
 for a in prep['inputs']:
  f=rd/a['path'];assert sha(f)==a['sha256'] and f.stat().st_size==a['size_bytes'];assert (not f.is_symlink()) if a['kind']=='copied_input' else f.resolve()==Path(a['resolved_path']);current.append(a)
 changes=[a['path'] for a,b in zip(prep['inputs'],bprep['inputs']) if a!=b];assert changes==(['TAPE5'] if coupled else (['TAPE3'] if sample==4 else ['TAPE5','TAPE3']))
 old=(baseline/'TAPE5').read_bytes();new=(d/'TAPE5').read_bytes();delta=[i for i,(a,b)in enumerate(zip(old,new)) if a!=b];assert len(old)==len(new) and delta==([]if sample==4 else[193]);assert new== (baseline/'TAPE5').read_bytes() if sample==4 else new[193:194]==b'8'
 got=json.loads((d/'od-parse-v1.json').read_text());assert [r['layer']for r in got['layers']]==list(range(1,46))
 for b,r in zip(bp['layers'],got['layers']):
  assert b['PAVE']==r['PAVE'] and b['TAVE']==r['TAVE'] and b['PZL_PZU_TZL_TZU_WBROAD_DV_V1_V2'][:5]==r['PZL_PZU_TZL_TZU_WBROAD_DV_V1_V2'][:5];assert r['finite'];assert sum(t['n']for t in r['panels'])==r['sample_count']
 t6=(rd/'TAPE6').read_text(errors='replace');assert 'Using MT_CKD' in t6
 rows.append({'case':name,'input_control_changes':changes,'deck_changed_offsets':delta,'staged_inputs_current_hash_match':len(current),'held45pressure_temperature_and_broadener_equal':True,'same_executable':True,'solver_actual_child_RC':e['actual_child_returncode'],'parser_actual_child_RC':pe['actual_child_returncode'],'samples':sum(r['sample_count']for r in got['layers']),'negative_count':sum(r['negative_count']for r in got['layers']),'minimum':min(r['value_min']for r in got['layers']),'physical_reference_acceptance':'FAIL_NEGATIVE_OD_PRESERVED','artifacts':[pin(rd/'execution.json'),pin(d/'parser-execution-v1.json'),pin(d/'od-parse-v1.json'),pin(d/'TAPE5')]})
report={'status':'PASS_SCOPED_CONTROL_AND_SAVED_OUTPUT_READBACK','scope':'Actualsaved3newstocksolves; control/input/header/countreadback only. NegativeODphysicalreferencegates remainFAIL. No solver/parser/build rerun by this checker.','cases':rows}
f=Path(__file__).with_name('report.json');assert not f.exists();f.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
