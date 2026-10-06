#!/usr/bin/env python3
"""Reconstruct only retained legacy CFC columns in actual REAL32 arithmetic."""
import gzip,importlib.util,json,struct,sys,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('audit_context',P/'audit.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def f32(x):return struct.unpack('>f',struct.pack('>f',x))[0]
def main():
 er=m.load('precision_export_reader',m.NIGHT/'parser/read_export_context.py').read_export
 with tempfile.TemporaryDirectory(prefix='bon-CFC-precision-') as td:
  p=Path(td)/'export';p.write_bytes(gzip.decompress((m.NIGHT/'exports/rrtmg4_d01_i13_j46_step721_lw.txt.gz').read_bytes()));ex=er(p,expected_context={'domain':1,'i':13,'j':46,'step':721,'source_seconds':43200.})['fields']
 rows=[]
 for row,n in enumerate(['CCl4_VMR','CFC11_VMR','CFC12_VMR','CFC22_VMR']):
  actual=[ex['INPUT','WX_CROSS_SECTION_COLUMNS_SCALED'].at(row,k) for k in range(45)]
  expected=[f32(f32(ex['INPUT','COLDry'].values[k]*ex['INPUT',n].values[k])*f32(1e-20)) for k in range(45)]
  assert m.equal(actual,expected)
  rows.append({'VMR':n,'layers':45,'operation_by_operation_REAL32_exact':True,'max_absolute_residual':0.})
 return {'schema':'bon-night-CFC-source-precision-addendum-v1','status':'PASS_EXACT_LEGACY_REAL32_CROSS_SECTION_COLUMNS','source':m.pin(m.ROOT/'build/udm37-export-selection-serial-build-v1/source/WRF/phys/module_ra_rrtmg_lw.f90'),'source_contract':'Executed parkind kind_rb=kind(1.0); native GNU default REAL is32. WX=COLDry*VMR*1.e-20_rb rounds after both multiplications; cross-section slot order CCl4,CFC11,CFC12,CFC22.','rows':rows,'audit_json_precision_clarification':'audit.json reconstruction reports a binary64 reference formula comparison, not source-typed exact recurrence. The small differences there are fully explained by the verified operation-by-operation REAL32 calculation; they are not evidence of omitted CFC amounts. The reconstructed legacy diffusivity list in audit.json is likewise a binary64 formula reference, not a captured or source-exact REAL32 secdiff array.','unjoined_CO_broadener_note':'Legacy WKL CO slot is zero, but setcoef replaces zero scaled colco with1e-32*COLDry (F:3851/3896). wbrodl is formed separately from COLDry and supplied gas mixture. GP removes unavailable gas names during coefficient load; its continuum/broadener treatment is not joined termwise by existing export. No magnitude or bug conclusion follows.','new_model_build_solver_calls':0}
if __name__=='__main__':
 r=main();p=P/'precision-addendum.json'
 with p.open('x') as f:json.dump(r,f,indent=2,sort_keys=True);f.write('\n')
 print(json.dumps(m.pin(p)))
