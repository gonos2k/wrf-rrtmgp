#!/usr/bin/env python3
"""Independently parse the fixture as a Fortran stream and audit against 64 captures."""
from pathlib import Path
import importlib.util,struct,hashlib,json,math
import numpy as np
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP');D=ROOT/'build/udm-lw-batch-wp-probe/fixtures-v2';CAP=ROOT/'build/udm-lw-batch-firstcall-v1'
FIELDS=['play','plev','tlay','tlev','tsfc','h2o','co2','o3','n2o','ch4','o2','emis','cf','lwp','iwp','swp','rel','rei','res','rwp','native_mass','gwp','hwp','lambda_g','lambda_h','cfc11','cfc12','cfc22','ccl4']
SHAPES={'play':(32,47),'plev':(32,48),'tlay':(32,47),'tlev':(32,48),'tsfc':(32,), 'h2o':(32,47),'co2':(32,47),'o3':(32,47),'n2o':(32,47),'ch4':(32,47),'o2':(32,47),'emis':(32,16),'cf':(32,47),'lwp':(32,47),'iwp':(32,47),'swp':(32,47),'rel':(32,47),'rei':(32,47),'res':(32,47),'rwp':(32,47),'native_mass':(32,39),'gwp':(32,47),'hwp':(32,47),'lambda_g':(32,47),'lambda_h':(32,47),'cfc11':(32,47),'cfc12':(32,47),'cfc22':(32,47),'ccl4':(32,47)}
SPEC=importlib.util.spec_from_file_location('capture_decoder',ROOT/'build/udm-lw-batch-firstcall-offline-decode.py');MOD=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MOD)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(mode):
    root=CAP/mode/'batch-diagnostic';xs=[]
    for p in sorted(root.glob('lwdiag_call01_mode*_row*.bin')):xs.append((p,MOD.decode_bytes(p.read_bytes())))
    xs.sort(key=lambda z:z[1]['header']['row'])
    if len(xs)!=32:raise ValueError(f'{mode}: capture count {len(xs)}')
    return xs
def fbytes(a):return np.asarray(a,dtype='>f4').tobytes()
batch=load('on-b32');scalar=load('on-scalar');p=D/'lw32-fortran-order.bin';raw=p.read_bytes();off=0
nc,nl=struct.unpack_from('>ii',raw,off);off+=8
constants=struct.unpack_from('>4fii',raw,off);off+=24
day,=struct.unpack_from('>i',raw,off);off+=4
seeds=struct.unpack_from('>32i',raw,off);off+=128
if (nc,nl)!=(32,47):raise ValueError(('header dims',nc,nl))
header_names=('gravity','cp_dry','mol_weight_dry','time','overlap','iceflag')
metadata=dict(zip(header_names,constants));metadata['day']=day
parsed={}
for name in FIELDS:
    shape=SHAPES[name];n=math.prod(shape);size=n*4
    if off+size>len(raw):raise ValueError(f'truncated at {name}')
    v=np.frombuffer(raw,dtype='>f4',count=n,offset=off).copy();off+=size
    parsed[name]=v.reshape(shape,order='F')
if off!=len(raw):raise ValueError(f'trailing input bytes: {len(raw)-off}')
batch_by_row={c['header']['row']:c['header'] for _,c in batch}
scalar_by_row={c['header']['row']:c['header'] for _,c in scalar}
all_header_fields=sorted(batch_by_row[next(iter(batch_by_row))].keys())
for row,bh in batch_by_row.items():
    sh=scalar_by_row[row]
    if {k:v for k,v in bh.items() if k!='mode'}!={k:v for k,v in sh.items() if k!='mode'}:
        raise ValueError(f'capture header metadata differs between modes at row {row}')
for mode,rows in [('batch32',batch),('scalar32',scalar)]:
    for r,((cap_path,capture),seed) in enumerate(zip(rows,seeds)):
        h=capture['header']
        if seed!=h['seed']:raise ValueError(f'{mode} seed mismatch row {r+1}')
        if h['row']!=batch[r][1]['header']['row']:raise ValueError(f'{mode} row order mismatch')
        for k in header_names:
            if k in ('overlap','iceflag'):
                if int(metadata[k])!=int(h[k]):raise ValueError(f'{mode} header {k} mismatch')
            elif np.asarray(metadata[k],dtype='>f4').tobytes()!=np.asarray(h[k],dtype='>f4').tobytes():
                raise ValueError(f'{mode} header {k} bits differ row {r+1}')
        if day!=h['day']:raise ValueError(f'{mode} day mismatch')
        for name in FIELDS:
            got=parsed[name][r] if len(SHAPES[name])==2 else np.asarray([parsed[name][r]])
            exp=capture['arrays'][name]
            if fbytes(got)!=fbytes(exp):raise ValueError(f'{mode} {name} mismatch row {r+1} capture={cap_path}')
# Explicit physical structure/data validity checks on the parsed stream.
for key,a in parsed.items():
    if not np.isfinite(a).all():raise ValueError(f'nonfinite {key}')
if not np.all(np.diff(parsed['plev'],axis=1)<0):raise ValueError('pressure interfaces not strictly decreasing')
if not np.all(parsed['native_mass']>0):raise ValueError('native dry layer mass not positive')
# Ensure both original run modes provide bit-identical values for every input.
for _,b in batch:
    r=b['header']['row'];s=next(c for _,c in scalar if c['header']['row']==r)
    for k in FIELDS:
        if fbytes(b['arrays'][k])!=fbytes(s['arrays'][k]):raise ValueError(f'original scalar/batch captures differ row {r} {k}')
# Verify the reference default-real output streams against original captured output arrays.
out_audit={}
for mode,rows in [('batch32',batch),('scalar32',scalar)]:
    ep=D/f'expected-{mode}.bin';eraw=ep.read_bytes();eoff=0;checked={}
    for name in ('up','dn','hr','upc','dnc','hrc'):
        shape=(32,47 if name in ('hr','hrc') else 48);n=math.prod(shape)
        got=np.frombuffer(eraw,dtype='>f4',count=n,offset=eoff).copy().reshape(shape,order='F');eoff+=n*4
        for i,(_,capture) in enumerate(rows):
            if fbytes(got[i])!=fbytes(capture['arrays'][name]):raise ValueError(f'{mode} expected {name} mismatch row {i+1}')
        checked[name]={'shape':list(shape),'values':n}
    if eoff!=len(eraw):raise ValueError(f'{mode} expected output trailing bytes')
    out_audit[mode]={'sha256':sha(ep),'bytes':len(eraw),'arrays':checked}
report={'status':'PASS','method':'independent byte-stream parser; reshape using Fortran column-major declared arrays then compare each column to original capture decoder output','fixture':str(p),'fixture_sha256':sha(p),'fixture_bytes':len(raw),'capture_count':64,'input_field_count':len(FIELDS),'all_fields_compared_to_each_capture':True,'headers_and_seeds_compared_to_each_capture':True,'capture_header_fields_checked_between_modes':all_header_fields,'capture_header_metadata_matches_across_modes':True,'pressure_strictly_decreasing_all_columns':True,'native_mass_positive_all_values':True,'all_input_values_finite':True,'parsed_shapes':{k:list(v.shape) for k,v in parsed.items()},'expected_output_streams':out_audit,'capture_file_hashes':{str(x):sha(x) for x in [p for p,_ in batch]+[p for p,_ in scalar]}}
out=D/'independent-decode-receipt.json';out.write_text(json.dumps(report,indent=2)+'\n');print(out,sha(out))
