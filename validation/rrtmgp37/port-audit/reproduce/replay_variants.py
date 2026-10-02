from pathlib import Path
import sys,os,json,subprocess,numpy as np
root=Path.cwd();sys.path.insert(0,str(root/'WRF/test/rrtmgp'));sys.path.insert(0,str(root/'build/port-audit-inputs'))
from test_column_replay import read_input,read_raw
from compare_column_replay import read_result
# No production modification: each variant calls only the independent standalone executable.
def read_audit(p):
 lines=p.read_text().splitlines();h=lines[1].split();rec={};i=2
 while i<len(lines):
  t=lines[i].split();i+=1;shape=tuple(map(int,t[2:]));n=int(np.prod(shape));rec[t[0]]=np.array([float(x) for x in lines[i:i+n]]).reshape(shape,order='F');i+=n
 return h,rec
out=root/'build/port-audit-inputs/variants';out.mkdir(exist_ok=True)
env=os.environ.copy();deps=root.parent/'deps';env['LD_LIBRARY_PATH']=str(deps/'netcdf/lib')+':'+str(deps/'root/usr/lib/x86_64-linux-gnu')+':'+env.get('LD_LIBRARY_PATH','');env['OMP_NUM_THREADS']='1'
report={}
for case in sorted((root/'build/port-audit-inputs/cases-v2').iterdir()):
 if not case.is_dir():continue
 report[case.name]={}
 for phase in ['lw','sw']:
  path=case/'ra37/capture'/f'{phase}.input';ph,nc,nl,overlap,seed,iceflag,base=read_input(path)
  h4,old=read_audit(case/'ra4/capture'/f'{ph}.audit');_,_,_,raw=read_raw(case/'ra37/capture'/f'{phase}.raw')
  variants={}
  for mode in ['actual','background_fallback','allcloud_actual','allcloud_background_fallback','clear']:
   a={k:v.copy() for k,v in base.items()}
   if 'background_fallback' in mode:
    for s,bg in [('CLOUD',2.49e-6),('ICE',4.99e-6),('SNOW',9.99e-6)]:
     key={'CLOUD':'REL','ICE':'REI','SNOW':'RES'}[s]
     source=raw.get('SOURCE_RE_'+s);has=raw.get({'CLOUD':'HAS_REQC','ICE':'HAS_REQI','SNOW':'HAS_REQS'}[s],np.array([0])).item()
     if source is not None and has:
      m=source.astype(np.float32)==np.float32(bg)
      target=old[key][0,:len(source)].copy()
      if key=='REI' and int(h4[-2])==3:target/=1.0315
      a[key][0,:len(source)][m]=target[m]
   if mode.startswith('allcloud'):a['CF'][a['CF']>0]=1
   if mode=='clear':
    for key in ['CF','LWP','IWP','SWP']:a[key][:]=0
   f=out/f'{case.name}.{phase}.{mode}.input';result=f.with_suffix('.result')
   lines=['RRTMGP_REPLAY_V2',f'{ph} {nc} {nl} {overlap} {seed} {iceflag}']
   for k,v in a.items():lines += [f'{k} {v.shape[0]} {v.shape[1]}']+[f'{x:.16e}' for x in v.flatten(order='F')]
   f.write_text('\n'.join(lines)+'\n')
   subprocess.run([str(root/'build/cloud-column-check/reference_column'),str(root/'WRF/run'),str(f),str(result)],env=env,check=True,stdout=subprocess.DEVNULL)
   sec=read_result(result)['sections'];variants[mode]={'surface_down':float(sec['DN'][0,0,0]),'toa_up':float(sec['UP'][0,-1,0]),'max_abs_heating_k_day':float(np.max(abs(sec['HR'])))}
  report[case.name][ph]=variants
  print(case.name,ph,'radiusdelta',variants['background_fallback']['surface_down']-variants['actual']['surface_down'],'fullcloudradiusdelta',variants['allcloud_background_fallback']['surface_down']-variants['allcloud_actual']['surface_down'])
(out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
