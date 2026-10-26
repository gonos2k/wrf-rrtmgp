"""Seven actual campaign-boundary counterexamples; no new model execution."""
from pathlib import Path
import importlib.util,unittest,copy
P=Path(__file__).resolve().parent;s=importlib.util.spec_from_file_location('saved',P/'verify_saved.py');V=importlib.util.module_from_spec(s);s.loader.exec_module(V)
class InteriorEvaluationBoundaries(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.d,cls.obs,cls.plan,cls.old,cls.contrast=V.data()
 def test_old_index_is_not_the_same_station(self):
  d=copy.deepcopy(self.d);d['grid']['selected_j_i_zero_based']=[96,36]
  with self.assertRaises(ValueError):V.A.evaluate(d,self.obs,self.plan,self.old)
 def test_original_grid_guard_is_preserved(self):
  with self.assertRaises(ValueError):V.A.S.match_grid(self.d['grid'])
 def test_instantaneous_SW_is_not_a_scored_mean(self):
  d=copy.deepcopy(self.d);d['model']['SWDOWN_instantaneous_W_m2_not_scored']=[12345.]*25
  self.assertEqual(V.A.score(d['model'],d['grid'],self.obs)['statistics'],V.A.score(self.d['model'],self.d['grid'],self.obs)['statistics'])
 def test_shifted_UTC_endpoint_is_refused(self):
  d=copy.deepcopy(self.d);d['model']['times_utc'][17]='2016-10-06_17:01:00'
  with self.assertRaises(ValueError):V.A.evaluate(d,self.obs,self.plan,self.old)
 def test_surface_flux_must_replay_the_applied_accumulator(self):
  d=copy.deepcopy(self.d);d['surface']['values']['SWDNB'][1]+=1.
  with self.assertRaises(ValueError):V.A.evaluate(d,self.obs,self.plan,self.old)
 def test_no_observation_QC_fill(self):
  obs=list(self.obs);lines=obs[0].decode().splitlines()
  for n,line in enumerate(lines[2:],2):
   x=line.split()
   if int(x[4])==16 and int(x[5])==1:x[11]='1';lines[n]=' '.join(x);break
  obs[0]=('\n'.join(lines)+'\n').encode()
  with self.assertRaises(ValueError):V.A.evaluate(self.d,obs,self.plan,self.old)
 def test_posthoc_physical_tolerance_is_refused(self):
  p=copy.deepcopy(self.plan);p['physical_tolerance_W_m2']=999.
  with self.assertRaises(ValueError):V.A.evaluate(self.d,self.obs,p,self.old)
if __name__=='__main__':unittest.main()
