#!/usr/bin/env python3
"""Authenticate the dry-sedimentation density archive and recheck V2 packets."""
import argparse
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[2]
EXPECTED_SOURCES = {
    "WRF/phys/module_mp_udm.F": "7998df8f1f6a3b9f63f285a60016447cbbcf4802b7a31a711442c90b8c59a8fc",
    "WRF/phys/module_microphysics_driver.F": "7e15f93341b1fa079136aa60b2f2061c6e7844f107446ae8e7951edff00820fb",
    "WRF/phys/module_ra_rrtmgp_trace.F": "c08a1cae7a93f85a08ed59042aa1b98dc1ef6b42d33c6f344b93a9eca9d652e9",
    "WRF/phys/module_mp_radar.F": "fa5e06a4d64bbc32089a1357bfa5c57e6c682e5b68c706842698c2b0f292e68e",
    "WRF/phys/module_gfs_machine.F": "300ee4f75663e89d34c8a9b8733cc07a5dd48c3d973da019d31cb76524babe25",
    "WRF/test/rrtmgp/test_udm_entry_density.py": "364d163bceaa3773d246b741e4f7c181e1efd5a328d9817d0220a1f6ec43e4cb",
    "WRF/test/rrtmgp/test_udm_radius_stage.py": "4a0117959f3b716c52bb3e2fdc051715956299019cc5ff4aa84e8de63b9b4fe8",
    "WRF/test/rrtmgp/test_udm_sedimentation_density.py": "b64e6b7184cbd0d3d3c0ac96324dc77f0dceffc19450ac1bde4c9eaad76c161b",
    "WRF/test/rrtmgp/test_udm_sedimentation_density.f90": "865d2c71653d20ab074ee198124e4f731e3e14631265eb4c2f664f916bec303d",
}
EXPECTED_ARCHIVED_ORIGINS = {
    "receipts/scm-execution.json.gz": ("build/udm37-dry-sed-scm-v1/execution.json", "98177c9cc0c88d48679b350042b1a0f101e7e5f43877bfec5430ac28a177a6ca", 1141995),
    "receipts/fresh-build-execution.json.gz": ("build/udm37-dry-sed-build-v2/run-v1/execution.json", "e429892e7f288f0c2dadf947e24d102a0f6a8bbdca5b260d1a3103587d34439f", 3177884),
    "receipts/zero-compile-build-preflight-failure.json.gz": ("build/udm37-dry-sed-build-v1/run-v1/execution.json", "af99e728bb558558c126fa74b5bd535fc4a117a16762bf0fc4de046803a07602", 1895),
    "receipts/scm-cli-nameerror-preflight-failure.json.gz": ("build/udm37-dry-sed-runner-contract-v1/preflight-failure-v1.json", "bf03d1e384f37f8baad72041e10e0fdf2146a29a24ecf5b1d2fe540a2ede0c25", 1154),
    "receipts/native-fixture-summary.json.gz": ("build/udm37-dry-sed-native-test-v1/summary.json", "31d122c05066aa7e833b7eb1bf24a29d6b755388822e28e36a91950cf3b4d2d5", 13158),
    "receipts/native-fixture-attempt-01.json.gz": ("build/udm37-dry-sed-native-test-v1/attempt-01/receipt.json", "d9e29bcf4a13f3161b2d81b5648883cbcc0ee998f30ec0e5ce043637b7c98821", 12460),
    "receipts/native-fixture-attempt-02.json.gz": ("build/udm37-dry-sed-native-test-v1/attempt-02/receipt.json", "d54e06bcb591df2c1f5151590ee6e1756b2c97a56dad700539af2d42f9803108", 12474),
    "receipts/native-fixture-attempt-03.json.gz": ("build/udm37-dry-sed-native-test-v1/attempt-03/receipt.json", "b12bd40115ccee2ca269ef732f05d3aae4fe42c21de4bd6797d3e16a12b38d5e", 47577),
    "receipts/native-hazard-source.json.gz": ("build/udm37-dry-sed-native-test-v1/hazard-source.json", "3c28cc41fde938c380547fbe4e6b8a883d4b2006e01b7eb7efa076718cbd850a", 3014),
    "receipts/density-source-review.json.gz": ("build/udm37-dry-sed-source-review-v1/source-review.json", "1090d2f785d217e53ee4c0359f05e1c6c0005e376a030ca42c99eb648aa55abc", 4254),
    "receipts/runner-contract-attempt.json.gz": ("build/udm37-dry-sed-runner-contract-v1/contract-attempt-01.json", "0d0c70d49915d4907855d3948dae386d462280fd8ece311ec82bb75f99905141", 1486),
    "receipts/runner-contract-preflight-failure.json.gz": ("build/udm37-dry-sed-runner-contract-v1/preflight-failure-v1.json", "bf03d1e384f37f8baad72041e10e0fdf2146a29a24ecf5b1d2fe540a2ede0c25", 1154),
    "receipts/rain-only-control-v1.json.gz": ("build/udm37-dry-sed-native-test-v1/rain-only-controls-v1/execution.json", "ff99293e6f60529b30b4873009bc034d353a55ba8c60fd86eea718771550e671", 4157),
    "receipts/rain-only-control-v2.json.gz": ("build/udm37-dry-sed-native-test-v1/rain-only-controls-v2/execution.json", "8313d06173e876c9a1cdbf9028e942c170873ccfcee939c8001e4d7ab08905c0", 4432),
    "receipts/independent-runtime-review.json.gz": ("build/udm37-dry-sed-runtime-review-v1/review.json", "59bfcd360c5f9a3abe1e82fddd11d62170eb726b724b110ce6701bb59091053f", 127496),
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pin(path):
    data = path.read_bytes()
    return {"sha256": sha(data), "size_bytes": len(data)}


def checked(root, name):
    rel = Path(name)
    require(name and not rel.is_absolute() and ".." not in rel.parts, "unsafe path")
    path = root / rel
    require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()),
            "missing/escaped file: " + name)
    return path


