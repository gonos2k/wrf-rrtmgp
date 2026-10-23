"""Reject false state/phase/physical-component attribution; no model runs."""
from pathlib import Path
import importlib.util,unittest,json,copy
P=Path(__file__).resolve().parent;s=importlib.util.spec_from_file_location('sterling_replay',P/'verify_saved.py');V=importlib.util.module_from_spec(s);s.loader.exec_module(V);A=V.A
class AttributionBoundaries(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.data,cls.comparison,cls.obs=V.data()
 def edit(self,tag,j,index,value):
  d=self.data.copy();lines=d['host/sterling-cloud.txt'].decode().splitlines()
  for n,line in enumerate(lines):
   x=line.split();ji=3 if tag in ['input','return'] else 2
   if x[1]==tag and int(float(x[ji]))==j:
    x[index+2]=str(value);lines[n]=' '.join(x);break
  else:raise AssertionError('missing mutation target')
  d['host/sterling-cloud.txt']=('\n'.join(lines)+'\n').encode();return d
 def test_actual_input_layer_cannot_be_omitted(self):
  d=self.data.copy();lines=d['host/sterling-cloud.txt'].splitlines();d['host/sterling-cloud.txt']=b'\n'.join(lines[1:])+b'\n'
  with self.assertRaises(ValueError):A.evaluate(d,self.comparison,self.obs)
 def test_positive_consumed_CF_contradicts_clear_input_claim(self):
  with self.assertRaises(ValueError):A.evaluate(self.edit('input',97,13,1.),self.comparison,self.obs)
 def test_unused_UDM_diagnostic_is_not_consumed_CF(self):
  original=A.evaluate(self.data,self.comparison,self.obs);changed=A.evaluate(self.edit('input',97,15,0.),self.comparison,self.obs)
  self.assertEqual(original['original_site']['model_allsky_held_W_m2'],changed['original_site']['model_allsky_held_W_m2']);self.assertTrue(changed['received_site_cloud_and_CU_paths_all_zero'])
 def test_other_component_cannot_replace_physical_direct(self):
  with self.assertRaises(ValueError):A.evaluate(self.edit('held',95,8,1000.),self.comparison,self.obs)
 def test_held_source_phase_cannot_shift(self):
  with self.assertRaises(ValueError):A.evaluate(self.edit('held',97,2,57000.),self.comparison,self.obs)
 def test_observed_hour_cannot_be_redefined(self):
  obs=list(self.obs);lines=obs[0].decode().splitlines()
  for n,line in enumerate(lines[2:],2):
   x=line.split()
   if int(x[4])==16 and int(x[5])==1:x[12]=str(float(x[12])+60);lines[n]=' '.join(x);break
  obs[0]=('\n'.join(lines)+'\n').encode()
  with self.assertRaises(ValueError):A.evaluate(self.data,self.comparison,obs)
 def test_changed_host_array_cannot_pass_observer_check(self):
  c=json.loads(self.data['history-comparison.json']);next(iter(next(iter(c['inventory'].values())).values()))['right_sha256']='0'*64
  with self.assertRaises(ValueError):V.comparison_check(c)
if __name__=='__main__':unittest.main()
