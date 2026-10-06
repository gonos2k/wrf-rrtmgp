#!/usr/bin/env python3
"""Exercise shape, precision and provenance failures in the observation reader."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('read_export', Path(__file__).with_name('read_export.py'))
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

VALID = '''RRTMG4_SELECTED_COLUMN_EXPORT_V1
phase SW
domain 1
step 2161
source_seconds 1.2960000000000000E+005
i 24
j 55
layout fortran_order_first_index_fastest
stage INPUT
PLAY hPa 2
9.0000000000000000E+002
8.0000000000000000E+002
stage CLOUD
TAU 1 2 2
1.0000000000000000E+000
2.0000000000000000E+000
3.0000000000000000E+000
4.0000000000000000E+000
stage GAS
TAUGAS 1 2 2
0 0 0 0
stage RESULT
HEAT K_day 2
-4.9764225259423200E+000
5.2551133483648230E+000
'''


class ExportReaderTest(unittest.TestCase):
    def read(self, content):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'observation.txt'
            p.write_text(content, encoding='ascii')
            return module.read_export(p, expected_phase='SW')

    def test_valid_matrix_order_and_negative_heating(self):
        out = self.read(VALID)
        tau = out['fields']['CLOUD', 'TAU']
        self.assertEqual(tau.shape, (2, 2))
        self.assertEqual(tau.at(0, 1), 3)
        self.assertEqual(tau.at(1, 0), 2)
        self.assertEqual(out['fields']['RESULT', 'HEAT'].values,
                         (-4.97642252594232, 5.255113348364823))

    def test_wrong_clock_rejected(self):
        with self.assertRaisesRegex(ValueError, 'context source_seconds'):
            self.read(VALID.replace('1.2960000000000000E+005', '1.3020000000000000E+005'))

    def test_driver_lowercase_phase(self):
        self.assertEqual(self.read(VALID.replace('phase SW', 'phase sw'))['metadata']['phase'], 'SW')

    def test_wrong_phase_rejected(self):
        with self.assertRaisesRegex(ValueError, 'phase does not match'):
            self.read(VALID.replace('phase SW', 'phase LW'))

    def test_nonfinite_optics_rejected(self):
        with self.assertRaisesRegex(ValueError, 'nonfinite value'):
            self.read(VALID.replace('3.0000000000000000E+000', 'NaN'))

    def test_excess_shape_data_rejected(self):
        with self.assertRaisesRegex(ValueError, 'excess values'):
            self.read(VALID.replace('1.0000000000000000E+000', '1 2 3 4 5'))

    def test_duplicate_field_rejected(self):
        repeated = 'TAU 1 1\n0\n'
        with self.assertRaisesRegex(ValueError, 'duplicate field'):
            self.read(VALID.replace('stage GAS', repeated + 'stage GAS'))

    def test_truncated_field_rejected(self):
        with self.assertRaisesRegex(ValueError, 'truncated field'):
            self.read(VALID.rsplit('\n', 2)[0] + '\n')

    def test_missing_result_rejected(self):
        with self.assertRaisesRegex(ValueError, 'required stages'):
            self.read(VALID.split('stage RESULT')[0])

    def test_missing_gas_rejected(self):
        with self.assertRaisesRegex(ValueError, 'required stages'):
            self.read(VALID.replace('stage GAS\nTAUGAS 1 2 2\n0 0 0 0\n', ''))

    def test_reordered_stages_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unexpected stage order'):
            self.read(VALID.replace('stage CLOUD', 'stage TEMP').replace(
                'stage GAS', 'stage CLOUD').replace('stage TEMP', 'stage GAS'))

    def test_unsupported_layout_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unsupported array layout'):
            self.read(VALID.replace('layout fortran_order_first_index_fastest', 'layout row_major'))


if __name__ == '__main__':
    unittest.main()
