#!/usr/bin/env python3
"""Local NetCDF producer boundary tests; not a model simulation."""
import unittest,tempfile
from pathlib import Path
from netCDF4 import Dataset,stringtochar
import numpy as np
from zero_number_input import produce,MASS,NUMBER,SUFFIX
class Producer(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.p=Path(self.temp.name)
  for name,bdy in [('initial',False),('boundary',True)]:
   with Dataset(self.p/name,'w') as d:
    d.createDimension('Time',1);d.createDimension('DateStrLen',19);v=d.createVariable('Times','S1',('Time','DateStrLen'));v[:]=np.asarray(list('2016-10-06_00:00:00'),dtype='S1')[None,:]
    for n in MASS+NUMBER:
     for suffix in (SUFFIX if bdy else ('',)):d.createVariable(n+suffix,'f4',('Time',))[:]=0
    d.createVariable('OTHER','f4',('Time',))[:]=3.5
 def run_producer(self):return produce(self.p/'initial',self.p/'boundary',self.p/'out')
 def test_exact_zero_preserves_every_array(self):
  r=self.run_producer();self.assertTrue(r['all_arrays_preserved']);self.assertFalse(r['boundary_runtime_support'])
  with Dataset(self.p/'out/wrfinput_d01') as d:self.assertEqual(d.UDM_NUMBER_POLICY,1);self.assertEqual(float(d['OTHER'][0]),3.5)
 def test_nonzero_mass_rejected_without_output(self):
  with Dataset(self.p/'initial','r+') as d:d['QICE'][:]=1e-9
  with self.assertRaisesRegex(ValueError,'QICE'):self.run_producer()
  self.assertFalse((self.p/'out').exists())
 def test_nonzero_boundary_tendency_rejected(self):
  with Dataset(self.p/'boundary','r+') as d:d['QNCLOUD_BTXS'][:]=1
  with self.assertRaisesRegex(ValueError,'QNCLOUD_BTXS'):self.run_producer()
 def test_nonfinite_number_rejected(self):
  with Dataset(self.p/'initial','r+') as d:d['QNRAIN'][:]=np.nan
  with self.assertRaisesRegex(ValueError,'QNRAIN'):self.run_producer()
if __name__=='__main__':unittest.main()
