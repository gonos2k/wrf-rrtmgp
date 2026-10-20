#!/usr/bin/env python3
"""Retain actual paired processes and replay analysis; no scientific launches."""
from pathlib import Path
import gzip,json,hashlib,importlib.util
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;RUN=B/'udm37-same-state-run-v1';BUILD=B/'udm37-same-state-build-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def save(n,d):
 p=P/'saved'/(n+'.gz');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(gzip.compress(d,mtime=0))
if __name__=='__main__':
 receipt=json.loads((RUN/'receipt.json').read_text())
 for p in RUN.glob('command-*'):save('runtime/'+p.name,p.read_bytes())
 for p in BUILD.glob('command-*'):save('build/'+p.name,p.read_bytes())
 for n in ['receipt.json','plan.json']:save('runtime/'+n,(RUN/n).read_bytes())
 save('build/receipt.json',(BUILD/'receipt.json').read_bytes())
 for n in ['plan.json','compare.f90','build.py','run.py']:save('executed/'+n,(P/n).read_bytes())
 for label in ['build','run']:save('logs/'+label+'.log',(B/('udm37-same-state-'+label+'-v1.log')).read_bytes())
 if (B/'udm37-same-state-acceptance.log').exists():save('logs/local-acceptance.log',(B/'udm37-same-state-acceptance.log').read_bytes())
 for row in receipt['runs']:
  n=row['name'];ph=row['phase'];d=RUN/n
  for f in ['input.dat','before.bin','after4.bin','after37.bin','native4.txt']:save(n+'/'+f,(d/f).read_bytes())
  for f in [ph+'.input',ph+'.result']:save(n+'/'+f,(d/'capture'/f).read_bytes())
  save(n+'/export4.txt',next((d/'export4').glob('*.txt')).read_bytes())
 old=json.loads((R/'validation/rrtmgp37/liquid-endpoint-optics/identity.json').read_text())
 source={n:sha(R/n) for n in old['source_files']};source['WRF/phys/module_ra_rrtmgp_audit.F']=sha(R/'WRF/phys/module_ra_rrtmgp_audit.F')
 assert all(source[n]==v for n,v in old['source_files'].items())
 coeff={n:sha(R/n) for n in old['coefficient_files']}
 for f in ['RRTMG_LW_DATA','RRTMG_SW_DATA']:coeff['WRF/run/'+f]=sha(R/'WRF/run'/f)
 ident={'baseline_main':'20690e7cd3d787f723b706301148116334efb2bd','baseline_tree':'f529e8745582bd3291ffb300901ee3edac78570f','runtime_source_files':source,'coefficients':coeff,'build':json.loads((BUILD/'receipt.json').read_text()),'runtime_sources_unchanged':True,'number1_guard_unchanged':True,'forecast_state_not_loaded_or_updated':True,'new_caller_compiles':1,'new_links':1,'actual_new_processes':6,'actual_engine_calls':12,'new_WRF_forecasts':0,'production_accepted':False}
 ident['caller_compiler']='GNU Fortran (Ubuntu 13.3.0-6ubuntu2~24.04) 13.3.0; version inspected after execution; flags and actual compile/link processes retained'
 ident['calculation_precision']={'engine4':'native REAL32','engine37_flux_and_heating_trace':'REAL64','common_Cstar_and_decomposition':'REAL64'}
 write(P/'identity.json',ident)
 s=importlib.util.spec_from_file_location('analysis',P/'analyze_saved.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
 read=lambda n:gzip.decompress((P/'saved'/(n+'.gz')).read_bytes());result=a.analyze(read,json.loads((P/'plan.json').read_text()));write(P/'result.json',result)
 sealed={str(p.relative_to(P)):sha(p) for p in (P/'saved').rglob('*') if p.is_file()}
 for n in ['plan.json','identity.json']:sealed[n]=sha(P/n)
 write(P/'manifest.json',{'files':sealed})
 print('SAME_STATE_RETAINED',result['max_dry_gas_column_relative_difference'])
