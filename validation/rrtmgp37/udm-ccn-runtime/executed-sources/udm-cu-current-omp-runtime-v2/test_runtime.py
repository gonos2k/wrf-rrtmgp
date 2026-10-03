import importlib.util,json,tempfile,unittest
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('cu_omp_runtime',HERE/'runtime.py');r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
class RuntimeControls(unittest.TestCase):
    def test_namelist_exact_changes(self):
        _,stage,_=r.parent();text=(Path(stage['case']['case_path'])/'namelist.input').read_text();new=r.nml(text)
        expected=text
        for before,after in [('= 24,','= 3,'),('end_day                              = 25','end_day                              = 24'),('end_hour                             = 12','end_hour                             = 15'),('restart_interval                    = 720','restart_interval                    = 180')]:
            expected=expected.replace(before,after,1)
        # Preserve every byte outside four value replacements and one tile insertion.
        self.assertEqual(new.replace('\n numtiles = 2,',''),expected)
        with self.assertRaises(ValueError):r.nml(text.replace('run_hours                           = 24','run_hours                           = 2'))
    def test_default_no_stage_and_collision(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'cases';got=r.prepare(out,False)
            self.assertEqual(got['status'],'READY_NOT_STAGED');self.assertFalse(out.exists())
            out.mkdir()
            with self.assertRaises(FileExistsError):r.prepare(out,False)
    def test_default_fill(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'fill.nc'
            with Dataset(p,'w') as d:d.createDimension('n',1);d.createVariable('q','f4',('n',))
            self.assertEqual(r.default_fills(p)['hits'],{'q':1})
    def test_signed_zero_metadata_and_values(self):
        with tempfile.TemporaryDirectory() as t:
            paths=[Path(t)/n for n in ('a.nc','b.nc')]
            for p in paths:
                with Dataset(p,'w') as d:
                    d.createDimension('n',1);d.createVariable('q','f4',('n',))[:]=[0.0];d.setncattr('reference',np.float32(0.0))
            self.assertTrue(r.compare_file(*paths)['passed'])
            with Dataset(paths[1],'a') as d:d['q'][:]=[-0.0]
            self.assertFalse(r.compare_file(*paths)['passed'])
            with Dataset(paths[1],'a') as d:d['q'][:]=[0.0];d.setncattr('reference',np.float32(-0.0))
            self.assertFalse(r.compare_file(*paths)['metadata_equal'])
if __name__=='__main__':unittest.main()
