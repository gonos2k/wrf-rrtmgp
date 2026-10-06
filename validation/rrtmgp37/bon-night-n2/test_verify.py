#!/usr/bin/env python3
"""Offline evidence-contract controls; no compiled-reader/solver error-path claim."""
import copy,importlib.util,sys,unittest
from pathlib import Path
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('n2verify',Path(__file__).with_name('verify.py'));v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
def field(values,shape=(1,1,1)):return {'shape':shape,'values':values}
class Contracts(unittest.TestCase):
 def test_held_positive(self):
  a={'MASK':field([0.,1.])};v.must_hold(a,copy.deepcopy(a),{'MASK'})
 def test_signed_zero_rejected(self):
  with self.assertRaises(ValueError):v.must_hold({'MASK':field([0.])},{'MASK':field([-0.])},{'MASK'})
 def test_missing_held_rejected(self):
  with self.assertRaises(ValueError):v.must_hold({'MASK':field([1.])},{},{'MASK'})
 def gases(self):
  a={n:field([0.]*5760,(1,45,128)) for n in v.GAS};b=copy.deepcopy(a)
  for n in v.GAS:b[n]['values'][0]=.25
  return a,b
 def test_locality_positive(self):
  a,b=self.gases();self.assertEqual(v.gas_check(a,b,[1000.]*45,9948.)['changed_gas_cells'],1)
 def test_outside_support_rejected(self):
  a,b=self.gases()
  for n in v.GAS:b[n]['values'][45*29]=.25
  with self.assertRaises(ValueError):v.gas_check(a,b,[1000.]*45,9948.)
 def test_upper_pressure_tail_rejected(self):
  a,b=self.gases()
  for n in v.GAS:b[n]['values'][45*122]=.25
  with self.assertRaises(ValueError):v.gas_check(a,b,[10.]*45,9948.)
 def test_wrong_total_rejected(self):
  a,b=self.gases();b['TOTAL_TAU']['values'][0]=.26
  with self.assertRaises(ValueError):v.gas_check(a,b,[1000.]*45,9948.)
 def side(self):
  sh={'SOURCE_LAYER':(1,45,128),'SOURCE_LEVEL':(1,46,128),'SOURCE_SURFACE':(1,1,128),'BAND_LIMITS_GPOINT':(2,16,1),'BAND_LIMITS_WAVENUMBER':(2,16,1),'TRANSPORT_POLICY':(1,1,1),'N2_OVERRIDE':(1,1,1)}
  s={n:field([0.]*(q[0]*q[1]*q[2]),q) for n,q in sh.items()};s['TRANSPORT_POLICY']['values']=[1.];s['N2_OVERRIDE']['values']=[.7808];return s
 def test_declared_vmr_positive(self):v.side_check(self.side(),.7808)
 def test_wrong_declared_vmr_rejected(self):
  with self.assertRaises(ValueError):v.side_check(self.side(),0.)
 def test_extra_sidecar_rejected(self):
  s=self.side();s['EXTRA']=field([0.])
  with self.assertRaises(ValueError):v.side_check(s,.7808)
if __name__=='__main__':unittest.main()
