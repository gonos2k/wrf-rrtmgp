#!/usr/bin/env python3
"""Offline-only parser for 32 scalar WP chunks; never calls the radiation executable."""
from pathlib import Path
import argparse,hashlib,json,math,struct
import numpy as np

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def parse(p):
    lines=Path(p).read_text().splitlines();chunks={};i=0
    while i<len(lines):
        h=lines[i].split();i+=1
        if len(h) not in (3,4):raise ValueError(f'bad section header: {h}')
        name=h[0];shape=tuple(map(int,h[1:]));n=math.prod(shape);tokens=lines[i:i+n];i+=n
        if len(tokens)!=n or any(len(t)!=16 for t in tokens):raise ValueError(f'bad/truncated WP section {name}')
        vals=[struct.unpack('>d',int(t,16).to_bytes(8,'big'))[0] for t in tokens]
        if not all(math.isfinite(x) for x in vals):raise ValueError(f'nonfinite WP value in {name}')
        chunks.setdefault(name,[]).append((shape,tokens))
    merged={}
    for name,parts in chunks.items():
        rank=len(parts[0][0]);tail=parts[0][0][1:]
        if any(len(s)!=rank or s[1:]!=tail for s,_ in parts):raise ValueError(f'inconsistent chunk shapes in {name}')
        fullshape=(sum(s[0] for s,_ in parts),)+tail
        arrays=[np.asarray(t,dtype=object).reshape(s,order='F') for s,t in parts]
        arr=np.concatenate(arrays,axis=0)
        if arr.shape!=fullshape:raise ValueError(f'aggregate shape mismatch for {name}')
        merged[name]={'shape':fullshape,'tokens':arr.flatten(order='F').tolist(),'chunks':len(parts)}
    return merged

def bits(tok):return int(tok,16)
def ordered(x):
    # Monotone unsigned encoding of finite IEEE binary64 for ULP distance.
    b=bits(x)
    return (~b & ((1<<64)-1)) if (b>>63) else (b | (1<<63))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('runroot');ap.add_argument('--output',required=True);a=ap.parse_args()
    rr=Path(a.runroot);out=Path(a.output)
    if out.exists():raise SystemExit(f'refusing existing analysis receipt {out}')
    expected={'GAS_COL_DRY':(32,47),'GAS_TAU':(32,47,128),'SOURCE_LAY':(32,47,128),'SOURCE_LEV':(32,48,128),'SOURCE_SFC':(32,128),'CLEAR_FU':(32,48),'CLEAR_FD':(32,48),'CLEAR_HEAT':(32,47),'TOTAL_TAU':(32,47,128),'ALL_FU':(32,48),'ALL_FD':(32,48),'ALL_HEAT':(32,47)}
    batch=parse(rr/'batch32/wp.hex');scalar=parse(rr/'scalar32/wp.hex')
    if batch.keys()!=scalar.keys() or batch.keys()!=expected.keys():raise ValueError(f'section labels differ: batch={batch.keys()} scalar={scalar.keys()}')
    sections={}
    for name,want in expected.items():
        b=batch[name];s=scalar[name]
        if b['shape']!=want or s['shape']!=want:raise ValueError(f'{name} shape batch={b["shape"]} scalar={s["shape"]} expected={want}')
        bt,st=b['tokens'],s['tokens'];ids=[i for i,(x,y) in enumerate(zip(bt,st)) if x!=y]
        first=ids[0] if ids else None
        if ids:
            vals_b=[struct.unpack('>d',int(bt[i],16).to_bytes(8,'big'))[0] for i in ids]
            vals_s=[struct.unpack('>d',int(st[i],16).to_bytes(8,'big'))[0] for i in ids]
            maxabs=max(abs(x-y) for x,y in zip(vals_b,vals_s))
            maxulp=max(abs(ordered(bt[i])-ordered(st[i])) for i in ids)
            loc=[]
            for q in ids[:10]:
                r=q;coords=[]
                for d in want:
                    coords.append(r%d);r//=d
                loc.append({'fortran_zero_based_index':coords,'batch_hex':bt[q],'scalar_hex':st[q],
                    'batch_value':struct.unpack('>d',int(bt[q],16).to_bytes(8,'big'))[0],
                    'scalar_value':struct.unpack('>d',int(st[q],16).to_bytes(8,'big'))[0]})
        else:maxabs=0.;maxulp=0;loc=[]
        sections[name]={'shape':want,'batch_chunks':b['chunks'],'scalar_chunks':s['chunks'],'differing_values':len(ids),
            'total_values':len(bt),'max_abs_difference':maxabs,'max_ulp_difference':maxulp,'first_10_differences':loc}
    expected_f32={}
    for mode in ('batch32','scalar32'):
        actual=rr/mode/'actual-f32.bin';exp=Path(__file__).resolve().parent/'fixtures-v2'/f'expected-{mode}.bin'
        ar=actual.read_bytes();er=exp.read_bytes()
        if len(ar)!=len(er):raise ValueError(f'{mode} float32 output size differs')
        if ar!=er:raise ValueError(f'{mode} float32 output oracle differs')
        expected_f32[mode]={'exact_bytes':True,'actual_sha256':sha(actual),'expected_sha256':sha(exp),'bytes':len(ar)}
    firstdiff=next((k for k,v in sections.items() if v['differing_values']),None)
    report={'status':'PASS_OFFLINE_REANALYSIS','engine_calls':0,'original_run_receipt_sha256':sha(rr/'run-receipt.json'),
        'batch_wp_sha256':sha(rr/'batch32/wp.hex'),'scalar_wp_sha256':sha(rr/'scalar32/wp.hex'),
        'batch_f32_oracles':expected_f32,'first_differing_wp_stage':firstdiff,'sections':sections,
        'note':'Original run receipt remains unchanged and FAIL_PRESERVED because its scalar validator rejected repeated per-column WP sections; this separate parser joins 32 scalar chunks by the Fortran leading column dimension. No radiation was rerun.'}
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(out)
if __name__=='__main__':main()
