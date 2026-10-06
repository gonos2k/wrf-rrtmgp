import hashlib,json,os,statistics,subprocess,time
from pathlib import Path
root=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP');scratch=root/'build/udm-workspace-oracle';work=root/'build/udm-workspace-reuse-work'
env={**os.environ,'LD_LIBRARY_PATH':str(root/'build/deps/netcdf/lib'),'OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE'}
env.pop('WRF_RRTMGP_CAPTURE_DIR',None)
rows=[]
for mode in [0,1]:
    for repeat in range(5):
        for label in (['baseline','candidate'] if repeat%2==0 else ['candidate','baseline']):
            binary=scratch/'release'/f'bench_workspace_{label}'
            out=scratch/f'benchmark-mode{mode}-{label}-{repeat}.csv'
            cmd=[str(binary),str(work/'WRF/run'),str(mode),str(work/'validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc'),'1500']
            p=subprocess.Popen(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            _,status,usage=os.wait4(p.pid,0)
            p.returncode=os.waitstatus_to_exitcode(status)
            stdout,stderr=p.communicate()
            out.write_text(stdout);out.with_suffix('.time').write_text(stderr+str(usage))
            if p.returncode: raise RuntimeError(stderr)
            count,lw,sw,checksum=stdout.strip().split(',')
            rss=usage.ru_maxrss
            rows.append({'frozen_mode':mode,'repeat':repeat,'label':label,'ncol':1,'nlay':60,'calls':int(count),'lw_seconds':float(lw),'sw_seconds':float(sw),'checksum':checksum,'peak_rss_kb':rss})
            print(mode,repeat,label,round(float(lw),4),round(float(sw),4),rss,flush=True)
summary=[]
for mode in [0,1]:
    d={'frozen_mode':mode,'measurements':[]}
    for label in ['baseline','candidate']:
        r=[x for x in rows if x['frozen_mode']==mode and x['label']==label]
        d['measurements'].append({'label':label,'lw_median_seconds':statistics.median(x['lw_seconds'] for x in r),'sw_median_seconds':statistics.median(x['sw_seconds'] for x in r),'lw_range_seconds':[min(x['lw_seconds'] for x in r),max(x['lw_seconds'] for x in r)],'sw_range_seconds':[min(x['sw_seconds'] for x in r),max(x['sw_seconds'] for x in r)],'peak_rss_kb_range':[min(x['peak_rss_kb'] for x in r),max(x['peak_rss_kb'] for x in r)]})
    summary.append(d)
j={'scope':'GNU Release standalone CPU adapter only; ncol1,nlay60; native UDM rain and LW CFC inputs always supplied; SW pre-delta always requested; 1500 changing-state daylight calls per phase per measurement including first cold call; no WRF throughput claim','source_sha256':{str(p.relative_to(work)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [work/'WRF/phys/module_ra_rrtmgp.F',work/'WRF/test/rrtmgp/test_workspace.F90']},'bench_sha256':hashlib.sha256((scratch/'bench_workspace.F90').read_bytes()).hexdigest(),'rows':rows,'summary':summary}
(scratch/'benchmark-results.json').write_text(json.dumps(j,indent=2)+'\n')
print(summary,flush=True)
