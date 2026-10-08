"""Corruption tests for roster identity and scoped conclusions."""
import copy, importlib.util, unittest, struct
from pathlib import Path
BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('roster_saved',BASE/'verify_saved.py')
saved = importlib.util.module_from_spec(spec); spec.loader.exec_module(saved)

class Corruption(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.args = saved.load()
    def reject(self, mutate):
        args = list(copy.deepcopy(self.args)); mutate(args)
        with self.assertRaises(ValueError): saved.core.verify(*args)
    def test_missing_roster_member(self):
        def mutate(a):
            raw=bytearray(a[3]);n=struct.unpack_from('<I',raw,8)[0]
            struct.pack_into('<I',raw,8,n-1);del raw[12:48];a[3]=bytes(raw)
        self.reject(mutate)
    def test_same_count_replacement(self):
        def mutate(a):
            raw=bytearray(a[3]);raw[20]^=1;a[3]=bytes(raw)
        self.reject(mutate)
    def test_strength_default_claim(self):
        self.reject(lambda a:a[1]['LNFL_strength_rejection']['CO2'].update(strength_rejection=1.873e-29))
    def test_bin_omission(self):
        self.reject(lambda a:a[0]['source_bins25cm1'].pop('600'))
    def test_wrong_selected_record(self):
        self.reject(lambda a:a[0]['TAPE3']['selected'].update(slot_1based=125))
    def test_physical_acceptance_promotion(self):
        self.reject(lambda a:a[0].update(original_mixing_physical_partner_completeness_established=True))

if __name__=='__main__': unittest.main()
