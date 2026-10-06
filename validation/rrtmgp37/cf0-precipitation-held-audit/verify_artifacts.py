"""Stdlib retained evidence checks only; never invoke numerical helpers."""
import hashlib
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
def read(name):
    return json.loads((HERE / name).read_text())
def main():
    manifest = read("manifest.json")
    for row in manifest["files"]:
        path = HERE / row["path"]
        assert path.stat().st_size == row["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
    index = read("index.json")
    for row in index["verbatim_origins"]:
        path = HERE / row["retained_path"]
        assert path.stat().st_size == row["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
    s = read("summary.json")
    assert s["eight_call_results_frozen"] is True
    assert s["frozen_proposal_source_sha256"] == "939981fd290b1a7f2ba6ece9d124a18b7a4d6be2135ebe10a789fcdb64f07df9"
    assert s["integrated_test_helper_sha256"] == "93214328388a1a7e242be1a298d34ae61e76f81d201ed9cf039e7f07ac580e6f"
    assert all(v == 0 for v in s["curation_calls"].values())
    assert s["current_forecast_evidence"] is False
    old = read("history/preparation-summary.json")
    assert old["eight_call_results_frozen"] is False
    assert old["zero_sidecar_controls"]["actual"] == old["positive_sidecar_calls"]["actual"] == 0
    assert read("forensic/proposal-status-v2.json")["status"] == "PATCH_PROPOSED_NOT_COMPILED_OR_EXECUTED"
    execution = read("campaign/execution.json")
    assert execution["status"] == "PASS_ALL_EIGHT_CALLS" and execution["solver_invocations"] == 8
    assert len(execution["calls"]) == 8 and all(c["returncode"] == 0 and c["pid"] > 0 for c in execution["calls"])
    assert execution["postflight"]["immutable_pin_count"] == 281
    assert all(execution["postflight"][k] for k in ["immutable_pins_unchanged", "generated_outputs_unchanged", "runtime_closure_unchanged"])
    assert len(index["campaign_generated_outputs"]) == 8
    analysis = read("campaign/analysis.json")
    assert len(analysis["zero_controls"]) == len(analysis["positive_cases"]) == 4
    assert all(c["byte_identical"] and c["oracle_sha256"] == c["output"]["sha256"] for c in analysis["zero_controls"])
    assert all(c["output_validation"] == "POSITIVE_OUTPUT_CONTRACT_PASS" for c in analysis["positive_cases"])
    peer = read("review/campaign-result-review.json")
    assert peer["status"] == "INDEPENDENT_OFFLINE_READBACK_PASS"
    assert peer["campaign_execution_sha256"] == hashlib.sha256((HERE / "campaign/execution.json").read_bytes()).hexdigest()
    assert read("current-helper/build-receipt-v2.json")["status"] == "BUILD_PASS_NO_SOLVER"
    assert read("current-helper/test-receipt-v4.json")["status"] == "TEST_PASS"
    cr = read("current-helper/compiled-reader-report-v4.json")
    assert cr["compiled_fortran_reader_exercised"] is True
    assert cr["process_counts"] == {"fixture_adapter_attempts": 2, "model_forecasts": 0,
        "reference_column_attempts": 14, "reference_column_rejected_before_output": 4, "reference_column_successes": 10}
    assert len(cr["reject_controls"]) == 4 and all(v == "PASS_REJECTED_BEFORE_OUTPUT" for v in cr["reject_controls"].values())
    assert read("validation/python-controls.json")["test_methods"] == 23
    assert read("validation/python-controls.json")["compiled_fortran_reader_exercised"] is False
    print(json.dumps({"status": "PASS_RETAINED_HASHES_SCOPED_HISTORICAL_AND_CURRENT_READER_CONTRACTS",
        "retained_artifacts": len(manifest["files"]), "external_arrays_recomputed": False,
        "new_model_REAL_build_solver_calls": 0}))
if __name__ == "__main__":
    main()
