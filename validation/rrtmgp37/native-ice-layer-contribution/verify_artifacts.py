"""Portable receipt/hash verification only; never invoke scientific processes."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
def read(name): return json.loads((HERE/name).read_text())
def main():
    manifest=read('manifest.json')
    for x in manifest['files']:
        p=HERE/x['path']
        assert p.is_file() and p.stat().st_size==x['bytes'],x['path']
        assert hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256'],x['path']
    index=read('index.json')
    for x in index['verbatim_origins']:
        p=HERE/x['retained_path']
        assert p.stat().st_size==x['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256']
    assert index['models']==0 and index['builds']==0 and index['scientific_policy']=='OPEN'
    assert index['historical_capture_reference_invocations']=={'baseline':6,'contribution':6,'total':12}
    summary=read('inventory/summary.json')
    assert summary['winter_triples_inspected']==65 and summary['winter_clipped_ice_only_population_layers']==0
    b=read('baseline/execution.json');s=read('sensitivity/execution.json')
    assert b['status']=='PASS_SCOPED_SIX_UNMODIFIED_HELD_CAPTURE_BASELINES'
    assert s['status']=='PASS_SCOPED_SIX_CALL_NATIVE_ICE_LAYER_CONTRIBUTION'
    assert b['reference_calls_attempted']==s['reference_calls_attempted']==6
    assert b['new_models']==s['new_models']==b['new_builds']==s['new_builds']==0
    assert len(b['cases'])==len(s['cases'])==6
    for row in b['cases']: assert row['comparison']['passed'] and row['return_code']==0
    controls=[r for r in s['cases'] if r['mode']=='control'];assert len(controls)==2
    for row in controls:
        assert len(row['all_sections_bitwise_equal'])==46 and all(row['all_sections_bitwise_equal'].values())
    for row in s['cases']:
        assert row['return_code']==0
        if row['mode']!='control':assert all(row['unchanged_sections_bitwise'].values())
    assert all(s['offline_negative_controls'].values())
    assert s['predelta_policy'].startswith('EXCLUDED_FROM_COUNTERFACTUAL')
    assert read('baseline/independent-review.json')['status']=='PASS_INDEPENDENT_READ_ONLY_REPLAY_AUDIT'
    assert read('sensitivity/readback.json')['status']=='PASS_READ_ONLY_RESULT_RECOMPUTATION'
    print(json.dumps({'status':'PASS_RETAINED_ARTIFACTS_AND_RECEIPT_CONTRACTS',
       'retained_files':len(manifest['files']),'reference_calls':0,'model_calls':0,
       'external_arrays_recomputed':False}))
if __name__=='__main__':main()
