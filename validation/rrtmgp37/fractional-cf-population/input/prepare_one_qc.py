from pathlib import Path
import hashlib,json,shutil,sys
import netCDF4 as nc
import numpy as np
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
original=ROOT/'build/udm37-activation-supersat-input-v1/derived/wrfinput_d01'
out=ROOT/'build/udm37-fractional-cf-input-v1'
derived=out/'derived/wrfinput_d01'
expected='4be27d2dfbec0286a5dc7e8a73d0b2ee78de028e7cacf735fd8b393567e44380'
def pin(p):
 b=p.read_bytes();return {'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'size_bytes':len(b)}
def attrs(o):
 return {k:{'dtype':str(np.asarray(o.getncattr(k)).dtype),'shape':list(np.asarray(o.getncattr(k)).shape),'bytes_sha256':hashlib.sha256(np.asarray(o.getncattr(k)).tobytes()).hexdigest()} for k in o.ncattrs()}
origpin=pin(original);assert origpin['sha256']==expected
assert not derived.exists()
derived.parent.mkdir()
shutil.copyfile(original,derived)
idx=(0,6,1,22)
with nc.Dataset(derived,'r+') as d:
 d.set_auto_maskandscale(False)
 assert len(d.variables)==197
 v=d.variables['QCLOUD']; assert v.dtype==np.dtype('float32')
 before=float(v[idx]);v[idx]=np.float32(1.e-4)
rows=[]
with nc.Dataset(original) as a,nc.Dataset(derived) as b:
 a.set_auto_maskandscale(False);b.set_auto_maskandscale(False)
 assert a.data_model==b.data_model
 assert attrs(a)==attrs(b)
 dims=lambda d:{k:[len(v),v.isunlimited()] for k,v in d.dimensions.items()}
 assert dims(a)==dims(b)
 assert list(a.variables)==list(b.variables)
 for name in a.variables:
  va,vb=a.variables[name],b.variables[name]
  meta=lambda v:{'dtype':str(v.dtype),'dimensions':list(v.dimensions),'shape':list(v.shape),'attrs':attrs(v),'endian':v.endian(),'chunking':v.chunking(),'filters':v.filters()}
  assert meta(va)==meta(vb),name
  aa=np.asarray(va[:]);bb=np.asarray(vb[:])
  ah=hashlib.sha256(aa.tobytes()).hexdigest();bh=hashlib.sha256(bb.tobytes()).hexdigest()
  if name=='QCLOUD':
   assert aa.shape==(1,44,99,90)
   bit_a=aa.view('uint32');bit_b=bb.view('uint32')
   different=np.argwhere(bit_a!=bit_b)
   assert different.tolist()==[list(idx)]
   assert bb[idx]==np.float32(1.e-4)
   bb[idx]=aa[idx]
   assert aa.tobytes()==bb.tobytes()
   changed=1
  else:
   assert aa.tobytes()==bb.tobytes(),name
   changed=0
  rows.append({'name':name,'shape':list(aa.shape),'dtype':str(aa.dtype),'source_array_sha256':ah,'derived_array_sha256':bh,'changed_stored_elements':changed,'metadata_byte_equal':True})
assert pin(original)==origpin
report={'status':'PASS_SCOPED_ONE_QCLOUD_ELEMENT_DERIVATION','baseline':origpin,'derived':pin(derived),'changed_variable':'QCLOUD','python_index':list(idx),'fortran_identity':{'i':23,'j':2,'k':7},'old_value':before,'new_stored_real32_value':float(np.float32(1.e-4)),'schema_variables':197,'all_dimensions_and_attributes_unchanged':True,'other_196_variable_arrays_byte_equal':True,'qcloud_other_stored_elements_byte_equal':True,'variables':rows,'limits':['One intervention relative to supersaturation baseline4be; inherited QV change means two interventions relative to original849f.','Source-expression CF certificate is conditional; dynamics and number adjustment can alter predivision QC/QI.','Require actual predivision QC>0, NC>0, and0<CF<1; no retries or tuning on NON_DISCRIMINATING fixture.','No Nc/CCN unit, PSD, LUT or physical-accuracy approval.'],'model_calls':0,'compiler_calls':0,'scientific_acceptance':False}
(out/'input-variable-join.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='variables'},indent=2))
