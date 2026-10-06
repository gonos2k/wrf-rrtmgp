#!/usr/bin/env python3
"""Verify the archived synthetic UDM cloud-top-shrink receipts and logs."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SCHEMA = "UDM_CLOUD_TOP_SHRINK_EVIDENCE_V1"
SOURCE_PINS = {
    "WRF/phys/module_mp_udm.F": ("18bac4328061b828c1a57fcbead77986eb71bf5b6a56985fbed0672647bc7d4d", 193968),
    "WRF/test/rrtmgp/test_udm_cloud_top_shrink.f90": ("cccd593abe58b797e18063c0af97ca2481fd40b0560c3eb6ece99b87863011d0", 3993),
    "WRF/test/rrtmgp/test_udm_cloud_top_shrink.py": ("1b352e8f0a28b330f3a4e1c05ab92b7371db7501efc797de0bd333bc7ad4c4b3", 11534),
    "WRF/test/rrtmgp/test_udm_rain_only_slopes.py": ("b287ddb29ac58fb9abda16077c6b38c0b22baef5b691bd64bd22bf54daae94ea", 21389),
    "WRF/phys/module_mp_radar.F": ("fa5e06a4d64bbc32089a1357bfa5c57e6c682e5b68c706842698c2b0f292e68e", 25452),
    "WRF/phys/module_gfs_machine.F": ("300ee4f75663e89d34c8a9b8733cc07a5dd48c3d973da019d31cb76524babe25", 567),
}


def need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_bytes(path: Path) -> bytes:
    need(path.is_file() and not path.is_symlink(), f"missing/symlink file: {path}")
    return path.read_bytes()


def json_file(path: Path, zipped: bool = False):
    raw = file_bytes(path)
    if zipped:
        raw = gzip.decompress(raw)
    return json.loads(raw)


def check_log_index(pkg: Path, index_rel: str) -> int:
    index_path = pkg / index_rel
    index = json_file(index_path)
    rows = index.get("logs")
    need(isinstance(rows, list) and rows, f"empty log index: {index_rel}")
    seen = set()
    folder = pkg / Path(index_rel).parent / "logs"
    for row in rows:
        rel = row.get("path", "")
        need(rel and rel not in seen, f"duplicate log path {rel}")
        seen.add(rel)
        packed = file_bytes(folder / rel)
        need(digest(packed) == row["gzip_sha256"] and len(packed) == row["gzip_size_bytes"],
             f"gzip pin mismatch {rel}")
        raw = gzip.decompress(packed)
        need(digest(raw) == row["sha256"] and len(raw) == row["size_bytes"],
             f"decompressed log pin mismatch {rel}")
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*.gz") if p.name != Path(index_rel).name}
    need(actual == seen, f"log roster mismatch in {index_rel}")
    return len(rows)


def check_initial(pkg: Path) -> dict:
    base = pkg / "initial-experiment"
    plan = json_file(base / "plan.json")
    receipt = json_file(base / "receipt.json")
    need(plan["status"] == "FROZEN_PREPARED_FOR_ONE_BOUNDED_STANDALONE_EXPERIMENT",
         "initial experiment plan status changed")
    need(receipt["status"] == "PASS_SCOPED_NATURAL_SHRINK_AND_SLOPE_RETENTION",
         "initial experiment receipt status mismatch")
    need(receipt["counts"] == {"compile_link_processes": 10, "fixture_executions": 2,
                                "WRF_forecasts": 0, "REAL_calls": 0, "RTE_calls": 0}
         and plan["expected_process_budget"]["UDM_invocations"] == 18,
         "initial experiment counts/scope mismatch")
    need(receipt["driver_sha256"] == plan["pins"]["experiment_driver"]["sha256"]
         and receipt["runner_sha256"] == plan["pins"]["experiment_runner"]["sha256"],
         "initial plan/receipt runner or driver link mismatch")
    need(digest(gzip.decompress(file_bytes(base / "test_udm_rain_only_shrink.f90.gz"))) == receipt["driver_sha256"],
         "initial archived driver differs from receipt")
    need(digest(file_bytes(base / "run_shrink_experiment.py")) == receipt["runner_sha256"],
         "initial archived runner differs from receipt")
    instrumented = gzip.decompress(file_bytes(base / "instrumented_module_mp_udm.F.gz"))
    need(digest(instrumented) == plan["instrumented_candidate"]["sha256"],
         "initial instrumented module source pin mismatch")
    need(digest(gzip.decompress(file_bytes(base / "references/prior-native-run-v3-receipt.json.gz"))) ==
         plan["pins"]["prior_v3_receipt"]["sha256"], "initial plan prior-v3 receipt link mismatch")
    need(digest(gzip.decompress(file_bytes(base / "references/trace-placement-review-v1.json.gz"))) ==
         plan["pins"]["corrected_marker_review"]["sha256"], "initial plan trace-review link mismatch")
    for opt in ("O0", "O2"):
        row = receipt["results"][opt]["candidate"]["cold_freeze_shrinking_top"]["shrink_retention"]
        need(row["observed"] is True and row["all_nine_branch_mode_records_pass"], f"initial {opt} retention failed")
        need(len(row["records"]) == 9 and all(r["first_cloud_top"] == 5 and r["second_cloud_top"] == 4
             and r["retained_levels_1based"] == [5] and r["same_substep_values_preserved"]
             for r in row["records"]), f"initial {opt} retained records mismatch")
    logs = check_log_index(pkg, "initial-experiment/log-index.json")
    need(logs == 12, "initial log count mismatch")
    return {"initial_logs": logs, "initial_fixture_calls": 18}


def parse_profile(raw: bytes) -> dict:
    lines = raw.decode("ascii").splitlines()
    groups = {}
    result_rows = {}
    active = None
    pending_result = None
    for line_no, line in enumerate(lines, 1):
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "CALL":
            need(len(parts) == 4 and int(parts[1]) == 6, f"bad CALL at line {line_no}")
            active = (int(parts[2]), int(parts[3]))
            need(active not in groups, f"duplicate CALL identity {active}")
            groups[active] = {}
            pending_result = None
        elif parts[0] == "SLOPEV":
            need(active is not None and len(parts) == 12, f"malformed SLOPEV at line {line_no}")
            site, phase, top = map(int, parts[2:5])
            key = (site, phase)
            need(key not in groups[active], f"duplicate slope marker {active}/{key}")
            vals = [float(x) for x in parts[5:]]
            need(len(vals) == 7 and all(math.isfinite(x) for x in vals), f"invalid slope vector {active}/{key}")
            groups[active][key] = (top, vals)
        elif parts[0] == "RESULT":
            need(active is not None and len(parts) == 5, f"malformed RESULT at line {line_no}")
            key = (int(parts[2]), int(parts[3])); count = int(parts[4])
            need(key == active and count == 121 and key not in result_rows, f"RESULT identity/count mismatch {key}")
            pending_result = key
        elif pending_result is not None:
            words = parts
            need(len(words) == 121 and all(len(w) == 8 for w in words), f"bad RESULT payload {pending_result}")
            try:
                vals = [struct.unpack(">f", bytes.fromhex(w))[0] for w in words]
            except (ValueError, struct.error) as exc:
                raise ValueError(f"invalid RESULT word at line {line_no}") from exc
            need(all(math.isfinite(x) for x in vals), f"nonfinite RESULT payload {pending_result}")
            result_rows[pending_result] = len(vals)
            pending_result = None
    need(set(groups) == {(b, m) for b in (1, 2, 3) for m in (0, 1, 2)}, "wrong branch/mode call roster")
    need(set(result_rows) == set(groups), "missing result payloads")
    retained = []
    slots = {(1, 0), (1, 1), (2, 0), (2, 1)}
    for key, rows in sorted(groups.items()):
        need(set(rows) == slots, f"incomplete marker pair {key}")
        tops = [rows[x][0] for x in ((1, 0), (1, 1), (2, 0), (2, 1))]
        need(tops == [5, 5, 4, 4], f"unexpected top transition at {key}: {tops}")
        vals = [rows[x][1][4] for x in ((1, 0), (1, 1), (2, 0), (2, 1))]
        need(vals[0] != vals[1] and vals[1] == vals[2] == vals[3],
             f"k5 slope not changed then retained exactly at {key}: {vals}")
        retained.append({"branch": key[0], "density_mode": key[1], "first_top": tops[0],
                         "second_top": tops[2], "k5_initializer": vals[0],
                         "k5_first_post": vals[1], "k5_second_pre_post": vals[2]})
    return {"records": retained, "result_arrays": len(result_rows), "all_result_words_finite": True}


def check_native(pkg: Path) -> dict:
    base = pkg / "native-shrink"
    receipt = json_file(base / "execution-receipt.json")
    review = json_file(base / "independent-review.json.gz", zipped=True)
    need(receipt["status"] == "PASS_SCOPED_NATURAL_SHRINK_AND_SLOPE_RETENTION",
         "public wrapper receipt status mismatch")
    need(receipt["counts"] == {"compile_link_processes": 10, "fixture_processes": 2,
                                "udm_invocations": 18, "WRF_forecasts": 0, "REAL_calls": 0, "RTE_calls": 0},
         "public wrapper counts/scope mismatch")
    need(review["status"] == "PASS_SCOPED_PUBLIC_WRAPPER_AND_NATIVE_READBACK",
         "independent wrapper review mismatch")
    need(review["evidence"]["execution_receipt"]["sha256"] == digest(file_bytes(base / "execution-receipt.json"))
         and review["evidence"]["wrapper"]["sha256"] == SOURCE_PINS["WRF/test/rrtmgp/test_udm_cloud_top_shrink.py"][0]
         and review["evidence"]["driver"]["sha256"] == SOURCE_PINS["WRF/test/rrtmgp/test_udm_cloud_top_shrink.f90"][0],
         "independent review does not bind this execution/source")
    for rel, pin_key in (("test_udm_cloud_top_shrink.py", "runner"),
                         ("test_udm_cloud_top_shrink.f90.gz", "driver"),
                         ("test_udm_rain_only_slopes.py", "helper")):
        data = file_bytes(base / rel)
        if rel.endswith(".gz"):
            data = gzip.decompress(data)
        need(digest(data) == receipt["source_pins_before"][pin_key]["sha256"],
             f"archived public {pin_key} differs from receipt")
    before = dict(receipt["source_pins_before"])
    repo_head = before.pop("repository_head", None)
    need(repo_head == "ba8c82706034e0576101e6a77f8952478c7b1b2f"
         and before == receipt["source_pins_after"], "public source pins changed during fixture")
    need(len(receipt["processes"]) == 12 and all(p["actual_returncode"] == 0 and not p["timed_out"]
         for p in receipt["processes"]), "public fixture process ledger mismatch")
    need(receipt["source_pins_before"]["candidate_udm"]["sha256"] == SOURCE_PINS["WRF/phys/module_mp_udm.F"][0],
         "public candidate UDM source pin mismatch")
    need(receipt["source_pins_before"]["helper"]["sha256"] == SOURCE_PINS["WRF/test/rrtmgp/test_udm_rain_only_slopes.py"][0],
         "public shared helper pin mismatch")
    need(receipt["source_pins_before"]["runner"]["sha256"] == SOURCE_PINS["WRF/test/rrtmgp/test_udm_cloud_top_shrink.py"][0],
         "public runner pin mismatch")
    need(receipt["source_pins_before"]["driver"]["sha256"] == SOURCE_PINS["WRF/test/rrtmgp/test_udm_cloud_top_shrink.f90"][0],
         "public driver pin mismatch")
    for opt in ("O0", "O2"):
        generated = gzip.decompress(file_bytes(base / f"source/instrumented_module_mp_udm_{opt}.F.gz"))
        need(digest(generated) == receipt["instrumented_candidate"][opt]["sha256"]
             and len(generated) == receipt["instrumented_candidate"][opt]["size_bytes"],
             f"public {opt} generated source pin mismatch")
        result = receipt["optimization_results"][opt]
        need(result["actual_returncode"] == 0 and result["output_records"] == 9
             and result["slope_trace_records"] == 36, f"public {opt} status/count mismatch")
        compressed_log = file_bytes(base / f"logs/{opt}/profile6.log.gz")
        raw_log = gzip.decompress(compressed_log)
        need(digest(raw_log) == result["log"]["sha256"]
             and len(raw_log) == result["log"]["size_bytes"], f"public {opt} log receipt mismatch")
        parsed = parse_profile(raw_log)
        need(len(parsed["records"]) == 9 and parsed["result_arrays"] == 9, f"public {opt} raw-log gate mismatch")
        retained = result["retention"]
        need(retained["all_nine_records_pass"] and len(retained["records"]) == 9,
             f"public {opt} receipt retention mismatch")
        for actual, record in zip(parsed["records"], retained["records"]):
            for k in ("branch", "density_mode", "first_top", "second_top"):
                need(actual[k] == record[k], f"public {opt} receipt/log identity mismatch {k}")
            for a, b in ((actual["k5_initializer"], record["k5_initializer"]),
                         (actual["k5_first_post"], record["k5_first_call_post"]),
                         (actual["k5_second_pre_post"], record["k5_second_call_pre_post"])):
                need(a == b, f"public {opt} receipt/log numeric mismatch")
    logs = check_log_index(pkg, "native-shrink/log-index.json")
    need(logs == 12, "public wrapper log count mismatch")
    return {"public_native_logs": logs, "public_fixture_records": 18,
            "retention_records": 18, "result_arrays": 18}


def verify(pkg: Path, repo: Path) -> dict:
    manifest_path = pkg / "manifest.json"
    manifest = json_file(manifest_path)
    need(manifest.get("schema") == SCHEMA, "manifest schema mismatch")
    rows = manifest.get("files")
    need(isinstance(rows, list) and rows, "manifest files missing")
    roster = {}
    for row in rows:
        rel = row.get("path", "")
        need(rel and rel not in roster and not Path(rel).is_absolute() and ".." not in Path(rel).parts,
             f"invalid/duplicate manifest path {rel}")
        roster[rel] = row
    paths = list(pkg.rglob("*"))
    need(not any(p.is_symlink() for p in paths), "package contains a symlink")
    actual = {p.relative_to(pkg).as_posix() for p in paths if p.is_file() and p != manifest_path}
    need(actual == set(roster), f"closed roster mismatch missing={sorted(set(roster)-actual)} extra={sorted(actual-set(roster))}")
    for rel, row in roster.items():
        data = file_bytes(pkg / rel)
        need(digest(data) == row.get("sha256") and len(data) == row.get("size_bytes"), f"payload pin mismatch {rel}")
    source_rows = manifest.get("source_pins")
    need(isinstance(source_rows, list) and {x.get("path") for x in source_rows} == set(SOURCE_PINS),
         "source pin roster mismatch")
    for row in source_rows:
        rel = row["path"]
        expected = SOURCE_PINS[rel]
        data = file_bytes(repo / rel)
        need((digest(data), len(data)) == expected, f"source pin changed: {rel}")
        need(row.get("sha256") == expected[0] and row.get("size_bytes") == expected[1],
             f"manifest source pin mismatch: {rel}")
    candidate_copy = gzip.decompress(file_bytes(pkg / "source/module_mp_udm.F.gz"))
    need(digest(candidate_copy) == SOURCE_PINS["WRF/phys/module_mp_udm.F"][0],
         "archived production UDM source snapshot mismatch")
    initial = check_initial(pkg)
    native = check_native(pkg)
    return {"status": "PASS_SCOPED_CLOUD_TOP_SHRINK_EVIDENCE", "payload_files": len(rows),
            "source_pins": len(source_rows), **initial, **native,
            "claims": {"synthetic_top_transition": "5_to_4", "level_5_slope_changed_then_retained_exactly": True,
                       "rain_consumer_tested": False, "WRF_forecasts": 0, "REAL_calls": 0, "RTE_calls": 0}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        result = verify(Path(__file__).resolve().parent, args.repo_root.resolve())
        text = json.dumps(result, sort_keys=True, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(text)
        else:
            print(text, end="")
        return 0
    except Exception as exc:
        print(f"VERIFY_FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
