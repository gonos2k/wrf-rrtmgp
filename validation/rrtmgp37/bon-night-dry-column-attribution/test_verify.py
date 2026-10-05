#!/usr/bin/env python3
"""Offline rejection checks; no reference executable is invoked."""
import importlib.util,sys,unittest
from pathlib import Path
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('bon_dry_verifier',Path(__file__).with_name('verify.py'));v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
def sample(n):
 return b'HEADER\nHELD_PREFIX 1 1\n-0.0\nNATIVE_DRY_LAYER_MASS_KG_M2 1 '+str(n).encode()+b'\n'+b'1.0\n'*n+b'HELD_SUFFIX 1 1\n2.0\n'
class Controls(unittest.TestCase):
 def test_allowed_mass_carrier(self):self.assertTrue(v.mass_only_edit(sample(32),sample(45))['prefix_suffix_bytes_exact'])
 def test_other_input_change_rejected(self):
  with self.assertRaises(ValueError):v.mass_only_edit(sample(32),sample(45).replace(b'2.0',b'3.0'))
 def test_signed_zero_input_change_rejected(self):
  with self.assertRaises(ValueError):v.mass_only_edit(sample(32),sample(45).replace(b'-0.0',b'0.0'))
 def test_wrong_carrier_count_rejected(self):
  with self.assertRaises(ValueError):v.mass_only_edit(sample(32),sample(44))
 def test_duplicate_section_rejected(self):
  with self.assertRaises(ValueError):v.mass_only_edit(sample(32),sample(45)+b'NATIVE_DRY_LAYER_MASS_KG_M2 1 45\n')
if __name__=='__main__':unittest.main()
