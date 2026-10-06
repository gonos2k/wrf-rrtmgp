#!/usr/bin/env python3
"""Python parser controls only: no compiled Fortran reader or solver calls."""
import tempfile
import unittest
from pathlib import Path
from cf0_precip_sidecar import (SidecarError, UNITS, encode, decode, validate_payload,
                                parse_input_matrix, validate_against_raw)

class ValidatorTests(unittest.TestCase):
    def payload(self):
        cf = [[0.0, 0.5, 0.0]]
        rain = [[2.0, 0.0, 0.0]]
        snow = [[0.0, 0.0, 0.0]]
        return ["LW", 1, 3, 1, 1.0, rain, snow, cf, 5]
    def test_roundtrip_native_only(self):
        p = self.payload(); text = encode(*p); d = decode(text)
        self.assertEqual((d[0],d[1],d[2],d[3]), ("LW",1,3,1))
        self.assertEqual(d[5], [[2.0,0.0,0.0]])
        self.assertEqual(len(d[5][0]), 3)  # engine padding is added as zero by reader
    def test_reject_cf_positive(self):
        p = self.payload(); p[5] = [[2.0,1.0,0.0]]
        with self.assertRaises(SidecarError): encode(*p)
    def test_reject_shape(self):
        p = self.payload(); p[5] = [[2.0,0.0]]
        with self.assertRaises(SidecarError): encode(*p)
    def test_reject_multicolumn_scope(self):
        with self.assertRaises(SidecarError):
            validate_payload("LW",2,3,1,1.0,[[1.,0.,0.],[1.,0.,0.]],[[0.,0.,0.],[0.,0.,0.]],[[0.,0.,0.],[0.,0.,0.]])
    def test_reject_units(self):
        p = self.payload(); text = encode(*p).replace(UNITS,"PATH_UNITS_KG_M2")
        with self.assertRaises(SidecarError): decode(text)
    def test_reject_nonfinite(self):
        p = self.payload(); p[5] = [[float('nan'),0.0,0.0]]
        with self.assertRaises(SidecarError): encode(*p)
    def test_reject_negative(self):
        p = self.payload(); p[5] = [[-1.0,0.0,0.0]]
        with self.assertRaises(SidecarError): encode(*p)
    def test_reject_species_mix(self):
        p = self.payload(); p[6] = [[0.0,0.0,1.0]]
        with self.assertRaises(SidecarError): encode(*p)
    def test_reject_occurrence(self):
        p = self.payload(); p[4] = 0.5
        with self.assertRaises(SidecarError): encode(*p)
    def test_reject_phase(self):
        p = self.payload(); p[0] = "MIXED"
        with self.assertRaises(SidecarError): encode(*p)
    def test_reject_engine_extension(self):
        p = self.payload(); p[2] = 5; p[5] = [[2.0,0.0,0.0,0.0,0.0]]; p[6] = [[0.0]*5]; p[7] = [[0.0]*5]; p[8] = 4
        with self.assertRaises(SidecarError): encode(*p)
    def test_reject_trailing_data(self):
        text=encode(*self.payload())+"UNEXPECTED 1\n0\n"
        with self.assertRaises(SidecarError): decode(text)
    def raw_fixture(self, source_radius_m):
        sections={"HAS_REQS":[1.0],"CF":[0.0,0.0],"SOURCE_RE_SNOW":[source_radius_m,source_radius_m],
                  "RES":[source_radius_m*1e6,source_radius_m*1e6],
                  "RWP_OMITTED":[0.0,0.0],"SWP_OMITTED":[0.0,1.0]}
        lines=["RRTMGP_RAW_V1","LW 7 9 2"]
        for name,values in sections.items(): lines += [f"{name} {len(values)}", " ".join(str(v) for v in values)]
        return "\n".join(lines)+"\n"
    def test_input_matrix_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/"input"; f.write_text("RRTMGP_REPLAY_V1\nRES 1 3\n1 2 3\n")
            self.assertEqual(parse_input_matrix(f,"RES"),(1,3,[1.0,2.0,3.0]))
    def test_snow_radius_source_eligibility(self):
        text=encode("LW",1,2,2,1.0,[[0.,0.]],[[0.,1.]],[[0.,0.]],3)
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/"valid.raw"; raw.write_text(self.raw_fixture(25e-6))
            inp=Path(tmp)/"valid.input"; inp.write_text("RRTMGP_REPLAY_V1\nRES 1 3\n2.5e1 2.5e1 2.5e1\n")
            validate_against_raw(text,raw,"snow",3,inp)
    def test_reject_input_radius_mismatch(self):
        text=encode("LW",1,2,2,1.0,[[0.,0.]],[[0.,1.]],[[0.,0.]],3)
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/"raw"; raw.write_text(self.raw_fixture(25e-6))
            inp=Path(tmp)/"input"; inp.write_text("RRTMGP_REPLAY_V1\nRES 1 3\n25 24 25\n")
            with self.assertRaises(SidecarError): validate_against_raw(text,raw,"snow",3,inp)
    def test_reject_background_snow_radius(self):
        text=encode("LW",1,2,2,1.0,[[0.,0.]],[[0.,1.]],[[0.,0.]],3)
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/"background.raw"; raw.write_text(self.raw_fixture(9.99e-6))
            with self.assertRaises(SidecarError): validate_against_raw(text,raw,"snow",3)
    def test_reject_extension_shape(self):
        p = self.payload(); p[2] = 5; p[5] = [[2.0,0.0,0.0,0.0,0.0]]; p[6] = [[0.0]*5]; p[7] = [[0.0]*5]
        with self.assertRaises(SidecarError): encode(*p[:-1], engine_n=3)

