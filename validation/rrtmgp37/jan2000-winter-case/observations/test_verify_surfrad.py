#!/usr/bin/env python3
"""Synthetic contract tests for verify_surfrad.py (no network or model files)."""
from datetime import datetime, timedelta
import unittest

import verify_surfrad as v


def row_at(when, solar=100.0, solar_qc=0, diffuse=20.0, diffuse_qc=0):
    fields = [2000, when.timetuple().tm_yday, when.month, when.day, when.hour, when.minute, 12.0, 100.0]
    # 20 value/QC pairs; assign flux channel fields used by the reducer.
    pairs = [[0.0, 0] for _ in range(20)]
    pairs[0] = [solar, solar_qc]      # dw_solar
    pairs[1] = [35.0, 0]             # uw_solar
    pairs[2] = [120.0, 0]            # direct_n
    pairs[3] = [diffuse, diffuse_qc] # diffuse
    pairs[4] = [250.0, 0]            # dw_ir
    pairs[7] = [300.0, 0]            # uw_ir
    for val, qc in pairs:
        fields.extend([val, qc])
    return {"time": when, "values": [float(x) for x in fields]}


def scoring_rows():
    start = v.START
    rows = [row_at(start, solar=999.0)]  # start endpoint is excluded
    for k, when in enumerate(v.expected_endpoints()):
        solar = -8.0 if when == datetime(2000, 1, 25, 0, 3) else 100.0
        rows.append(row_at(when, solar=solar))
    return rows


class TestSurfradContracts(unittest.TestCase):
    def test_expected_endpoints_and_hour_bins(self):
        endpoints = v.expected_endpoints()
        self.assertEqual(len(endpoints), 480)
        self.assertEqual(endpoints[0], datetime(2000, 1, 24, 12, 3))
        self.assertEqual(endpoints[-1], datetime(2000, 1, 25, 12, 0))
        rows, coverage = v.hourly_reduce(scoring_rows())
        self.assertEqual(coverage["target_records"], 480)
        self.assertEqual(rows[0]["records_present"], 20)
        self.assertTrue(rows[0]["complete"])
        # Valid QC0 negative nocturnal values remain in the mean and energy.
        midnight = next(r for r in rows if r["station"] is None and r["channel"] == "dw_solar"
                        and r["hour_start_utc"] == "2000-01-25T00:00:00Z")
        self.assertEqual(midnight["negative_qc0_samples_retained"], 1)
        self.assertAlmostEqual(midnight["mean_flux_W_m-2"], (19*100.0-8.0)/20)
        self.assertAlmostEqual(midnight["energy_J_m-2"], (19*100.0-8.0)*180.0)
        nightrow = next(r for r in scoring_rows() if r["time"] == datetime(2000, 1, 25, 0, 3))
        self.assertGreaterEqual(nightrow["values"][7], 90.0)  # zenith angle is in degrees
        self.assertEqual(nightrow["values"][8], -8.0)  # negative nighttime global SW is retained verbatim

    def test_bad_qc_or_fill_makes_bin_incomplete_without_imputation(self):
        rows = scoring_rows()
        bad_qc_time = datetime(2000, 1, 24, 13, 3)
        for r in rows:
            if r["time"] == bad_qc_time:
                r["values"][9] = 1.0
        # The next hour's global-solar bin has 19 QC0 samples; other channels remain valid.
        reduced, _ = v.hourly_reduce(rows)
        binrow = next(r for r in reduced if r["channel"] == "dw_solar" and r["hour_start_utc"] == "2000-01-24T13:00:00Z")
        self.assertEqual(binrow["records_present"], 20)
        self.assertEqual(binrow["qc0_usable"], 19)
        self.assertFalse(binrow["complete"])
        self.assertIsNone(binrow["mean_flux_W_m-2"])
        self.assertIsNone(binrow["energy_J_m-2"])
        self.assertTrue(next(r for r in reduced if r["channel"] == "uw_ir" and r["hour_start_utc"] == "2000-01-24T13:00:00Z")["complete"])
        # Missing sentinel is invalid even when its QC flag was erroneously left at zero.
        for r in rows:
            if r["time"] == datetime(2000, 1, 24, 14, 3):
                r["values"][8] = -9999.9
        reduced, _ = v.hourly_reduce(rows)
        sentinel_bin = next(r for r in reduced if r["channel"] == "dw_solar" and r["hour_start_utc"] == "2000-01-24T14:00:00Z")
        self.assertFalse(sentinel_bin["complete"])

    def test_missing_and_duplicate_timestamps_rejected(self):
        rows = scoring_rows()
        with self.assertRaisesRegex(ValueError, "target grid mismatch"):
            v.hourly_reduce(rows[:-1])
        rows.append(rows[1])
        with self.assertRaisesRegex(ValueError, "duplicate interval-end"):
            v.hourly_reduce(rows)

    def test_daily_parser_rejects_internal_gap_and_validates_header(self):
        day = datetime(2000, 1, 24)
        lines = [" Goodwin Creek", "   34.25  -89.87   98 m version 1"]
        for n in range(480):
            t = day + timedelta(minutes=3*n)
            tokens = row_at(t)["values"]
            lines.append(" ".join(str(int(x)) if i < 6 or i in (9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,41,43,45,47) else str(x)
                                  for i,x in enumerate(tokens)))
        parsed, rows = v.parse_daily_text("\n".join(lines), "gwn", day)
        self.assertEqual(parsed["record_count"], 480)
        self.assertEqual(len(rows), 480)
        gapped = lines[:2] + lines[3:]
        with self.assertRaisesRegex(ValueError, "expected 480"):
            v.parse_daily_text("\n".join(gapped), "gwn", day)
        duplicated = lines.copy(); duplicated[20] = duplicated[19]
        with self.assertRaisesRegex(ValueError, "duplicate/gapped"):
            v.parse_daily_text("\n".join(duplicated), "gwn", day)
        wrong_header = lines.copy(); wrong_header[1] = "34.26 -89.87 98 m version 1"
        with self.assertRaisesRegex(ValueError, "rounded file-header"):
            v.parse_daily_text("\n".join(wrong_header), "gwn", day)


if __name__ == "__main__":
    unittest.main(verbosity=2)
