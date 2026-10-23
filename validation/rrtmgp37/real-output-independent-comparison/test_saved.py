"""Scientific support and QC counterexamples; no model or data downloads."""
from pathlib import Path
import importlib.util,unittest,copy,datetime as dt
P=Path(__file__).resolve().parent;s=importlib.util.spec_from_file_location('actual_independent_saved',P/'verify_saved.py');V=importlib.util.module_from_spec(s);s.loader.exec_module(V);A=V.A
class ComparisonBoundaries(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.args=V.data()
 def test_missing_or_flagged_primary_minute_never_uses_PSP(self):
  obs,_=A.observations(self.args[2]);t=A.START+dt.timedelta(minutes=1)
  missing=copy.deepcopy(obs);del missing[t]
  self.assertIsNone(A.hour(missing,A.START)['primary_W_m2'])
  blobs=list(self.args[2]);lines=blobs[0].decode().splitlines();x=lines[3].split();x[11]='1';lines[3]=' '.join(x);blobs[0]=('\n'.join(lines)+'\n').encode()
  flagged,_=A.observations(blobs);h=A.hour(flagged,A.START)
  self.assertIsNone(h['primary_W_m2']);self.assertIsNotNone(h['secondary_W_m2'])
 def test_midnight_period_end_support(self):
  obs,_=A.observations(self.args[2]);before=A.hour(obs,A.START);obs[A.START]['primary']=1e10
  self.assertEqual(A.hour(obs,A.START),before)
  start=A.END-dt.timedelta(hours=1);last=A.hour(obs,start);obs[A.END]['primary']+=60
  self.assertAlmostEqual(A.hour(obs,start)['primary_W_m2']-last['primary_W_m2'],1.,places=10)
 def test_signed_negative_measurements_are_preserved(self):
  blobs=list(self.args[2]);lines=blobs[0].decode().splitlines();x=lines[3].split();x[10]='-2';x[12]='-3';x[11]=x[13]='0';lines[3]=' '.join(x);blobs[0]=('\n'.join(lines)+'\n').encode();obs,_=A.observations(blobs)
  self.assertEqual(obs[A.START+dt.timedelta(minutes=1)]['primary'],-3.)
 def test_instantaneous_model_field_is_not_hour_mean(self):
  args=copy.deepcopy(self.args);args[0]['SWDOWN_instantaneous_W_m2_not_scored']=[1e8]*25
  self.assertEqual(A.evaluate(*args),A.evaluate(*self.args))
 def test_shifted_time_or_accumulator_reset_is_rejected(self):
  for kind in ['time','reset']:
   args=copy.deepcopy(self.args)
   if kind=='time':args[0]['times_utc'][0]='2016-10-06_01:00:00'
   else:args[0]['ACSWDNB_J_m2'][-1]=-1.
   with self.assertRaises(ValueError):A.evaluate(*args)
 def test_boundary_site_cannot_be_relabelled_as_interior(self):
  args=copy.deepcopy(self.args);args[1]['spec_bdy_width']=0
  with self.assertRaises(ValueError):A.evaluate(*args)
 def test_posthoc_tolerance_cannot_promote_acceptance(self):
  args=copy.deepcopy(self.args);args[3]['physical_acceptance_tolerance_W_m2']=1e6
  with self.assertRaises(ValueError):A.evaluate(*args)
if __name__=='__main__':unittest.main()
