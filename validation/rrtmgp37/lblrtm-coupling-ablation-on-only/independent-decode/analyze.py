#!/usr/bin/env python3
"""Bounded saved-output decoder for actual same-TAPE5 OFF/ON LBLRTM arms.
No execution, interpolation, clipping, or source mutation.
"""
from __future__ import annotations
import hashlib, json, math, struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PAIR=ROOT/'build/udm37-lblrtm-sametape3-coupling-ablation-v1'
BASE=ROOT/'build/udm37-lblrtm-candidate-decision-run-v3/runs/od-v3'
OFF=PAIR/'runs-v4/off'
ON=PAIR/'runs-on-only-v3/on'
TARGETS=[666.3135288888894,666.3738311111116,666.4341333333339]
PROBE_TOL=1.0e-9  # representational grid reconstruction only; no nearest-point replacement

def sha_bytes(b): return hashlib.sha256(b).hexdigest()
def sha_file(p):
    h=hashlib.sha256(); n=0
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):
            h.update(block);n+=len(block)
    return h.hexdigest(),n

def readrec(f, *, keep=True):
    lead=f.read(4)
    if not lead: return None
    if len(lead)!=4: raise ValueError('truncated record marker')
    n=struct.unpack('<i',lead)[0]
    if n<0 or n>100_000_000: raise ValueError(f'invalid record length {n}')
    payload=f.read(n) if keep else None
    if not keep: f.seek(n,1)
    trail=f.read(4)
    if len(trail)!=4 or struct.unpack('<i',trail)[0]!=n: raise ValueError('record marker mismatch')
    if keep and (payload is None or len(payload)!=n): raise ValueError('short record read')
    return (n,payload)

def parse_file(path, expected_layer, values=False):
    panels=[]; flat=[]; nneg=0; negmin=None; vmin=None; vmax=None; samples=0
    with path.open('rb') as f:
        head=readrec(f)
        if head is None: raise ValueError(f'{path}: empty')
        hn,hb=head
        if hn!=177*8: raise ValueError(f'{path}: FILHDR length {hn}')
        layer=struct.unpack_from('<q',hb,165*8)[0]
        if layer!=expected_layer: raise ValueError(f'{path}: layer {layer} != {expected_layer}')
        pave,tave=struct.unpack_from('<2d',hb,11*8)
        while True:
            item=readrec(f)
            if item is None: raise ValueError(f'{path}: missing ENDFIL')
            n,payload=item
            if n==6*8 and struct.unpack('<6q',payload)==(-99,)*6:
                if f.read(1): raise ValueError(f'{path}: bytes after ENDFIL')
                break
            if n!=4*8: raise ValueError(f'{path}: unexpected panel header length {n}')
            v1,v2,dv=struct.unpack_from('<3d',payload,0)
            nlim=struct.unpack_from('<q',payload,24)[0]
            if not math.isfinite(v1+v2+dv) or dv<=0 or nlim<=0: raise ValueError('invalid PNLHDR')
            drec=readrec(f,keep=values)
            if drec is None or drec[0]!=nlim*8: raise ValueError('panel data NLIM mismatch')
            vals=None
            if values:
                vals=struct.unpack('<'+'d'*nlim,drec[1])
                if not all(math.isfinite(x) for x in vals): raise ValueError('nonfinite OD sample')
                for x in vals:
                    samples+=1; vmin=x if vmin is None else min(vmin,x); vmax=x if vmax is None else max(vmax,x)
                    if x<0: nneg+=1; negmin=x if negmin is None else min(negmin,x)
            matches=[]
            for ti,target in enumerate(TARGETS):
                q=(target-v1)/dv; idx=round(q)
                if 0<=idx<nlim:
                    got=v1+idx*dv
                    if abs(got-target)<=PROBE_TOL:
                        matches.append({'target':target,'target_index':ti,'zero_based_index':idx,'one_based_index':idx+1,
                                        'coordinate':got,'coordinate_error':got-target,
                                        'value':vals[idx] if vals is not None else None})
            panels.append({'v1':v1,'v2':v2,'dv':dv,'n':nlim,'exact_probe_matches':matches,
                           'values':vals})
    return {'path':path.name,'layer':layer,'pave':pave,'tave':tave,'panels':panels,
            'sample_count':samples,'value_min':vmin,'value_max':vmax,
            'negative_count':nneg,'negative_min':negmin}

def digest_rows(path): return json.loads(path.read_text())

# Process receipt first: if incomplete, do not inspect OD values.
exec_path=PAIR/'runs-on-only-v3/execution.json'; on_exec=json.loads(exec_path.read_text())
proc_path=PAIR/'runs-on-only-v3/process-on.json'; proc=json.loads(proc_path.read_text())
if not (on_exec.get('status')=='TERMINAL_ON_DESCRIPTIVE_ONLY' and on_exec.get('attempted_solver_arms')==1
        and on_exec.get('physical_reference_accepted') is False
        and proc.get('status')=='TERMINAL' and proc.get('actual_child_returncode')==0
        and proc.get('reaped') is True and proc.get('timed_out') is False
        and proc.get('process_group_cleanup',{}).get('process_group_clean') is True):
    raise SystemExit('ON process receipt is not terminal RC0/reaped; refusing data decode')
