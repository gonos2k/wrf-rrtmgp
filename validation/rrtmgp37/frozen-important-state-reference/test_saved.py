"""Reject changed scientific inputs and false scope promotion, without model runs."""
import json, unittest, importlib.util
from pathlib import Path
s=importlib.util.spec_from_file_location("frozen_saved",Path(__file__).resolve().parent/"verify_saved.py");V=importlib.util.module_from_spec(s);s.loader.exec_module(V)
E=V.E
class ScientificCounterexamples(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.saved=V.data()
 def reject_payload(self, key, change):
  d=self.saved.copy();d[key]=change(d[key]);
  with self.assertRaises((AssertionError,ValueError)): E.evaluate(d)
 def test_wrong_selected_layer(self):
  self.reject_payload('rte/fine/coefficients.dat',lambda b:b.replace(b'17 ',b'18 ',1))
 def test_wrong_density_normalization(self):
  def change(b):
   w=b.decode().split();w[4]=str(float(w[4])*912/1000);return (' '.join(w)+'\n').encode()
  self.reject_payload('rte/fine/coefficients.dat',change)
 def test_radius_refinement_changes_spectral_grid(self):
  r=json.loads(self.saved['reference/result.json']);r['records'][0]['levels'][-1]['radius_half']['spectral_degree']//=2
  with self.assertRaises(ValueError): E.reference_check(r,r['state'])
 def test_unqualified_absorption_cannot_be_promoted(self):
  r=json.loads(self.saved['reference/result.json']);g=r['records'][0]['levels'][-1];q=g['radius_half']
  for m in q['monochromatic_kappa_m2_kg']:
   for k in range(4):m[k]*=1.1
  for k in q['moments_m2_kg']:q['moments_m2_kg'][k]*=1.1
  a=g['fine']['moments_m2_kg']['abs'];g['absorption_radius_relative_change']=abs(a-q['moments_m2_kg']['abs'])/a
  with self.assertRaises(ValueError):E.reference_check(r,r['state'])
 def test_nonselected_clear_flux_changes(self):
  def change(b):
   # Edit one actual result payload number under the clear UP record.
   lines=b.decode().splitlines();idx=next(i for i,l in enumerate(lines) if l.split() and l.split()[0]=='UPC');parts=lines[idx+1].split();parts[0]=str(float(parts[0])+1);lines[idx+1]=' '.join(parts);return ('\n'.join(lines)+'\n').encode()
  self.reject_payload('rte/fine/capture/lw.result',change)
 def test_physical_approval_not_inferred_from_convergence(self):
  r=json.loads(self.saved['reference/result.json']);r['physical_accuracy_approved']=True
  with self.assertRaises(ValueError):E.reference_check(r,r['state'])
 def test_omitted_host_variable(self):
  c=json.loads(self.saved['capture/history-comparison.json']);first=next(iter(c['inventory'].values()));del first[next(iter(first))]
  with self.assertRaises(ValueError):V.compare_inventory(c)
if __name__=='__main__':unittest.main()
