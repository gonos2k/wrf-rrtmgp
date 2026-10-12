import copy,importlib.util,json,math,tempfile,unittest
from pathlib import Path

P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('saved_ice',P/'verify_saved.py');v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
s=importlib.util.spec_from_file_location('ice_run',P/'run.py');runner=importlib.util.module_from_spec(s);s.loader.exec_module(runner)


class SensitivityBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        v.restore(P,cls.root)
        case=cls.root/'on-i1-j1-sw-s0'
        cls.Z=v.a.records(case/'Z/sw.result');cls.B=v.a.records(case/'B/sw.result')

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_actual_saved_sensitivity(self):
        r=v.verify();self.assertEqual(r['status'],'PASS_SCOPED_OMITTED_ICE_SENSITIVITY');self.assertFalse(r['production_accepted'])
        self.assertEqual(len(r['groups']),152)

    def test_reject_changed_existing_mask(self):
        b=copy.deepcopy(self.B);b['MASK']['values'][0]=1-b['MASK']['values'][0]
        with self.assertRaisesRegex(ValueError,'MASK'):v.a.check_unchanged(self.Z,b,'sw')

    def test_reject_double_delta_scaling(self):
        k=52;nl=60
        raw=self.B['ICE_EXTRA_TAU_RAW']['values'][k];tau=self.B['ICE_EXTRA_TAU']['values'][k]
        sr=self.B['ICE_EXTRA_SSA_RAW']['values'][k];gr=self.B['ICE_EXTRA_G_RAW']['values'][k]
        ss=self.B['ICE_EXTRA_SSA']['values'][k];gg=self.B['ICE_EXTRA_G']['values'][k]
        self.assertGreater(raw,0.)
        with self.assertRaisesRegex(ValueError,'scaling'):v.a.check_scaling(raw,tau*(1-ss*gg*gg),sr,gr,ss,gg,'sw')

    def test_seed_wrap_preserves_baseline_and_prevents_observed_overflow(self):
        for original in (679102814,2000000000,2147483647):
            self.assertEqual(runner.normalize_seed(original,0),original)
            value=runner.normalize_seed(original,966003740)
            self.assertTrue(1<=value<=2147483647)

    def test_reject_false_physical_approval(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);m=json.loads((P/'manifest.json').read_text());m['production_accepted']=True
            (p/'manifest.json').write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError,'physical approval'):v.verify(p)

if __name__=='__main__':unittest.main()
