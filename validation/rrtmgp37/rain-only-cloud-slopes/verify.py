#!/usr/bin/env python3
"""Authenticate the archived rain-only UDM evidence; standard library plus parser."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True


SCHEMA = "UDM_RAIN_ONLY_SLOPES_EVIDENCE_V1"
EXPECTED_SOURCE = {
    "WRF/phys/module_mp_udm.F": ("18bac4328061b828c1a57fcbead77986eb71bf5b6a56985fbed0672647bc7d4d", 193968),
    "WRF/phys/module_microphysics_driver.F": ("7e15f93341b1fa079136aa60b2f2061c6e7844f107446ae8e7951edff00820fb", 198427),
    "WRF/phys/module_ra_rrtmgp_trace.F": ("c08a1cae7a93f85a08ed59042aa1b98dc1ef6b42d33c6f344b93a9eca9d652e9", 41541),
    "WRF/test/rrtmgp/test_udm_rain_only_slopes.f90": ("4898d06127322e18b4a16264ca1369ff713bd369df521e7caaf6fe69749a6d8f", 5069),
    "WRF/test/rrtmgp/test_udm_rain_only_slopes.py": ("b287ddb29ac58fb9abda16077c6b38c0b22baef5b691bd64bd22bf54daae94ea", 21389),
    "WRF/test/rrtmgp/test_udm_rain_only_slopes_scm.py": ("55408198200934897b454cf74e177b37ad4223b5646218b5637d30a4e61796be", 41045),
    "WRF/test/rrtmgp/test_udm_entry_density.py": ("364d163bceaa3773d246b741e4f7c181e1efd5a328d9817d0220a1f6ec43e4cb", 33672),
    "WRF/test/rrtmgp/test_udm_radius_stage.py": ("4a0117959f3b716c52bb3e2fdc051715956299019cc5ff4aa84e8de63b9b4fe8", 21254),
}


def need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pin(path: Path) -> dict:
    need(path.is_file() and not path.is_symlink(), f"missing or symlinked file: {path}")
    raw = path.read_bytes()
    return {"sha256": sha(raw), "size_bytes": len(raw)}


def read_json(path: Path) -> dict:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return json.loads(raw)


def normalize_paths(value):
    if isinstance(value, dict):
        return {k: (Path(v).name if k == "path" and isinstance(v, str) and v.startswith("/")
                    else normalize_paths(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_paths(v) for v in value]
    return value


def load_parser(path: Path):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("_rain_slopes_entry_parser", path)
    need(spec is not None and spec.loader is not None, "cannot load archived entry parser")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def check_logs(pkg: Path) -> int:
    index = read_json(pkg / "logs/log-index.json")
    entries = index.get("entries")
    need(isinstance(entries, list) and entries, "log index has no entries")
    seen = set()
    for row in entries:
        rel = row.get("payload_path", "")
        need(rel and rel not in seen, f"duplicate/empty log-index path: {rel}")
        seen.add(rel)
        p = pkg / rel
        need(row.get("receipt_ref") and (pkg / row["receipt_ref"]).is_file(),
             f"missing referenced receipt for log: {rel}")
        raw_gz = p.read_bytes()
        need(sha(raw_gz) == row["gzip_sha256"] and len(raw_gz) == row["gzip_size_bytes"],
             f"gzip log pin mismatch: {rel}")
        raw = gzip.decompress(raw_gz)
        need(sha(raw) == row["source_sha256"] and len(raw) == row["source_size_bytes"],
             f"decompressed log pin mismatch: {rel}")
    actual = {p.relative_to(pkg).as_posix() for p in (pkg / "logs").rglob("*.gz")}
    need(actual == seen, "log gzip roster differs from log-index.json")
    return len(entries)


def check_captures(pkg: Path) -> tuple[int, int]:
    tool_dir = pkg / "tools/WRF/test/rrtmgp"
    parser_path = tool_dir / "test_udm_entry_density.py"
    radius_path = tool_dir / "test_udm_radius_stage.py"
    for p in (parser_path, radius_path):
        need(p.is_file() and not p.is_symlink(), f"missing parser: {p}")
    parser = load_parser(parser_path)
    total_packets = total_levels = 0
    for name in ("cold", "warm"):
        cap = pkg / "captures" / name
        entries = sorted(p for p in cap.glob("*.raw") if p.name.startswith("udm_entry_density_"))
        radii = sorted(p for p in cap.glob("*.raw") if p.name.startswith("udm_radius_"))
        need(len(entries) == 6 and len(radii) == 6,
             f"{name}: expected six entry and six post-radius packets")
        report = parser.inspect(cap, cap)
        need(report["status"] == "ENTRY_DENSITY_DIAGNOSTIC_CONTRACT_CHECKED", f"{name}: parser status")
        need(report["schema"] == "UDM_ENTRY_DENSITY_CONTRACT_V2", f"{name}: V2 schema required")
        need(report["packet_count"] == 6 and report.get("join_count") == 6, f"{name}: join count")
        need(len(report["post_radius_joins"]) == 6, f"{name}: missing joins")
        need(all(x["same_call_key_exact"] and x["time_seconds_exact"] is not None
                 and x["DEN_unchanged_binary32"] for x in report["post_radius_joins"]),
             f"{name}: identity/time/DEN join failed")
        need(all(x["version"] == 2 and x["source_time_present"] == 1 for x in report["entry_packets"]),
             f"{name}: entry version/clock mismatch")
        total_levels += sum(len(x["levels"]) for x in report["entry_packets"])
        archived = read_json(pkg / f"analysis/{name}-entry-density-report.json.gz")
        need(json.dumps(normalize_paths(report), sort_keys=True, allow_nan=True) ==
             json.dumps(normalize_paths(archived), sort_keys=True, allow_nan=True),
             f"{name}: recomputed raw packet report differs from archived report")
        total_packets += len(entries) + len(radii)
    need(total_packets == 24 and total_levels == 708, "capture totals differ from 24 packets / 708 levels")
    return total_packets, total_levels


def check_receipts(pkg: Path) -> dict:
    scm1 = read_json(pkg / "receipts/scm-v1-failed-execution.json.gz")
    scm2 = read_json(pkg / "receipts/scm-v2-execution.json.gz")
    build = read_json(pkg / "receipts/fresh-build-execution.json.gz")
    n1 = read_json(pkg / "receipts/native-run-v1-comparator-failure.json.gz")
    n2 = read_json(pkg / "receipts/native-run-v2-pass.json.gz")
    n3 = read_json(pkg / "receipts/native-run-v3.json.gz")
    controls = read_json(pkg / "receipts/native-rain-only-controls-v2.json.gz")
    review = read_json(pkg / "reviews/independent-runtime-review.json.gz")
    need(scm1["status"] == "FAIL_PRESERVED" and scm1["actual_forecast_invocations"] == 2
         and "expected six entry packets, got 0" in scm1.get("failure", ""),
         "SCM v1 historical runner failure receipt changed")
    need(scm2["status"] == "PASS_SCOPED_RAIN_ONLY_SLOPES_SCM_CONTRACT"
         and scm2["actual_forecast_invocations"] == 6
         and scm2["standalone_rte_invocations"] == 0, "SCM v2 receipt is not scoped PASS")
    need(len(scm2["arms"]) == 6 and all(a["status"] == "PASS_OUTPUTS_VALIDATED" and a["returncode"] == 0
                                         for a in scm2["arms"].values()),
         "SCM v2 per-arm status/returncode mismatch")
    strict_names = {"cold_37_off_vs_on", "warm_37_off_vs_on", "cold_4_vs_archive", "warm_4_vs_archive"}
    for name in strict_names:
        row = scm2["comparisons"][name]
        need(row["status"] == "PASS_STRICT_IDENTITY" and row["whole_file_byte_identical"],
             f"SCM strict control failed: {name}")
    for name in ("cold_37_off_vs_archive", "cold_37_on_vs_archive",
                 "warm_37_off_vs_archive", "warm_37_on_vs_archive"):
        need(scm2["comparisons"][name]["comparison_scope"] == "descriptive-archive-difference",
             f"archive comparison must remain descriptive: {name}")
    need(build["status"] == "BUILD_PASS_SCOPED" and build["base_head"] == "e3b9e52c2a20811830a27d34420721ca89b62e59",
         "fresh build receipt/base mismatch")
    need(set(build["overlay"]) == {"WRF/phys/module_mp_udm.F"}
         and build["overlay"]["WRF/phys/module_mp_udm.F"]["sha256"] == EXPECTED_SOURCE["WRF/phys/module_mp_udm.F"][0],
         "build overlay/source pin mismatch")
    need(n1["status"] == "FAIL_PRESERVED_STOPPED", "native v1 failure was not preserved")
    need(n2["status"] == "PASS_SCOPED_RAIN_ONLY_SLOPE_INITIALIZATION", "native v2 receipt missing")
    need(n3["status"] == "PASS_SCOPED_RAIN_ONLY_SLOPE_INITIALIZATION", "native v3 receipt missing")
    need(n3["counts"] == {"REAL_calls": 0, "RTE_calls": 0, "WRF_forecasts": 0,
                           "compile_link_processes": 20, "fixture_executions": 20},
         "native v3 scope/count mismatch")
    need(n3["candidate_source_sha256"] == EXPECTED_SOURCE["WRF/phys/module_mp_udm.F"][0],
         "native v3 candidate source pin mismatch")
    need(n3["driver_sha256"] == EXPECTED_SOURCE["WRF/test/rrtmgp/test_udm_rain_only_slopes.f90"][0],
         "native v3 driver pin mismatch")
    need(len(n3["processes"]) == 40 and all(not p["timed_out"] for p in n3["processes"]),
         "native v3 process ledger mismatch")
    for opt in ("O0", "O2"):
        baseline = n3["results"][opt]["baseline"]
        candidate = n3["results"][opt]["candidate"]
        for case in ("rain_only", "rain_above_cloud"):
            need(baseline[case]["actual_returncode"] == -8 and baseline[case]["trap_marker_observed"],
                 f"native v3 inherited hazard control mismatch: {opt}/{case}")
            need(candidate[case]["result_keys"] and len(candidate[case]["result_keys"]) == 9,
                 f"native v3 candidate profile missing results: {opt}/{case}")
    need(all(x.get("observed") is False for x in n3["shrink_retention_controls"]),
         "native v3 must not be represented as observing shrink retention")
    review3 = read_json(pkg / "reviews/native-run-v3-runtime-review.json.gz")
    need(review3["status"] == "PASS_SCOPED_RUN_V3_READBACK"
         and review3["receipt_contract"]["status"] == n3["status"]
         and review3["independent_log_checks"]["defined_control_parity"]["comparisons"] == 54
         and review3["independent_log_checks"]["actual_marker_readback"]["shrink_or_retention_observed"] is False,
         "independent native v3 readback mismatch")
    need(controls["status"] == "PASS_EXPECTED_INHERITED_RAIN_ONLY_TRAPS", "inherited control receipt mismatch")
    need(review["status"] == "PASS_SCOPED", "independent SCM review status mismatch")
    return {"scm_forecast_invocations": 8, "native_fixture_generations": 3,
            "native_compile_link_processes_v3": 20, "native_fixture_executions_v3": 20,
            "native_v3_compiles_and_fixtures": 40,
            "native_shrink_retention_observed": False}


def verify(package: Path, repo: Path) -> dict:
    package = package.resolve()
    manifest_path = package / "manifest.json"
    need(manifest_path.is_file(), "manifest.json is required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    need(manifest.get("schema") == SCHEMA, "manifest schema mismatch")
    rows = manifest.get("files")
    need(isinstance(rows, list) and rows, "manifest payload roster missing")
    roster = {}
    for row in rows:
        rel = row.get("path", "")
        need(rel and rel not in roster and not Path(rel).is_absolute() and ".." not in Path(rel).parts,
             f"invalid/duplicate manifest path: {rel}")
        roster[rel] = row
    actual = {p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file() and p != manifest_path}
    need(not any(p.is_symlink() for p in package.rglob("*")), "symlinks are forbidden in the sealed package")
    need(actual == set(roster), f"payload roster mismatch missing={sorted(set(roster)-actual)} extra={sorted(actual-set(roster))}")
    for rel, row in roster.items():
        p = package / rel
        got = pin(p)
        need(got["sha256"] == row.get("sha256") and got["size_bytes"] == row.get("size_bytes"),
             f"payload hash/size mismatch: {rel}")
    source_rows = manifest.get("source_pins")
    need(isinstance(source_rows, list) and source_rows, "source_pins missing")
    need({row.get("path") for row in source_rows} == set(EXPECTED_SOURCE),
         "source pin roster differs from the required eight-source set")
    for row in source_rows:
        rel = row.get("path", "")
        need(rel and not Path(rel).is_absolute() and ".." not in Path(rel).parts, f"bad source pin path {rel}")
        p = repo / rel
        got = pin(p)
        need(got["sha256"] == row.get("sha256") and got["size_bytes"] == row.get("size_bytes"),
             f"source pin mismatch: {rel}")
    for rel, expected in EXPECTED_SOURCE.items():
        got = pin(repo / rel)
        need((got["sha256"], got["size_bytes"]) == expected, f"compiled source changed: {rel}")
    log_count = check_logs(package)
    packet_count, level_count = check_captures(package)
    receipt_summary = check_receipts(package)
    return {"status": "PASS_SCOPED_RAIN_ONLY_CLOUD_SLOPE_EVIDENCE",
            "payload_files": len(rows), "source_pins": len(source_rows),
            "logs": log_count, "capture_packets": packet_count, "native_levels": level_count,
            **receipt_summary,
            "limitations": ["No precipitation accuracy or domain-wide conservation claim.",
                            "Corrected native fixture did not observe cloud-top shrink/retention."]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        result = verify(Path(__file__).resolve().parent, args.repo_root.resolve())
        text = json.dumps(result, indent=2, sort_keys=True) + "\n"
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
