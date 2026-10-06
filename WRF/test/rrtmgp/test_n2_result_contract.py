#!/usr/bin/env python3
"""Check optional LW N2 result provenance without a compiler or solver."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from compare_column_replay import (INTERFACE_SECTIONS, LAYER_SCALAR_SECTIONS,
                                   REQUIRED_SECTIONS, ReplayFormatError,
                                   compare, read_result)


class N2ResultContract(unittest.TestCase):
    def result(self, phase="LW", n2="0.7808", shape=(1, 1, 1)):
        names = set(REQUIRED_SECTIONS)
        if phase == "SW":
            names.update({"GAS_SSA", "GAS_G", "CLOUD_SSA", "CLOUD_G", "PREPARED_SSA",
                          "PREPARED_G", "TOTAL_SSA", "TOTAL_G", "DIRECT", "DIFFUSE",
                          "DIRECTC", "VISDIR", "VISDIF", "NIRDIR", "NIRDIF"})
        lines = ["RRTMGP_RESULT_V1", f"{phase} 1 1"]
        for name in sorted(names):
            dimensions = (1, 2, 1) if name in INTERFACE_SECTIONS else (1, 1, 1)
            lines.append(name + " " + " ".join(map(str, dimensions)))
            lines.extend("0.0" for _ in range(int(np.prod(dimensions))))
        if n2 is not None:
            lines.append("VMR_N2 " + " ".join(map(str, shape)))
            lines.extend(n2 for _ in range(int(np.prod(shape))))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result"
            path.write_text("\n".join(lines) + "\n", encoding="ascii")
            return read_result(path)

    def test_new_lw_profile(self):
        value = self.result()
        self.assertEqual(value["sections"]["VMR_N2"].shape, (1, 1, 1))
        self.assertTrue(compare(value, value)["passed"])

    def test_historical_lw_and_sw_without_n2(self):
        for phase in ("LW", "SW"):
            self.assertNotIn("VMR_N2", self.result(phase=phase, n2=None)["sections"])

    def test_n2_comparison_is_exact(self):
        actual, expected = self.result(), self.result()
        actual["sections"]["VMR_N2"][0, 0, 0] = np.nextafter(0.7808, 1.0)
        self.assertIn("VMR_N2", compare(actual, expected)["failed_sections"])

    def test_shape_is_layer_scalar(self):
        self.assertIn("VMR_N2", LAYER_SCALAR_SECTIONS)
        with self.assertRaisesRegex(ReplayFormatError, "VMR_N2 must have shape"):
            self.result(shape=(1, 1, 2))

    def test_phase_is_lw(self):
        with self.assertRaisesRegex(ReplayFormatError, "VMR_N2 requires LW"):
            self.result(phase="SW")

    def test_range_and_finiteness(self):
        for value in ("-0.001", "1.001", "NaN", "Inf"):
            with self.subTest(value=value), self.assertRaises(ReplayFormatError):
                self.result(n2=value)
        for value in ("0.0", "1.0"):
            self.result(n2=value)


if __name__ == "__main__":
    unittest.main()
