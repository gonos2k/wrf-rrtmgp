#!/usr/bin/env python3
"""Semantic counterexamples for the executed reference boundary."""
import importlib.util,json,unittest,copy
from pathlib import Path
P=Path(__file__).resolve().parent
def load(n):
 s=importlib.util.spec_from_file_location(n,P/(n+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v=load('verify_saved');a=load('analyze_saved')
class ReferenceMeaning(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.read,cls.prior=map(staticmethod,v.readers());cls.plan=json.loads((P/'plan.json').read_text())
 def altered(self,name,change):
  def read(n):
   data=self.read(n)
   if n==name:
    d=json.loads(data);change(d);return json.dumps(d).encode()
   return data
  return read
 def test_diagonal_refinement_cannot_replace_separate_axes(self):
  def change(d):d['records'][0]['levels'][-1]['radius_half']['ns']//=2
  with self.assertRaisesRegex(ValueError,'radius axis changes spectral'):a.analyze(self.altered('mie/result.json',change),self.prior,self.plan)
 def test_failure_cannot_be_promoted_to_qualified(self):
  def change(d):
   row=d['records'][0];g=row['levels'][-1]['radius_half']
   for k in a.M:g[k]*=2
   g['abs_ext_minus_sca_residual']*=2
  with self.assertRaisesRegex(ValueError,'qualification contradicts'):a.analyze(self.altered('mie/result.json',change),self.prior,self.plan)
 def test_unselected_coefficient_cannot_be_overwritten(self):
  target='night_peak_lw_B_fine/optics.dat'
  def read(n):
   data=self.read(n)
   if n==target:
    lines=data.decode().splitlines();row=lines[3].split();row[0]=str(float(row[0])+1.);lines[3]=' '.join(row);return ('\n'.join(lines)+'\n').encode()
   return data
  with self.assertRaisesRegex(ValueError,'unqualified or unselected'):a.analyze(read,self.prior,self.plan)
 def test_extended_TOA_is_not_native_top(self):
  with self.assertRaisesRegex(ValueError,'native-top boundary'):a.values({},native_top=121)
if __name__=='__main__':unittest.main()