if on_exec['completed_process_records'][0].get('sha256')!=sha_file(proc_path)[0]:
    raise SystemExit('execution-to-process receipt SHA mismatch')
off_exec=json.loads((PAIR/'runs-v4/execution.json').read_text())
off_proc=json.loads((PAIR/'runs-v4/process-off.json').read_text())
if not (off_exec.get('status')=='FAIL_STOP_PRESERVED' and off_exec.get('attempted_solver_arms')==1
        and off_exec.get('completed_process_records',[{}])[0].get('actual_child_returncode')==0
        and off_proc.get('status')=='TERMINAL' and off_proc.get('actual_child_returncode')==0
        and off_proc.get('reaped') is True and off_proc.get('timed_out') is False):
    raise SystemExit('OFF context no longer matches preserved terminal RC0 fail-stop')

plan=json.loads((PAIR/'on-only-plan-v3.json').read_text())
# Check arm summaries and panel metadata for all 45 files. This pass skips data vectors.
off_post=digest_rows(PAIR/'runs-v4/postflight-off.json'); on_post=digest_rows(PAIR/'runs-on-only-v3/postflight-on.json')
for post,folder in [(off_post,OFF),(on_post,ON)]:
    outs={x['path']:x for x in post['outputs'] if x['path'].startswith('ODdeflt_')}
    if len(outs)!=45: raise SystemExit('missing/extra OD roster')
    for i in range(1,46):
        nm=f'ODdeflt_{i:03d}'; p=folder/nm
        row=outs[nm]
        if (p.stat().st_size!=row['size_bytes'] or sha_file(p)[0]!=row['sha256']):
            raise SystemExit(f'postflight pin mismatch for {nm}')

meta={'OFF':{},'ON':{}}
for arm,folder in [('OFF',OFF),('ON',ON)]:
    for k in range(1,46):
        nm=f'ODdeflt_{k:03d}'
        meta[arm][nm]=parse_file(folder/nm,k,values=False)

# Full-value scan only for the intervention layer. Keep signed OD values as stored.
off21=parse_file(OFF/'ODdeflt_021',21,values=True)
on21=parse_file(ON/'ODdeflt_021',21,values=True)
if len(off21['panels'])!=len(on21['panels']): raise SystemExit('layer21 panel count changed')
changed_segments=[]; total_sample_diffs=0; total_byte_diffs=0; changed_frequency_min=None; changed_frequency_max=None
for pi,(a,b) in enumerate(zip(off21['panels'],on21['panels'])):
    if (a['v1'],a['v2'],a['dv'],a['n'])!=(b['v1'],b['v2'],b['dv'],b['n']):
        raise SystemExit(f'layer21 panel grid metadata changed at panel {pi}')
    va=a['values']; vb=b['values']; diffs=[i for i,(x,y) in enumerate(zip(va,vb)) if x!=y]
    raw_a=struct.pack('<'+'d'*len(va),*va); raw_b=struct.pack('<'+'d'*len(vb),*vb)
    byte_diffs=sum(x!=y for x,y in zip(raw_a,raw_b)); total_byte_diffs+=byte_diffs; total_sample_diffs+=len(diffs)
    if diffs:
        for j in diffs:
            w=a['v1']+j*a['dv']
            changed_frequency_min=w if changed_frequency_min is None else min(changed_frequency_min,w)
            changed_frequency_max=w if changed_frequency_max is None else max(changed_frequency_max,w)
        # Coalesce adjacent changed sample indices within each panel.
        runs=[]; lo=prev=diffs[0]
        for j in diffs[1:]:
            if j!=prev+1: runs.append((lo,prev));lo=j
            prev=j
        runs.append((lo,prev))
        changed_segments.extend({'panel_index_1based':pi+1,'v1':a['v1'],'dv':a['dv'],
                                 'first_index_0based':lo,'last_index_0based':hi,
                                 'first_wavenumber':a['v1']+lo*a['dv'],'last_wavenumber':a['v1']+hi*a['dv'],
                                 'sample_count':hi-lo+1} for lo,hi in runs)

# Probe lookup must be unique exact grid sample in a panel; no nearest or interpolation.
def unique_probes(row):
    out=[]
    for target in TARGETS:
        found=[m for p in row['panels'] for m in p['exact_probe_matches'] if m['target']==target]
        out.append({'target_cm-1':target,'exact_match_count':len(found),
                    'match':found[0] if len(found)==1 else None,
                    'status':'EXACT' if len(found)==1 else ('UNSAMPLED' if not found else 'AMBIGUOUS')})
    return out

