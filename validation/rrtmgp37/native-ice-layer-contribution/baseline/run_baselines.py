"""Six authorized unchanged held-state reference calls; no WRF/build/sensitivity."""
import datetime, hashlib, json, os, pathlib, re, shutil, subprocess, sys, time, traceback
sys.dont_write_bytecode = True
R = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE/'runs-v1'
INV_PATH = R/'build/udm37-occurrence-clipping-replay-inventory-v1/inventory.json'
INV_SHA = 'fd124f5dd5f8c5a6b3cb28cf1d16fab9159f6666c6c091944fdbdd0e190dc416'
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def pin(p):
    p=pathlib.Path(p);return {'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}
def save(receipt): (OUT/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n')
def main():
    assert not OUT.exists(), 'output collision'
    assert sha(INV_PATH)==INV_SHA
    inv=json.loads(INV_PATH.read_text())
    files={R/x['path']:x['sha256'] for x in inv['helper_pins']+inv['external_evidence_pins']}
    files.update({R/x['path']:x['sha256'] for x in inv['existing_reference_pins']})
    profiles=[('winter-native-cu', x) for x in inv['winter_inventory']
         if x['pins'][0]['path'].endswith(('lw_000018.input','sw_000011.input'))]
    profiles += [(name,x) for name in ['ice_clip_low_cloud_proxy','ice_clip_high_cloud_proxy']
         for x in inv['historical_anchors'][name]]
    assert len(profiles)==6
    for _,x in profiles:
        files.update({R/a['path']:a['sha256'] for a in x['pins']})
    for x in inv['source_compatibility']:
        for k in ['current','capture_source']:
            if x[k]:files[R/x[k]['path']]=x[k]['sha256']
    # Authenticate all snapshots before import or solver calls.
    def verify():
        for path,digest in files.items(): assert sha(path)==digest,(path,'pin changed')
    verify()
    support=R/'build/udm37-phase-diagnostic-contract-pr-work/WRF/test/rrtmgp'
    sys.path.insert(0,str(support))
    import test_column_replay as t
    import compare_column_replay as c
    import numpy as np
    refs={x['role']:R/x['path'] for x in inv['existing_reference_pins']}
    exe=refs['reference_executable'];data=refs['cloud_lw'].parent;table=refs['frozen_table']
    env={k:v for k,v in os.environ.items() if not k.startswith('WRF_RRTMGP_') and k!='LD_PRELOAD'}
    env.update(OMP_NUM_THREADS='1',OMP_DYNAMIC='FALSE',OPENBLAS_NUM_THREADS='1',
       WRF_RRTMGP_FROZEN_TABLE=str(table),LD_LIBRARY_PATH=str(R/'build/deps/netcdf/lib')+':/usr/lib/x86_64-linux-gnu')
    def dependencies():
        q=subprocess.run(['ldd',str(exe)],env=env,text=True,capture_output=True,check=False)
        assert q.returncode==0 and 'not found' not in q.stdout
        paths=re.findall(r'(?:=>\s+)?(/[^\s]+)\s+\(',q.stdout)
        return sorted((pin(path) for path in set(paths)),key=lambda x:x['path'])
    deps=dependencies();OUT.mkdir()
    receipt={'status':'RUNNING','scope':'Six unmodified historical held-call reference baselines; not current PR60 WRF trajectory',
       'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
       'new_models':0,'new_builds':0,'reference_calls_attempted':0,'maximum_reference_calls':6,
       'inventory':pin(INV_PATH),'runner':pin(__file__),'pinned_files_before':[pin(x) for x in files],
       'normalized_dependencies_before':deps,'controlled_environment':env,'cases':[]}
    # Store controlled scientific keys only; inherited ambient environment need not be published.
    receipt['controlled_environment']={k:env[k] for k in ['OMP_NUM_THREADS','OMP_DYNAMIC','OPENBLAS_NUM_THREADS','WRF_RRTMGP_FROZEN_TABLE','LD_LIBRARY_PATH']}
    save(receipt)
    failure=None
    try:
        for name,x in profiles:
            verify();phase=x['phase'];case=OUT/(name+'-'+phase.lower());case.mkdir();cap=case/'capture';cap.mkdir()
            for suffix,item in zip(['input','raw','result'],x['pins']):
                target=cap/(phase.lower()+'.'+suffix);shutil.copyfile(R/item['path'],target)
                assert sha(target)==item['sha256']
            inp_path=cap/(phase.lower()+'.input');raw_path=cap/(phase.lower()+'.raw')
            _,nc,nl,ov,seed,iceflag,a=t.read_input(inp_path);_,i,j,raw=t.read_raw(raw_path)
            raw_nl=len(raw['DP_HPA']);magic=inp_path.read_text().splitlines()[0]
            if magic in ['RRTMGP_REPLAY_V10','RRTMGP_REPLAY_V11']:
                t.validate_cu_population_records(a,nc,nl,phase,magic,inp_path)
                t.validate_cu_population_raw(raw,a,raw_nl,raw_path)
            assert int(raw['MP_PHYSICS'].item())==27
            # This checker reads its frozen identity environment explicitly.
            os.environ['WRF_RRTMGP_FROZEN_TABLE']=str(table)
            t.verify_frozen_table(a,nc,nl,case)
            mapping=t.compare_input_to_raw(phase,raw,a,raw_nl)
            species=t.check_microphysics_mapping(27,raw,a,phase,raw_nl)
            ref=cap/(phase.lower()+'.reference.result')
            cmd=[str(exe),str(data),str(inp_path),str(ref)]
            row={'name':name,'phase':phase,'command':cmd,'cwd':str(case),'status':'RUNNING',
                 'source_capture_pins':x['pins'],'copied_capture_pins':[pin(p) for p in sorted(cap.iterdir())]}
            receipt['cases'].append(row);receipt['reference_calls_attempted']+=1;save(receipt)
            start=time.monotonic()
            with (case/'reference.stdout').open('wb') as stdout,(case/'reference.stderr').open('wb') as stderr:
                result=subprocess.run(cmd,cwd=case,env=env,stdout=stdout,stderr=stderr,timeout=120,check=False)
            row.update(return_code=result.returncode,elapsed_seconds=time.monotonic()-start)
            assert result.returncode==0 and ref.is_file(), 'reference process failed'
            production=c.read_result(cap/(phase.lower()+'.result'));reference=c.read_result(ref)
            for z in [production,reference]:
                assert all(np.isfinite(v).all() for v in z['sections'].values())
            comparison=c.compare(production,reference);row['comparison']=comparison
            assert comparison['passed'],comparison['failed_sections']
            assert np.array_equal(production['sections']['MASK'],reference['sections']['MASK'])
            row['wrf_diagnostics']=t.check_wrf_diagnostics(phase,production,raw,raw_nl)
            row['input_raw_checks']=mapping;row['species_mapping']=species
            if phase=='SW' and 'RAW_GAS_TAU' in a:
                expected=production['sections']['GAS_TAU'].astype(np.float32).astype(np.float64)
                assert np.array_equal(a['RAW_GAS_TAU'],expected)
                row['raw_gas_serialization']='EXACT binary32(GAS_TAU), no tolerance relaxation'
            for suffix,item in zip(['input','raw','result'],x['pins']):assert sha(cap/(phase.lower()+'.'+suffix))==item['sha256']
            row['output_pins']=[pin(p) for p in [ref,case/'reference.stdout',case/'reference.stderr']]
            row['status']='PASS_STRICT_HELD_CAPTURE_BASELINE';verify();save(receipt)
            print(json.dumps({'name':name,'phase':phase,'status':row['status'],
                'sections':comparison['sections_compared'],'elapsed_seconds':row['elapsed_seconds']}),flush=True)
        receipt['status']='PASS_SCOPED_SIX_UNMODIFIED_HELD_CAPTURE_BASELINES'
    except BaseException as exc:
        receipt['status']='FAILED_PRESERVED_STOPPED';receipt['error']=repr(exc);receipt['traceback']=traceback.format_exc();failure=exc
    finally:
        try:
            verify();assert dependencies()==deps
            receipt['immutable_inputs_sources_reference_dependencies']='PASS'
        except BaseException as exc:
            receipt['status']='FAILED_PRESERVED_STOPPED';receipt['postflight_error']=repr(exc);failure=exc
        receipt['ended_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();save(receipt)
    print(json.dumps({'status':receipt['status'],'calls':receipt['reference_calls_attempted'],'receipt':pin(OUT/'execution.json')}),flush=True)
    if failure:raise SystemExit(1)
if __name__=='__main__':main()
