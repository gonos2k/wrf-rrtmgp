"""Standard-library retained-artifact checks; never execute scientific helpers."""
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
def read(name):return json.loads((HERE/name).read_text())
def main():
    manifest=read('manifest.json')
    for row in manifest['files']:
        path=HERE/row['path'];assert path.is_file() and path.stat().st_size==row['bytes'],row['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],row['path']
    index=read('index.json')
    for row in index['verbatim_origins']:
        path=HERE/row['retained_path'];assert path.stat().st_size==row['bytes']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
    s=read('summary.json');orig=read('failure/original-running-execution.json')
    assert s['new_historical_model_invocations']==1 and s['curation_model_build_solver_calls']==0
    assert orig['status']==s['preserved_failure']['original_receipt_status']=='RUNNING'
    rc=s['run']['launcher_returncode'];assert rc['observed'] is False and rc['value'] is None
    assert s['preserved_failure']['numeric_launcher_rc']=='UNAVAILABLE'
    assert s['run']['MPI_ranks']==4 and s['run']['configured_OMP_threads']==2 and s['run']['duration_hours']==24
    assert s['run']['restart_launches']==0 and s['restart_execution']=='NOT_RUN'
    assert len(s['run']['rank_success'])==4 and all(x['success_marker'] for x in s['run']['rank_success'])
    h=s['history'];assert h['variables']==225 and len(h['Times'])==25
    assert h['Times'][0]=='2000-01-24_12:00:00' and h['Times'][-1]=='2000-01-25_12:00:00'
    assert len(s['checkpoints'])==2
    for row in [h]+s['checkpoints']:
        assert row['baseline_sha256']==row['candidate_sha256'] and row['whole_file_equal']
        assert row['all_arrays_dims_dtypes_full_attributes_and_variable_sets_exact']
        assert all(v==0 for v in row['quality'].values())
    assert all(row['variables']==667 for row in s['checkpoints'])
    d=s['diagnostics'];assert (d['cu_population_records'],d['cu_clip_records'],d['native_phase_records'])==(1556,778,3338)
    old=s['legacy_diagnostics'];assert old['status']=='UNCHANGED' and old['baseline_rows']==old['candidate_rows']==7149
    assert all(s['immutability'].values()) and s['scientific_accuracy']=='NOT_ASSESSED'
    assert read('build/build-result-v1.json')['status']=='BUILD_PASS'
    assert read('pre-run/independent-review.json')['verdict']=='PASS'
    peer=s['independent_posthoc_review']
    if peer=='PENDING':status='PASS_RETAINED_HASHES_PEER_REVIEW_PENDING'
    else:
        assert isinstance(peer,dict) and peer['review_passed'] is True
        assert read(peer['retained_path'])['verdict']==peer['verdict']=='PASS_DATA_AND_DIAGNOSTIC_READBACK; LAUNCHER_RC_UNAVAILABLE'
        status='PASS_RETAINED_HASHES_AND_SCOPED_RECEIPT_CONTRACTS'
    print(json.dumps({'status':status,'retained_artifacts':len(manifest['files']),
        'external_arrays_recomputed':False,'new_models':0,'new_builds':0,'new_solver_calls':0}))
if __name__=='__main__':main()
