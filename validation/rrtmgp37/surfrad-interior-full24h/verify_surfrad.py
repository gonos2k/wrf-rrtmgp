#!/usr/bin/env python3
"""Offline verifier and hourly reducer for preserved Jan 2000 SURFRAD files."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
RAW_SHA256 = {
    "gwn00024.dat": "6c3edac924706826370fa7efe415ec555773c9210dea190bd7e49c563ab431c0",
    "gwn00025.dat": "e18725d4a106fdbc666b89e82e02c244990630708671cba406f6569b8694060b",
    "psu00024.dat": "803bb4be1b1606b4fe26d1b1afd4f2c3970052f85826a6bf77b2f3a1cceac383",
    "psu00025.dat": "cc70d05546f14f3b2c79ce646404909d074dd971e67c5cb9934294dcbf8fff72",
    "bon00024.dat": "62d1ad850b1b970e2882cb8b8e9f07c1b98886c9b3ccbfe8a69dd144c881eca4",
    "bon00025.dat": "429d7deeda5ae70d620b0b207bf0f0d341ad49cf8ad0f4ea0d5bc0c7269be795",
}
DOC_SHA256 = {
    "README_SURFRAD.txt": "ed3e5c16f169a9def997877e6037735977f2761c9c3c39d493c8f3127e82f3a6",
    "surfrad_problems.html": "81e1fadfbef2259cc38b4aa0d4c4d72c6ad95dc2a06df02efd2b59ea11c41355",
}
STATIONS = {
    "gwn": {"name": "Goodwin Creek", "official_lat": 34.2547, "official_lon": -89.8729, "elevation_m": 98},
    "psu": {"name": "Penn State", "official_lat": 40.72012, "official_lon": -77.93085, "elevation_m": 376},
    "bon": {"name": "Bondville", "official_lat": 40.05192, "official_lon": -88.37309, "elevation_m": 213},
}
# Token offsets in each 48-token record: numeric value followed by its QC flag.
CHANNELS = {
    "dw_solar": (8, 9), "uw_solar": (10, 11), "direct_n": (12, 13),
    "diffuse": (14, 15), "dw_ir": (16, 17), "uw_ir": (22, 23),
}
START = datetime(2000, 1, 24, 12, 0)
END = datetime(2000, 1, 25, 12, 0)
PERIOD_SECONDS = 180


def parse_daily_text(text: str, station: str, expected_date: datetime) -> tuple[dict, list[dict]]:
    """Parse one raw daily file; retain values and QC codes without corrections."""
    if station not in STATIONS:
        raise ValueError(f"unsupported station code {station}")
    lines = text.splitlines()
    if len(lines) < 3:
        raise ValueError("file must contain two header records and data")
    expected_name = STATIONS[station]["name"]
    if lines[0].strip() != expected_name:
        raise ValueError(f"station name mismatch: {lines[0].strip()!r}")
    header = lines[1].split()
    if len(header) < 6 or header[3] != "m" or header[4] != "version":
        raise ValueError(f"malformed station header: {lines[1]!r}")
    lat, lon = float(header[0]), float(header[1])
    elev, version = int(header[2]), int(header[5])
    meta = STATIONS[station]
    if (round(lat, 2), round(lon, 2), elev) != (round(meta["official_lat"], 2), round(meta["official_lon"], 2), meta["elevation_m"]):
        raise ValueError("rounded file-header coordinates/elevation do not match NOAA site metadata")
    if version != 1:
        raise ValueError(f"unexpected file version {version}")
    rows = []
    previous = None
    for lineno, line in enumerate(lines[2:], start=3):
        tokens = line.split()
        if len(tokens) != 48:
            raise ValueError(f"line {lineno}: expected 48 tokens, got {len(tokens)}")
        try:
            year, jday, month, day, hour, minute = map(int, tokens[:6])
            values = [float(v) for v in tokens]
        except ValueError as e:
            raise ValueError(f"line {lineno}: nonnumeric record") from e
        when = datetime(year, month, day, hour, minute)
        if year != expected_date.year or month != expected_date.month or day != expected_date.day:
            raise ValueError(f"line {lineno}: date disagrees with filename")
        if jday != expected_date.timetuple().tm_yday:
            raise ValueError(f"line {lineno}: Julian day disagrees with filename")
        if previous is not None and when - previous != timedelta(seconds=PERIOD_SECONDS):
            raise ValueError(f"line {lineno}: daily file has duplicate/gapped/non-3-minute timestamp")
        previous = when
        rows.append({"time": when, "values": values})
    if len(rows) != 480:
        raise ValueError(f"expected 480 3-minute records in daily file, got {len(rows)}")
    if rows[0]["time"] != datetime(expected_date.year, expected_date.month, expected_date.day, 0, 0) or rows[-1]["time"] != datetime(expected_date.year, expected_date.month, expected_date.day, 23, 57):
        raise ValueError("daily file does not span exact 00:00 through 23:57 period-end grid")
    return {"station": station, "name": expected_name, "header_lat": lat, "header_lon": lon,
            "header_elevation_m": elev, "file_version": version,
            "date": expected_date.date().isoformat(), "record_count": len(rows)}, rows


def expected_endpoints() -> list[datetime]:
    # SURFRAD reports period end times: (start, end] is represented by 12:03 ... 12:00.
    return [START + timedelta(seconds=PERIOD_SECONDS * k) for k in range(1, 481)]


def hourly_reduce(rows: list[dict]) -> tuple[list[dict], dict]:
    """QC0-only 24-hour bins. No fill, interpolation, clipping, or night correction."""
    target = [r for r in rows if START < r["time"] <= END]
    times = [r["time"] for r in target]
    if len(times) != len(set(times)):
        raise ValueError("duplicate interval-end timestamps in scoring window")
    exp = expected_endpoints()
    missing = sorted(set(exp) - set(times))
    unexpected = sorted(set(times) - set(exp))
    if missing or unexpected or len(target) != 480:
        raise ValueError(f"target grid mismatch: {len(target)} rows, {len(missing)} missing, {len(unexpected)} unexpected")
    output = []
    channel_summary = {}
    for channel, (vi, qi) in CHANNELS.items():
        invalid = 0
        qc_counts = {}
        negative_qc0 = 0
        for r in target:
            v, q = r["values"][vi], int(r["values"][qi])
            qc_counts[str(q)] = qc_counts.get(str(q), 0) + 1
            if q != 0 or v == -9999.9 or not math.isfinite(v):
                invalid += 1
            elif v < 0:
                negative_qc0 += 1
        channel_summary[channel] = {"target_records": len(target), "invalid_qc_or_fill_or_nonfinite": invalid,
                                    "qc_histogram": qc_counts, "negative_qc0_values_retained": negative_qc0}
        for hour in range(24):
            begin = START + timedelta(hours=hour)
            end = begin + timedelta(hours=1)
            binrows = [r for r in target if begin < r["time"] <= end]
            good = [r["values"][vi] for r in binrows
                    if int(r["values"][qi]) == 0 and r["values"][vi] != -9999.9 and math.isfinite(r["values"][vi])]
            complete = len(binrows) == 20 and len(good) == 20
            output.append({"station": None, "channel": channel, "hour_start_utc": begin.isoformat()+"Z",
                           "hour_end_utc": end.isoformat()+"Z", "expected_records": 20,
                           "records_present": len(binrows), "qc0_usable": len(good), "complete": complete,
                           "mean_flux_W_m-2": sum(good)/20 if complete else None,
                           "energy_J_m-2": sum(good)*PERIOD_SECONDS if complete else None,
                           "negative_qc0_samples_retained": sum(v < 0 for v in good)})
    return output, {"target_records": len(target), "expected_records": len(exp),
                    "first_end_utc": times[0].isoformat()+"Z", "last_end_utc": times[-1].isoformat()+"Z",
                    "timestamp_gaps": 0, "unexpected_timestamps": 0, "channels": channel_summary}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_pins(root: Path) -> dict:
    """No-network verification: only read local files; never opens a URL."""
    manifest_path = root / "download_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    expected_entries = {}
    for name, digest in RAW_SHA256.items():
        station = name[:3]
        expected_entries[name] = (digest, f"https://gml.noaa.gov/aftp/data/radiation/surfrad/{station}/2000/{name}")
    for name, digest in DOC_SHA256.items():
        if name == "README_SURFRAD.txt":
            url = "https://gml.noaa.gov/aftp/data/radiation/surfrad/psu/README_SURFRAD.txt"
        else:
            url = "https://gml.noaa.gov/grad/surfrad/problems.html"
        expected_entries["metadata/"+name] = (digest, url)
    listed = {entry["file"]: entry for entry in manifest["files"]}
    if set(listed) != set(expected_entries):
        raise ValueError("manifest file list differs from the fixed six-file plus two-doc inventory")
    for name, (digest, url) in expected_entries.items():
        entry = listed[name]
        if entry.get("sha256") != digest or entry.get("url") != url or entry.get("http_status") != 200:
            raise ValueError(f"manifest provenance mismatch for {name}")
    observed = {}
    for name, expected_hash in RAW_SHA256.items():
        path = root / "raw" / name
        if not path.is_file():
            raise ValueError(f"missing raw input {path}")
        got = sha256(path)
        if got != expected_hash:
            raise ValueError(f"raw SHA mismatch for {name}: {got}")
        observed[name] = {"sha256": got, "size_bytes": path.stat().st_size}
    for name, expected_hash in DOC_SHA256.items():
        path = root / "metadata" / name
        got = sha256(path)
        if got != expected_hash:
            raise ValueError(f"documentation SHA mismatch for {name}: {got}")
        observed["metadata/"+name] = {"sha256": got, "size_bytes": path.stat().st_size}
    return {"mode": "offline_no_network", "manifest_entries": len(manifest["files"]), "verified_local_files": observed}


def grid_match(root: Path, input_path: Path) -> dict:
    try:
        import numpy as np
        from netCDF4 import Dataset
    except ImportError as e:
        raise RuntimeError("grid matching requires numpy and netCDF4") from e
    expected_sha = "0cc7e188ef585a93ab52550816c6af236932254820fb1bc6937f464bfed38637"
    if sha256(input_path) != expected_sha:
        raise ValueError("winter input SHA does not match approved immutable input")
    radius = 6371000.0
    def distance(lat1, lon1, lat2, lon2):
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp, dl = p2-p1, math.radians(lon2-lon1)
        a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        return 2*radius*math.asin(math.sqrt(a))
    result = {"input_path": str(input_path), "input_sha256": sha256(input_path), "stations": {}}
    with Dataset(input_path) as ds:
        if len(ds.dimensions["west_east"]) != 73 or len(ds.dimensions["south_north"]) != 60:
            raise ValueError("unexpected domain dimensions")
        if float(ds.getncattr("DX")) != 30000.0 or float(ds.getncattr("DY")) != 30000.0:
            raise ValueError("unexpected nominal grid spacing")
        lat = np.asarray(ds.variables["XLAT"][0]); lon = np.asarray(ds.variables["XLONG"][0])
        hgt = np.asarray(ds.variables["HGT"][0]); mapfac = np.asarray(ds.variables["MAPFAC_M"][0])
        expected_shape = (60, 73)
        for name, values in (("XLAT", lat), ("XLONG", lon), ("HGT", hgt), ("MAPFAC_M", mapfac)):
            if values.shape != expected_shape:
                raise ValueError(f"{name} grid shape {values.shape} != {expected_shape}")
        for station, meta in STATIONS.items():
            d = np.empty(lat.shape)
            for idx in np.ndindex(lat.shape):
                d[idx] = distance(meta["official_lat"], meta["official_lon"], float(lat[idx]), float(lon[idx]))
            ij = np.unravel_index(np.argmin(d), d.shape)
            result["stations"][station.upper()] = {
                "official_site_lat_lon": [meta["official_lat"], meta["official_lon"]],
                "nearest_cell_i_j_1based": [int(ij[1])+1, int(ij[0])+1],
                "cell_lat_lon": [float(lat[ij]), float(lon[ij])],
                "great_circle_distance_m": float(d[ij]), "cell_HGT_m": float(hgt[ij]),
                "site_elevation_m": meta["elevation_m"], "terrain_difference_m": float(hgt[ij])-meta["elevation_m"],
                "mapfac_m": float(mapfac[ij]),
            }
    return result


def write_outputs(root: Path, input_path: Path) -> dict:
    pins = verify_pins(root)
    station_results, csv_rows = {}, []
    for station in STATIONS:
        all_rows = []
        for day, doy in ((datetime(2000,1,24), "024"), (datetime(2000,1,25), "025")):
            filename = f"{station}00{doy}.dat"
            meta, rows = parse_daily_text((root/"raw"/filename).read_text(), station, day)
            all_rows.extend(rows)
        all_rows.sort(key=lambda row: row["time"])
        times = [r["time"] for r in all_rows]
        if len(times) != 960 or len(times) != len(set(times)):
            raise ValueError(f"{station}: expected 960 unique records across the two files")
        if any(times[i]-times[i-1] != timedelta(seconds=PERIOD_SECONDS) for i in range(1,len(times))):
            raise ValueError(f"{station}: expected contiguous 3-minute records over both files")
        hourly_rows, cov = hourly_reduce(all_rows)
        for row in hourly_rows:
            row["station"] = station.upper()
        csv_rows.extend(hourly_rows)
        station_results[station.upper()] = {"header_site": meta, "daily_records": len(all_rows),
                                            "first_file_record_utc": times[0].isoformat()+"Z",
                                            "last_file_record_utc": times[-1].isoformat()+"Z", **cov}
    grid = grid_match(root, input_path)
    with (root/"hourly_observations.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_rows[0]))
        writer.writeheader(); writer.writerows(csv_rows)
    packages = {}
    for package in ("numpy", "netCDF4"):
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = None
    result = {"status": "OBSERVATIONS_VERIFIED_NO_MODEL_COMPARISON", "window_start_exclusive_utc": START.isoformat()+"Z",
              "window_end_inclusive_utc": END.isoformat()+"Z", "record_interval_seconds": PERIOD_SECONDS,
              "expected_records_per_station": 480, "expected_records_per_hour_channel": 20,
              "negative_qc0_values_are_retained": True, "no_fill_or_interpolation": True,
              "offline_verification": pins, "grid_match": grid, "stations": station_results,
              "hourly_csv": "hourly_observations.csv", "hourly_rows": len(csv_rows),
              "parser_sha256": sha256(Path(__file__).resolve()),
              "test_sha256": sha256(root/"test_verify_surfrad.py"),
              "python_version": sys.version.split()[0], "dependency_versions": packages,
              "method_note": "Hourly mean flux is the mean of 20 QC0 3-minute period-end averages; energy is their sum times 180 s. No nighttime negative global/diffuse values are clamped. Incomplete bins would be null, not filled."}
    (root/"verified_observations.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline-verify", action="store_true", help="verify local fixed SHA pins and reparse; makes no network requests")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--wrfinput", type=Path, default=None,
                    help="approved winter wrfinput; default is the pinned workspace input")
    args = ap.parse_args()
    if not args.offline_verify:
        ap.error("--offline-verify is required; this tool has no download path")
    root = args.root.resolve()
    inp = args.wrfinput.resolve() if args.wrfinput else ROOT.parents[1] / "build/udm-alternate-jan2000-data/real-preflight/case/wrfinput_d01"
    result = write_outputs(root, inp)
    print(json.dumps({
        "status": result["status"],
        "stations": {s: {"n": v["target_records"], "gaps": v["timestamp_gaps"],
                          "channel_qc_invalid": {c: v["channels"][c]["invalid_qc_or_fill_or_nonfinite"]
                                                  for c in CHANNELS}}
                     for s, v in result["stations"].items()},
        "hourly_rows": result["hourly_rows"], "input_sha256": result["grid_match"]["input_sha256"]
    }, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
