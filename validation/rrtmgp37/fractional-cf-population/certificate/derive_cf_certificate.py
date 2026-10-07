#!/usr/bin/env python3
"""Source-expression certificate only; no input editing or native execution."""
import ctypes, hashlib, json, pathlib, struct
ROOT=pathlib.Path(__file__).resolve().parent
SOURCE=ROOT.parent/'udm37-positive-nc-stage-observer-source-v2/WRF/phys/module_mp_udm.F'
def f(x):return struct.unpack('<f',struct.pack('<f',float(x)))[0]
def m(a,b):return f(f(a)*f(b))
def d(a,b):return f(f(a)/f(b))
def a(x,y):return f(f(x)+f(y))
def s(x,y):return f(f(x)-f(y))
lib=ctypes.CDLL('libm.so.6');lib.powf.argtypes=[ctypes.c_float,ctypes.c_float];lib.powf.restype=ctypes.c_float
qc=f(1e-4);qi=f(0);dx=f(10000)
def cv(q,n,p,denom):return d(m(f(n),lib.powf(m(max(f(0),q),f(1000)),f(p))),f(denom))
lo=a(cv(qc,4.82,.94,1.04),cv(qi,4.82,.94,.96));hi=a(cv(qc,5.77,1.07,1.04),cv(qi,5.77,1.07,.96))
raw=d(a(m(s(d(dx,1000),50),s(hi,lo)),m(50,lo)),50);cf=min(f(1),max(f(0),raw))
if a(qc,qi)<f(1e-6):cf=f(0)
if cf<f(.01):cf=f(0)
if cf>f(.99):cf=f(1)
if cf>=f(.01) and cf<f(.5):cf=f(.5)
incloud=d(qc,cf);restored=m(incloud,cf)
assert f(.5)<cf<f(.99) and qc>f(1e-6)
result={'status':'PASS_SCOPED_CONDITIONAL_SOURCE_EXPRESSION_CERTIFICATE','source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'source_constants':{'dxmeter_m':10000.0,'cldmin':50.,'cldmax':100.,'cldf_min':.5,'QC_plus_QI_cutoff':1e-6},'conditional_inputs':{'QC':qc,'QI':qi,'dxmeter':dx},'cvf_min':lo,'cvf_max':hi,'unclamped_CF':raw,'CF_after_source_clamps':cf,'CF_raw_margin_above_floor':cf-f(.5),'CF_raw_margin_below_snap':f(.99)-cf,'QC_divided':incloud,'QC_divide_multiply_roundtrip':restored,'QC_roundtrip_exact_for_this_tuple':qc==restored,'predicted_future_model_CF':False,'limits':['QI=0 and actual conversion QC equal selected hypothetical input are conditions, not runtime observations.','cldf_diag arguments T/P/Q are unused in this source; actual native dxmeter is fixed10000m, not gridDX.','C libm powf plus explicit binary32 arithmetic is a source-expression evaluation, not a newly compiled native acceptance test or universal compiler identity.','Input/dynamics/preprocessing may change QC/QI before diagnostic; future actual gate must use captured states and source-derived CF.','No count units/population/PSD/radiation correction or physical approval.'],'counts':{'pure_python_source_expression_runs':1,'input_writes':0,'source_edits':0,'compiler':0,'WRF_model':0,'RTE':0}}
(ROOT/'certificate.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps({'CF':cf,'QC':qc,'QI':qi,'QC_incloud':incloud,'status':result['status']}))
