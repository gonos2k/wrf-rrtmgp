#!/usr/bin/env python3
"""Offline semantic rejection controls; no compiled executable invocation."""
import copy,importlib.util,sys,unittest
from pathlib import Path
sys.dont_write_bytecode=True
s=importlib.util.spec_from_file_location('transport_verifier',Path(__file__).with_name('verify.py'));v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
def field(vals,shape=(1,1,1)):return {'shape':shape,'values':vals}
def side():return {'TRANSPORT_POLICY':field([1.]),'SOURCE_LAYER':field([1.]*5760,(1,45,128)),'SOURCE_LEVEL':field([1.]*5888,(1,46,128)),'SOURCE_SURFACE':field([1.]*128,(1,1,128)),'BAND_LIMITS_GPOINT':field([1.]*32,(2,16,1)),'BAND_LIMITS_WAVENUMBER':field([1.]*32,(2,16,1))}
class Controls(unittest.TestCase):
 def test_exact_held(self):v.must_hold({'GAS_TAU':field([0.])},{'GAS_TAU':field([0.])},{'GAS_TAU'})
 def test_signed_zero_rejected(self):
  with self.assertRaises(ValueError):v.must_hold({'MASK':field([-0.])},{'MASK':field([0.])},{'MASK'})
 def test_missing_gas_rejected(self):
  with self.assertRaises(ValueError):v.must_hold({'GAS_TAU':field([1.])},{},{'GAS_TAU'})
 def test_source_change_rejected(self):
  a=side();b=copy.deepcopy(a);b['SOURCE_SURFACE']['values'][0]+=1.
  with self.assertRaises(ValueError):v.must_hold(a,b,v.SOURCE)
 def test_valid_default_sidecar(self):v.policy_check(side(),1)
 def test_wrong_angular_value_rejected(self):
  a=side();a['TRANSPORT_POLICY']=field([2.]);a['LW_DIFFUSIVITY_ANGLE']=field([1.6])
  with self.assertRaises(ValueError):v.policy_check(a,2)
 def test_extra_sidecar_field_rejected(self):
  a=side();a['UNDECLARED']=field([1.])
  with self.assertRaises(ValueError):v.policy_check(a,1)
if __name__=='__main__':unittest.main()