probe_off=unique_probes(off21); probe_on=unique_probes(on21)
# Coverage over native layers is computed from panel headers. Sums are permitted only with one exact sample per layer.
coverage={}
for target in TARGETS:
    for arm in ('OFF','ON'):
        per=[]
        for k in range(1,46):
            panels=meta[arm][f'ODdeflt_{k:03d}']['panels']
            count=sum(1 for panel in panels if any(m['target']==target for m in panel['exact_probe_matches']))
            per.append(count)
        coverage[f'{arm}:{target:.13f}']={'layers_with_exact_match':sum(x==1 for x in per),
                                            'layers_without_exact_match':sum(x==0 for x in per),
                                            'layers_with_ambiguous_multi_panel_match':sum(x>1 for x in per),
                                            'exact_vertical_sum_supported':all(x==1 for x in per)}

# The ON runner's event/payload receipts are part of the terminal execution contract; cross-check their statuses.
payload=json.loads((PAIR/'runs-on-only-v3/on-scientific-payload-comparison.json').read_text())
events=json.loads((PAIR/'runs-on-only-v3/on-event-analysis.json').read_text())
if payload.get('status')!='PASS_NONSELECTED_44_EXACT' or events.get('status')!='PASS_SCOPED_SELECTED_COUPLING_EVENTS_OMITTED_DESCRIPTIVE_ONLY':
    raise SystemExit("ON runner's exact nonselected/event checks are not terminal passing")

result={
 'schema':'lblrtm-sametape3-coupling-ablation-saved-decode-v1',
 'status':'SAVED_DATA_DECODE_COMPLETE_DESCRIPTIVE_ONLY',
 'execution_pins':{
  'on_execution':{'path':str(exec_path.relative_to(ROOT)),'sha256':sha_file(exec_path)[0],'status':on_exec['status'],'child_rc':proc['actual_child_returncode'],'reaped':proc['reaped'],'pid':proc['pid']},
  'off_execution':{'path':str((PAIR/'runs-v4/execution.json').relative_to(ROOT)),'sha256':sha_file(PAIR/'runs-v4/execution.json')[0],'status':off_exec['status'],'child_rc':off_proc['actual_child_returncode'],'reaped':off_proc['reaped']},
  'plan_v3_sha256':sha_file(PAIR/'on-only-plan-v3.json')[0],
  'executable_sha256':plan['candidate_executable']['sha256'],
  'TAPE3_sha256':plan['same_tape3_sha256'],'TAPE5_sha256':plan['same_tape5_sha256'],
  'on_payload_status':payload['status'],'event_status':events['status'],
  'physical_reference_accepted':False,'original_off_full_file_hash_failure':'PRESERVED_NOT_WAIVED'
 },
 'decoder':{'source':'build/udm37-lblrtm-od-output-parser-v1/parse_od.py','sha256':'d172651ea902c6d7157b34678742db721872bbb7d153ac923bebeb9e9a79759a',
            'record_layout':'4-byte little-endian sequential markers, 177 REAL*8 FILHDR words, PNLHDR (3 REAL*8 + INTEGER*8 NLIM), NLIM REAL*8 samples, six INTEGER*8 -99 ENDFIL',
            'values_decoded':'ODdeflt_021 only in both arms; other 44 layers were metadata-only panel-grid scans for exact vertical-sum coverage.'},
 'layer21':{
  'OFF':{k:v for k,v in off21.items() if k!='panels'},
  'ON':{k:v for k,v in on21.items() if k!='panels'},
  'panel_count':len(off21['panels']),
  'off_on_panel_grid_identical':True,
  'OFF_exact_probe_matches':probe_off,
  'ON_exact_probe_matches':probe_on,
  'changed_sample_count':total_sample_diffs,'changed_raw_sample_byte_count':total_byte_diffs,
  'changed_wavenumber_min_cm-1':changed_frequency_min,'changed_wavenumber_max_cm-1':changed_frequency_max,
  'changed_contiguous_segments_count':len(changed_segments),
  'changed_segments':changed_segments,
  'signed_values_preserved':True
 },
 'all45_exact_grid_coverage':coverage,
 'column_sum_status':'UNSUPPORTED_NO_INTERPOLATION unless every one of 45 layers has exactly one exact-grid sample; see per-arm/target coverage.',
 'limits':['Single held case, layer-21 selected-event ablation; not a general coupling or physical-reference conclusion.',
           'No interpolation, nearest-point substitution, clipping, or normalization.',
           'Nonselected 44 payload identity and selected event omission are preserved checks; layer 21 output change is descriptive.',
           'The previous ICNTNM=0 decoder plan is not reused as an ICNTNM=1 input/output authority; only its format is reused.',
           'OFF strict full-file hashes still fail only because the timestamp differs; this does not become a PASS and does not change the prior failure record.']
}
out=Path(__file__).with_name('result.json');out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
print(out)
