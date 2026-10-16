"""Actual NetCDF producer check; separate from stdlib-only saved replay CI."""
import gzip,importlib.util,tempfile,unittest
from pathlib import Path
import netCDF4,numpy as np
B=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('producer',B/'make_input.py');p=importlib.util.module_from_spec(s);s.loader.exec_module(p)
class Producer(unittest.TestCase):
 def test_producer_matches_executed_physical_input(self):
  with tempfile.TemporaryDirectory() as td:
   d=Path(td);seed=d/'seed.nc';seed.write_bytes(gzip.decompress((B/'saved/inputs/ideal-seed.nc.gz').read_bytes()));expected=d/'expected.nc';expected.write_bytes(gzip.decompress((B/'saved/inputs/final.nc.gz').read_bytes()));out=d/'new.nc';p.generate(seed,out,d/'receipt.json')
   with netCDF4.Dataset(out) as a,netCDF4.Dataset(expected) as b:
    self.assertEqual(set(a.variables),set(b.variables))
    for n in a.variables:self.assertEqual(np.asarray(a[n][:]).tobytes(),np.asarray(b[n][:]).tobytes(),n)
    self.assertEqual(a.UDM_NUMBER_POLICY,1);self.assertEqual(a.UDM_POPULATION_POLICY,2)
 def test_inconsistent_seed_cannot_be_repaired_by_number_retagging(self):
  with tempfile.TemporaryDirectory() as td:
   d=Path(td);seed=d/'bad.nc';seed.write_bytes(gzip.decompress((B/'saved/inputs/ideal-seed.nc.gz').read_bytes()))
   with netCDF4.Dataset(seed,'r+') as a:a['ALB'][:]*=1.1
   with self.assertRaisesRegex(ValueError,'geometry'):p.generate(seed,d/'new.nc',d/'r.json')
if __name__=='__main__':unittest.main(verbosity=2)
