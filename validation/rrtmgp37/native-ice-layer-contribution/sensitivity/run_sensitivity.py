"""Exactly six authorized offline calls: two SW controls, two SW and two LW variants."""
import hashlib,json,os,pathlib,re,subprocess,sys,time,traceback,datetime
sys.dont_write_bytecode=True
R=pathlib.Path(__file__).resolve().parents[2];H=pathlib.Path(__file__).resolve().parent;O=H/'runs-v1'
B=R/'build/udm37-occurrence-clipping-baseline-replay-v1/runs-v1'
RECEIPT_SHA='fd1264d843996eeaef44e28cd0ae393a95f3be08c0a8e3dc5fa36612ebc13603'
PROFILES={'ice_clip_low_cloud_proxy':[15,16,17,18],'ice_clip_high_cloud_proxy':[17,18,19]}
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def pin(p):
    p=pathlib.Path(p);return {'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}
def save(z):(O/'execution.json').write_text(json.dumps(z,indent=2)+'\n')
def main():
    import numpy as np
    assert not O.exists(),'output collision'
    assert sha(B/'execution.json')==RECEIPT_SHA
    base_receipt=json.loads((B/'execution.json').read_text());assert base_receipt['status']=='PASS_SCOPED_SIX_UNMODIFIED_HELD_CAPTURE_BASELINES'
    files={pathlib.Path(x['path']):x['sha256'] for x in base_receipt['pinned_files_before']}
    for row in base_receipt['cases']:
        for x in row['output_pins']+row['copied_capture_pins']:files[pathlib.Path(x['path'])]=x['sha256']
    for x in base_receipt['normalized_dependencies_before']:files[pathlib.Path(x['path'])]=x['sha256']
    files[B/'execution.json']=RECEIPT_SHA
    def verify():
        for p,s in files.items():assert sha(p)==s,(p,'changed pin')
    verify()
    S=R/'build/udm37-phase-diagnostic-contract-pr-work/WRF/test/rrtmgp';sys.path.insert(0,str(S))
    import test_column_replay as t
    import compare_column_replay as c
    exe=R/'build/udm-cu-focused-v2/reference_column';data=R/'build/udm-cu-optics-design-work/WRF/run'
    env={k:v for k,v in os.environ.items() if not k.startswith('WRF_RRTMGP_') and k!='LD_PRELOAD'}
    env.update(base_receipt['controlled_environment'])
    # IEEE bytes, including signed zeros; all comparison data are float64.
    def exact(a,b):return a.shape==b.shape and a.dtype==b.dtype and a.tobytes()==b.tobytes()
    def reject_nonpure(a,layers):
        assert not any(n.startswith('CU_') for n in a),'CU population not allowed'
        assert a['PRECIPITATION_OPTICS'].item()==1,'snow must be separate precip'
        for k in layers:
            assert a['LWP'][0,k-1]==0 and a['IWP'][0,k-1]>0 and a['CF'][0,k-1]>0
            assert 2*a['REI'][0,k-1]>180,'not clipped eligible ice'
    def check_replacement(v,original,precip,layers):
        for field in ['TAU','SSA','G']:
            expected=original['PREPARED_'+field].copy()
            for k in layers:expected[:,k-1,:]=precip['PRECIP_'+field][:,k-1,:]
            assert exact(v[field],expected),'replacement must retain original precipitation only'
    snapshots={};eligibility={}
    for name,layers in PROFILES.items():
        snapshots[name]={};eligibility[name]={}
        for phase in ['LW','SW']:
            case=B/(name+'-'+phase.lower());inp=case/'capture'/f'{phase.lower()}.input';rawp=case/'capture'/f'{phase.lower()}.raw'
            ph,nc,nl,ov,seed,ice,a=t.read_input(inp);_,i,j,raw=t.read_raw(rawp);z=c.read_result(case/'capture'/f'{phase.lower()}.reference.result')
            assert ph==phase and ice==4 and ov!=0;reject_nonpure(a,layers)
            snapshots[name][phase]=(a,z,inp)
            eligibility[name][phase]=[{'native_k_1based':k,'requested_diameter_um':float(2*a['REI'][0,k-1]),
              'used_diameter_um':float(z['sections']['DI_USED'][0,k-1,0]),'grid_iwp_g_m2':float(raw['IWP_GRID'][k-1]),
              'incloud_iwp_g_m2':float(a['IWP'][0,k-1]),'liquid_path':0,'CF':float(a['CF'][0,k-1]),
              'sampled_gpoints':int(np.count_nonzero(z['sections']['MASK'][0,k-1])),
              'gpoints':int(z['sections']['MASK'].shape[2]),
              'sampled_fraction':float(np.mean(z['sections']['MASK'][0,k-1]))} for k in layers]
            assert all(x['used_diameter_um']==180 for x in eligibility[name][phase])
        assert exact(snapshots[name]['SW'][0]['BAND_LIMS_WAVENUMBER'],
               snapshots[name]['SW'][0]['BAND_LIMS_WAVENUMBER'])
    # No extra solver calls: fail an actual mixed native layer and a wrong replacement array.
    controls={}
    a=snapshots['ice_clip_high_cloud_proxy']['SW'][0]
    try:reject_nonpure(a,[16])
    except AssertionError:controls['mixed_layer_k16_rejected']=True
    else:raise AssertionError('non-pure negative control failed')
    for name,layers in PROFILES.items():
        s=snapshots[name]['SW'][1]['sections'];wrong={f:s['PREPARED_'+f].copy() for f in ['TAU','SSA','G']}
        for f in wrong:
            for k in layers:wrong[f][:,k-1,:]=s['CLOUD_'+f][:,k-1,:]
        try:check_replacement(wrong,s,s,layers)
        except AssertionError:controls[name+'_cloud_instead_precip_rejected']=True
        else:raise AssertionError('cloud-tau negative control failed')
    O.mkdir();receipt={'status':'RUNNING','scope':'Finite native ice-layer contribution; not clipping error, physical accuracy or current WRF trajectory',
       'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runner':pin(__file__),
       'baseline_receipt':pin(B/'execution.json'),'pins_before':[pin(p) for p in files],
       'source_contract_pins':[pin(S/'reference_column.f90'),pin(S/'test_column_replay.py'),pin(S/'compare_column_replay.py')],
       'controlled_environment':base_receipt['controlled_environment'],'eligibility':eligibility,
       'offline_negative_controls':controls,'maximum_reference_calls':6,'reference_calls_attempted':0,
       'new_models':0,'new_builds':0,'cases':[],'predelta_policy':'EXCLUDED_FROM_COUNTERFACTUAL: raw extinction and pre-delta direct remain unchanged baseline under SW prepared override'};save(receipt)
    failed=None
    try:
        for mode,phase in [('control','SW'),('remove_native_ice','SW'),('remove_native_ice','LW')]:
            for name,layers in PROFILES.items():
                verify();a,z,original=snapshots[name][phase];s=z['sections'];case=O/(name+'-'+phase.lower()+'-'+mode);case.mkdir()
                inp=original;override=None
                if phase=='SW':
                    arr={f:s['PREPARED_'+f].copy() for f in ['TAU','SSA','G']}
                    if mode=='remove_native_ice':
                        for f in arr:
                            for k in layers:arr[f][:,k-1,:]=s['PRECIP_'+f][:,k-1,:]
                        check_replacement(arr,s,s,layers)
                    bands=a['BAND_LIMS_WAVENUMBER'];assert bands.shape==(2,14) and bands[1,0]==2680 and bands[0,1]==2680
                    override=case/'prepared-optics.override'
                    with override.open('w') as f:
                        f.write('WRF_SW_OPTICS_OVERRIDE_V1\n1 '+str(a['IWP'].shape[1])+' 14\nBAND_LIMITS 2 14\n')
                        f.write('\n'.join(format(v,'.17e') for v in bands.ravel(order='F'))+'\n')
                        for label,key in [('TAU','TAU'),('SSA','SSA'),('ASYM','G')]:
                            v=arr[key];f.write(f'{label} {v.shape[0]} {v.shape[1]} {v.shape[2]}\n')
                            f.write('\n'.join(format(q,'.17e') for q in v.ravel(order='F'))+'\n')
                else:
                    text=original.read_text();lines=text.splitlines(keepends=True)
                    idx=next(i for i,l in enumerate(lines) if l.startswith('IWP '));assert tuple(map(int,lines[idx].split()[1:]))==a['IWP'].shape
                    v=a['IWP'].copy()
                    for k in layers:v[0,k-1]=0
                    # Only IWP block is replaced; other records remain byte-identical.
                    end=idx+1;count=0
                    while count<v.size:count+=len(lines[end].split());end+=1
                    assert count==v.size
                    inp=case/'lw.variant.input';inp.write_text(''.join(lines[:idx+1])+''.join(format(q,'.17e')+'\n' for q in v.ravel(order='F'))+''.join(lines[end:]))
                    *_,parsed=t.read_input(inp);assert set(parsed)==set(a)
                    for field in a:assert exact(parsed[field],v if field=='IWP' else a[field]),field
                output=case/'reference.result';cmd=[str(exe),str(data),str(inp),str(output)]
                if override:cmd+=['1',str(override)]
                row={'profile':name,'phase':phase,'mode':mode,'status':'RUNNING','command':cmd,'cwd':str(case),
                   'input':pin(inp),'override':pin(override) if override else None};receipt['cases'].append(row);receipt['reference_calls_attempted']+=1;save(receipt)
                start=time.monotonic()
                with (case/'stdout').open('wb') as out,(case/'stderr').open('wb') as err:
                    result=subprocess.run(cmd,cwd=case,env=env,stdout=out,stderr=err,timeout=120,check=False)
                row.update(return_code=result.returncode,elapsed_seconds=time.monotonic()-start);assert result.returncode==0
                new=c.read_result(output);v=new['sections'];assert set(v)==set(s)
                assert all(np.isfinite(q).all() for q in v.values())
                if mode=='control':
                    row['all_sections_bitwise_equal']={field:exact(s[field],v[field]) for field in s}
                    assert all(row['all_sections_bitwise_equal'].values()),'override identity control mismatch'
                else:
                    unchanged=[field for field in s if field.startswith(('GAS_','PRECIP_','GRAUPEL_','HAIL_','FROZEN_')) or field in ['MASK','UPC','DNC','HRC','DIRECTC','RL_USED','DI_USED','DS_USED'] or field.endswith('_PREDELTA')]
                    row['unchanged_sections_bitwise']={field:exact(s[field],v[field]) for field in unchanged}
                    assert all(row['unchanged_sections_bitwise'].values()),'fixed component changed'
                    other=np.ones(s['PREPARED_TAU'].shape[1],dtype=bool);other[np.array(layers)-1]=False
                    for field in ['TAU','SSA','G'] if phase=='SW' else ['TAU']:
                        assert exact(s['PREPARED_'+field][:,other,:],v['PREPARED_'+field][:,other,:]),'unselected layer changed'
                    if phase=='SW':check_replacement({f:v['PREPARED_'+f] for f in ['TAU','SSA','G']},s,s,layers)
                    metrics={}
                    for field in ['UP','DN','HR']+(['DIRECT','DIFFUSE'] if phase=='SW' else []):
                        d=v[field]-s[field];metrics[field]={'variant_minus_baseline_surface_or_lowest':float(d[0,0,0]),
                          'variant_minus_baseline_toa_or_highest':float(d[0,-1,0]),'max_abs':float(np.max(np.abs(d))),
                          'vertical_variant_minus_baseline':d[0,:,0].tolist(),'units':'K/day' if field=='HR' else 'W/m2'}
                    d=(v['DN']-v['UP'])-(s['DN']-s['UP']);metrics['NET_DOWN']={'surface':float(d[0,0,0]),'toa':float(d[0,-1,0]),'vertical':d[0,:,0].tolist(),'units':'W/m2'}
                    row['finite_layer_contribution']=metrics
                row['status']='PASS_SCOPED_CONTROL' if mode=='control' else 'PASS_SCOPED_NATIVE_ICE_LAYER_CONTRIBUTION'
                row['output_pins']=[pin(output),pin(case/'stdout'),pin(case/'stderr')];verify();save(receipt)
                print(json.dumps({'profile':name,'phase':phase,'mode':mode,'status':row['status']}),flush=True)
        receipt['status']='PASS_SCOPED_SIX_CALL_NATIVE_ICE_LAYER_CONTRIBUTION'
    except BaseException as e:
        receipt['status']='FAILED_PRESERVED_STOPPED';receipt['error']=repr(e);receipt['traceback']=traceback.format_exc();failed=e
    finally:
        try:verify();receipt['original_source_inputs_binary_libraries_unchanged']='PASS'
        except BaseException as e:receipt['status']='FAILED_PRESERVED_STOPPED';receipt['postflight_error']=repr(e);failed=e
        receipt['ended_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();save(receipt)
    print(json.dumps({'status':receipt['status'],'calls':receipt['reference_calls_attempted'],'receipt':pin(O/'execution.json')}),flush=True)
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
