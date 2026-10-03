#!/usr/bin/env python3
"""Copied-package baseline and semantic tamper checks. Only Python processes, no WRF/reference."""
import hashlib,json,shutil,subprocess,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;SOURCE=HERE/'package'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def update_manifest(pkg,name):
 m=json.loads((pkg/'manifest.json').read_text());f=pkg/name;m['artifacts'][name]['sha256']=sha(f);m['artifacts'][name]['bytes']=f.stat().st_size
 m['canonical_artifacts_sha256']=hashlib.sha256(json.dumps(m['artifacts'],sort_keys=True,separators=(',',':')).encode()).hexdigest();(pkg/'manifest.json').write_text(json.dumps(m,sort_keys=True,indent=2)+'\n')
results=[]
for case in ['baseline_detached_cwd','changed_CF0_corrected_snow','illegal_frozen_padding','malformed_frozen_mode']:
 with tempfile.TemporaryDirectory(prefix='canonical-evidence-verify-') as d:
  work=Path(d);pkg=work/'evidence';shutil.copytree(SOURCE,pkg)
  name='evidence/canonical/material_cf0_snow_daylight_proxy/profiles-lw.json'
  if case!='baseline_detached_cwd':
   p=pkg/name;x=json.loads(p.read_text())
   if case=='changed_CF0_corrected_snow':
    assert x['raw_CF'][7]==0 and x['corrected_native_q']['QS'][7]>0;x['corrected_native_q']['QS'][7]*=2
   elif case=='illegal_frozen_padding':x['adapter']['GWP'][-1]=1.
   elif case=='malformed_frozen_mode':x['frozen_mode']=0.
   p.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n');update_manifest(pkg,name)
  command=[sys.executable,'-I','-S',str(pkg/'verify_artifacts.py')]
  run=subprocess.run(command,cwd=work,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  expected=0 if case=='baseline_detached_cwd' else 1
  assert run.returncode==expected,(case,run.stdout)
  results.append(dict(case=case,command=['python3','-I','-S','temporary-copy/verify_artifacts.py'],returncode=run.returncode,output=run.stdout,semantic_check_beyond_manifest_hash=(case!='baseline_detached_cwd')))
p=HERE/'portable-verifier-tests.json';p.write_text(json.dumps(dict(status='DETACHED_PORTABLE_PASS_AND_THREE_SEMANTIC_TAMPERS_REJECTED',test_sha256=sha(Path(__file__)),original_manifest_sha256=sha(SOURCE/'manifest.json'),original_verifier_sha256=sha(SOURCE/'verify_artifacts.py'),results=results,model_calls=0,reference_calls=0),indent=2,sort_keys=True)+'\n')
print(sha(p))
