#!/usr/bin/env python3
"""Check rounding semantics; no model or scientific fixture is generated."""
from fractions import Fraction
import importlib.util
import math
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location('precision', Path(__file__).with_name('analyze.py'))
precision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(precision)


class RoundingSemantics(unittest.TestCase):
    def test_binade_boundary_is_asymmetric(self):
        lo, hi, included = precision.positive_rounding_hull(1.)
        self.assertEqual(lo, Fraction(1)-Fraction(1,2**25))
        self.assertEqual(hi, Fraction(1)+Fraction(1,2**24))
        self.assertTrue(included)

    def test_odd_significand_excludes_midpoint_ties(self):
        odd = struct.unpack('<f', struct.pack('<I', 0x3f800001))[0]
        lo, hi, included = precision.positive_rounding_hull(odd)
        self.assertFalse(included)
        self.assertNotEqual(precision.f32(float(lo)), precision.f32(odd))
        self.assertNotEqual(precision.f32(float(hi)), precision.f32(odd))

    def test_mixed_fail_does_not_determine_publisher_prewrite_fail(self):
        x, r = 415.5838165100244, 415.5838317871094
        y = struct.unpack('<f', precision.f32(x))[0]
        result = precision.metrics(x,y,r)
        self.assertTrue(result['stored_strict_fail'])
        self.assertTrue(result['mixed_strict_fail'])
        self.assertTrue(result['conditional_error_bounds_straddle_tolerance'])
        self.assertEqual(result['publisher_prewrite_strict_decision'], 'UNKNOWN_PUBLISHER_PREWRITE_UNAVAILABLE')
        witnesses = result['hypothetical_per_cell_reference_prewrite_witnesses']
        near, far = witnesses['under_tolerance']['value'], witnesses['over_tolerance']['value']
        self.assertEqual(precision.f32(near), precision.f32(r))
        self.assertEqual(precision.f32(far), precision.f32(r))
        self.assertLess(abs(x-near), 1e-5)
        self.assertGreater(abs(x-far), 1e-5)
        self.assertFalse(witnesses['actual_publisher_values'])
        self.assertFalse(witnesses['jointly_realizable_publisher_run_established'])

    def test_cast_join_and_finite_reference_are_required(self):
        for args in [(1.,2.,1.),(math.nan,1.,1.),(1.,1.,1.00000001)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                precision.metrics(*args)


if __name__ == '__main__':
    unittest.main()
