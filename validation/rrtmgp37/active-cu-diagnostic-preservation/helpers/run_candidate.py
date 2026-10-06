#!/usr/bin/env python3
"""Strict one-shot PR60 diagnostics candidate runner. Default performs preflight only."""
from __future__ import annotations
import argparse, hashlib, json, os, re, resource, shutil, signal, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from netCDF4 import Dataset, default_fillvals

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]
BASE=ROOT/'build/udm37-restart-cloud-diagnostics-runtime-v2/runs-v2/cases/long-b1'
BASE_RUN=ROOT/'build/udm37-restart-cloud-diagnostics-runtime-v2/runs-v2/execution.json'
BUILD=HERE/'build-result-v1.json'; BUILD_PREP=HERE/'source-preparation-v3.json'; MANIFEST=HERE/'source-manifest-v3.json'
STAGE=HERE/'stage-receipt-v1.json'; CASE=HERE/'runs-v1/case-pr60-cu-active'; PREFLIGHT=HERE/'candidate-preflight-v1.json'; OUT=HERE/'candidate-run-v1'
MPICH=ROOT/'build/deps/mpich-sock/bin/mpiexec'
OMP_FIELDS={'OMP_NUM_THREADS':'2','OMP_DYNAMIC':'FALSE','OMP_STACKSIZE':'512M','OMP_MAX_ACTIVE_LEVELS':'1','OMP_NESTED':'FALSE','OMP_PROC_BIND':'FALSE','OPENBLAS_NUM_THREADS':'1'}
EXPECTED_TIMES=[f'2000-01-{24+(12+i)//24:02d}_{(12+i)%24:02d}:00:00' for i in range(25)]
EXPECTED_CHECKPOINTS=['wrfrst_d01_2000-01-25_00:00:00','wrfrst_d01_2000-01-25_12:00:00']
TOKEN=re.compile(r'([A-Za-z][A-Za-z0-9_]*)=\s*([^\s]+)')
TILE_I=re.compile(r'\btile_i=\s*(\d+)\s*:\s*(\d+)'); TILE_J=re.compile(r'\btile_j=\s*(\d+)\s*:\s*(\d+)')
TAGS=('RRTMGP_UDM_PHASE_PATH','RRTMGP_UDM_CF0_OMITTED','RRTMGP_UDM_LUT_CLIP','RRTMGP_CU_POPULATION','RRTMGP_CU_LUT_CLIP')

def now(): return datetime.now(timezone.utc).isoformat()
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def pin(path):
 p=Path(path); return {'path':str(p.resolve()),'size_bytes':p.stat().st_size,'sha256':sha(p)}
