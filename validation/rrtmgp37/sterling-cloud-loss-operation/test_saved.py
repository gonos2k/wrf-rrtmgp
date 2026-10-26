"""Actual-operand semantic counterexamples, not extra scientific closure gates."""
from pathlib import Path
import sys,json,unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import analyze as A
import verify_saved as V
class LocalOperatorEvidence(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.raw=V.load();cls.text=cls.raw['observer/cloud_operations.txt'].decode();cls.parsed=A.parse(cls.text)
 def changed(self,key,offset,value,message):
  d,nb,n=self.parsed;old=d[key];d[key]=old.copy();d[key][offset]=value
  try:
   with self.assertRaisesRegex(ValueError,message):A.analyze('',(d,nb,n))
  finally:d[key]=old
 def test_post_PD_clipping_cannot_replace_the_source_operation(self):
  key=(60600,'pd_after',3,1,1);q=self.parsed[0][key][0]
  self.changed(key,0,A.f32(q+1e-4),'PD scalar replay')
 def test_wrong_shared_face_flux_is_refused(self):
  key=(60600,'faces',3,1,1);x=self.parsed[0][key][0]
  self.changed(key,0,A.f32(x+1e5),'directional divergence replay')
 def test_predictor_dt_is_not_a_second_physical_interval(self):
  self.changed((60600,'rk_factors',3,1,1),0,20.,'dt/coupling')
 def test_unobserved_source_is_not_silently_zero_filled(self):
  d,nb,n=self.parsed;key=(60600,'pd_source',3,1,1);old=d.pop(key)
  try:
   with self.assertRaises(KeyError):A.analyze('',(d,nb,n))
  finally:d[key]=old
 def test_wrong_time_window_is_refused(self):
  text=self.text.replace('60600.0','60540.0',1)
  with self.assertRaisesRegex(ValueError,'time support'):A.parse(text)
 def test_complete_saved_result_and_scope_replay(self):
  r=V.verify();self.assertEqual(r['cold_array_pairs_equal'],1800);self.assertFalse(r['physical_accuracy_approved']);self.assertFalse(r['production_changes'])
if __name__=='__main__':unittest.main()
