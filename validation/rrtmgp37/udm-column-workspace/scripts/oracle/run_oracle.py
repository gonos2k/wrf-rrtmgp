import hashlib,json,os,subprocess
from pathlib import Path
root=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
scratch=root/'build/udm-workspace-oracle'
worktree=root/'build/udm-workspace-reuse-work'
table=worktree/'validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc'
data=worktree/'WRF/run'
results=[]
for variant in ['debug','release']:
    build=scratch/variant
    if not (build/'baseline_workspace').exists(): continue
    for mode in ['0','1']:
        dirs=[];outputs=[]
        for label,binary in [('baseline',build/'baseline_workspace'),('candidate',build/'candidate/test_rrtmgp_workspace')]:
            outdir=scratch/f'{variant}-mode{mode}-{label}'
            outdir.mkdir(exist_ok=True)
            trace=outdir/'trace';trace.mkdir(exist_ok=True)
            snapshot=outdir/'outputs.bin'
            env={**os.environ,'LD_LIBRARY_PATH':str(root/'build/deps/netcdf/lib'),'OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE','WRF_RRTMGP_CAPTURE_DIR':str(trace),'WRF_RRTMGP_CAPTURE_ALL':'1'}
            p=subprocess.run([str(binary),str(data),mode,str(table),str(snapshot)],capture_output=True,text=True,env=env)
            (outdir/'run.log').write_text(p.stdout+p.stderr)
            if p.returncode: raise RuntimeError(f'{variant} {mode} {label}: {p.stdout} {p.stderr}')
            outputs.append(snapshot.read_bytes());dirs.append(trace)
        a={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dirs[0].glob('*')}
        b={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dirs[1].glob('*')}
        result={'configuration':variant,'frozen_mode':int(mode),'all_6_lw_and_17_sw_output_bytes_equal':outputs[0]==outputs[1],'output_bytes':len(outputs[0]),'output_sha256':hashlib.sha256(outputs[1]).hexdigest(),'adapter_trace_files':len(a),'all_adapter_trace_bytes_equal':a==b,'differing_trace_files':[name for name in sorted(a.keys()|b.keys()) if a.get(name)!=b.get(name)]}
        results.append(result)
        print(result,flush=True)
(scratch/'oracle-results.json').write_text(json.dumps(results,indent=2)+'\n')
if not all(r['all_6_lw_and_17_sw_output_bytes_equal'] and r['all_adapter_trace_bytes_equal'] for r in results): raise RuntimeError('original base numerical oracle divergence')
