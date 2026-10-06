#!/usr/bin/env python3
"""Selected-layer-only binary OD reader extracted from the pinned saved-data decoder.
Reads two supplied ODdeflt_021 files only; no solver, file discovery or network.
"""
from __future__ import annotations
import argparse, hashlib, json, math, struct
from pathlib import Path
TARGETS=[666.3135288888894,666.3738311111116,666.4341333333339]
PROBE_TOL=1.0e-9
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
def summarize(path,arm):
 row=parse_file(path,21,values=True)
 return {'arm':arm,'sample_count':row['sample_count'],'negative_count':row['negative_count'],'negative_min':row['negative_min'],'value_min':row['value_min'],'value_max':row['value_max'],'pave':row['pave'],'tave':row['tave'],'panel_count':len(row['panels']),'probes':[{ 'target_cm-1':t,'matches':[m for p in row['panels'] for m in p['exact_probe_matches'] if m['target']==t]} for t in TARGETS]}, row
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--off',type=Path,required=True);ap.add_argument('--on',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 off,orow=summarize(a.off,'OFF');on,nrow=summarize(a.on,'ON')
 if len(orow['panels'])!=len(nrow['panels']): raise SystemExit('panel-count mismatch')
 sample_diff=byte_diff=0; grids_equal=True
 for x,y in zip(orow['panels'],nrow['panels']):
  if (x['v1'],x['v2'],x['dv'],x['n'])!=(y['v1'],y['v2'],y['dv'],y['n']): grids_equal=False;raise SystemExit('panel-grid mismatch')
  va=x['values'];vb=y['values']
  if len(va)!=len(vb): raise SystemExit('sample-length mismatch')
  sample_diff+=sum(u!=v for u,v in zip(va,vb))
  ba=struct.pack('<'+'d'*len(va),*va);bb=struct.pack('<'+'d'*len(vb),*vb);byte_diff+=sum(u!=v for u,v in zip(ba,bb))
 result={'schema':'lblrtm-selected-layer21-independent-decode-v1','status':'SAVED_DATA_DESCRIPTIVE_ONLY','source_decoder_path':'build/udm37-lblrtm-sametape3-on-saved-decode-v1/analyze.py','source_decoder_sha256':'720bb2497bfa8af8f074e45a0635203c997e29fb7cd70bfc46f3893ced1f8b82','off':off,'on':on,'panel_grid_identical':grids_equal,'changed_sample_count':sample_diff,'changed_raw_sample_byte_count':byte_diff,'physical_reference_accepted':False,'scope':'Only supplied ODdeflt_021 files; no vertical sum, no other-layer claim.'}
 a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n');print(json.dumps({'status':result['status'],'off_negative_count':off['negative_count'],'off_min':off['negative_min'],'on_negative_count':on['negative_count'],'on_min':on['negative_min'],'changed_sample_count':sample_diff,'changed_raw_sample_byte_count':byte_diff,'panel_grid_identical':grids_equal}))
if __name__=='__main__':main()