def checked_dir(root, name):
    rel = Path(name)
    require(name and not rel.is_absolute() and ".." not in rel.parts, "unsafe directory path")
    path = root / rel
    require(path.is_dir() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()),
            "missing/escaped directory: " + name)
    return path


def archive_json(name):
    return json.loads(gzip.decompress(checked(PACKAGE, name).read_bytes()))


def portable(value):
    # Runtime absolute packet paths relocate; all other report content is exact.
    if isinstance(value, dict):
        return {k: portable(v) for k, v in value.items() if k != "path"}
    if isinstance(value, list):
        return [portable(v) for v in value]
    return value


def build_relative(path_text):
    parts = Path(path_text).parts
    try:
        idx = parts.index("build")
    except ValueError:
        raise ValueError("receipt path has no build/ anchor")
    return Path(*parts[idx:]).as_posix()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-root", type=Path, default=REPO)
    args = ap.parse_args()
    source_root = args.source_root.resolve()
    manifest = json.loads(checked(PACKAGE, "manifest.json").read_text())
    require(manifest.get("schema") == "UDM_DRY_SEDIMENTATION_DENSITY_EVIDENCE_V1", "manifest schema")

    rows = manifest.get("payload")
    require(isinstance(rows, list), "payload roster")
    names = [r.get("path") for r in rows if isinstance(r, dict)]
    require(len(names) == len(rows) == len(set(names)), "duplicate or malformed payload rows")
    require(all(set(r) == {"path", "sha256", "size_bytes"} for r in rows), "payload row schema")
    for row in rows:
        require(pin(checked(PACKAGE, row["path"])) == {"sha256": row["sha256"], "size_bytes": row["size_bytes"]},
                "payload pin mismatch: " + row["path"])
    actual = {p.relative_to(PACKAGE).as_posix() for p in PACKAGE.rglob("*")
              if p.is_file() and p != PACKAGE / "manifest.json" and "__pycache__" not in p.parts}
    require(actual == set(names), "closed payload roster mismatch")
    origins = manifest.get("archive_origins")
    require(isinstance(origins, list), "archive origins")
    require({r.get("archive_path"): (r.get("origin_path"), r.get("sha256"), r.get("size_bytes"))
             for r in origins} == EXPECTED_ARCHIVED_ORIGINS, "archive origin roster/pins changed")
    for archive_path, (origin_path, expected_sha, expected_size) in EXPECTED_ARCHIVED_ORIGINS.items():
        raw = gzip.decompress(checked(PACKAGE, archive_path).read_bytes())
        require(len(raw) == expected_size and sha(raw) == expected_sha,
                "compressed original receipt differs: " + archive_path)

    source_rows = manifest.get("sources")
    require(isinstance(source_rows, list), "source pins")
    source_names = [r.get("path") for r in source_rows if isinstance(r, dict)]
    require(len(source_names) == len(source_rows) == len(set(source_names)), "duplicate/malformed source rows")
    require({r["path"]: r["sha256"] for r in source_rows} == EXPECTED_SOURCES, "source roster/pin constants changed")
    for row in source_rows:
        p = checked(source_root, row["path"])
        require(pin(p) == {"sha256": row["sha256"], "size_bytes": row["size_bytes"]}, "source pin mismatch: " + row["path"])

    # Validate archived original receipts, including the preserved failed attempts.
    scm = archive_json("receipts/scm-execution.json.gz")
    require(scm["status"] == "PASS_SCOPED_DRY_DEND_PASSIVITY_AND_4_ARCHIVE_REGRESSION", "SCM receipt status")
    require(scm["actual_forecast_invocations"] == 6 and scm["model_attempts_started"] == 6
            and scm["standalone_rte_invocations"] == 0, "SCM call counts")
    require(set(scm["arms"]) == {"cold-37-off", "cold-37-on", "cold-4", "warm-37-off", "warm-37-on", "warm-4"}, "SCM arms")
    require(all(a["returncode"] == 0 and a["status"] == "PASS_OUTPUTS_VALIDATED" for a in scm["arms"].values()), "SCM arm failure")
    for tag in ("cold", "warm"):
        off_on = scm["comparisons"][tag + "_37_off_vs_on"]
        require(off_on["status"] == "PASS_STRICT_IDENTITY" and off_on["whole_file_byte_identical"]
                and off_on["strict_all_array_data_and_masks_equal"] and off_on["all_metadata_equal"], tag + " off/on passivity")
        ordinary4 = scm["comparisons"][tag + "_4_vs_archive"]
        require(ordinary4["status"] == "PASS_STRICT_IDENTITY" and ordinary4["whole_file_byte_identical"]
                and ordinary4["strict_all_array_data_and_masks_equal"], tag + " RRTMGP4 archive control")
        require(scm["comparisons"][tag + "_37_on_vs_archive"]["status"] == "RECORDED_DESCRIPTIVE_ARCHIVE_DIFFERENCES",
                tag + " archive differences must remain descriptive")

    build = archive_json("receipts/fresh-build-execution.json.gz")
    require(build["status"] == "BUILD_PASS_SCOPED" and build["build_command_invocations"] == 1
            and build["build_invocation"]["returncode"] == 0 and build["model_invocations"] == 0
            and build["standalone_RTE_invocations"] == 0 and build["success_footer_seen"], "fresh build receipt")
    require(build["source_manifest_before"] == build["source_manifest_after"]
            and len(build["source_manifest_before"]) == 7894, "fresh build source immutability")
    old_build = archive_json("receipts/zero-compile-build-preflight-failure.json.gz")
    require(old_build["status"] == "PREFLIGHT_FAILED_PRESERVED" and old_build["build_command_invocations"] == 0
            and old_build["model_invocations"] == 0, "preserved zero-compile build failure")
    nameerror = archive_json("receipts/scm-cli-nameerror-preflight-failure.json.gz")
    require(nameerror["status"] == "FAIL_PREFLIGHT_NO_OUTPUT_ROOT_OR_FORECAST"
            and nameerror["forecast_invocations"] == 0 and nameerror["build_invocations"] == 0,
            "preserved SCM preflight failure")

    summary = archive_json("receipts/native-fixture-summary.json.gz")
    require(summary["status"] == "PASS_SCOPED_WITH_INHERITED_RAIN_ONLY_HAZARD_PRESERVED", "native fixture status")
    counts = summary["actual_process_counts"]
    require(counts["WRF_forecasts"] == counts["full_WRF_builds"] == counts["REAL_calls"] == counts["RTE_calls"] == 0,
            "native fixture call counts")
    require(counts["successful_outer_UDM_calls"] == 48 and counts["isolated_native_sedimentation_calls"] == 16,
            "native fixture call totals")
    attempt01 = archive_json("receipts/native-fixture-attempt-01.json.gz")
    attempt02 = archive_json("receipts/native-fixture-attempt-02.json.gz")
    require(attempt01["status"] == "FAIL_PRESERVED_STOPPED" and attempt02["status"] == "FAIL_PRESERVED_STOPPED",
            "native fixture attempts 01/02 must remain preserved failures")
    attempt = archive_json("receipts/native-fixture-attempt-03.json.gz")
    require(attempt["status"] == "PASS_SCOPED_NATIVE_SEDIMENTATION_AND_COMPATIBILITY", "native final attempt")
    hazard = archive_json("receipts/native-hazard-source.json.gz")
    require(hazard.get("status") or hazard.get("schema"), "native rain-only hazard receipt empty")
    source_review = archive_json("receipts/density-source-review.json.gz")
    require(source_review["status"] == "PASS_SCOPED_STATIC_REVIEW_NO_BUILD_OR_RUNTIME", "source review")
    runner_failure = archive_json("receipts/runner-contract-preflight-failure.json.gz")
    require(runner_failure["status"] == "FAIL_PREFLIGHT_NO_OUTPUT_ROOT_OR_FORECAST" and runner_failure["forecast_invocations"] == 0,
            "runner contract failure retained")
    runner_control = archive_json("receipts/runner-contract-attempt.json.gz")
    require(runner_control["status"] == "FAIL_EXPECTED_CONTROL_EXCEPTION_NOT_CAUGHT"
            and runner_control["forecast_build_rte_invocations"] == 0, "runner source-control failure retained")

    # The log archive itself records exact original log bytes and must join to
    # the log pins in the immutable SCM/build receipts where applicable.
    log_archive = json.loads(gzip.decompress(checked(PACKAGE, "archives/execution-logs.json.gz").read_bytes()))
    require(log_archive["schema"] == "UDM_DRY_SEDIMENTATION_LOG_ARCHIVE_V1", "log archive schema")
    log_by_path = {}
    for row in log_archive["files"]:
        require(row["path"] not in log_by_path, "duplicate log path")
        data = base64.b64decode(row["content_base64"], validate=True)
        require(len(data) == row["size_bytes"] and sha(data) == row["sha256"], "log archive inner hash")
        log_by_path[row["path"]] = row
    build_log = build_relative(build["build_invocation"]["log_pin"]["path"])
    require(build_log in log_by_path and log_by_path[build_log]["sha256"] == build["build_invocation"]["log_pin"]["sha256"],
            "full-build log join")
    for arm_name in ("cold-37-off", "cold-37-on", "cold-4", "warm-37-off", "warm-37-on", "warm-4"):
        arm = scm["arms"][arm_name]
        rel_log = build_relative(arm["log_pin"]["path"])
        require(rel_log in log_by_path and log_by_path[rel_log]["sha256"] == arm["log_pin"]["sha256"],
                "SCM log join: " + arm_name)
    failure_log = build_relative(runner_failure["stdout_log_pin"]["path"])
    require(failure_log in log_by_path and log_by_path[failure_log]["sha256"] == runner_failure["stdout_log_pin"]["sha256"],
            "preserved SCM preflight log join")

    # Reparse current source against the archived packet bytes and compare with
    # the saved report while ignoring only relocated absolute path strings.
    parser_path = checked(source_root, "WRF/test/rrtmgp/test_udm_entry_density.py")
    spec = importlib.util.spec_from_file_location("_density_evidence_parser", parser_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    case_summaries = {}
    for tag, arm_name in (("cold", "cold-37-on"), ("warm", "warm-37-on")):
        cap = checked_dir(PACKAGE, "capture/" + tag)
        fresh = mod.inspect(cap, cap)
        saved = json.loads(checked(PACKAGE, "analysis/" + tag + "-entry-density-report.json").read_text())
        require(portable(fresh) == portable(saved), tag + " parser report differs")
        require(fresh["schema"] == "UDM_ENTRY_DENSITY_CONTRACT_V2" and fresh["packet_count"] == 6
                and fresh["join_count"] == 6, tag + " V2 packet/join counts")
        steps = [x["identity"]["step"] for x in fresh["entry_packets"]]
        require(steps == list(range(1, 7)), tag + " step roster")
        require(all(x["version"] == 2 and x["input_density_is_dry"] == 1 for x in fresh["entry_packets"]),
                tag + " selected density policy")
        require(all(x["source_time_seconds"] == (x["identity"]["step"]-1)*10 for x in fresh["entry_packets"]),
                tag + " time roster")
        require(all(len(x["levels"]) == 59 for x in fresh["entry_packets"]), tag + " level count")
        require(all(level["DEND_REEVALUATED_PRECALL_KG_M3"] == level["DEN_PASSED_KG_M3"]
                    for packet in fresh["entry_packets"] for level in packet["levels"]), tag + " selected DEN identity")
        require(all(join["DEN_unchanged_binary32"] for join in fresh["post_radius_joins"]), tag + " DEN join")
        pin_rows = {r["name"]: r for r in scm["arms"][arm_name]["entry_packet_pins"] + scm["arms"][arm_name]["radius_packet_pins"]}
        for packet_file in sorted(cap.glob("*.raw")):
            require(packet_file.name in pin_rows, tag + " unlisted packet")
            require(pin(packet_file) == {"sha256": pin_rows[packet_file.name]["sha256"],
                                        "size_bytes": pin_rows[packet_file.name]["size_bytes"]},
                    tag + " raw packet differs from SCM receipt: " + packet_file.name)
        require(len(list(cap.glob("udm_entry_density_*.raw"))) == 6
                and len(list(cap.glob("udm_radius_*.raw"))) == 6, tag + " raw family counts")
        case_summaries[tag] = {"entry_packets": 6, "post_radius_packets": 6, "joined_levels": 354,
                               "selected_DEN_exact": True, "report_recomputed": True}

    result = {"status": "PASS_SCOPED_DRY_SEDIMENTATION_DENSITY_EVIDENCE",
              "cases": case_summaries, "payload_count": len(names), "source_count": len(source_rows),
              "archived_log_count": len(log_by_path), "native_fixture_attempts_preserved": 3,
              "build_invocations_in_successful_build": 1, "SCM_forecasts": 6,
              "fresh_build_model_RTE_calls": 0,
              "scope": "saved density packets, selected/counterfactual equations, exact joins and recorded SCM/native-fixture contracts; no independent physical-density or accuracy claim"}
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
