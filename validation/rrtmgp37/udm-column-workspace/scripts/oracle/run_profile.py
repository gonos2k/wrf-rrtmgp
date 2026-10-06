import csv,json,os,subprocess
from pathlib import Path
root=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP');scratch=root/'build/udm-workspace-oracle';worktree=root/'build/udm-workspace-reuse-work'
fields=['phase','call','malloc_or_realloc','requested_bytes','gas_init','descriptor_init','optics1_alloc','optics2_alloc','source_alloc','diagnostic_malloc','diagnostic_bytes']
results={}
for mode in [0,1]:
    for label,binary in [('baseline',scratch/'profile/baseline_workspace'),('candidate',scratch/'profile/candidate/test_rrtmgp_workspace')]:
        out=scratch/f'profile-mode{mode}-{label}';out.mkdir(exist_ok=True)
        profile=out/'calls.csv';profile.write_text(','.join(fields)+'\n')
        env={**os.environ,'LD_LIBRARY_PATH':str(root/'build/deps/netcdf/lib'),'OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE','WORKSPACE_PROFILE_FILE':str(profile)}
        env.pop('WRF_RRTMGP_CAPTURE_DIR',None)
        p=subprocess.run([str(binary),str(worktree/'WRF/run'),str(mode),str(worktree/'validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc'),str(out/'outputs.bin')],capture_output=True,text=True,env=env)
        (out/'run.log').write_text(p.stdout+p.stderr)
        if p.returncode: raise RuntimeError(p.stdout+p.stderr)
        with profile.open() as f: rows=list(csv.DictReader(f))
        results[f'{mode}-{label}']={}
        for phase in ['LW','SW']:
            # First shape 1x3: call1 fresh state1, call2 first workspace state1,
            # call3 fresh state2, call4 reused workspace state2.
            r=[r for r in rows if r['phase']==phase]
            results[f'{mode}-{label}'][phase]={'first_four_calls':r[:4],'calls_total':len(r),'aggregate':{k:sum(int(row[k]) for row in r) for k in fields[2:]}}
        print(mode,label,results[f'{mode}-{label}'],flush=True)
(scratch/'allocation-profile-results.json').write_text(json.dumps(results,indent=2)+'\n')
