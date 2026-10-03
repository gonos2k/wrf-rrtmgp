#!/usr/bin/env python3
"""Python-only policy/path failure tests; no model or reference executable is run."""
from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from test_column_replay import (FROZEN_NAMES, ReplayError, compare_input_to_raw,
                                read_input, verify_frozen_table)


TABLE_BYTES = b"synthetic table identity fixture, never used for optics\n"
DIGEST = hashlib.sha256(TABLE_BYTES).hexdigest()
NNATIVE = 3
NADAPTER = 5


def fixture(frozen: bool, positive_hail: bool = True):
    # Positive G/H at both CF0 and CF>0 prevents tiny-tail-only coverage.
    raw = {
        "DRY_LAYER_MASS_KG_M2": np.array([100., 80., 60.]),
        "DP_HPA": np.array([100., 100., 100.]),
        "P_HPA": np.array([950., 850., 750.]),
        "SOURCE_T": np.full(NNATIVE, 270.),
        "QV": np.full(NNATIVE, 0.001), "AMD_W": np.array([1.6]),
        "GRAVITY": np.array([9.81]), "CF": np.array([0., 0.5, 1.]),
        "NEGATIVE_Q_LIMITS": np.full(6, 1.e-7),
    }
    inp = {
        "PLAY": np.array([[950., 850., 750., 650., 550.]]),
        "PLEV": np.array([[1000., 900., 800., 700., 600., 500.]]),
        "TLAY": np.full((1, NADAPTER), 270.),
        "TLEV": np.full((1, NADAPTER+1), 270.),
        "H2O": np.full((1, NADAPTER), 0.0016),
        "CF": np.array([[0., 0.5, 1., 0., 0.]]),
    }
    for q, path in (("QC", "LWP"), ("QI", "IWP"), ("QS", "SWP"),
                    ("QG", "GWP"), ("QH", "HWP")):
        raw[q] = (np.array([0.001, 0.002, 0.]) if q == "QG" else
                  np.array([0.003, 0.004, 0.]) if q == "QH" and positive_hail else
                  np.zeros(NNATIVE))
        raw["NUMERIC_CLIPPED_"+q] = np.zeros(NNATIVE)
        raw["NEGATIVE_GRID_CORRECTION_"+path] = np.zeros(NNATIVE)
        grid = raw[q]*raw["DRY_LAYER_MASS_KG_M2"]*1000.
        if q in {"QG", "QH"}:
            raw[path+"_GRID"] = grid.copy()
            raw[path+"_OMITTED"] = np.zeros(NNATIVE) if frozen else grid.copy()
            raw[path+"_RADIATION"] = grid.copy() if frozen else np.zeros(NNATIVE)
            if frozen:
                inp[path] = np.concatenate((grid, [0., 0.]))[None, :]
        else:
            inp[path] = np.zeros((1, NADAPTER))
    for name in ("REL", "REI", "RES"):
        raw[name] = np.full(NNATIVE, 10.)
        inp[name] = np.full((1, NADAPTER), 10.)
    if frozen:
        inp["NATIVE_DRY_LAYER_MASS_KG_M2"] = raw["DRY_LAYER_MASS_KG_M2"][None, :].copy()
        for short in ("G", "H"):
            raw[f"FROZEN_LAMBDA_{short}_M-1"] = np.array([1000., 2000., 20000.])
            inp["LAMBDA_"+short] = np.array([[1000., 2000., 20000., 20000., 20000.]])
        inp["FROZEN_MODE"] = np.ones((1, 1))
        inp["FROZEN_OCCURRENCE"] = np.ones((1, 1))
        inp["FROZEN_TABLE_SHA256_BYTES"] = np.array([ord(c) for c in DIGEST])[:, None]
    return raw, inp


def write_v7(path, inp):
    records = copy.deepcopy(inp)
    records.update({"ICE_ROUGHNESS": np.ones((1, 1)),
                    "GRAVITY": np.array([[9.81]]), "CP_DRY": np.array([[1004.5]]),
                    "MOL_WEIGHT_DRY": np.array([[0.028966]])})
    lines = ["RRTMGP_REPLAY_V7", f"LW 1 {NADAPTER} 1 12345 2"]
    for name, values in records.items():
        lines.append(f"{name} {' '.join(str(n) for n in values.shape)}")
        lines.append(" ".join(f"{v:.17g}" for v in values.flatten(order="F")))
    path.write_text("\n".join(lines)+"\n", encoding="ascii")


