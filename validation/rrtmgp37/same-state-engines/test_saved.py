#!/usr/bin/env python3
"""Semantic negative tests of common state, masks and source accounting."""
import json,unittest,importlib.util
from pathlib import Path
s=importlib.util.spec_from_file_location('same_state_verify',Path(__file__).with_name('verify_saved.py'));v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
A=v.load();PLAN=json.loads((v.P/'plan.json').read_text())
class Meaning(unittest.TestCase):
 def altered(self,callback):
  def read(n):return callback(n,v.read(n))
  return read
 def test_gas_column_unit_mismatch_is_rejected(self):
  def edit(n,d):
   if n=='lw_clear/lw.result':
    ls=d.decode().splitlines();i=ls.index('GAS_COL_DRY 1 121 1')+1;z=ls[i].split();z[0]=str(float(z[0])*1.1);ls[i]=' '.join(z);return ('\n'.join(ls)+'\n').encode()
   return d
  with self.assertRaisesRegex(ValueError,'gas molecular column'):A.analyze(self.altered(edit),PLAN)
 def test_shared_Cstar_cannot_be_replaced_by_other_capacity(self):
  def edit(n,d):
   if n=='lw_clear/native4.txt':
    ls=d.decode().splitlines();z=ls[-1].split();z[0]=str(float(z[0])*1.01);ls[-1]=' '.join(z);return ('\n'.join(ls)+'\n').encode()
   return d
  with self.assertRaisesRegex(ValueError,'declared host Cstar'):A.analyze(self.altered(edit),PLAN)
 def test_equal_seed_does_not_substitute_for_equal_mask(self):
  def edit(n,d):
   if n=='lw_liquid/export4.txt':
    ls=d.decode().splitlines();i=next(i for i,l in enumerate(ls) if l.startswith('MCICA_MASK '))+1;z=ls[i].split();z[29*140]='0';ls[i]=' '.join(z);return ('\n'.join(ls)+'\n').encode()
   return d
  with self.assertRaisesRegex(ValueError,'4 cloud sample/path'):A.analyze(self.altered(edit),PLAN)
 def test_native_heating_must_close_its_own_source(self):
  def edit(n,d):
   if n=='lw_clear/native4.txt':
    ls=d.decode().splitlines();z=ls[5].split();z[29]=str(float(z[29])+1);ls[5]=' '.join(z);return ('\n'.join(ls)+'\n').encode()
   if n=='lw_clear/export4.txt':
    ls=d.decode().splitlines();i=next(i for i,l in enumerate(ls) if l.startswith('HEATING '))+1;z=ls[i].split();z[29]=str(float(z[29])+1);ls[i]=' '.join(z);return ('\n'.join(ls)+'\n').encode()
   return d
  with self.assertRaisesRegex(ValueError,'4 flux/heating source'):A.analyze(self.altered(edit),PLAN)
 def test_extended_TOA_cannot_be_native_boundary(self):
  with self.assertRaisesRegex(ValueError,'not native top'):A.target([],[],[],native_top=121)
if __name__=='__main__':unittest.main()
