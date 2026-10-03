#!/usr/bin/env python3
"""Offline validation of a completed selected-column OFF/ON runtime pair."""
from __future__ import annotations
import argparse, csv, datetime as dt, hashlib, importlib.util, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run_selected_column_audit.py"
SPEC = importlib.util.spec_from_file_location("selected_runner", RUNNER)
runner = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(runner)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture_check(run: Path, phase: str, expected_step: int, expected_seconds: float) -> dict:
    cap = run / "capture"
    raw_path, input_path, result_path = (cap / f"{phase.lower()}.{ext}" for ext in ("raw", "input", "result"))
    raw, raw_header = runner.parse_raw_records(raw_path)
    input_records, input_dims, input_header = runner.parse_replay_input(input_path)
    result, result_dims, result_header = runner.parse_result_records(result_path)
    phase_meta = raw_header[1].split()
    if phase_meta != [phase, "169", "80", "39"]:
        raise RuntimeError(f"{phase}: unexpected raw capture coordinates/layers {phase_meta}")
    input_meta = input_header[1].split()
    if input_header[0] not in {"RRTMGP_REPLAY_V8", "RRTMGP_REPLAY_V9"} or len(input_meta) != 6:
        raise RuntimeError(f"{phase}: unsupported replay capture header {input_header}")
    if input_meta[0] != phase or int(input_meta[1]) != 1:
        raise RuntimeError(f"{phase}: replay input phase/column mismatch")
    engine_nl = int(input_meta[2])
    if input_dims != [1, engine_nl, int(input_meta[3]), int(input_meta[4]), int(input_meta[5])]:
        raise RuntimeError(f"{phase}: inconsistent replay dimensions")
    if result_header[0] != "RRTMGP_RESULT_V1" or result_dims != [1, engine_nl]:
        raise RuntimeError(f"{phase}: result dimensions differ from replay input")
    if "PI" not in raw or len(raw["PI"]) != 39 or not all(__import__("math").isfinite(x) and x > 0 for x in raw["PI"]):
        raise RuntimeError(f"{phase}: native PI must be 39 finite positive values")
    if "WRF_THETA_HR" not in result or len(result["WRF_THETA_HR"]) != 39:
        raise RuntimeError(f"{phase}: expected 39-level native WRF_THETA_HR result")
    step = int(round(raw["RADIATION_STEP"][0]))
    source_seconds = raw["SOURCE_TIME_SECONDS"][0]
    if step != expected_step or abs(source_seconds - expected_seconds) > 1.e-3:
        raise RuntimeError(f"{phase}: captured step/time {step}/{source_seconds} != {expected_step}/{expected_seconds}")
    if "FROZEN_TABLE_SHA256_BYTES" not in input_records:
        raise RuntimeError(f"{phase}: replay input omitted frozen table digest")
    frozen_sha = "".join(chr(int(round(v))) for v in input_records["FROZEN_TABLE_SHA256_BYTES"])
    if frozen_sha != runner.ASSET_SHA["frozen-ice-psd-moments.nc"]:
        raise RuntimeError(f"{phase}: frozen table digest mismatch {frozen_sha}")
    return {"phase": phase, "step": step, "source_seconds": source_seconds,
            "raw_native_layers": 39, "engine_layers": engine_nl,
            "header_versions": {"raw": raw_header[0], "input": input_header[0], "result": result_header[0]},
            "frozen_table_sha256": frozen_sha,
            "files": {p.suffix.lstrip("."): {"path": str(p), "sha256": sha(p)}
                      for p in (raw_path, input_path, result_path)},
            "pi_finite_positive": True, "theta_heating_native_levels": 39}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", type=Path, required=True)
    ap.add_argument("--off-run-dir", type=Path, required=True)
    ap.add_argument("--on-run-dir", type=Path, required=True)
    ap.add_argument("--off-receipt", type=Path, required=True)
    ap.add_argument("--on-receipt", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    ws, off, on = args.workspace.resolve(), args.off_run_dir.resolve(), args.on_run_dir.resolve()
    out = args.output.resolve()
    if out.exists():
        ap.error(f"refusing existing evidence path: {out}")
    off_rec, on_rec = json.loads(args.off_receipt.read_text()), json.loads(args.on_receipt.read_text())
    if off_rec.get("status") != "OFF_COMPLETE_AWAITING_ON" or on_rec.get("status") != "FAIL":
        raise RuntimeError("expected completed OFF and preserved ON validator-failure receipts")
    if off_rec.get("executable_sha256") != on_rec.get("executable_sha256"):
        raise RuntimeError("OFF/ON executable hashes differ")
    if off_rec.get("source_tree_sha256") != on_rec.get("source_tree_sha256"):
        raise RuntimeError("OFF/ON source manifest hashes differ")
    source = Path(off_rec["source_root"]).resolve()
    exe = Path(off_rec["binary_path"]).resolve()
    manifest_sha, manifest_info = runner.verify_build_manifest(ws, source, exe)
    if manifest_sha != off_rec["source_tree_sha256"]:
        raise RuntimeError("post-run source manifest differs from the launch receipt")
    shared_after = runner.snapshot_shared_assets(source, ws)
    if shared_after != off_rec["source_asset_hashes"] or shared_after != on_rec["source_asset_hashes"]:
        raise RuntimeError("shared coefficient/input/LUT assets changed during runs")
    case_immutable = {}
    for tag, case_key, run_dir in (("off", "audit-off", off), ("on", "audit-on", on)):
        expected = (off_rec if tag == "off" else on_rec)["cases"][case_key]["immutable_assets"]
        actual = runner.immutable_tree_hashes(run_dir)
        if actual != expected:
            raise RuntimeError(f"{tag.upper()} immutable staged assets changed after WRF")
        case_immutable[tag] = {"file_count": len(actual), "matches_launch_snapshot": True}
    for filename in ("namelist.input", "wrfinput_d01", "wrfbdy_d01",
                     "wrfrst_d01_2010-06-11_12:00:00", "selected_audit_iofields.txt"):
        if sha(off / filename) != sha(on / filename):
            raise RuntimeError(f"OFF/ON immutable input differs: {filename}")
    # Confirm ON forecast itself completed successfully despite the known validator parser failure.
    on_log = on / "wrf.stdout.log"
    log_text = on_log.read_text(errors="replace")
    if "SUCCESS COMPLETE WRF" not in log_text:
        raise RuntimeError("ON WRF run lacks its success marker")
    audit_path = on / "audit/same_state.csv"
    with audit_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    audit = runner.parse_audit(audit_path)
    if audit["activations"] != [{"step": 721, "source_seconds": 43200.0},
                                 {"step": 731, "source_seconds": 43800.0}]:
        raise RuntimeError(f"unexpected observed activation schedule: {audit['activations']}")
    captures = {phase: capture_check(on, phase, 731, 43800.0) for phase in ("LW", "SW")}
    raw_captures = {phase: runner.parse_raw_records(on / f"capture/{phase.lower()}.raw")[0]
                    for phase in ("LW", "SW")}
    history = runner.compare_history(off, on, rows, dt.datetime(2010, 6, 11, 0, 0), raw_captures)
    if not history["numeric_fields_bitwise_equal"]:
        raise RuntimeError("OFF/ON numeric history is not bitwise identical")
    if not history["metadata_equal"]:
        raise RuntimeError("OFF/ON metadata differs; inspect emitted metadata differences")
    off_histories = sorted(off.glob("wrfout_d01_*"))
    on_histories = sorted(on.glob("wrfout_d01_*"))
    output_hashes = {"off_history": {p.name: sha(p) for p in off_histories},
                     "on_history": {p.name: sha(p) for p in on_histories},
                     "off_stdout_log": sha(off / "wrf.stdout.log"),
                     "on_stdout_log": sha(on_log),
                     "audit_csv": sha(audit_path)}
    output = {"schema": "UDM_SELECTED_REAL_AUDIT_VALIDATION_V2",
              "status": "PASS_HISTORY_AND_CAPTURE_CONTRACTS",
              "scope": "post-run offline validation; no forecast rerun",
              "source_tree_sha256": off_rec["source_tree_sha256"],
              "executable_sha256": off_rec["executable_sha256"],
              "post_run_source_manifest": manifest_info,
              "post_run_shared_assets_unchanged": True,
              "post_run_case_immutable_assets": case_immutable,
              "off_on_inputs_identical": True,
              "launch_runner_sha256": sha(HERE / "runner-on-450f9267.py"),
              "offline_validator_sha256": sha(Path(__file__).resolve()),
              "corrected_runner_source_sha256": sha(RUNNER),
              "failed_launch_receipt_preserved": str(args.on_receipt.resolve()),
              "failed_launch_receipt_sha256": sha(args.on_receipt.resolve()),
              "forecast_success": True, "forecast_returncode": 0,
              "off_receipt_sha256": sha(args.off_receipt.resolve()),
              "audit": audit, "capture_contracts": captures,
              "history_pair": history, "output_hashes": output_hashes,
              "notes": ["The original ON receipt remains FAIL because its loaded runner did not accept lowercase phase labels / raw-input file split.",
                        "This V2 is an offline re-validation of existing outputs, not a second WRF run.",
                        "Layer heating is checked only for capture step 731; step 721 PI was not captured."]}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(f"{output['status']}: {out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
