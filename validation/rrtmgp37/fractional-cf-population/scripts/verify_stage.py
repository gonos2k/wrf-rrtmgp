#!/usr/bin/env python3
import pathlib,json,hashlib,os,sys
sys.dont_write_bytecode=True
root=pathlib.Path(__file__).resolve().parent
plan=json.loads((root/'stage-plan.json').read_text())
def pin(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return {'path':str(p.resolve()),'sha256':h.hexdigest(),'size_bytes':p.stat().st_size,'link':os.readlink(p) if p.is_symlink() else None}
errors=[]
for arm,c in plan['cases'].items():
 d=pathlib.Path(c['directory']);actual={p.name for p in d.iterdir() if p.name not in ('capture','number_capture')}
 if actual!=set(c['files']):errors.append(arm+': file roster differs')
 for n,q in c['files'].items():
  if not (d/n).is_file() or pin(d/n)!=q:errors.append(arm+'/'+n+': pin mismatch')
 if pin(d/'wrfinput_d01')['sha256']!=plan['positive_input']['sha256']:errors.append(arm+': input differs')
 for k in ('capture_directory','number_capture_directory'):
  q=pathlib.Path(c[k])
  if not q.is_dir() or any(q.iterdir()):errors.append(arm+': capture not fresh')
 if list(d.glob('wrfout*')) or list(d.glob('wrfrst*')) or list(d.glob('rsl.*')) or (d/'namelist.output').exists():errors.append(arm+': output exists')
print(json.dumps({'status':'FAIL' if errors else 'PASS_STAGED_UNRUN','errors':errors,'files_per_arm':104,'models':0}))
sys.exit(1 if errors else 0)
