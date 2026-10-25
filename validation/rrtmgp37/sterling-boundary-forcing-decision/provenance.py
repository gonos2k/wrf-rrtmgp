"""Read original inputs and effective global intermediates; do not infer weather from zeros."""
from pathlib import Path
import json,hashlib,struct,importlib.util
import numpy as np
from netCDF4 import Dataset,chartostring
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-sterling-provenance-v1';O.mkdir(exist_ok=False)
def pin(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
COND=['QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL']
flag=['FLAG_QC','FLAG_QR','FLAG_QI','FLAG_QS','FLAG_QG','FLAG_QH','FLAG_SPECCLDL','FLAG_SPECCLDF']
def inventory(p):
 with Dataset(p) as d:
  d.set_auto_maskandscale(False)
  candidates={n:pin_value(v[:]) for n,v in d.variables.items() if n in COND or any(n.startswith(c+'_B') for c in COND) or n in ['QC','QR','QI','QS','QG','QH','SPECCLDL','SPECCLDF']}
  return {**pin(p),'title':getattr(d,'TITLE',''),'times':chartostring(d['Times'][:]).astype(str).tolist(),'variables':list(d.variables),'provided_flags':{n:getattr(d,n) for n in flag if n in d.ncattrs()},'condensate':candidates,'number_contract':{n:int(getattr(d,n)) for n in ['UDM_NUMBER_POLICY','UDM_POPULATION_POLICY','UDM_SPECIFIED_NUMBER_CONTRACT'] if n in d.ncattrs()}}
def pin_value(a):
 a=np.asarray(a);return {'shape':list(a.shape),'sha256':hashlib.sha256(a.tobytes()).hexdigest(),'nonzero':int(np.count_nonzero(a)),'nonfinite':int(np.count_nonzero(~np.isfinite(a))),'min':float(np.min(a)),'max':float(np.max(a))}
def records(p):
 with p.open('rb') as f:
  while x:=f.read(4):
   n=struct.unpack('>I',x)[0];assert n<3000000
   v=f.read(n);assert len(v)==n and struct.unpack('>I',f.read(4))[0]==n
   yield v
intermediate=[]
for p in sorted((B/'udm37-sterling-interior-inputs-v1/intermediate').glob('FILE:*')):
 rr=iter(records(p));fields=[]
 for version in rr:
  assert struct.unpack('>i',version)[0]==5
  head=next(rr);assert len(head)==156
  field=head[60:69].decode().strip();unit=head[69:94].decode().strip();desc=head[94:140].decode().strip();level,nx,ny,proj=struct.unpack('>fiii',head[140:]);assert nx==360 and ny==181
  next(rr);assert len(next(rr))==4;assert len(next(rr))==nx*ny*4
  fields.append({'name':field,'units':unit,'description':desc,'level':level})
 intermediate.append({**pin(p),'fields':fields,'unique_field_names':sorted({x['name'] for x in fields})})
met=[inventory(p) for p in sorted((B/'udm37-matthew-48h-forcing-v1/met_em').glob('met_em*.nc'))];assert len(met)==9
raw=B/'udm37-matthew-real-v1/case';encoded=B/'udm37-specified-number-run-v2/encoded';zero=B/'udm37-clear-reference-real-v3/number1_input'
chain={label:{name:inventory(d/name) for name in ['wrfinput_d01','wrfbdy_d01']} for label,d in [('original_REAL',raw),('metadata_only',zero),('specified_contract',encoded)]}
for name in ['wrfinput_d01','wrfbdy_d01']:
 with Dataset(raw/name) as x,Dataset(zero/name) as y,Dataset(encoded/name) as z:
  x.set_auto_maskandscale(False);y.set_auto_maskandscale(False);z.set_auto_maskandscale(False)
  assert set(x.variables)==set(y.variables)==set(z.variables)
  for n in x.variables:
   assert np.asarray(x[n][:]).tobytes()==np.asarray(y[n][:]).tobytes()==np.asarray(z[n][:]).tobytes(),n
for m in met:assert not m['condensate'] and not m['provided_flags']
for m in chain['original_REAL'].values():assert m['condensate'] and all(x['nonzero']==x['nonfinite']==0 for x in m['condensate'].values())
old=B/'udm37-pr60-active-cu-current-build-v1/source-v3/WRF/dyn_em/module_initialize_real.F';current=R/'WRF/dyn_em/module_initialize_real.F'
a=old.read_text();b=current.read_text();start='         IF ( flag_qr .EQ. 1 ) THEN';end='         IF ( flag_qni .EQ. 1 ) THEN'
section_equal=a[a.index(start):a.index(end)]==b[b.index(start):b.index(end)]
result={'status':'EFFECTIVE_FORCING_CONDENSATE_NOT_PROVIDED_DEFAULT_ZERO','classification':{c:'not provided by actual met_em; raw REAL output is zero; not demonstrated external-model physical clear sky' for c in COND},'actual_original_met_em':met,'global_intermediate':intermediate,'original_chain':chain,'all_variable_arrays_preserved_both_producers':True,'retained_REAL_condensate_interpolation_section_equals_current':section_equal,'retained_REAL_source':pin(old),'current_REAL_source':pin(current),'original_REAL_receipt':pin(B/'udm37-matthew-real-v1/execution-receipt.json'),'original_met_em_download':json.loads((B/'udm37-matthew-48h-forcing-v1/archive/download-receipt.json').read_text()),'raw_FNL_cloud_parameter_availability_not_claimed':True,'effective_preprocessing_absence_does_not_prove_raw_FNL_absence':True,'boundary_zeros_are_valid_external_clear_sky':False,'production_changes':False}
assert section_equal
(O/'provenance.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'],len(intermediate),'global intermediates',len(met),'original met_em')
