"""Failure controls for the direct, unmerged restart-boundary checker."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

import netCDF4
import numpy as np

SPEC = importlib.util.spec_from_file_location(
    "restart_probe", Path(__file__).with_name("run_restart_determinism.py"))
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)
TIME = "2000-01-01_00:00:00"


def fixture(path):
    with netCDF4.Dataset(path, "w") as ds:
        ds.createDimension("Time", None)
        ds.createDimension("DateStrLen", 19)
        ds.createDimension("x", 2)
        ds.createVariable("Times", "S1", ("Time", "DateStrLen"))[0] = np.frombuffer(TIME.encode(), dtype="S1")
        for name in PROBE.UDM_CF_DIAGNOSTICS:
            dtype = "f4" if name == "UDM_CLDFRA" else "i4"
            ds.createVariable(name, dtype, ("Time", "x"))[0] = [0, 1]


class RestartDiagnostics(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.donor = Path(self.temp.name) / "donor.nc"
        self.history = Path(self.temp.name) / "restart.nc"
        fixture(self.donor)
        fixture(self.history)

    def check(self):
        return PROBE.require_restart_diagnostics(self.donor, self.history, TIME)

    def test_exact_first_restart_record(self):
        self.assertTrue(self.check()["raw_and_decoded_exact"])

    def test_first_record_reset_rejected_even_if_later_recovers(self):
        with netCDF4.Dataset(self.history, "r+") as ds:
            for name in PROBE.UDM_CF_DIAGNOSTICS:
                ds[name][1] = ds[name][0]
                ds[name][0] = -1
        with self.assertRaisesRegex(RuntimeError, "differs"):
            self.check()

    def test_wrong_timestamp_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "first timestamp"):
            PROBE.require_restart_diagnostics(self.donor, self.history, "2000-01-01_00:01:00")

    def test_missing_checkpoint_diagnostic_rejected(self):
        with netCDF4.Dataset(self.donor, "r+") as ds:
            ds.renameVariable("UDM_CF_STEP", "MISSING_CF_STEP")
        with self.assertRaisesRegex(RuntimeError, "missing UDM_CF_STEP"):
            self.check()

    def test_nonfinite_diagnostic_rejected(self):
        with netCDF4.Dataset(self.history, "r+") as ds:
            ds["UDM_CLDFRA"][0, 0] = np.nan
        with self.assertRaisesRegex(RuntimeError, "nonfinite"):
            self.check()

    def test_decoding_difference_rejected(self):
        with netCDF4.Dataset(self.history, "r+") as ds:
            ds["UDM_CLDFRA"].scale_factor = np.float32(2)
        with self.assertRaisesRegex(RuntimeError, "decoded"):
            self.check()


if __name__ == "__main__":
    unittest.main()
