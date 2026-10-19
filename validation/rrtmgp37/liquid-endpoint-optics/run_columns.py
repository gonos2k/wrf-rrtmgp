#!/usr/bin/env python3
"""Use existing #182 column inputs; vary only selected raw liquid moments."""
from pathlib import Path
import os,sys,json,importlib.util,shutil
ROOT=Path(__file__).resolve().parents[3];B=ROOT.parent
sys.path.insert(0,str(ROOT/'WRF/test/rrtmgp'))
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=load(ROOT/'WRF/test/rrtmgp/test_netcdf_zz.py','runner');p=load(ROOT/'validation/rrtmgp37/radiation-occurrence-runtime/verify_saved.py','parser')
OUT=B/'udm37-endpoint-rte-v2';OUT.mkdir(exist_ok=False)
MIE=B/'udm37-endpoint-mie-v1/result.json';mie=json.loads(MIE.read_text())
assert 'all_coefficients_converged' in mie,'Mie campaign not finished'
exe=B/'udm37-endpoint-column-v2/column'
runner=h.Runner(OUT,120,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},15)
receipt={'executable':h.pin(exe),'mie':h.pin(MIE),'runs':[],'production_accepted':False}
for case,ph in [('night_peak','lw'),('day_peak','lw'),('day_peak','sw')]:
 name=case+'_'+ph;cap=B/'udm37-lut-exposure-captures-v1'/case/'capture'
 _,inp=p.trace((cap/(ph+'.input')).read_bytes(),'input');_,original=p.trace((cap/(ph+'.result')).read_bytes(),'result')
 nl=inp['REL']['shape'][1];nb=16 if ph=='lw' else 14
 selected=[int(r>21.5 and inp['LWP']['values'][k]>0) for k,r in enumerate(inp['REL']['values'])]
 for mode in ['A','B_coarse','B','C_coarse','C']:
  d=OUT/(name+'_'+mode);d.mkdir();(d/'capture').mkdir()
  shutil.copyfile(B/'udm37-lut-attribution-v1'/(name+'_baseline')/'input.dat',d/'input.dat')
  txt=f'{ph.upper()} {nl} {nb}\n'+' '.join(map(str,selected if mode!='A' else [0]*nl))+'\n'
  for band in range(1,nb+1):
   for k in range(nl):
    z=[0.]*4
    if selected[k] and mode!='A':
     r=21.5 if mode.startswith('B') else inp['REL']['values'][k]
     row=next(x for x in mie['records'] if x['phase']==ph and x['band']==band and x['reff_um']==r)
     v=row['grids'][-2 if mode.endswith('coarse') else -1]
     z=[v[n] for n in ['ext','sca','abs','sca_g']]
    txt+=' '.join(format(x,'.17e') for x in z)+'\n'
  (d/'optics.dat').write_text(txt)
  runner.environment.update(WRF_RRTMGP_CAPTURE_DIR=str(d/'capture'),WRF_RRTMGP_CAPTURE_CALL='1')
  log=runner.run([exe,ROOT/'WRF/run',d/'input.dat',d/'optics.dat'],d,d.name).read_text()
  assert 'LUT_PATH_ATTRIBUTION_COMPLETE' in log and 'FATAL' not in log.upper()
  _,got=p.trace((d/'capture'/(ph+'.result')).read_bytes(),'result')
  if mode=='A':
   for n,v in original.items():
    if not n.startswith('WRF_'):assert got[n]==v,(name,n)
  receipt['runs'].append({'case':name,'mode':mode,'selected_native_levels':[k+1 for k,v in enumerate(selected) if v], 'input':h.pin(d/'input.dat'),'optics':h.pin(d/'optics.dat'),'result':h.pin(d/'capture'/(ph+'.result'))})
  receipt['commands']=runner.commands;h.write_json(OUT/'receipt.json',receipt)
  print(name,mode,'COMPLETE',flush=True)