class FrozenRawContract(unittest.TestCase):
    def check(self, raw, inp):
        # Exercise the actual integration point for both phase temperature paths.
        for phase in ("LW", "SW"):
            with self.subTest(phase=phase):
                compare_input_to_raw(phase, raw, inp, NNATIVE)

    def reject(self, raw, inp, message):
        for phase in ("LW", "SW"):
            with self.subTest(phase=phase), self.assertRaisesRegex(ReplayError, message):
                compare_input_to_raw(phase, raw, inp, NNATIVE)

    def test_material_positive_frozen_graupel_and_hail(self):
        raw, inp = fixture(True)
        self.assertGreater(raw["GWP_GRID"].sum(), 100.)
        self.assertGreater(raw["HWP_GRID"].sum(), 100.)
        self.check(raw, inp)

    def test_mode0_diagnostic_graupel_and_hail_refusal(self):
        self.check(*fixture(False, positive_hail=False))
        self.reject(*fixture(False), "positive hail must be refused")

    def test_legacy_without_negative_contract(self):
        raw, inp = fixture(False, positive_hail=False)
        del raw["NEGATIVE_Q_LIMITS"]
        self.check(raw, inp)

    def test_missing_frozen_records(self):
        for name in sorted(FROZEN_NAMES):
            raw, inp = fixture(True)
            del inp[name]
            with self.subTest(record=name):
                self.reject(raw, inp, "must be complete")
        raw, inp = fixture(True)
        for name in FROZEN_NAMES:
            del inp[name]
        self.reject(raw, inp, "raw frozen slopes require complete")
        del raw["FROZEN_LAMBDA_G_M-1"], raw["FROZEN_LAMBDA_H_M-1"]
        self.reject(raw, inp, "GWP_OMITTED.*mismatch")

    def test_malformed_policy_and_hash(self):
        for name, invalid in (("FROZEN_MODE", np.zeros((1, 1))),
                              ("FROZEN_MODE", np.array([[1.5]])),
                              ("FROZEN_OCCURRENCE", np.zeros((1, 1))),
                              ("FROZEN_OCCURRENCE", np.ones((1, 2))),
                              ("FROZEN_MODE", np.array([[np.nan]])),
                              ("FROZEN_TABLE_SHA256_BYTES", np.full((64, 1), ord("A"))),
                              ("FROZEN_TABLE_SHA256_BYTES", np.full((64, 1), 48.5)),
                              ("FROZEN_TABLE_SHA256_BYTES", np.full((63, 1), ord("a")))):
            raw, inp = fixture(True)
            inp[name] = invalid
            with self.subTest(record=name, value=invalid.tolist()):
                self.reject(raw, inp, "frozen policy|frozen table SHA")

    def test_parser_requires_frozen_markers(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/"lw.input"
            _, inp = fixture(True)
            write_v7(path, inp)
            parsed = read_input(path)[-1]
            self.assertEqual(parsed["FROZEN_MODE"].item(), 1.)
            for name in sorted(FROZEN_NAMES):
                invalid = copy.deepcopy(inp)
                del invalid[name]
                write_v7(path, invalid)
                with self.subTest(record=name), self.assertRaisesRegex(ReplayError, "missing required frozen"):
                    read_input(path)
            for name in ("FROZEN_MODE", "FROZEN_OCCURRENCE"):
                invalid = copy.deepcopy(inp)
                invalid[name][0, 0] = 0.
                write_v7(path, invalid)
                with self.subTest(record=name), self.assertRaisesRegex(ReplayError, "scalar one"):
                    read_input(path)

    def test_mode1_zero_omission_and_padding_are_exact(self):
        for short in ("GWP", "HWP"):
            raw, inp = fixture(True)
            raw[short+"_OMITTED"][2] = 1.e-20
            self.reject(raw, inp, short+"_OMITTED.*mismatch")
            raw, inp = fixture(True)
            inp[short][0, NNATIVE] = 1.e-20
            self.reject(raw, inp, "padded "+short+".*mismatch")

    def test_changed_native_paths(self):
        for short in ("GWP", "HWP"):
            for target in ("GRID", "RADIATION", "adapter"):
                raw, inp = fixture(True)
                if target == "adapter":
                    inp[short][0, 0] += 1.
                else:
                    raw[short+"_"+target][0] += 1.
                with self.subTest(species=short, target=target):
                    self.reject(raw, inp, short+".*mismatch")
        raw, inp = fixture(False, positive_hail=False)
        raw["GWP_RADIATION"][0] = 1.
        self.reject(raw, inp, "GWP_RADIATION.*mismatch")

    def test_grid_radiation_adapter_identity_is_exact(self):
        for short in ("GWP", "HWP"):
            raw, inp = fixture(True)
            # Below the existing q*mass tolerance, but cross-record identity is exact.
            raw[short+"_RADIATION"][0] += 1.e-8
            self.reject(raw, inp, short+" radiation preserves grid path.*mismatch")
            raw, inp = fixture(True)
            inp[short][0, 0] += 1.e-8
            self.reject(raw, inp, "adapter "+short+" preserves radiation path.*mismatch")

    def test_native_mass_and_slope_contract(self):
        for name in ("DRY_LAYER_MASS_KG_M2", "FROZEN_LAMBDA_G_M-1", "QG"):
            raw, inp = fixture(True)
            del raw[name]
            with self.subTest(record=name):
                self.reject(raw, inp, "missing DRY_LAYER_MASS|must appear together|omitted QG")
        raw, inp = fixture(True)
        del inp["NATIVE_DRY_LAYER_MASS_KG_M2"]
        self.reject(raw, inp, "requires native dry layer mass")
        raw, inp = fixture(True)
        inp["NATIVE_DRY_LAYER_MASS_KG_M2"][0, 0] += 1.
        self.reject(raw, inp, "native dry mass.*mismatch")
        raw, inp = fixture(True)
        inp["LAMBDA_H"][0, 0] += 1.
        self.reject(raw, inp, "LAMBDA_H.*mismatch")
        raw, inp = fixture(True)
        del raw["FROZEN_LAMBDA_G_M-1"], raw["FROZEN_LAMBDA_H_M-1"]
        self.check(raw, inp)  # Older raw snapshots do not contain slope diagnostics.

    def test_malformed_frozen_paths_and_slopes(self):
        for name, invalid in (("GWP", np.full((1, NADAPTER), -1.)),
                              ("HWP", np.zeros((1, NADAPTER-1))),
                              ("LAMBDA_G", np.zeros((1, NADAPTER))),
                              ("LAMBDA_H", np.full((1, NADAPTER), np.nan))):
            raw, inp = fixture(True)
            inp[name] = invalid
            with self.subTest(record=name):
                self.reject(raw, inp, "frozen path|frozen input|frozen slope")
        for name in ("GWP_GRID", "GWP_OMITTED", "HWP_RADIATION"):
            raw, inp = fixture(True)
            del raw[name]
            self.reject(raw, inp, "omitted "+name)
        raw, inp = fixture(True)
        raw["FROZEN_LAMBDA_H_M-1"][0] = 0.
        self.reject(raw, inp, "FROZEN_LAMBDA_H_M-1 must be positive")

    def test_negative_corrections_remain_strict_in_both_modes(self):
        for frozen in (False, True):
            for q, short in (("QG", "GWP"), ("QH", "HWP")):
                raw, inp = fixture(frozen, positive_hail=frozen)
                raw[q][2] = -5.e-8
                raw["NUMERIC_CLIPPED_"+q][2] = -5.e-8
                raw["NEGATIVE_GRID_CORRECTION_"+short][2] = 0.003
                self.check(raw, inp)
                invalid = copy.deepcopy(raw)
                invalid["NEGATIVE_GRID_CORRECTION_"+short][2] = 0.
                self.reject(invalid, inp, "NEGATIVE_GRID_CORRECTION_"+short+".*mismatch")
                invalid = copy.deepcopy(raw)
                invalid[q][2] = -1.e-7
                self.reject(invalid, inp, "strict bound")
                invalid = copy.deepcopy(raw)
                del invalid["NUMERIC_CLIPPED_"+q]
                self.reject(invalid, inp, "missing, wrong shape, or nonfinite correction")

    def test_table_identity_before_reference(self):
        _, inp = fixture(True)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            table = root/"table.nc"
            table.write_bytes(TABLE_BYTES)
            with patch.dict("os.environ", {"WRF_RRTMGP_FROZEN_TABLE": "table.nc"}):
                verify_frozen_table(inp, 1, NADAPTER, root)
                table.write_bytes(TABLE_BYTES+b"changed")
                with self.assertRaisesRegex(ReplayError, "table identity differs"):
                    verify_frozen_table(inp, 1, NADAPTER, root)
            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaisesRegex(ReplayError, "requires WRF_RRTMGP_FROZEN_TABLE"):
                    verify_frozen_table(inp, 1, NADAPTER, root)
                verify_frozen_table(fixture(False)[1], 1, NADAPTER, root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
