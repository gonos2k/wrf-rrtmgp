#!/usr/bin/env python3
"""Saved-only startup optics and OFF/ON contract controls; no WRF launches.

Optionally validate an existing case with --saved-case and its --execution.
The manufactured controls test one lost band, wrong LW magnitude and corrupted
SW absorption independently of the native snow-radius diagnosis fixture.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import test_udm_startup_snow_scm as startup


def manufactured(phase: str, real_bits: int = 32) -> dict:
    records = {"SWP": np.array([[10.]]), "RWP": np.array([[0.]]),
               "RES": np.array([[100.]])}
    if phase == "LW":
        # 1.5*1.05756*10/100, identical in every band.
        records["RESULT_PRECIP_TAU"] = np.full((1, 1, 16), .158634)
    else:
        # Build an independent delta-scaled fixture from pre-delta optical
        # moments, with the module's cap retained in conservative bands.
        t0 = 10. * 1.09087 * 1.5 / (1.0315 * 100.)
        kind = np.float32 if real_bits == 32 else np.float64
        absorption = np.array([float(kind(.460))] * 8 +
                              [float(kind(1.62e-5)) * 1.0315 * 100.] * 2 + [1.e-6] * 4)
        omega = 1. - absorption
        g = np.array([.970] * 10 + [.700] * 4)
        transmitted_fraction = 1. - omega * g**2
        records["RESULT_PRECIP_TAU"] = (t0 * transmitted_fraction)[None, None, :]
        records["RESULT_PRECIP_SSA"] = (omega * (1. - g**2) / transmitted_fraction)[None, None, :]
    return records


class OpticsControls(unittest.TestCase):
    def test_analytic_LW_and_absorption_SW(self):
        for phase, bands in (("LW", 16), ("SW", 14)):
            self.assertEqual(startup.validate_precipitation_optics(phase, manufactured(phase), 0)["checked_bands"], bands)

    def test_default_REAL64_literals(self):
        startup.validate_precipitation_optics("SW", manufactured("SW", 64), 0, 64)

    def test_wrong_default_literal_kind_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "absorption disagrees"):
            startup.validate_precipitation_optics("SW", manufactured("SW", 64), 0, 32)

    def test_every_band_required(self):
        for phase in ("LW", "SW"):
            records = manufactured(phase)
            records["RESULT_PRECIP_TAU"][0, 0, -1] = 0.
            with self.assertRaisesRegex(RuntimeError, "every fixture-layer"):
                startup.validate_precipitation_optics(phase, records, 0)

    def test_one_LW_band_wrong(self):
        records = manufactured("LW")
        records["RESULT_PRECIP_TAU"][0, 0, 7] *= 1.01
        with self.assertRaisesRegex(RuntimeError, "independent analytic"):
            startup.validate_precipitation_optics("LW", records, 0)

    def test_all_LW_positive_but_wrong(self):
        records = manufactured("LW")
        records["RESULT_PRECIP_TAU"] *= 2.
        with self.assertRaisesRegex(RuntimeError, "independent analytic"):
            startup.validate_precipitation_optics("LW", records, 0)

    def test_SW_SSA_absorption_corruption(self):
        records = manufactured("SW")
        records["RESULT_PRECIP_SSA"][0, 0, 2] += .01
        with self.assertRaisesRegex(RuntimeError, "absorption disagrees"):
            startup.validate_precipitation_optics("SW", records, 0)

    def test_SW_extinction_absorption_corruption(self):
        records = manufactured("SW")
        records["RESULT_PRECIP_TAU"][0, 0, 8] *= 1.1
        with self.assertRaisesRegex(RuntimeError, "absorption disagrees"):
            startup.validate_precipitation_optics("SW", records, 0)

    def test_conservative_band_cap_required(self):
        records = manufactured("SW")
        records["RESULT_PRECIP_SSA"][0, 0, -1] = 1.
        with self.assertRaisesRegex(RuntimeError, "absorption disagrees"):
            startup.validate_precipitation_optics("SW", records, 0)

    def test_missing_SSA(self):
        records = manufactured("SW")
        del records["RESULT_PRECIP_SSA"]
        with self.assertRaisesRegex(RuntimeError, "missing or invalid PRECIP_SSA"):
            startup.validate_precipitation_optics("SW", records, 0)

    def test_missing_band_shape(self):
        records = manufactured("LW")
        records["RESULT_PRECIP_TAU"] = records["RESULT_PRECIP_TAU"][:, :, :-1]
        with self.assertRaisesRegex(RuntimeError, "shape/values"):
            startup.validate_precipitation_optics("LW", records, 0)

    def test_nonfinite_tau(self):
        records = manufactured("SW")
        records["RESULT_PRECIP_TAU"][0, 0, 0] = np.nan
        with self.assertRaisesRegex(RuntimeError, "shape/values"):
            startup.validate_precipitation_optics("SW", records, 0)

    def test_nonfinite_path(self):
        records = manufactured("SW")
        records["SWP"][0, 0] = np.inf
        with self.assertRaisesRegex(RuntimeError, "non-finite snow optics inputs"):
            startup.validate_precipitation_optics("SW", records, 0)


class CapturePairControls(unittest.TestCase):
    def records(self, root: Path):
        files = [root / "off.nc", root / "on.nc"]
        for f in files:
            f.write_bytes(b"manufactured identical full history bytes")
        a, b = [{"radiation_option": 37, "capture_enabled": flag,
                 "wrfinput_sha256": "same-manufactured-seed", "history_path": str(f),
                 "namelist_sha256": "same-manufactured-namelist",
                 "process": {"executable_sha256": "same-manufactured-executable"},
                 "history_sha256": startup.sha256(f)} for f, flag in zip(files, (False, True))]
        return a, b

    def test_identical_pair(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = self.records(Path(d))
            with patch.object(startup, "_read_history_arrays", return_value={"field": np.array([1., 2.])}):
                result = startup.compare_capture_pair(a, b)
            self.assertTrue(result["complete_history_bytes_identical"])

    def test_changed_file_rejected_even_when_common_arrays_identical(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = self.records(Path(d))
            Path(b["history_path"]).write_bytes(b"different metadata or extra variable")
            b["history_sha256"] = startup.sha256(Path(b["history_path"]))
            with self.assertRaisesRegex(RuntimeError, "complete NetCDF history bytes differ"):
                startup.compare_capture_pair(a, b)

    def test_changed_after_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = self.records(Path(d))
            Path(b["history_path"]).write_bytes(b"changed after receipt")
            with self.assertRaisesRegex(RuntimeError, "changed after its forecast receipt"):
                startup.compare_capture_pair(a, b)

    def test_different_seed_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = self.records(Path(d))
            b["wrfinput_sha256"] = "another-seed"
            with self.assertRaisesRegex(RuntimeError, "same-input candidate37"):
                startup.compare_capture_pair(a, b)

    def test_different_executable_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = self.records(Path(d))
            b["process"]["executable_sha256"] = "another-executable"
            with self.assertRaisesRegex(RuntimeError, "same-input candidate37"):
                startup.compare_capture_pair(a, b)

    def test_different_namelist_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = self.records(Path(d))
            b["namelist_sha256"] = "another-namelist"
            with self.assertRaisesRegex(RuntimeError, "same-input candidate37"):
                startup.compare_capture_pair(a, b)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saved-case", type=Path)
    parser.add_argument("--execution", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if bool(args.saved_case) != bool(args.execution):
        parser.error("--saved-case and --execution must be supplied together")
    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {"status": "PASS_SAVED_ONLY_STARTUP_OPTICS_CONTROLS" if result.wasSuccessful() else "FAIL",
               "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
               "model_invocations": 0, "compiler_invocations": 0}
    if not result.wasSuccessful():
        if args.output:
            startup.atomic_json(args.output, receipt)
        return 1
    if args.saved_case:
        saved = json.loads(args.execution.read_text())
        receipt["saved_case"] = str(args.saved_case.resolve())
        receipt["saved_execution_sha256"] = startup.sha256(args.execution)
        receipt["retained_capture_checks"] = startup.validate_startup_capture(args.saved_case, saved["seed"])
    if args.output:
        startup.atomic_json(args.output, receipt)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
