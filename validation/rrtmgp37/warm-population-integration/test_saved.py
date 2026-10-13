"""The actual exchange boundary distinguishes a missing footprint weighting."""
import copy,importlib.util,json,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('verified_warm',Path(__file__).with_name('verify_saved.py'))
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
B,ROOT,read,load,exchange,verify=v.B,v.ROOT,v.read,v.load,v.exchange,v.verify
class Saved(unittest.TestCase):
 def test_actual_execution_and_restart(self):self.assertFalse(verify()['production_accepted'])
 def test_unweighted_evaporation_is_rejected(self):
  test=load(ROOT/'WRF/test/rrtmgp/test_udm_population_integration.py','negative_exchange');r=json.loads((B/'saved/module/receipt.json').read_text())
  for n,p in enumerate(r['processes'],1):
   if p['kind']=='UDM_observed_evap_candidate_on' and '/O2/' in p['argv'][0]:
    data=test.parse(read(f'saved/module/command-{n:02d}.stdout.gz').decode())[0];break
  original=exchange(data,test);self.assertGreater(original,0)
  wrong=copy.deepcopy(data)
  for key,v in wrong.items():
   if key[0]=='EXCHANGE' and v[2]<1.:
    _,c,i,k,loop=key;local=wrong['WARM_LOCAL',c,i,k,loop];v[0]=test.f32(local[0]+local[2]);break
  with self.assertRaisesRegex(ValueError,'grid mean'):exchange(wrong,test)
if __name__=='__main__':unittest.main()
