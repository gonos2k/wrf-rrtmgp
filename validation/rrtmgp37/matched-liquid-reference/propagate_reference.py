#!/usr/bin/env python3
"""Propagate only qualified matched coefficient entries through unchanged RTE."""
from pathlib import Path
import sys,os,json,importlib.util,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent
sys.path.insert(0,str(R/'WRF/test/rrtmgp'))
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=load(R/'WRF/test/rrtmgp/test_netcdf_zz.py','runner');parser=load(R/'validation/rrtmgp37/radiation-occurrence-runtime/verify_saved.py','parser')
OUT=B/'udm37-matched-reference-rte-v1';OUT.mkdir(exist_ok=False);MIE=B/'udm37-matched-reference-v1/result.json';ref=json.loads(MIE.read_text());assert ref['completed']
exe=B/'udm37-endpoint-column-v2/column';runner=h.Runner(OUT,120,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},18)
receipt={'executable':h.pin(exe),'reference':h.pin(MIE),'new_WRF_runs':0,'production_accepted':False,'runs':[]}
for case in ['night_peak_lw','day_peak_lw','day_peak_sw']:
 ph=case.rsplit('_',1)[1];original=B/'udm37-endpoint-rte-v2'
 for mode in ['B','C']:
  old=original/(case+'_'+mode);_,inp=parser.trace((old/'capture'/(ph+'.input')).read_bytes(),'input');_,base=parser.trace((old/'capture'/(ph+'.result')).read_bytes(),'result')
  lines=(old/'optics.dat').read_text().splitlines();_,nl,nb=lines[0].split();nl=int(nl);nb=int(nb);selected=list(map(int,lines[1].split()));coeff=[list(map(float,l.split())) for l in lines[2:] if l.strip()]
  for grid in ['fine','radius_half','spectral_half']:
   d=OUT/(case+'_'+mode+'_'+grid);d.mkdir();(d/'capture').mkdir();shutil.copyfile(old/'input.dat',d/'input.dat');copy=[v[:] for v in coeff];changes=[]
   for band in range(1,nb+1):
    for k in range(nl):
     if not selected[k]:continue
     radius=21.5 if mode=='B' else inp['REL']['values'][k]
     row=next((r for r in ref['records'] if r['phase']==ph and r['band']==band and r['reff_um']==radius and r['qualified_numerical_axes']),None)
     if row is None:continue
     v=row['levels'][-1][grid];copy[(band-1)*nl+k]=[v[n] for n in ['ext','sca','abs','sca_g']];changes.append({'layer':k+1,'band':band,'radius_um':radius})
   text=lines[0]+'\n'+lines[1]+'\n'+'\n'.join(' '.join(format(v,'.17e') for v in row) for row in copy)+'\n';(d/'optics.dat').write_text(text)
   runner.environment.update(WRF_RRTMGP_CAPTURE_DIR=str(d/'capture'),WRF_RRTMGP_CAPTURE_CALL='1')
   log=runner.run([exe,R/'WRF/run',d/'input.dat',d/'optics.dat'],d,d.name).read_text();assert 'LUT_PATH_ATTRIBUTION_COMPLETE' in log and 'FATAL' not in log.upper()
   _,got=parser.trace((d/'capture'/(ph+'.result')).read_bytes(),'result')
   for n in ['UPC','DNC','HRC','GAS_TAU','GAS_SSA','GAS_G','PRECIP_TAU','PRECIP_SSA','PRECIP_G','MASK','NATIVE_CAPACITY_J_M2_K','RL_USED']:
    if n in base:assert got[n]==base[n],(case,mode,n)
   receipt['runs'].append({'case':case,'mode':mode,'grid':grid,'changed_entries':changes,'input':h.pin(d/'input.dat'),'optics':h.pin(d/'optics.dat'),'result':h.pin(d/'capture'/(ph+'.result'))});receipt['commands']=runner.commands;h.write_json(OUT/'receipt.json',receipt)
   print(d.name,'entries',len(changes),flush=True)
