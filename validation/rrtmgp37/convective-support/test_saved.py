#!/usr/bin/env python3
"""Counterexamples for support, native counter evaluation, CU timing and duration."""
from pathlib import Path
import copy, importlib.util, json, unittest

P = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('convective_verifier', P / 'verify_saved.py')
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)

class ConvectiveSupport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = V.data()
        cls.prior = json.loads((P.parent / 'real-case-budget/result.json').read_text())
        cls.meta = json.loads(cls.d['rain-spatial.json'])
        # Reuse the actual three-minute records, not six repetitions of the full day.
        cls.prefix = '\n'.join(line for line in cls.d['host/real-budget.txt'].decode().splitlines()
                               if (line.split()[1] == 'geometry' or
                                   int(float(line.split()[0])) in [21540, 21600, 21660])) + '\n'

    def mutated(self, predicate, mutate):
        rows = []
        for line in self.prefix.splitlines():
            a = line.split()
            if predicate(a):
                mutate(a)
            rows.append(' '.join(a))
        return '\n'.join(rows) + '\n'

    def test_independent_interior_average_is_not_whole_area_contribution(self):
        prior = copy.deepcopy(self.prior)
        prior['area_m2'] *= (88 * 97) / (90 * 99)
        with self.assertRaisesRegex(ValueError, 'whole physical area'):
            V.S.analyze(self.d['rain-spatial.bin'], self.meta, prior)

    def test_separate_RAINC_delta_cannot_replace_native_counter_sum(self):
        prior = copy.deepcopy(self.prior)
        spatial = V.S.analyze(self.d['rain-spatial.bin'], self.meta, prior)
        for old, row in zip(prior['water_steps'], spatial['steps']):
            old['P_before_microphysics'] = row['precipitation']['RAINC']['all_domain_mean_kg_m2']
        with self.assertRaisesRegex(ValueError, 'native sum'):
            V.S.analyze(self.d['rain-spatial.bin'], self.meta, prior)

    def test_post_expiry_must_use_the_same_pre_call_cohort(self):
        raw = self.mutated(lambda a: a[1] == 'expiry_after',
                           lambda a: a.__setitem__(5, str(float(a[5]) + 1)))
        with self.assertRaisesRegex(ValueError, 'expiry mask changed'):
            V.A.analyze(raw, {'status': 'SUCCESS'})

    def test_retained_precipitation_must_not_be_reported_as_cleared(self):
        raw = self.mutated(lambda a: a[1] == 'expiry_after', lambda a: a.__setitem__(4, '0'))
        with self.assertRaisesRegex(ValueError, 'changed selected PRATEC'):
            V.A.analyze(raw, {'status': 'SUCCESS'})

    def test_successful_short_prefix_is_not_a_24_hour_evaluation(self):
        result = V.A.analyze(self.prefix, {'status': 'SUCCESS'})
        self.assertFalse(result['target_period_completed'])
        self.assertEqual(result['completed_steps'], 3)
        self.assertEqual(result['status'], 'FIXED_REAL_EVALUATION_STOPPED')

    def test_changed_original_overlap_is_not_noninterference(self):
        history = json.loads(self.d['history.json'])
        history['original_overlap'][0]['all_byte_equal'] = False
        with self.assertRaisesRegex(ValueError, 'changed original trajectory'):
            V.check_history(history, {'target_period_completed': False})

    def test_nighttime_missing_SW_is_not_replaced_by_zero_flux(self):
        result = V.A.analyze(self.prefix, {'status': 'SUCCESS'})
        for step in result['radiation_steps']:
            sw = step['native_flux'][1]
            self.assertFalse(sw['current_radiation_phase_observed'])
            self.assertIsNone(sw['native_convergence'])

if __name__ == '__main__':
    unittest.main()
