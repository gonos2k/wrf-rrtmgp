#!/usr/bin/env python3
"""Posthoc independent byte-array check for same-executable restart outputs.

This is a newly retained reproduction utility, not the inline checker that
produced root-restart-bitwise-recheck.json. It reads arrays with netCDF4
mask/scale disabled and compares their exposed dtype, shape, and bytes. It
reports global metadata separately; START_DATE is expected to differ.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import netCDF4


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    if isinstance(value, bytes):
        try: return value.decode('utf-8')
        except UnicodeDecodeError: return {'bytes_hex':value.hex()}
    if isinstance(value, np.ndarray):
        if value.dtype.kind == 'S':
            return [canonical(x.tobytes()) for x in value.reshape(-1)]
        if value.dtype.kind == 'U': return value.reshape(-1).tolist()
        if value.dtype.kind in 'fiu': return value.tolist()
        return {'dtype':value.dtype.str,'shape':list(value.shape),'bytes':value.tobytes().hex()}
    if isinstance(value, np.generic): return canonical(np.asarray(value))
    if isinstance(value, (list,tuple)): return [canonical(x) for x in value]
    return value


def compare(reference: Path, restarted: Path) -> dict:
    out={'reference':str(reference),'restart':str(restarted),
         'reference_sha256':sha256(reference),'restart_sha256':sha256(restarted),
         'mode':'raw-array-bytes; netCDF4 automatic mask/scale disabled',
         'passed':False,'numeric_arrays_equal':0,'other_arrays_equal':0,
         'array_differences':[],'variable_metadata_differences':[],
         'global_attribute_differences':[]}
    with netCDF4.Dataset(reference,'r') as left, netCDF4.Dataset(restarted,'r') as right:
        left.set_auto_maskandscale(False); right.set_auto_maskandscale(False)
        ld={n:(len(d),d.isunlimited()) for n,d in left.dimensions.items()}
        rd={n:(len(d),d.isunlimited()) for n,d in right.dimensions.items()}
        if ld != rd: out['array_differences'].append({'dimensions':{'reference':ld,'restart':rd}})
        ln,rn=set(left.variables),set(right.variables)
        if ln != rn: out['array_differences'].append({'variables':{'only_reference':sorted(ln-rn),'only_restart':sorted(rn-ln)}})
        for name in sorted(ln & rn):
            a,b=left.variables[name],right.variables[name]
            if a.dimensions != b.dimensions:
                out['array_differences'].append({'variable':name,'dimensions':[a.dimensions,b.dimensions]})
                continue
            aa,bb=np.asarray(a[:]),np.asarray(b[:])
            if aa.dtype != bb.dtype or aa.shape != bb.shape or aa.tobytes(order='C') != bb.tobytes(order='C'):
                out['array_differences'].append({'variable':name,'reference_dtype':aa.dtype.str,
                    'restart_dtype':bb.dtype.str,'reference_shape':list(aa.shape),'restart_shape':list(bb.shape),
                    'reference_bytes_sha256':hashlib.sha256(aa.tobytes(order='C')).hexdigest(),
                    'restart_bytes_sha256':hashlib.sha256(bb.tobytes(order='C')).hexdigest()})
            elif aa.dtype.kind in 'fiu': out['numeric_arrays_equal'] += 1
            else: out['other_arrays_equal'] += 1
            la,ra=set(a.ncattrs()),set(b.ncattrs())
            if la != ra:
                out['variable_metadata_differences'].append({'variable':name,'attribute_names':[sorted(la),sorted(ra)]})
            for attr in sorted(la & ra):
                va,vb=canonical(a.getncattr(attr)),canonical(b.getncattr(attr))
                if va != vb:
                    out['variable_metadata_differences'].append({'variable':name,'attribute':attr,
                                                                  'reference':va,'restart':vb})
        la,ra=set(left.ncattrs()),set(right.ncattrs())
        if la != ra:
            out['global_attribute_differences'].append({'attribute_names':[sorted(la),sorted(ra)]})
        for attr in sorted(la & ra):
            va,vb=canonical(left.getncattr(attr)),canonical(right.getncattr(attr))
            if va != vb:
                out['global_attribute_differences'].append({'attribute':attr,'reference':va,'restart':vb})
    changed_global={x.get('attribute') for x in out['global_attribute_differences'] if 'attribute' in x}
    expected_start=(len(changed_global)==1 and changed_global=={'START_DATE'} and
                    next(x for x in out['global_attribute_differences'] if x.get('attribute')=='START_DATE') ==
                    {'attribute':'START_DATE','reference':'2010-06-11_00:00:00','restart':'2010-06-11_12:00:00'})
    out['expected_START_DATE_difference_only']=expected_start
    out['passed']=(not out['array_differences'] and not out['variable_metadata_differences'] and expected_start)
    return out


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--restart',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists(): p.error(f'refusing to overwrite {a.output}')
    result=compare(a.reference,a.restart)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:result[k] for k in ('passed','numeric_arrays_equal','other_arrays_equal','expected_START_DATE_difference_only')},indent=2))
    return 0 if result['passed'] else 1

if __name__=='__main__': sys.exit(main())
