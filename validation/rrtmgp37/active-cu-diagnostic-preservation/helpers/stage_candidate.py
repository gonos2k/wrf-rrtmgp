#!/usr/bin/env python3
"""Stage a clean PR60 candidate case from the validated long-b1 asset set; no model launch."""
from __future__ import annotations
import hashlib,json,os,shutil
from datetime import datetime,timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]
BASE=ROOT/'build/udm37-restart-cloud-diagnostics-runtime-v2/runs-v2/cases/long-b1'
RUN=ROOT/'build/udm37-restart-cloud-diagnostics-runtime-v2/runs-v2/execution.json'
BUILD=HERE/'build-result-v1.json'; SOURCE=HERE/'source-v3'; DEST=HERE/'runs-v1/case-pr60-cu-active'
EXPECTED_INPUTS={'wrfinput_d01':'0cc7e188ef585a93ab52550816c6af236932254820fb1bc6937f464bfed38637',
 'wrfbdy_d01':'ba4241de4f4661a77733cf157f0c87f90668f107df86f8c92d092b56d7bd7bd4'}
EXPECTED_CAM='9a427fd106f8e36b30e0b29266bff1398b025b82af5b878e5a7a8e9dfe268ca7'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def pin(p):
 p=Path(p); return {'path':str(p.resolve()),'sha256':sha(p),'size_bytes':p.stat().st_size}
def target_record(link):
 p=Path(os.readlink(link)); resolved=link.resolve(strict=True)
 if resolved.is_file():
  return {'link_text':os.readlink(link),'resolved':str(resolved),'kind':'file','sha256':sha(resolved),'size_bytes':resolved.stat().st_size}
 if resolved.is_dir():
  rows=[]
  for f in sorted(x for x in resolved.rglob('*') if x.is_file() and not x.is_symlink()): rows.append({'path':str(f.relative_to(resolved)),'size_bytes':f.stat().st_size,'sha256':sha(f)})
  digest=hashlib.sha256((json.dumps(rows,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()
  return {'link_text':os.readlink(link),'resolved':str(resolved),'kind':'directory','sha256':digest,'files':len(rows)}
 raise ValueError(f'unsupported asset type: {link.name} -> {resolved}')
def main():
 if DEST.exists(): raise FileExistsError(f'refuse nonfresh stage {DEST}')
 build=json.loads(BUILD.read_text())
 if build.get('status')!='BUILD_PASS' or build.get('model_invocations')!=0: raise ValueError('fresh build is not PASS or model count not zero')
 exe=SOURCE/'WRF/main/wrf.exe'
 if pin(exe)['sha256']!=build['executables']['wrf.exe']['sha256']: raise ValueError('candidate executable differs from build receipt')
 campaign=json.loads(RUN.read_text()); arm=campaign.get('arms',{}).get('long-b1')
 if campaign.get('status')!='PASS_SCOPED_RESTART_DIAGNOSTIC_ARRAYS_AND_INVOCATION_METADATA' or not arm or arm.get('status')!='CASE_VALIDATED' or arm.get('returncode')!=0 or arm.get('model_invoked') is not True: raise ValueError('baseline arm no longer independently validated')
 if pin(BASE/'namelist.input')['sha256']!=arm['entry']['immutable']['files']['namelist.input']['sha256'] if 'files' in arm['entry']['immutable'] else False: raise ValueError('baseline namelist receipt changed')
 links={p.name:target_record(p) for p in sorted(BASE.iterdir()) if p.is_symlink()}
 for name,digest in EXPECTED_INPUTS.items():
  if links.get(name,{}).get('sha256')!=digest: raise ValueError(f'input hash mismatch: {name}')
 if links.get('CAMtr_volume_mixing_ratio',{}).get('sha256')!=EXPECTED_CAM: raise ValueError('SSP245 CAM tracer link mismatch')
 if 'rrtmgp-gas-lw-g128.nc' not in links or 'rrtmgp-gas-sw-g112.nc' not in links or 'frozen-ice-psd-moments.nc' not in links: raise ValueError('required gas/frozen-optics asset missing')
 existing_outputs=[p.name for p in BASE.iterdir() if p.name.startswith(('rsl.','wrfout','wrfrst','wrfdiag','namelist.output'))]
 if not existing_outputs: raise ValueError('baseline provenance unexpectedly has no run outputs')
 DEST.mkdir(parents=True)
 for name,item in links.items():
  if name in {'wrf.exe','ideal.exe','real.exe','ndown.exe','tc.exe'}: continue
  os.symlink(item['link_text'],DEST/name)
 shutil.copy2(BASE/'namelist.input',DEST/'namelist.input')
 os.symlink(str(exe),DEST/'wrf.exe')
 staged={p.name:target_record(p) for p in sorted(DEST.iterdir()) if p.is_symlink()}
 for name,item in links.items():
  if name not in {'wrf.exe','ideal.exe','real.exe','ndown.exe','tc.exe'} and staged.get(name)!=item: raise ValueError(f'staged asset mismatch {name}')
 if staged['wrf.exe']['sha256']!=build['executables']['wrf.exe']['sha256']: raise ValueError('staged executable mismatch')
 nml=pin(DEST/'namelist.input')
 if nml['sha256']!=pin(BASE/'namelist.input')['sha256']: raise ValueError('staged namelist changed')
 if any(p.name.startswith(('rsl.','wrfout','wrfrst','wrfdiag','namelist.output')) for p in DEST.iterdir()): raise ValueError('staged output collision')
 receipt={'schema':'udm37-pr60-active-cu-stage-v1','status':'STAGED_NOT_RUN','created_utc':datetime.now(timezone.utc).isoformat(),
  'model_invocations':0,'build_result':pin(BUILD),'candidate_executable':pin(exe),'baseline_run_receipt':pin(RUN),
  'baseline_campaign_status':campaign['status'],'baseline_arm_status':arm['status'],'baseline_returncode':arm['returncode'],'baseline_elapsed_seconds':arm['elapsed_seconds'],
  'baseline_case':str(BASE),'candidate_case':str(DEST),'baseline_namelist':pin(BASE/'namelist.input'),'staged_namelist':nml,
  'baseline_links':links,'staged_links':staged,'ignored_baseline_regular_outputs':existing_outputs,
  'expected_inputs':EXPECTED_INPUTS,'expected_camtr_ssp245':EXPECTED_CAM,
  'run_configuration':{'start':'2000-01-24_12:00:00','end':'2000-01-25_12:00:00','hours':24,'history_interval_minutes':60,'restart_interval_minutes':720,'physics_from_validated_long_b1_namelist':True},
  'model_launched':False}
 (HERE/'stage-receipt-v1.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'status':receipt['status'],'candidate_case':str(DEST),'staged_links':len(staged),'model_invocations':0,'baseline_elapsed_seconds':arm['elapsed_seconds']},indent=2))
if __name__=='__main__':main()
