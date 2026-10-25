"""Small semantic counterexamples at the actual attribution/decision boundaries."""
from pathlib import Path
import unittest,importlib.util,json,copy
P=Path(__file__).resolve().parent;s=importlib.util.spec_from_file_location('saved',P/'verify_saved.py');V=importlib.util.module_from_spec(s);s.loader.exec_module(V)
class ActualBoundaryDecision(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.d,cls.inputs,cls.result=V.data()
 def edit(self,tag,index,value):
  lines=self.d['native/sterling-boundary.txt'].decode().splitlines()
  for k,l in enumerate(lines):
   w=l.split()
   if w[1]==tag:w[index+2]=str(value);lines[k]=' '.join(w);break
  return ('\n'.join(lines)+'\n').encode()
 def test_wrong_neighbour_cannot_replay_fivepoint(self):
  with self.assertRaises(ValueError):V.A.evaluate(self.edit('core',10,999.))
 def test_assumed_coefficient_cannot_replace_actual(self):
  with self.assertRaises(ValueError):V.A.evaluate(self.edit('core',5,0.))
 def test_missing_native_time_cannot_be_zero_filled(self):
  with self.assertRaises(ValueError):V.A.evaluate(b'\n'.join(self.d['native/sterling-boundary.txt'].splitlines()[1:])+b'\n')
 def test_predictor_dt_cannot_replace_full_source_dt(self):
  with self.assertRaises(ValueError):V.A.evaluate(self.edit('pd_before',3,20.))
 def test_missing_condensate_cannot_be_external_clear_truth(self):
  d=json.loads(self.d['provenance.json']);d['boundary_zeros_are_valid_external_clear_sky']=True
  with self.assertRaises(ValueError):V.provenance_check(d)
 def test_old_boundary_cell_cannot_be_interior_validation(self):
  d=json.loads(self.d['preflight/receipt.json']);d['site']['cells_to_nearest_physical_edge']=2
  with self.assertRaises(ValueError):V.interior_check(d)
 def test_changed_native_array_cannot_pass_observation_check(self):
  d=json.loads(self.d['history-comparison.json']);next(iter(next(iter(d['inventory'].values())).values()))['right_sha256']='0'*64
  with self.assertRaises(ValueError):V.compare_check(d)
if __name__=='__main__':unittest.main()