class AdditionalFailureControls(unittest.TestCase):
    payload = ValidatorTests.payload
    raw_fixture = ValidatorTests.raw_fixture
    def test_zero_sidecar_roundtrip(self):
        p = self.payload(); p[5] = [[0.0] * 3]
        d = decode(encode(*p))
        self.assertEqual(d[5], [[0.0] * 3]); self.assertEqual(d[6], [[0.0] * 3])

    def test_truncated_and_malformed_sidecar(self):
        text = encode(*self.payload())
        for bad in [text.rsplit("\n", 2)[0], text.replace("LW 1 3 1 1.0", "LW x 3 1 1.0"),
                    text.replace("LW 1 3 1 1.0", "LW -1 3 1 1.0")]:
            with self.subTest(text=bad), self.assertRaises(SidecarError): decode(bad)

    def test_zero_control_against_raw_and_nonzero_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)/"raw"; raw.write_text(self.raw_fixture(25e-6))
            zero = encode("LW", 1, 2, 2, 1.0, [[0., 0.]], [[0., 0.]], [[0., 0.]], 3)
            self.assertEqual(validate_against_raw(zero, raw, "snow", 3, zero_control=True)["control"], "all-zero")
            positive = encode("LW", 1, 2, 2, 1.0, [[0., 0.]], [[0., 1.]], [[0., 0.]], 3)
            with self.assertRaises(SidecarError): validate_against_raw(positive, raw, "snow", 3, zero_control=True)
            with self.assertRaises(SidecarError): validate_against_raw(zero, raw, "snow", 3)

    def test_cf_outside_bounds(self):
        for cf in [-0.1, 1.1, float("nan"), float("inf")]:
            p = self.payload(); p[7] = [[cf, 0.5, 0.0]]
            with self.subTest(cf=cf), self.assertRaises(SidecarError): encode(*p)

    def test_wrong_omitted_mass_rejected(self):
        text = encode("LW", 1, 2, 2, 1.0, [[0., 0.]], [[0., 2.]], [[0., 0.]], 3)
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)/"raw"; raw.write_text(self.raw_fixture(25e-6))
            with self.assertRaises(SidecarError): validate_against_raw(text, raw, "snow", 3)

    def test_missing_or_nonfinite_radius_rejected(self):
        text = encode("LW", 1, 2, 2, 1.0, [[0., 0.]], [[0., 1.]], [[0., 0.]], 3)
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)/"raw"
            for bad in [self.raw_fixture(25e-6).replace("RES 2\n25.0 25.0\n", ""),
                        self.raw_fixture(float("nan"))]:
                raw.write_text(bad)
                with self.subTest(raw=bad), self.assertRaises(SidecarError):
                    validate_against_raw(text, raw, "snow", 3)

if __name__ == "__main__":
    unittest.main(verbosity=2)
