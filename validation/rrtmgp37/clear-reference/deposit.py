#!/usr/bin/env python3
"""Deposit bounded raw diagnostic evidence, not generated model verification claims."""
from pathlib import Path
import json,gzip,hashlib,shutil,platform,tarfile,io
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;S=P/'saved';S.mkdir(exist_ok=False)
files={}
def put(key,p):
 b=p.read_bytes();dst=S/(key+'.gz');dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(gzip.compress(b,mtime=0));files[key]={'sha256':hashlib.sha256(b).hexdigest(),'size_bytes':len(b),'gzip':str(dst.relative_to(P))}
O=B/'udm37-clear-reference-run-v4';V=B/'udm37-clear-reference-vendor-v3';F=B/'udm37-clear-reference-real-v3'
for name in ['analysis.json','angular-arrays.json','angular-history.json','band-arrays.json','receipt.json'] :put(name,O/name)
for ph in ['lw','sw']:
 for n in ['flux.dat','input.dat','native4.txt']:put(ph+'/'+n,O/ph/n)
 if ph=='lw':put(ph+'/source.dat',O/ph/'source.dat')
 else:put(ph+'/optics.dat',O/ph/'optics.dat')
 put(ph+'/vendor-flux.dat',V/ph/'flux.dat')
 for n in ['input','result']:put(ph+'/adapter.'+n,B/f'udm37-same-state-run-v1/{ph}_clear/capture/{ph}.{n}')
put('legacy-export4.txt',next((O/'legacy_source/export4').glob('*.txt')))
put('legacy-native4.txt',O/'legacy_source/native4.txt');put('vendor-receipt.json',V/'receipt.json')
for n in ['receipt.json','number1_input/producer.json','legacy_real/namelist.input','legacy_real/combined.log','number1_boundary/namelist.input','number1_boundary/combined.log']:put('real/'+n,F/n)
# Keep every durable development command record, including failed compiles and bad staging.
campaign=[]
for glob in ['udm37-clear-reference-run-v*','udm37-clear-reference-vendor-v*','udm37-clear-reference-real-v*']:
 for d in sorted(B.glob(glob)):
  for p in sorted(d.glob('command-*.*')):put('campaign/'+d.name+'/'+p.name,p)
  campaign.extend(json.loads(p.read_text()) for p in sorted(d.glob('command-*.json')))
put('real/source-namelist.input',B/'udm37-matthew-real-v1/case/namelist.input')
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size_bytes':p.stat().st_size}
paths=['WRF/phys/module_ra_rrtmgp.F','WRF/phys/module_ra_rrtmg_lw.F','WRF/phys/module_ra_rrtmg_sw.F','WRF/phys/module_mp_udm.F','WRF/share/input_wrf.F','WRF/Registry/Registry.EM_COMMON','WRF/run/rrtmgp-gas-lw-g128.nc','WRF/run/rrtmgp-gas-sw-g112.nc','validation/rrtmgp37/bon-night-common-angle/analysis/angular_reference.py','validation/rrtmgp37/same-state-engines/analyze_saved.py','validation/rrtmgp37/same-state-engines/compare.f90']
# Original real files stay in build storage; publish full variable inventories and content pins.
external={str(p):pin(p) for p in [B/'udm37-matthew-real-v1/case/wrfinput_d01',B/'udm37-matthew-real-v1/case/wrfbdy_d01']}
identity={'base_commit':'69fa17d43d57997ef06631f27e9e847828630b4c','runtime_sources':{p:pin(R/p) for p in paths},'external_real_inputs':external,'saved':files,'qualified_radiation_processes':5,'qualified_radiation_engine_calls':6,'qualified_WRF_processes':2,'qualified_WRF_success_seconds':20,'development_command_records':len(campaign),'development_nonzero_returncodes':sum(x['actual_returncode']!=0 for x in campaign),'additional_debug_invocations':'Two gdb attempts: one loader failure, one reproduced staging segfault in modify_io_masks. No forecast success claimed.','python':platform.python_version(),'production_accepted':False}
archive=io.BytesIO()
with tarfile.open(fileobj=archive,mode='w') as tar:
 for key,v in list(files.items()):
  if key.startswith('campaign/'):
   raw=gzip.decompress((P/v['gzip']).read_bytes());info=tarfile.TarInfo(key.removeprefix('campaign/'));info.size=len(raw);info.mtime=0;tar.addfile(info,io.BytesIO(raw));del files[key]
raw=archive.getvalue();(S/'campaign.tar.gz').write_bytes(gzip.compress(raw,mtime=0));files['campaign.tar']={'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw),'gzip':'saved/campaign.tar.gz'}
shutil.rmtree(S/'campaign')
(P/'identity.json').write_text(json.dumps(identity,indent=2)+'\n')
print('DEPOSITED',len(files),'files')
