"""Direct candidate counterexamples; no extra physical gates."""
import importlib.util,json,unittest
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v=load(B/'verify_saved.py','v');test=load(ROOT/'WRF/test/rrtmgp/test_udm_partial_population.py','t')
class PopulationEvidence(unittest.TestCase):
 def data(self):return v.datasets(json.loads((B/'saved/receipt.json').read_text()),'O0')
 def test_saved_scope(self):self.assertFalse(v.verify()['production_accepted'])
 def test_missing_CF_weight_rejected(self):
  d=self.data();key=('WARM_RESTORED',2,1,1,1);d['warm','candidate','on']['obs'][key][19]*=2.
  with self.assertRaisesRegex(ValueError,'grid rate restore'):test.analyze(d)
 def test_final_host_number_wrong_population_rejected(self):
  d=self.data();d['warm','candidate','on']['outputs'][2][36]=d['warm','candidate','on']['outputs'][1][36]
  with self.assertRaisesRegex(ValueError,'final QC/QR/host'):v.final_joins(d)
if __name__=='__main__':unittest.main(verbosity=2)
