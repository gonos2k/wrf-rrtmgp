"""Two direct recorded-melting counterexamples and the scoped replay."""
import copy,importlib.util,json,unittest
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v=load(B/'verify_saved.py','v');melt=load(ROOT/'WRF/test/rrtmgp/test_udm_ice_melt_number.py','melt')
class FixEvidence(unittest.TestCase):
 def test_scoped_replay(self):self.assertFalse(v.verify()['production_accepted'])
 def test_cleared_ice_number_rejected(self):
  r=json.loads((B/'saved/module/receipt.json').read_text());d=v.datasets(r,'O0');key=('MELT_POST',1,1,1,1);d['observed',1]['observations'][key][10]=1000.
  with self.assertRaisesRegex(ValueError,'incoming ice dependence'):melt.analyze(d)
 def test_missing_melt_cell_rejected(self):
  r=json.loads((B/'saved/module/receipt.json').read_text());d=v.datasets(r,'O0');del d['observed',1]['observations']['MELT_POST',1,1,1,1]
  with self.assertRaisesRegex(ValueError,'actual melt branch'):melt.analyze(d)
if __name__=='__main__':unittest.main(verbosity=2)
