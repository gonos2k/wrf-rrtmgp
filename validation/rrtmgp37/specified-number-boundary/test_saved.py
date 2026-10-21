#!/usr/bin/env python3
"""Semantic counterexamples against the saved boundary evidence (no model runs)."""
from pathlib import Path
import importlib.util
import json
import unittest

P = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('specified_verifier', P / 'verify_saved.py')
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)


class BoundaryEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = V.data()
        cls.plan = json.loads((P / 'plan.json').read_text())

    def reject_json(self, name, change, message):
        data = dict(self.saved)
        obj = json.loads(data[name])
        change(obj)
        data[name] = json.dumps(obj).encode()
        with self.assertRaisesRegex(ValueError, message):
            V.A.analyze(data.__getitem__, self.plan)

    def test_constant_volume_does_not_mean_zero_coupled_tendency(self):
        self.reject_json('manufactured.json',
                         lambda x: x['fields'].__setitem__('QNCLOUD_BTXS', [0., 0.]),
                         'stored coupled endpoint tendencies')

    def test_wire_values_include_native_mass_factor(self):
        self.reject_json('manufactured.json',
                         lambda x: x['fields'].__setitem__('QNCLOUD_BXS', [1.e8, 1.25e8]),
                         'stored native mass-number values')

    def test_zero_file_ccn_cannot_erase_inflow_reservoir(self):
        data = dict(self.saved)
        rows = data['kernel/good/kernel.txt'].decode().splitlines()
        rows[0] = '0 50000000 62500000 50000000 70000000'
        data['kernel/good/kernel.txt'] = ('\n'.join(rows) + '\n').encode()
        with self.assertRaisesRegex(ValueError, 'dry CCN inflow/outflow'):
            V.A.analyze(data.__getitem__, self.plan)

    def test_stale_first_boundary_record_is_rejected(self):
        def stale(x):
            source = json.loads(self.saved['selected.json'])['south_MU_source_records']
            row = x['boundary_records'][-1]
            row['south_MU'] = [V.A.f32(a + V.A.f32(row['elapsed_s'] * b))
                               for a, b in zip(source['values'][0], source['tendencies'][0])]
        self.reject_json('analysis.json', stale, 'actual second boundary record not applied')

    def test_recorded_restart_failure_cannot_be_promoted(self):
        self.reject_json('analysis.json',
                         lambda x: x.__setitem__('predeclared_full_restart_bitwise_criterion_passed', True),
                         'full restart criterion falsely promoted')

    def test_checkpoint_must_keep_boundary_contract(self):
        self.reject_json('analysis.json',
                         lambda x: x['checkpoint'].__setitem__('UDM_SPECIFIED_NUMBER_CONTRACT', 0),
                         'checkpoint policy contract lost')


if __name__ == '__main__':
    unittest.main()
