#!/usr/bin/env python3
"""Offline fixed-threshold and exact-mapping negative controls; no solver."""
import importlib.util,sys,unittest
from pathlib import Path
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent;s=importlib.util.spec_from_file_location('bon_ref_controls',P/'verify.py');v=importlib.util.module_from_spec(s);sys.modules[s.name]=v;s.loader.exec_module(v)
class Controls(unittest.TestCase):
 def test_mask_exact_pass(self):self.assertTrue(v.compare_values('MASK',[0.,1.],[0.,1.])['passed'])
 def test_mask_difference_rejected(self):
  with self.assertRaises(ValueError):v.compare_values('MASK',[0.,.999],[0.,1.])
 def test_optical_threshold_rejected(self):
  with self.assertRaises(ValueError):v.compare_values('GAS_TAU',[1.+3e-12],[1.])
 def test_output_threshold_rejected(self):
  with self.assertRaises(ValueError):v.compare_values('DN',[1.+3e-6],[1.])
 def test_nonfinite_rejected(self):
  with self.assertRaises(ValueError):v.compare_values('DN',[float('nan')],[1.])
 def test_real32_mapping_and_wrong_PI(self):
  hr=[v.f32(-3.+k*.01) for k in range(32)];pi=[v.f32(.7+k*.005) for k in range(32)];theta=[v.f32(v.f32(h/86400.)/p) for h,p in zip(hr,pi)]
  prod={'DN':{'values':[10.,0.]},'UP':{'values':[20.,30.]},'HR':{'values':hr},'WRF_GLW':{'shape':(1,1,1),'values':[10.]},'WRF_OLR':{'shape':(1,1,1),'values':[30.]},'WRF_THETA_HR':{'shape':(1,32,1),'values':theta}}
  raw={'PI':{'shape':(32,),'values':pi}};self.assertTrue(v.mapping_checks(prod,raw)['native_theta32_f32_f32_HR_over86400_overPI']);pi[0]=.8
  with self.assertRaises(ValueError):v.mapping_checks(prod,raw)
if __name__=='__main__':unittest.main()
