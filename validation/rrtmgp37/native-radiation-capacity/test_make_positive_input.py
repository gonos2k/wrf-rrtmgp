"""Local optional NetCDF producer replay; CI scientific replay uses stdlib packets."""
import gzip,hashlib,importlib.util,tempfile,unittest
from pathlib import Path
import netCDF4,numpy as np
B=Path(__file__).resolve().parent;s=importlib.util.spec_from_file_location('producer',B/'make_positive_input.py');p=importlib.util.module_from_spec(s);s.loader.exec_module(p)
class PositiveInput(unittest.TestCase):
 def test_reproducer_matches_actual_all_variable_and_file_bytes(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);seed=d/'seed.nc';seed.write_bytes(gzip.decompress((B/'saved/input/canonical-clear-seed.nc.gz').read_bytes()));expected=gzip.decompress((B/'saved/input/positive.nc.gz').read_bytes());out=d/'new.nc'
   p.generate(seed,out,d/'r.json');self.assertEqual(out.read_bytes(),expected)
   with netCDF4.Dataset(out) as x:
    self.assertGreater(float(np.max(x['QCLOUD'][:])),0)
    rho=1/(np.asarray(x['AL'][0],float)+np.asarray(x['ALB'][0],float));active=np.asarray(x['QCLOUD'][0])>0
    self.assertLess(float(np.max(abs(rho[active]*np.asarray(x['QNCLOUD'][0])[active]/1e8-1))),1e-6)
if __name__=='__main__':unittest.main(verbosity=2)
