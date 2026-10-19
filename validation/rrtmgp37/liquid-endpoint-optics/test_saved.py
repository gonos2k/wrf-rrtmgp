#!/usr/bin/env python3
"""Semantic boundaries of this endpoint comparison, without model execution."""
import importlib.util,json,unittest
from pathlib import Path
B=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('v',B/'verify_saved.py');v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
s=importlib.util.spec_from_file_location('a',B/'analyze_saved.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
class EndpointBoundaries(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.read,cls.prior=map(staticmethod,v.readers());cls.plan=json.loads((B/'plan.json').read_text())
 def reject(self,target,mutate,message):
  def read(n):return mutate(self.read(n)) if n==target else self.read(n)
  with self.assertRaisesRegex(ValueError,message):a.analyze(read,self.prior,self.plan)
 def test_B_must_use_endpoint_not_actual_radius(self):
  def mutate(data):
   lines=data.decode().splitlines();nl=int(lines[0].split()[1]);r=json.loads(self.read('mie/result.json'))['records'];c=next(r for r in r if r['phase']=='lw' and r['band']==1 and r['reff_um']==22.4102725982666)['grids'][-1]
   lines[2]=' '.join(str(c[m]) for m in a.MOMENTS);return ('\n'.join(lines)+'\n').encode()
  self.reject('night_peak_lw_B/optics.dat',mutate,'radius/definition mapping')
 def test_double_SW_delta_scaling_is_rejected(self):
  def mutate(data):
   lines=data.decode().splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('CLOUD_TAU '));vals=lines[i+1].split();vals[0]=str(float(vals[0])*.8);lines[i+1]=' '.join(vals);return ('\n'.join(lines)+'\n').encode()
  self.reject('day_peak_sw_C/sw.result',mutate,'SW exactly one delta')
 def test_unselected_liquid_layer_is_preserved(self):
  def mutate(data):
   lines=data.decode().splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('CLOUD_TAU '));vals=lines[i+5].split();vals[0]=str(float(vals[0])+.001);lines[i+5]=' '.join(vals);return ('\n'.join(lines)+'\n').encode()
  self.reject('day_peak_lw_C/lw.result',mutate,'unselected liquid optics')
 def test_unresolved_absorption_cannot_be_promoted_to_converged(self):
  def mutate(data):
   m=json.loads(data);next(r for r in m['records'] if not r['converged'])['converged']=True;return json.dumps(m).encode()
  self.reject('mie/result.json',mutate,'convergence classification')
 def test_signed_decomposition_is_not_maximum_subtraction(self):
  r=a.decomposition([0.,0.],[2.,-3.],[4.,1.],(1,2,1))
  self.assertEqual(r['signed_radius'],[2.,4.]);self.assertEqual(r['radius_C_minus_B']['max_abs'],4.)
  self.assertNotEqual(r['radius_C_minus_B']['max_abs'],r['total_C_minus_A']['max_abs']-r['definition_B_minus_A']['max_abs'])
if __name__=='__main__':unittest.main()
