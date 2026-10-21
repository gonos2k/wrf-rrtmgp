#!/usr/bin/env python3
"""Actual NetCDF nonzero boundary records and independent exact-arithmetic checks."""
from pathlib import Path
from fractions import Fraction as F
import importlib.util,unittest,tempfile,json
import numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2]
s=importlib.util.spec_from_file_location('conv',R/'WRF/test/rrtmgp/convert_udm_specified.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
TIMES=['2016-10-06_00:00:00','2016-10-06_01:00:00','2016-10-06_02:00:00']
def manufactured(path):
 with Dataset(path,'w') as d:
  for n,size in [('Time',2),('DateStrLen',19),('width',1),('k',1),('j',1)]:d.createDimension(n,size)
  d.UDM_NUMBER_POLICY=np.int32(1);d.UDM_SPECIFIED_NUMBER_CONTRACT=np.int32(1)
  d.createVariable('Times','S1',('Time','DateStrLen'))[:]=np.asarray([list(t) for t in TIMES[:-1]],dtype='S1')
  for n in ['QNCLOUD_BXS','QNCLOUD_BTXS','QCLOUD_BXS','QCLOUD_BTXS']:
   d.createVariable(n,'f4',('Time','width','k','j'))[:]=0 if n.startswith('QN') else (1. if n=='QCLOUD_BXS' else 0.)
 n=np.full((3,1,1,1),1.e8);rho=np.asarray([1.,.8,.7]).reshape(3,1,1,1);a=np.asarray([1000.,1200.,1400.]).reshape(3,1,1,1)
 return c.write_volume_series(path,'QNCLOUD','XS',n,rho,a,TIMES)
class Producer(unittest.TestCase):
 def test_nonzero_native_file_values_and_full_mass_tendencies(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'bdy.nc';r=manufactured(p)
   with Dataset(p) as d:
    self.assertEqual(d['QNCLOUD_BXS'].shape,(2,1,1,1));self.assertEqual(float(d['QNCLOUD_BXS'][0,0,0,0]),float(np.float32(1.e11)))
    expected=(F(1200)*F(10**8)/F(4,5)-F(1000)*F(10**8))/F(3600)
    stored_expected=np.float32(np.float32(d['QNCLOUD_BXS'][1,0,0,0]-d['QNCLOUD_BXS'][0,0,0,0])/np.float32(3600.))
    self.assertEqual(float(d['QNCLOUD_BTXS'][0,0,0,0]),float(stored_expected))
    self.assertLess(abs(float(stored_expected)-float(expected)),4.)
    self.assertGreater(float(d['QNCLOUD_BTXS'][0,0,0,0]),0.)
   # This is not the result of dividing the zero volume-number tendency by rho.
   self.assertEqual((F(10**8)/F(4,5)-F(10**8))/3600,F(62500,9))
 def test_nonfinite_or_nonpositive_density_rejected(self):
  for rho in [0.,-1.,np.nan]:
   with self.assertRaises(ValueError):c.coupled_volume_endpoints(1e8,1e8,1.,rho,1000.,1200.,3600.)
 def test_negative_number_or_mass_rejected(self):
  with self.assertRaises(ValueError):c.coupled_volume_endpoints(-1,1,1,1,1,1,1)
  with self.assertRaises(ValueError):c.coupled_volume_endpoints(1,1,1,1,1,0,1)
 def test_time_record_mismatch_rejected_before_write(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'bdy.nc';manufactured(p)
   with self.assertRaisesRegex(ValueError,'times differ'):c.write_volume_series(p,'QNCLOUD','XS',np.ones((3,1,1,1)),np.ones((3,1,1,1)),np.ones((3,1,1,1)),['2016-10-07_00:00:00','2016-10-07_01:00:00','2016-10-07_02:00:00'])
 def test_nonzero_number_on_zero_mass_rejected(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'bdy.nc';manufactured(p)
   with Dataset(p,'r+') as d:d['QCLOUD_BXS'][:]=0;d['QCLOUD_BTXS'][:]=0
   with self.assertRaisesRegex(ValueError,'matching condensate'):c.write_volume_series(p,'QNCLOUD','XS',np.ones((3,1,1,1)),np.ones((3,1,1,1)),np.ones((3,1,1,1)),TIMES)
if __name__=='__main__':unittest.main()
