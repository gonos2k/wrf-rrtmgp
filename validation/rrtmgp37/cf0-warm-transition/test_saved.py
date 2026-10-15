"""Direct transition/optics evidence counterexamples, without new physical gates."""
import gzip,importlib.util,unittest
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v=load(B/'verify_saved.py','verify');a=load(B/'analyze_columns.py','columns');t=load(ROOT/'WRF/test/rrtmgp/test_udm_cf0_transition.py','transition')
class TransitionEvidence(unittest.TestCase):
 def test_scope_and_actual_replay(self):self.assertFalse(v.verify()['production_accepted'])
 def test_artificial_CF0_water_source_rejected(self):
  import json
  r=json.loads((B/'saved/module/receipt.json').read_text());d={}
  for n,p in enumerate(r['processes'],1):
   if p['kind'].startswith('UDM_') and '/O0/' in p['argv'][0]:d[p['kind']]=t.parse(v.read(f'module/command-{n:02d}.stdout').decode())
  d['UDM_observed_on'][0]['CF_AFTER',1,1,1,1][1]=1.e-4
  with self.assertRaisesRegex(ValueError,'introduced water/number/temperature source'):t.analyze(d['UDM_observed_on'],d['UDM_observed_off'])
 def test_missing_uniform_optics_rejected(self):
  def altered(name):
   data=v.read(name)
   if name=='columns/lw-native/lw.result':data=data.replace(b'UNIFORM_CF0_TAU',b'LOST_UNIFORM_TAU')
   return data
  with self.assertRaises(KeyError):a.analyze(altered)
if __name__=='__main__':unittest.main(verbosity=2)