def target_record(link):
 link=Path(link); resolved=link.resolve(strict=True)
 base={'link_text':os.readlink(link),'resolved':str(resolved)}
 if resolved.is_file(): return {**base,'kind':'file','sha256':sha(resolved),'size_bytes':resolved.stat().st_size}
 if resolved.is_dir():
  rows=[{'path':str(f.relative_to(resolved)),'size_bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(x for x in resolved.rglob('*') if x.is_file() and not x.is_symlink())]
  return {**base,'kind':'directory','sha256':hashlib.sha256((json.dumps(rows,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest(),'files':len(rows)}
 raise ValueError(f'unsupported symlink target {link}: {resolved}')
def atomic(path,obj):
 tmp=Path(str(path)+'.tmp')
 with tmp.open('w') as f: json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
 os.replace(tmp,path)
def attr_sig(value):
 a=np.asarray(value)
 if a.dtype.kind=='O': return {'dtype':str(a.dtype),'shape':list(a.shape),'repr':repr(value)}
 return {'dtype':str(a.dtype),'shape':list(a.shape),'bytes':a.tobytes().hex()}
def attrs_sig(obj): return {n:attr_sig(obj.getncattr(n)) for n in sorted(obj.ncattrs())}
def decode_times(ds):
 if 'Times' not in ds.variables: raise ValueError(f"missing Times in {ds.filepath()}")
 v=ds.variables['Times']; a=np.asarray(v[:])
 if a.dtype.kind=='S': return [b''.join(row).decode('ascii').rstrip('\x00 ') for row in a]
 if a.dtype.kind=='U': return [''.join(row).rstrip('\x00 ') for row in a]
 raise ValueError(f"unexpected Times dtype {a.dtype}")
def quality_dataset(path, require_finite=True):
 report={'path':str(path),'variables':0,'numeric_values':0,'masked':0,'nonfinite':0,'fill_values':0}
 with Dataset(path) as ds:
  ds.set_auto_maskandscale(False)
  for name,v in ds.variables.items():
   report['variables']+=1
   x=v[:]
   if np.ma.isMaskedArray(x): report['masked']+=int(np.ma.getmaskarray(x).sum()); x=np.asarray(x.data)
   else: x=np.asarray(x)
   if x.dtype.kind in 'fiu':
    report['numeric_values']+=x.size
    if x.dtype.kind=='f': report['nonfinite']+=int((~np.isfinite(x)).sum())
    fill=v.getncattr('_FillValue') if '_FillValue' in v.ncattrs() else None
    if fill is not None:
     try: report['fill_values']+=int((x==fill).sum())
     except Exception: pass
    fill_key=('f'+str(x.dtype.itemsize)) if x.dtype.kind=='f' else (('i' if x.dtype.kind=='i' else 'u')+str(x.dtype.itemsize) if x.dtype.kind in 'iu' else None)
    dflt=default_fillvals.get(fill_key) if fill_key else None
    if dflt is not None:
     try: report['fill_values']+=int((x==dflt).sum())
     except Exception: pass
  report['dimensions']={n:{'length':len(d),'unlimited':d.isunlimited()} for n,d in ds.dimensions.items()}
  report['global_attrs']=attrs_sig(ds)
 if require_finite and any(report[k] for k in ('masked','nonfinite','fill_values')): raise ValueError(f"invalid data quality in {path}: {report}")
 return report
def exact_dataset_compare(left,right):
 diff=[]
 with Dataset(left) as a,Dataset(right) as b:
  a.set_auto_maskandscale(False); b.set_auto_maskandscale(False)
  da={n:(len(d),d.isunlimited()) for n,d in a.dimensions.items()}; db={n:(len(d),d.isunlimited()) for n,d in b.dimensions.items()}
  if da!=db: diff.append('dimensions')
  if attrs_sig(a)!=attrs_sig(b): diff.append('global_attrs')
  if set(a.variables)!=set(b.variables): diff.append('variable_names')
  for n in sorted(set(a.variables)&set(b.variables)):
   x,y=a[n],b[n]
   if (x.dtype,x.dimensions,x.shape)!=(y.dtype,y.dimensions,y.shape): diff.append(n+':layout'); continue
   if attrs_sig(x)!=attrs_sig(y): diff.append(n+':attrs')
   xv=np.asarray(x[:]); yv=np.asarray(y[:])
   if xv.tobytes()!=yv.tobytes(): diff.append(n+':raw_bytes')
 return diff
def histories(case): return sorted(case.glob('wrfout_d01_*'))
def source_integrity():
 manifest=json.loads(MANIFEST.read_text()); source=Path(build_source_path())
 entries=manifest['entries']
 for e in entries:
  p=source/e['path']
  if e['type']=='symlink':
   if not p.is_symlink() or os.readlink(p)!=e['target']: raise ValueError(f"source link changed: {e['path']}")
  elif not p.is_file() or p.stat().st_size!=e['size_bytes'] or sha(p)!=e['sha256']: raise ValueError(f"source changed: {e['path']}")
 return {'manifest_sha256':manifest['manifest_sha256'],'entry_count':len(entries),'configure':pin(source/'WRF/configure.wrf')}
def build_source_path(): return json.loads(BUILD.read_text())['source_before'].get('path',str(HERE/'source-v3'))
def legacy_native_diagnostics(case):
 out=[]; files=sorted(case.glob('rsl.error.[0-9][0-9][0-9][0-9]'))
 if len(files)!=4: raise ValueError(f'expected four legacy rank logs in {case}, got {len(files)}')
 for p in files:
  rank=int(p.name[-4:]); text=p.read_text(errors='strict')
  if 'SUCCESS COMPLETE WRF' not in text: raise ValueError(f'missing baseline rank success marker {p.name}')
  for line in text.splitlines():
   if not any(t in line for t in ('RRTMGP_UDM_CF0_OMITTED','RRTMGP_UDM_LUT_CLIP')): continue
   rec=parse_diag_line(line,rank,p.name)
   if rec is None or rec['tag'] not in ('RRTMGP_UDM_CF0_OMITTED','RRTMGP_UDM_LUT_CLIP'): continue
   # Compare old row's numeric field spellings exactly; these records were already part of baseline logs.
   out.append({'rank':rank,'band':rec['band'],'tag':rec['tag'],'phase':rec['phase'],'tile_i':rec['tile_i'],'tile_j':rec['tile_j'],
    'numeric':{k:v for k,v in rec['values'].items() if k not in {'tile_i','tile_j','phase'}}})
 return out
def legacy_summary_diagnostics(case):
 """Read old-format native/CU summaries; old CU-LUT rows lack tile/time and are multisets per rank/phase."""
 rows=[]; files=sorted(case.glob('rsl.error.[0-9][0-9][0-9][0-9]'))
 for p in files:
  rank=int(p.name[-4:]); text=p.read_text(errors='strict')
  for line in text.splitlines():
   tag=next((t for t in ('RRTMGP_UDM_CF0_OMITTED','RRTMGP_UDM_LUT_CLIP','RRTMGP_CU_POPULATION','RRTMGP_CU_LUT_CLIP') if t in line),None)
   if not tag: continue
   bm=re.search(r'\b(LW|SW)\s+'+re.escape(tag),line); pm=re.search(r'\bphase=\s*(LIQ|ICE|RAIN|SNOW)\b',line)
   if not bm or not pm: raise ValueError(f'malformed legacy diagnostic line in {p.name}: {line}')
   vals={k:v for k,v in TOKEN.findall(line) if k not in {'tile_i','tile_j','phase'}}
   for k,v in vals.items():
    try: n=float(v.replace('D','E').replace('d','e'))
    except ValueError as e: raise ValueError(f'bad legacy diagnostic numeric {k}={v} in {p.name}') from e
    if not np.isfinite(n): raise ValueError(f'nonfinite legacy diagnostic {k}={v} in {p.name}')
   ti=TILE_I.search(line); tj=TILE_J.search(line)
   if tag!='RRTMGP_CU_LUT_CLIP' and (not ti or not tj): raise ValueError(f'legacy row missing required tile bounds: {p.name}: {line}')
   rows.append({'rank':rank,'band':bm.group(1),'tag':tag,'phase':pm.group(1),
    'tile_i':tuple(map(int,ti.groups())) if ti else None,'tile_j':tuple(map(int,tj.groups())) if tj else None,'values':vals})
 return rows
def compare_legacy_diagnostics(candidate_records,baseline_rows):
 fields={
  'RRTMGP_UDM_CF0_OMITTED':('layers','sum_layer_grid_wp_g_m2','max_layer_grid_wp_g_m2'),
  'RRTMGP_UDM_LUT_CLIP':('low_layers','high_layers','low_clipped_layer_wp_sum_g_m2','high_clipped_layer_wp_sum_g_m2','eligible_layer_wp_sum_g_m2','clip_grid_wp_fraction','max_low_g_m2','max_high_g_m2'),
  'RRTMGP_CU_POPULATION':('accepted_grid_sum_g_m2','rejected_grid_sum_g_m2','rejected_grid_max_g_m2','omitted_cf0_count','omitted_cf0_sum_g_m2','omitted_cf0_max_g_m2','negative_source_count','negative_active_count'),
  'RRTMGP_CU_LUT_CLIP':('low_layers','low_grid_path_g_m2','high_layers','high_grid_path_g_m2','eligible_grid_path_g_m2','clipped_grid_path_fraction','max_low_g_m2','max_high_g_m2')}
 def grouped(rows):
  out={}
  for r in rows:
   tag=r['tag']; fs=fields[tag]
   absent=set(fs)-set(r['values'])
   if absent: raise ValueError(f'legacy summary incomplete {tag}: {sorted(absent)}')
   if tag=='RRTMGP_CU_LUT_CLIP': key=(r['rank'],r['band'],tag,r['phase'])
   else: key=(r['rank'],r['band'],tag,r['phase'],r['tile_i'],r['tile_j'])
   value=tuple(r['values'][f] for f in fs)
   out.setdefault(key,[]).append(value)
  # The historical CU LUT row has no tile/context; compare its multiset by rank/band/phase.
  for key,vals in out.items():
   if key[2]=='RRTMGP_CU_LUT_CLIP': out[key]=sorted(vals)
  return out
 old=grouped(baseline_rows)
 # Candidate diagnostics include richer per-call context. Compare historical columns only.
 cur=[]
 for r in candidate_records:
  tag=r['tag']
  if tag not in fields: continue
  fs=fields[tag]; values=r['values']
  if tag=='RRTMGP_CU_LUT_CLIP': key=(r['rank'],r['band'],tag,r['phase'])
  else: key=(r['rank'],r['band'],tag,r['phase'],r['tile_i'],r['tile_j'])
  cur.append({'rank':r['rank'],'band':r['band'],'tag':tag,'phase':r['phase'],'tile_i':r['tile_i'],'tile_j':r['tile_j'],'values':{f:values[f] for f in fs}})
 new=grouped(cur)
 return {'status':'UNCHANGED' if old==new else 'CHANGED','baseline_rows':sum(map(len,old.values())),'candidate_rows':sum(map(len,new.values())),
  'baseline_groups':len(old),'candidate_groups':len(new),'exact_numeric_fields':old==new}
def validate_times(case,expected):
 files=histories(case); seen=[]; rows=[]
 for f in files:
  with Dataset(f) as ds:
   ds.set_auto_maskandscale(False); ts=decode_times(ds); seen.extend(ts)
   rows.append({'file':f.name,'times':ts,'sha256':sha(f),'quality':quality_dataset(f)})
 if seen!=expected: raise ValueError(f"history Times mismatch: count={len(seen)}, first={seen[:2]}, last={seen[-2:]}")
 return rows
def validate_checkpoints(case):
 found=sorted(p.name for p in case.glob('wrfrst_d01_*'))
 if found!=EXPECTED_CHECKPOINTS: raise ValueError(f'checkpoint inventory mismatch: {found}')
 rows=[]
 for n in found:
  p=case/n
  with Dataset(p) as ds:
   ds.set_auto_maskandscale(False); ts=decode_times(ds)
  expected=p.name[len('wrfrst_d01_'):]
  if ts!=[expected]: raise ValueError(f'checkpoint time/file mismatch {p.name}: {ts}')
  rows.append({'file':n,'times':ts,'quality':quality_dataset(p),'sha256':sha(p)})
 return rows
def validate_case_pair(reference,candidate):
 refh=histories(reference); candh=histories(candidate)
 if [p.name for p in refh]!=[p.name for p in candh]: raise ValueError('history file names differ')
 ref_times=[]
 for f in refh:
  with Dataset(f) as ds: ds.set_auto_maskandscale(False); ref_times.extend(decode_times(ds))
 if ref_times!=EXPECTED_TIMES: raise ValueError(f'baseline history does not have exact 25 expected hourly records: {len(ref_times)}')
 history=[]; mismatches=[]
 for x,y in zip(refh,candh):
  with Dataset(x) as d1,Dataset(y) as d2:
   d1.set_auto_maskandscale(False);d2.set_auto_maskandscale(False)
   if decode_times(d1)!=decode_times(d2): mismatches.append(x.name+':Times')
  q1=quality_dataset(x); q2=quality_dataset(y)
  diff=exact_dataset_compare(x,y)
  history.append({'file':x.name,'times':q1.get('times'),'baseline_sha256':sha(x),'candidate_sha256':sha(y),'baseline_quality':q1,'candidate_quality':q2,'exact_differences':diff})
  mismatches.extend(x.name+':'+d for d in diff)
 base_cp=validate_checkpoints(reference); cand_cp=validate_checkpoints(candidate)
 for b,c in zip(base_cp,cand_cp):
  if b['file']!=c['file'] or b['times']!=c['times']: mismatches.append(b['file']+':checkpoint_times')
  diff=exact_dataset_compare(reference/b['file'],candidate/c['file']); c['exact_differences']=diff
  if diff: mismatches.extend(b['file']+':'+d for d in diff)
 return {'status':'EXACT_ALL_OUTPUTS' if not mismatches else 'OUTPUT_DIFFERENCES','history_count':len(history),'history':history,'baseline_checkpoints':base_cp,'candidate_checkpoints':cand_cp,'differences':mismatches}

def parse_diag_line(line, rank, filename):
 tag=next((t for t in TAGS if t in line),None)
 if tag is None:return None
 match=re.search(r'\b(LW|SW)\s+'+re.escape(tag)+r'\s+(?:phase=)?(LIQ|ICE|RAIN|SNOW)?',line)
 if not match: raise ValueError(f'malformed diagnostic tag ({filename}): {line}')
 band,phase=match.groups()
 if tag.endswith('CU_LUT_CLIP'): phase=phase or re.search(r'phase=\s*(LIQ|ICE)',line).group(1)
 if not phase: raise ValueError(f'diagnostic has no phase ({filename}): {line}')
 nums={k:v for k,v in TOKEN.findall(line)}
 # Fortran list-directed CU rows and explicit-format native rows both tokenize as key=value.
 for k,v in nums.items():
  if k in {'tile_i','tile_j','phase'}: continue
  try: n=float(v.replace('D','E').replace('d','e'))
  except ValueError as e: raise ValueError(f'bad numeric token {k}={v} ({filename})') from e
  if not np.isfinite(n): raise ValueError(f'nonfinite diagnostic value {k}={v} ({filename})')
 def tile(rx):
  m=rx.search(line)
  if not m: raise ValueError(f'missing tile bounds ({filename}): {line}')
  return tuple(map(int,m.groups()))
 ti,tj=tile(TILE_I),tile(TILE_J)
 required={
  'RRTMGP_UDM_PHASE_PATH':{'native_grid_path_sum_g_m2','cf0_omitted_grid_path_sum_g_m2','cf0_omitted_layer_count','cf0_grid_path_fraction','radiation_step','source_time_seconds','overlap','domain'},
  'RRTMGP_UDM_CF0_OMITTED':{'layers','sum_layer_grid_wp_g_m2','max_layer_grid_wp_g_m2'},
  'RRTMGP_UDM_LUT_CLIP':{'low_layers','high_layers','low_clipped_layer_wp_sum_g_m2','high_clipped_layer_wp_sum_g_m2','eligible_layer_wp_sum_g_m2','clip_grid_wp_fraction','max_low_g_m2','max_high_g_m2'},
  'RRTMGP_CU_POPULATION':{'accepted_grid_sum_g_m2','rejected_grid_sum_g_m2','rejected_grid_max_g_m2','omitted_cf0_count','omitted_cf0_sum_g_m2','omitted_cf0_max_g_m2','negative_source_count','negative_active_count','radiation_step','source_time_seconds','overlap','domain'},
  'RRTMGP_CU_LUT_CLIP':{'low_layers','low_grid_path_g_m2','high_layers','high_grid_path_g_m2','eligible_grid_path_g_m2','clipped_grid_path_fraction','max_low_g_m2','max_high_g_m2','radiation_step','source_time_seconds','overlap','domain'}}[tag]
 missing=required-set(nums)
 if missing: raise ValueError(f'incomplete/truncated {tag} line, missing={sorted(missing)} ({filename}): {line}')
 step=nums.get('radiation_step')
 source_time=nums.get('source_time_seconds')
 return {'rank':rank,'file':filename,'timestamp':None,'band':band,'tag':tag,'phase':phase,
  'tile_i':ti,'tile_j':tj,'radiation_step':step,'source_time_seconds':source_time,'values':nums,'raw':line.rstrip()}
def diagnostics(case):
 ranklogs=sorted(case.glob('rsl.error.[0-9][0-9][0-9][0-9]'))
 if len(ranklogs)!=4: raise ValueError(f'expected 4 rank error logs, found {len(ranklogs)}')
 records=[]; successes=[]; perlog={}
 for p in ranklogs:
  rank=int(p.name[-4:]); text=p.read_text(errors='strict'); success='SUCCESS COMPLETE WRF' in text
  successes.append({'rank':rank,'path':p.name,'sha256':sha(p),'success_marker':success})
  if not success: raise ValueError(f'no WRF success marker in {p.name}')
  rows=[]
  for line in text.splitlines():
   rec=parse_diag_line(line,rank,p.name)
   if rec: rows.append(rec)
  perlog[p.name]=rows; records.extend(rows)
  if any('*****' in x['raw'] for x in rows): raise ValueError(f'truncated diagnostic output in {p.name}')
 if not records: raise ValueError('no phase-path/CU diagnostics observed')
 # Validate per-record arithmetic, identifiers, and native-versus-CF0 accounting.
 native={}; omission=[]; cu_population=[]; cu_clip=[]; context_keys=set()
 for r in records:
  v=r['values']; tag=r['tag']; key=(r['rank'],r['timestamp'],r['band'],r['phase'],r['tile_i'],r['tile_j'],r['radiation_step'])
  if tag.endswith('PHASE_PATH'):
   domain=int(v['domain']); step=int(v['radiation_step']); source_seconds=float(v['source_time_seconds']); overlap=int(v['overlap'])
   if domain<1 or step<0 or source_seconds<0 or overlap<0: raise ValueError(f'invalid native diagnostic context: {r}')
   ctx=(r['rank'],r['band'],tag,r['phase'],r['tile_i'],r['tile_j'],domain,step,source_seconds,overlap)
   if ctx in context_keys: raise ValueError(f'duplicate per-call diagnostic context: {ctx}')
   context_keys.add(ctx)
   total=float(v['native_grid_path_sum_g_m2']); omitted=float(v['cf0_omitted_grid_path_sum_g_m2']); count=int(v['cf0_omitted_layer_count']); frac=float(v['cf0_grid_path_fraction'])
   if total<0 or omitted<0 or omitted>total+max(1e-10,abs(total)*1e-12) or count<0 or not 0<=frac<=1: raise ValueError(f'invalid native/omission accounting: {r}')
   if abs(frac-(omitted/total))>max(1e-12,abs(frac)*1e-12): raise ValueError(f'phase omission fraction mismatch: {r}')
   if key in native: raise ValueError(f'duplicate native phase row key {key}')
   native[key]=(count,omitted,total)
  elif tag.endswith('CF0_OMITTED'):
   omission.append({'rank':r['rank'],'band':r['band'],'phase':r['phase'],'layers':int(v['layers']),
    'sum':float(v['sum_layer_grid_wp_g_m2']),'max':float(v['max_layer_grid_wp_g_m2']),'tile_i':r['tile_i'],'tile_j':r['tile_j']})
  elif tag.endswith('CU_POPULATION'):
   domain=int(v['domain']); step=int(v['radiation_step']); source_seconds=float(v['source_time_seconds']); overlap=int(v['overlap'])
   if domain<1 or step<0 or source_seconds<0 or overlap<0: raise ValueError(f'invalid CU diagnostic context: {r}')
   ctx=(r['rank'],r['band'],tag,r['phase'],r['tile_i'],r['tile_j'],domain,step,source_seconds,overlap)
   if ctx in context_keys: raise ValueError(f'duplicate per-call diagnostic context: {ctx}')
   context_keys.add(ctx)
   acc=float(v['accepted_grid_sum_g_m2']); rej=float(v['rejected_grid_sum_g_m2']); om=float(v['omitted_cf0_sum_g_m2'])
   if min(acc,rej,om)<0 or int(v['omitted_cf0_count'])<0: raise ValueError(f'invalid CU path accounting: {r}')
   cu_population.append(r)
  elif tag.endswith('CU_LUT_CLIP'):
   domain=int(v['domain']); step=int(v['radiation_step']); source_seconds=float(v['source_time_seconds']); overlap=int(v['overlap'])
   if domain<1 or step<0 or source_seconds<0 or overlap<=0: raise ValueError(f'invalid CU clipping context or overlap: {r}')
   ctx=(r['rank'],r['band'],tag,r['phase'],r['tile_i'],r['tile_j'],domain,step,source_seconds,overlap)
   if ctx in context_keys: raise ValueError(f'duplicate per-call diagnostic context: {ctx}')
   context_keys.add(ctx)
   low=float(v['low_grid_path_g_m2']); high=float(v['high_grid_path_g_m2']); eligible=float(v['eligible_grid_path_g_m2']); frac=float(v['clipped_grid_path_fraction'])
   if min(low,high,eligible)<0 or eligible<=0 or not 0<=frac<=1: raise ValueError(f'invalid CU clip accounting: {r}')
   if abs(frac-(low+high)/eligible)>max(2e-6,abs(frac)*2e-6): raise ValueError(f'CU clip fraction mismatch: {r}')
   cu_clip.append(r)
 native_groups={}; omission_groups={}
 for key,val in native.items():
  count,omitted,total=val
  group=(key[0],key[2],key[3]); g=native_groups.setdefault(group,{'rows':0,'omitted_rows':0,'count':0,'omitted_sum':0.0,'native_sum':0.0})
  g['rows']+=1; g['count']+=count; g['omitted_sum']+=omitted; g['native_sum']+=total
  if count>0:g['omitted_rows']+=1
 for d in omission:
  group=(d['rank'],d['band'],d['phase']); g=omission_groups.setdefault(group,{'rows':0,'count':0,'sum':0.0})
  g['rows']+=1;g['count']+=d['layers'];g['sum']+=d['sum']
 if set(omission_groups)-set(native_groups): raise ValueError('CF0 detail group lacks full-precision phase rows')
 for group,g in native_groups.items():
  od=omission_groups.get(group,{'rows':0,'count':0,'sum':0.0})
  if od['rows']!=g['omitted_rows'] or od['count']!=g['count'] or abs(od['sum']-g['omitted_sum'])>max(1e-3,abs(g['omitted_sum'])*1e-6):
   raise ValueError(f'aggregate CF0 detail does not reconcile to phase-path context for {group}: native={g}, detail={od}')
 return {'rank_success':successes,'record_count':len(records),'records':records,'per_rank_tag_counts':{str(rank):{tag:sum(r['tag']==tag for r in rr) for tag in TAGS} for rank,rr in ((i,[x for x in records if x['rank']==i]) for i in range(4))},
  'native_phase_records':len(native),'native_cf0_detail_records':len(omission),'native_cf0_detail_aggregate':omission_groups,'cu_population_records':len(cu_population),'cu_clip_records':len(cu_clip),
  'positive_cu_accepted_grid_sum_g_m2':sum(float(r['values']['accepted_grid_sum_g_m2']) for r in cu_population),
  'positive_cu_rejected_grid_sum_g_m2':sum(float(r['values']['rejected_grid_sum_g_m2']) for r in cu_population),
  'positive_cu_clip_path_sum_g_m2':sum(float(r['values']['low_grid_path_g_m2'])+float(r['values']['high_grid_path_g_m2']) for r in cu_clip),
  'all_native_omissions_bounded':True,'records_by_ranklog':perlog}

def run_environment():
 # Reproduce the exact 12-key allowlisted environment recorded for retained long-b1.
 return {'LD_LIBRARY_PATH':f"{ROOT}/build/deps/netcdf/lib:{ROOT}/build/deps/root/usr/lib/x86_64-linux-gnu:{ROOT}/build/deps/mpich-sock/lib",
  'MPICH_INTERFACE_HOSTNAME':'127.0.0.1','NETCDF':str(ROOT/'build/deps/netcdf'),
  'OMP_DYNAMIC':'FALSE','OMP_MAX_ACTIVE_LEVELS':'1','OMP_NESTED':'FALSE','OMP_NUM_THREADS':'2','OMP_PROC_BIND':'FALSE','OMP_STACKSIZE':'512M',
  'OPENBLAS_NUM_THREADS':'1','PATH':f"{ROOT}/build/deps/mpich-sock/bin:/usr/bin:/bin",'WRF_RRTMGP_BATCH_SIZE':'1'}
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--execute',action='store_true',help='run the single staged candidate; requires a fresh execution directory'); ap.add_argument('--timeout',type=int,default=3600)
 a=ap.parse_args()
 if a.timeout!=3600: raise ValueError('this reviewed candidate has a fixed 3600-second limit')
 if OUT.exists(): raise FileExistsError(f'preserve previous execution output; use new generation: {OUT}')
 if a.execute and not PREFLIGHT.is_file(): raise FileNotFoundError('execute requires the reviewed immutable preflight receipt')
 if not a.execute and PREFLIGHT.exists(): raise FileExistsError(f'preserve previous preflight; use new generation: {PREFLIGHT}')
 prep=json.loads(BUILD_PREP.read_text()); build=json.loads(BUILD.read_text()); stage=json.loads(STAGE.read_text()); baserun=json.loads(BASE_RUN.read_text()); arm=baserun['arms']['long-b1']
 if build.get('status')!='BUILD_PASS' or build.get('model_invocations')!=0 or stage.get('status')!='STAGED_NOT_RUN': raise ValueError('build/stage not eligible')
 if arm.get('status')!='CASE_VALIDATED' or arm.get('returncode')!=0 or arm.get('model_invoked') is not True: raise ValueError('selected retained baseline arm not validated')
 newexe=Path(build['executables']['wrf.exe']['path']); baseexe=Path(arm['executable']['path'])
 if pin(newexe)['sha256']!=build['executables']['wrf.exe']['sha256'] or pin(baseexe)['sha256']!='6088620a5a27020bba4454d8380ecc149bbbea78ef1c82b37df15e719163fca5': raise ValueError('candidate or baseline binary pin mismatch')
 if pin(BASE/'namelist.input')['sha256']!=stage['baseline_namelist']['sha256'] or pin(CASE/'namelist.input')['sha256']!=stage['staged_namelist']['sha256']: raise ValueError('namelist changed')
 if pin(CASE/'wrfinput_d01')['sha256']!='0cc7e188ef585a93ab52550816c6af236932254820fb1bc6937f464bfed38637' or pin(CASE/'wrfbdy_d01')['sha256']!='ba4241de4f4661a77733cf157f0c87f90668f107df86f8c92d092b56d7bd7bd4': raise ValueError('candidate IC/BC pins mismatch')
 if pin(CASE/'wrf.exe')['sha256']!=build['executables']['wrf.exe']['sha256']: raise ValueError('candidate wrf.exe link mismatch')
 if sorted(p.name for p in CASE.glob('wrfout_d01_*')) or sorted(p.name for p in CASE.glob('wrfrst_d01_*')) or list(CASE.glob('rsl.*')): raise ValueError('candidate case is not clean')
 cmd=[str(MPICH),'-launcher','fork','-iface','lo','-n','4',str(newexe)]
 if not MPICH.is_file(): raise FileNotFoundError(MPICH)
 env=run_environment()
 if set(env)!=set(arm.get('environment',{})): raise ValueError('runtime environment key set differs from retained long-b1')
 expected_base_cmd=[str(MPICH),'-launcher','fork','-iface','lo','-n','4',str(baseexe)]
 if arm.get('command')!=expected_base_cmd: raise ValueError('retained long-b1 launcher/rank layout differs from approved command')
 for k,v in env.items():
  if arm.get('environment',{}).get(k)!=v: raise ValueError(f'candidate environment differs from retained long-b1 for {k}')
 old_quality=arm['quality']
 if old_quality.get('history',{}).get('status')!='QUALITY_PASS' or old_quality['history'].get('Times')!=EXPECTED_TIMES or old_quality['history'].get('variable_count')!=225 or old_quality['history'].get('numeric_variable_count')!=224:
  raise ValueError('retained baseline 25-record/225-variable quality evidence incomplete')
 if set(old_quality.get('checkpoints',{}))!={'2000-01-25_00:00:00','2000-01-25_12:00:00'}: raise ValueError('retained baseline own-checkpoint evidence incomplete')
 for t,cp in old_quality['checkpoints'].items():
  if cp.get('status')!='QUALITY_PASS' or cp.get('Times')!=[t] or cp.get('variable_count')!=667 or cp.get('numeric_variable_count')!=666: raise ValueError(f'baseline checkpoint quality evidence invalid {t}')
 if any(k.startswith(('WRF_RRTMGP_CAPTURE','WRF_RRTMGP_AUDIT','WRF_RRTMGP_TRACE')) for k in env): raise ValueError('capture/audit/trace environment leaked')
 stack_now=resource.getrlimit(resource.RLIMIT_STACK); stack_request=512*1024*1024
 if stack_now[1] not in (-1,resource.RLIM_INFINITY) and stack_now[1]<stack_request: raise ValueError(f'main-stack hard limit cannot support 512 MiB request: {stack_now}')
 inputs={p.name:(target_record(p) if p.is_symlink() else pin(p)) for p in sorted(CASE.iterdir()) if p.is_symlink() or p.name=='namelist.input'}
 immutable_history={p.name:sha(p) for p in histories(BASE)}; immutable_baseline_cp={p.name:sha(p) for p in BASE.glob('wrfrst_d01_*')}
 if set(immutable_baseline_cp)!=set(EXPECTED_CHECKPOINTS): raise ValueError('retained baseline own checkpoint file set mismatch')
 baseline_history_times=[]
 for f in histories(BASE):
  with Dataset(f) as ds: ds.set_auto_maskandscale(False); baseline_history_times.extend(decode_times(ds))
 if baseline_history_times!=EXPECTED_TIMES: raise ValueError('retained baseline history does not contain exact 25 expected records')
 base_diag_rows=legacy_summary_diagnostics(BASE)
 source_before=source_integrity()
 # The shared compiler/MPI/NetCDF inventory was checked at build time and is rechecked before and after execution.
 prepmod_path=ROOT/'build/udm37-restart-cloud-diagnostics-gnu-v1/prepare_restart_source_v4.py'
 import importlib.util
 spec=importlib.util.spec_from_file_location('pinned_deps',prepmod_path); depmod=importlib.util.module_from_spec(spec); spec.loader.exec_module(depmod)
 dep_before=depmod.deps_inventory()
 if dep_before['manifest_sha256']!=build['dependencies_before']['manifest_sha256']:
  raise ValueError('shared dependencies do not match build receipt')
 out_record={'schema':'udm37-pr60-active-cu-run-v1','status':'PREFLIGHT_READY_NOT_RUN','created_utc':now(),'model_launched':False,'model_invocations':0,
  'execute_requested':a.execute,'candidate_case':str(CASE),'baseline_case':str(BASE),'command':cmd,'timeout_seconds':a.timeout,'environment':env,
  'candidate_executable':pin(newexe),'baseline_executable':pin(baseexe),'baseline_arm':{'status':arm['status'],'returncode':arm['returncode'],'model_invoked':arm['model_invoked'],'elapsed_seconds':arm['elapsed_seconds'],'record_sha256':hashlib.sha256(json.dumps(arm,sort_keys=True,separators=(',',':')).encode()).hexdigest()},
  'build_result':pin(BUILD),'source_preparation':pin(BUILD_PREP),'source_manifest':pin(MANIFEST),'stage_receipt':pin(STAGE),'candidate_inputs_before':inputs,
  'baseline_history_hashes_before':immutable_history,'baseline_checkpoint_hashes_before':immutable_baseline_cp,
  'baseline_history_times_readback':baseline_history_times,'baseline_quality_receipt':{'history':{k:old_quality['history'][k] for k in ('status','variable_count','numeric_variable_count','Times')},'checkpoints':{t:{k:c[k] for k in ('status','variable_count','numeric_variable_count','Times')} for t,c in old_quality['checkpoints'].items()}},
  'baseline_legacy_diagnostic_rows':len(base_diag_rows),
  'source_integrity_before':source_before,'shared_dependencies_before':dep_before,
  'expected_history_times':EXPECTED_TIMES,'expected_checkpoint_names':EXPECTED_CHECKPOINTS,'comparison_policy':'exact all variables, dimensions including unlimitedness, variable/global attributes preserving dtype/shape/raw bytes; no tolerances or exclusions',
  'model_invocations_before':0}
 out_record.update({'launcher':pin(MPICH),'baseline_run_receipt':pin(BASE_RUN),'runner_sha256':sha(Path(__file__)),
  'baseline_environment_keys':sorted(arm['environment']),'requested_main_stack_limit_bytes':stack_request,
  'preflight_main_stack_limit':list(stack_now),'build_runtime_libraries':build.get('runtime_libraries'),
  'candidate_compiled_runtime_libraries':build['runtime_libraries'].get('wrf.exe')})
 if not a.execute:
  if PREFLIGHT.exists(): raise FileExistsError(f'preserve previous preflight; use new generation: {PREFLIGHT}')
  out_record['runner_sha256']=sha(Path(__file__)); out_record['source_script_policy']='This runner is pinned by this preflight; edits require a new generation.'
  atomic(PREFLIGHT,out_record); print(json.dumps({'status':out_record['status'],'model_invocations':0,'preflight':str(PREFLIGHT),'candidate_case':str(CASE)},indent=2)); return 0
 prior=json.loads(PREFLIGHT.read_text())
 if prior.get('status')!='PREFLIGHT_READY_NOT_RUN' or prior.get('model_invocations')!=0: raise ValueError('reviewed preflight receipt has invalid status')
 if prior.get('runner_sha256')!=sha(Path(__file__)): raise ValueError('runner changed since preflight')
 if prior.get('candidate_inputs_before')!=inputs or prior.get('candidate_executable')!=pin(newexe) or prior.get('baseline_history_hashes_before')!=immutable_history or prior.get('source_integrity_before')!=source_before or prior.get('shared_dependencies_before',{}).get('manifest_sha256')!=dep_before['manifest_sha256']: raise ValueError('preflight does not match current candidate/source/assets')
 out_record['preflight_receipt_sha256']=sha(PREFLIGHT)
 OUT.mkdir(parents=True); out_record['status']='RUNNING'; out_record['started_utc']=now(); atomic(OUT/'execution.json',out_record)
 proc=None; launched=False; rc=None; timeout=False; error=None; t0=time.monotonic();
 def stack512(): resource.setrlimit(resource.RLIMIT_STACK,(512*1024*1024,512*1024*1024))
 try:
  log=CASE/'wrf.stdout.log'
  with log.open('xb') as f:
   proc=subprocess.Popen(cmd,cwd=CASE,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=stack512)
   launched=True; out_record.update(model_launched=True,model_invocations=1,pid=proc.pid); atomic(OUT/'execution.json',out_record)
   try: rc=proc.wait(timeout=a.timeout)
   except subprocess.TimeoutExpired:
    timeout=True; os.killpg(proc.pid,signal.SIGTERM)
    try: rc=proc.wait(timeout=20)
    except subprocess.TimeoutExpired: os.killpg(proc.pid,signal.SIGKILL); rc=proc.wait()
 except Exception as e: error=f'{type(e).__name__}: {e}'
 out_record.update(returncode=rc,timed_out=timeout,error=error,elapsed_seconds=time.monotonic()-t0,log=pin(CASE/'wrf.stdout.log') if (CASE/'wrf.stdout.log').exists() else None)
 try:
  markers=[{'rank':p.name,'success':'SUCCESS COMPLETE WRF' in p.read_text(errors='replace'),'sha256':sha(p)} for p in sorted(CASE.glob('rsl.error.[0-9][0-9][0-9][0-9]'))]
  if len(markers)!=4 or not all(x['success'] for x in markers): raise ValueError(f'rank success markers invalid: {markers}')
  if rc!=0 or timeout: raise ValueError('launcher failed or exceeded bound')
  out_record['rank_success']=markers
  out_record['history_quality']=validate_times(CASE,EXPECTED_TIMES)
  out_record['checkpoint_quality']=validate_checkpoints(CASE)
  out_record['diagnostics']=diagnostics(CASE)
  base_native=legacy_summary_diagnostics(BASE)
  out_record['historical_diagnostic_rows']=compare_legacy_diagnostics(out_record['diagnostics']['records'],base_native)
  if out_record['historical_diagnostic_rows']['status']!='UNCHANGED': raise ValueError('historical native/CU diagnostic numeric rows changed')
  if out_record['diagnostics']['positive_cu_accepted_grid_sum_g_m2']<=0: raise ValueError('no positive CU path accepted in active-CU experiment')
  if out_record['diagnostics']['positive_cu_clip_path_sum_g_m2']<=0: raise ValueError('no positive CU LUT clipping observed in this known active-CU case')
  out_record['comparison']=validate_case_pair(BASE,CASE)
  if out_record['comparison']['status']!='EXACT_ALL_OUTPUTS': raise ValueError('full output comparison differs')
  out_record['status']='COMPLETE_EXACT_DIAGNOSTICS_VALIDATED'
 except Exception as e:
  out_record['postflight_error']=f'{type(e).__name__}: {e}'; out_record['status']='FAILED_POSTFLIGHT_PRESERVED'
 # Always recheck immutable inputs, baseline outputs, build source, and run receipt.
 try:
  after={p.name:(target_record(p) if p.is_symlink() else pin(p)) for p in sorted(CASE.iterdir()) if p.is_symlink() or p.name=='namelist.input'}
  out_record['candidate_inputs_after']=after; out_record['candidate_inputs_unchanged']=after==inputs
  out_record['baseline_history_hashes_after']={p.name:sha(p) for p in histories(BASE)}
  out_record['baseline_checkpoints_hashes_after']={p.name:sha(p) for p in BASE.glob('wrfrst_d01_*')}
  out_record['baseline_unchanged']=out_record['baseline_history_hashes_after']==immutable_history and out_record['baseline_checkpoints_hashes_after']==immutable_baseline_cp
  out_record['source_integrity_after']=source_integrity(); out_record['source_unchanged']=out_record['source_integrity_after']==source_before
  out_record['shared_dependencies_after']=depmod.deps_inventory(); out_record['dependencies_unchanged']=out_record['shared_dependencies_after']['manifest_sha256']==dep_before['manifest_sha256']
  if not out_record['candidate_inputs_unchanged'] or not out_record['baseline_unchanged'] or not out_record['source_unchanged'] or not out_record['dependencies_unchanged']: out_record['status']='FAILED_IMMUTABLE_POSTFLIGHT_PRESERVED'
 except Exception as e:
  out_record['immutable_postflight_error']=repr(e); out_record['status']='FAILED_IMMUTABLE_POSTFLIGHT_PRESERVED'
 out_record['finished_utc']=now(); atomic(OUT/'execution.json',out_record)
 print(json.dumps({'status':out_record['status'],'model_invocations':out_record['model_invocations'],'returncode':rc,'postflight_error':out_record.get('postflight_error')},indent=2))
 return 0 if out_record['status']=='COMPLETE_EXACT_DIAGNOSTICS_VALIDATED' else 1
if __name__=='__main__': raise SystemExit(main())
