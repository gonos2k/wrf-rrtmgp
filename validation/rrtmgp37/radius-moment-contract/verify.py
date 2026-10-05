#!/usr/bin/env python3
"""Standard-library-only integrity and bounded result-contract verifier."""
import hashlib
import json
import math
from pathlib import Path
import sys


PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[2]
MANIFEST = PACKAGE / "manifest.json"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    manifest = json.loads(MANIFEST.read_text())
    require(manifest.get("schema") == "udm37-radius-moment-contract-package-v1", "manifest schema")
    rows = manifest.get("files")
    require(isinstance(rows, list) and rows, "manifest files list")
    paths = [r["path"] for r in rows]
    require(len(paths) == len(set(paths)), "duplicate manifest path")
    actual = {p.relative_to(PACKAGE).as_posix() for p in PACKAGE.rglob("*") if p.is_file() and p != MANIFEST}
    require(set(paths) == actual, f"closed roster mismatch: missing={sorted(set(paths)-actual)}, extra={sorted(actual-set(paths))}")
    for row in rows:
        p = PACKAGE / row["path"]
        raw = p.read_bytes()
        require(len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"],
                f"payload pin mismatch: {row['path']}")

    result = json.loads((PACKAGE / "evidence/moment-result.json").read_text())
    review = json.loads((PACKAGE / "evidence/source-review.json").read_text())
    require(result.get("schema") == "udm37-liquid-radius-moment-audit-v1", "frozen result schema")
    require(result.get("status") == "PASS_SCOPED_SPHERICAL_GAMMA_MOMENT_DERIVATION_NO_POLICY_CHANGE", "result status")
    require(review.get("status") == "READ_ONLY_STATIC_AUDIT", "source review status")
    require(result.get("new_WRF_REAL_RTE_solver_build_calls") == 0 and result.get("production_changes") == 0,
            "result scope counters")
    qrows = result["quadrature"]["shape_rows"]
    samples = result["samples"]
    require(len(qrows) == 14 and [r["nu"] for r in qrows] == list(range(2, 16)), "shape rows")
    require(len(samples) == 15, "illustrative samples")
    require(math.isclose(result["bounds"]["min_gamma_to_volume_radius_ratio"], 1.0600476039461897, rel_tol=0, abs_tol=1e-14), "minimum ratio")
    require(math.isclose(result["bounds"]["max_gamma_to_volume_radius_ratio"], 1.2771823873225885, rel_tol=0, abs_tol=1e-14), "maximum ratio")
    maxerr = max(r["max_relative_quadrature_error"] for r in qrows)
    require(maxerr < 8e-14, "quadrature error bound")
    require("number_concentration_units" in review["findings"], "units issue documented")
    require("cloud_fraction" in review["findings"], "cloud-fraction issue documented")
    for file_row in review["source"]["files"]:
        source = REPO / file_row["path"]
        require(source.is_file(), f"missing source file {file_row['path']}")
        require(sha(source) == file_row["sha256"], f"source-review hash mismatch {file_row['path']}")

    provenance = json.loads((PACKAGE / "evidence/ice-lut-provenance-summary.json").read_text())
    require(provenance["pinned_tables"]["data_commit"] == "ea788bb39876948fa8d2c235665ccff19b4686b5", "LUT data commit")
    require(len(provenance["pinned_tables"]["files"]) == 2, "LUT file records")
    require(provenance["pinned_tables"]["metadata"]["ice_size_levels"] == 18, "LUT size metadata")
    require(provenance["pinned_tables"]["metadata"]["roughness_entries"] == 3, "LUT roughness metadata")
    require(not provenance["limits"]["exact_pinned_table_psd_or_habit_recipe_identified"], "LUT recipe limit")
    liquid = json.loads((PACKAGE / "evidence/liquid-provenance-note.json").read_text())
    require(liquid.get("schema") == "udm37-liquid-provenance-note-v1", "liquid provenance schema")
    require("does not establish" in liquid["bounded_absence_finding"], "liquid provenance limit")
    stage = json.loads((PACKAGE / "evidence/stage-identity.json").read_text())
    require(stage.get("schema") == "udm37-radius-stage-identity-v1", "stage identity schema")
    require(stage["source_comparison"]["exact_to_main_PR7"] is True, "local source continuity")
    require(stage["source_comparison"]["path"] == "WRF/phys/module_mp_udm.F", "stage source path")
    require(stage["source_comparison"]["routine_sha256"] == "994055162e02d61fc9a98dc0380fc5a6a779f5f0d4f86d043039106576b804df", "routine pin")
    require(stage["new_build_solver_WRF_forecast_calls"] == 0 and stage["production_changes"] == 0, "stage scope")
    independent = json.loads((PACKAGE / "evidence/independent-review.json").read_text())
    require(independent["material_blockers_in_final_evidence"] == [], "independent review blockers")
    require(independent["findings"]["gamma_moments"]["shape_range"] == [2, 15], "reviewed shape range")
    require(independent["findings"]["gamma_moments"]["ratio_range"] == [
        1.0600476039461897, 1.2771823873225885], "reviewed ratio range")
    print(json.dumps({"status": "PASS_SCOPED_RADIUS_MOMENT_EVIDENCE_ARCHIVE",
                      "payload_files_checked": len(rows), "shape_rows": len(qrows),
                      "illustrative_samples": len(samples), "max_quadrature_relative_error": maxerr,
                      "source_checkout": str(REPO), "physical_accuracy_claim": False}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
