"""Scientific boundary controls for the retained actual radiation call."""
import copy
import json
import importlib.util
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('occurrence_verify',Path(__file__).with_name('verify_saved.py'))
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PACKAGE,analyze_capture,read_capture,verify=(module.PACKAGE,module.analyze_capture,module.read_capture,module.verify)


class RadiationOccurrenceBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capture=read_capture(PACKAGE/'saved','on-i1-j1','lw')
        cls.packet=struct.unpack('<2360f',(PACKAGE/'saved/off/history_60s.bin').read_bytes())

    def run_capture(self,capture):
        return analyze_capture(capture,self.packet,1,1,'lw')

    def test_saved_actual_call_and_post_capture_files(self):
        result=verify()
        self.assertEqual(result['status'],'PASS_SCOPED')
        self.assertEqual(result['phase_summary']['LW']['IWP']['cf0_positive_cells'],12)
        self.assertFalse(result['production_accepted'])

    def test_history_cf_is_not_substituted_for_consumed_cf(self):
        result=self.run_capture(self.capture)
        self.assertEqual(result['history_CF_differs_from_radiation_CF_cells'],31)
        altered=copy.deepcopy(self.capture)
        hist=[self.packet[9*236+k*4] for k in range(59)]
        altered['raw'][1]['CF']['values']=hist
        altered['raw'][1]['RAD_CF_SOURCE']['values']=hist
        altered['input'][1]['CF']['values'][:59]=hist
        with self.assertRaisesRegex(ValueError,'occurrence partition'):
            self.run_capture(altered)

    def test_reject_wrong_source_time(self):
        altered=copy.deepcopy(self.capture)
        altered['raw'][1]['SOURCE_TIME_SECONDS']['values']=[70.]
        with self.assertRaisesRegex(ValueError,'SOURCE_TIME_SECONDS'):
            self.run_capture(altered)

    def test_reject_wrong_column(self):
        altered=copy.deepcopy(self.capture)
        altered['raw'][0][1]=2
        with self.assertRaisesRegex(ValueError,'column'):
            self.run_capture(altered)

    def test_reject_broken_backend_path(self):
        altered=copy.deepcopy(self.capture)
        altered['input'][1]['IWP']['values'][51]=0.1
        with self.assertRaisesRegex(ValueError,'backend path mapping'):
            self.run_capture(altered)

    def test_reject_nonzero_omitted_layer_optics(self):
        altered=copy.deepcopy(self.capture)
        altered['result'][1]['CLOUD_TAU']['values'][51]=0.1
        with self.assertRaisesRegex(ValueError,'nonzero hydrometeor'):
            self.run_capture(altered)

    def test_reject_false_physical_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            package=Path(directory)/'package'
            shutil.copytree(PACKAGE,package)
            m=json.loads((package/'manifest.json').read_text())
            m['production_accepted']=True
            (package/'manifest.json').write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError,'physical approval'):
                verify(package)

if __name__=='__main__':
    unittest.main()
