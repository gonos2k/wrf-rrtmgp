#!/usr/bin/env python3
"""Stage an old-RFMIP-solar SW coefficient clone; never runs RRTMGP."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import netCDF4
import numpy as np

ROOT_REL = Path("build/official-rrtmgp-reference")
OLD_REL = Path("build/udm37-rfmip-reference-provenance-v1/rrtmgp-data-sw-g224-2018-12-04.nc")
CURRENT_SW_REL = ROOT_REL / "data/rrtmgp-gas-sw-g224.nc"
INPUT_REL = ROOT_REL / "data/examples/rfmip-clear-sky/inputs/multiple_input4MIPs_radiation_RFMIP_UColorado-RFMIP-1-2_none.nc"
PUBLISHED_DIR_REL = ROOT_REL / "data/examples/rfmip-clear-sky/reference"
UPSTREAM_RUN_REL = ROOT_REL / "run-upstream"
EXE_REL = ROOT_REL / "source/examples/rfmip-clear-sky/rrtmgp_rfmip_sw"
EXPECTED = {
    OLD_REL.as_posix(): "b9f4b15796d132880fffb49ac45c29753c1ee70a8ee3fed733899cb315c75e9b",
    CURRENT_SW_REL.as_posix(): "584f1dd41ea9fc07d4ee3754eb1dafbd46ad3161cd6fd20fa06b6922b6f0702e",
    INPUT_REL.as_posix(): "b8dc05d7cd2e0e6354b4a6198771ddf3bc09f18d72b49f20a41e2024e2fd51f4",
    EXE_REL.as_posix(): "fcebb76288fec0fceba4d720f61001f495819489a975769eec7de57ca8daa74f",
}
SOLAR_MODIFIED = ("solar_source_quiet", "solar_source_facular", "solar_source_sunspot")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def nc_snapshot(path: Path):
    with netCDF4.Dataset(path) as ds:
        dims = {name: (len(dim), dim.isunlimited()) for name, dim in ds.dimensions.items()}
        attrs = {name: ds.getncattr(name) for name in ds.ncattrs()}
        vars_ = {}
        for name, var in ds.variables.items():
            vars_[name] = {
                "dims": tuple(var.dimensions), "dtype": str(var.dtype),
                "attrs": {key: var.getncattr(key) for key in var.ncattrs()},
                "data": np.array(var[:]),
            }
    return dims, attrs, vars_


def same(a, b) -> bool:
    if a.dtype != b.dtype or a.shape != b.shape:
        return False
    if a.dtype.kind in "fc":
        return bool(np.array_equal(a, b, equal_nan=True))
    return bool(np.array_equal(a, b))


def attr_equal(a, b) -> bool:
    try:
        aa, bb = np.asarray(a), np.asarray(b)
        if aa.shape != bb.shape:
            return False
        if aa.dtype.kind in "fc" or bb.dtype.kind in "fc":
            return bool(np.array_equal(aa, bb, equal_nan=True))
        return bool(np.array_equal(aa, bb))
    except (TypeError, ValueError):
        return a == b


def prepare(workspace: Path, output: Path):
    workspace = workspace.resolve()
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite evidence directory: {output}")
    pinned = {str(k): workspace / k for k in EXPECTED}
    before = {}
    for rel, path in pinned.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        got = digest(path)
        if got != EXPECTED[rel]:
            raise ValueError(f"input pin mismatch {rel}: {got}")
        before[rel] = got

    old_path = workspace / OLD_REL
    cur_path = workspace / CURRENT_SW_REL
    d_old, _, old_vars = nc_snapshot(old_path)
    d_cur, a_cur, cur_vars = nc_snapshot(cur_path)
    if d_old.get("gpt", (None,))[0] != d_cur.get("gpt", (None,))[0]:
        raise ValueError("old and current SW coefficient gpt counts differ")
    if "solar_source" not in old_vars:
        raise ValueError("old SW file lacks solar_source")
    old_solar = old_vars["solar_source"]["data"]
    if old_solar.shape != cur_vars["solar_source_quiet"]["data"].shape:
        raise ValueError("old source and current quiet source shapes differ")

    output.mkdir(parents=True)
    cf_coeff = output / "rrtmgp-gas-sw-g224-old-solar-counterfactual.nc"
    shutil.copy2(cur_path, cf_coeff)
    with netCDF4.Dataset(cf_coeff, "r+") as ds:
        # Promote old float32 entries to the current file's float64 source
        # representation. Zeroing both variability spectra makes the loader's
        # default formula return this old vector exactly.
        ds["solar_source_quiet"][:] = old_solar
        ds["solar_source_facular"][:] = np.zeros(ds["solar_source_facular"].shape, dtype=ds["solar_source_facular"].dtype)
        ds["solar_source_sunspot"][:] = np.zeros(ds["solar_source_sunspot"].shape, dtype=ds["solar_source_sunspot"].dtype)

    d_cf, a_cf, cf_vars = nc_snapshot(cf_coeff)
    if d_cf != d_cur or a_cf != a_cur:
        raise ValueError("counterfactual dimensions or global attributes changed")
    changed = []
    for name in cur_vars:
        a, b = cur_vars[name], cf_vars[name]
        attrs_match = (set(a["attrs"]) == set(b["attrs"]) and
                       all(attr_equal(a["attrs"][key], b["attrs"][key]) for key in a["attrs"]))
        if a["dims"] != b["dims"] or a["dtype"] != b["dtype"] or not attrs_match:
            raise ValueError(f"counterfactual changed metadata for {name}")
        if not same(a["data"], b["data"]):
            changed.append(name)
    if set(changed) != set(SOLAR_MODIFIED):
        raise ValueError(f"unexpected changed variable set: {changed}")
    if not np.array_equal(cf_vars["solar_source_quiet"]["data"], old_solar.astype(cf_vars["solar_source_quiet"]["data"].dtype)):
        raise ValueError("quiet-source clone is not the old source vector promoted to current dtype")
    default_mg = float(cur_vars["mg_default"]["data"])
    default_sb = float(cur_vars["sb_default"]["data"])
    reconstructed = (cf_vars["solar_source_quiet"]["data"]
                     + (default_mg - 0.1495954) * cf_vars["solar_source_facular"]["data"]
                     + (default_sb - 0.00066696) * cf_vars["solar_source_sunspot"]["data"])
    if not np.array_equal(reconstructed, old_solar.astype(reconstructed.dtype)):
        raise ValueError("loader default formula does not reproduce the old stored spectrum exactly")

    reference_dir = workspace / PUBLISHED_DIR_REL
    upstream_dir = workspace / UPSTREAM_RUN_REL
    run_names = {
        "rsd_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc",
        "rsu_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc",
    }
    staged_outputs = {}
    for arm in ("control", "old-solar-counterfactual"):
        arm_dir = output / arm
        arm_dir.mkdir()
        for name in sorted(run_names):
            src = reference_dir / name
            if not src.is_file() or not (upstream_dir / name).is_file():
                raise FileNotFoundError(src)
            shutil.copy2(src, arm_dir / name)
            staged_outputs.setdefault(name, {
                "published_reference_sha256": digest(src),
                "current_upstream_output_sha256": digest(upstream_dir / name),
                "staged_template_sha256": digest(arm_dir / name),
            })

    after = {rel: digest(path) for rel, path in pinned.items()}
    if before != after:
        raise RuntimeError("a pinned upstream input changed while staging")
    manifest = {
        "schema": "rfmip-sw-solar-counterfactual-stage-v1",
        "status": "STAGED_NOT_RUN",
        "scope": "one SW-only counterfactual; no exact RTE-RRTMGP-181204 source-SHA claim",
        "pinned_inputs_sha256_before_after": before,
        "source": {"repository": "https://github.com/earth-system-radiation/rte-rrtmgp", "commit": "41c5fcd950fed09b8afe186dede266824eca7fd3"},
        "data": {"repository": "https://github.com/earth-system-radiation/rrtmgp-data", "commit": "ea788bb39876948fa8d2c235665ccff19b4686b5"},
        "input_path": INPUT_REL.as_posix(),
        "exe_path": EXE_REL.as_posix(),
        "exe_sha256": before[EXE_REL.as_posix()],
        "current_sw_coeff_path": CURRENT_SW_REL.as_posix(),
        "current_sw_coeff_sha256": before[CURRENT_SW_REL.as_posix()],
        "old_sw_coeff_path": OLD_REL.as_posix(),
        "old_sw_coeff_sha256": before[OLD_REL.as_posix()],
        "counterfactual_coeff_path": cf_coeff.name,
        "counterfactual_coeff_sha256": digest(cf_coeff),
        "changed_variables_only": list(SOLAR_MODIFIED),
        "counterfactual_method": "quiet=old solar_source promoted from float32 to current float64; facular and sunspot spectra set to exact zero; all gas/lookup variables, mg_default, sb_default, tsi_default, dimensions and attributes held unchanged",
        "loader_check": {"mg_default": default_mg, "sb_default": default_sb,
                         "current_set_solar_variability_formula_reproduces_old_vector_exactly": True,
                         "formula": "quiet + (mg_default-0.1495954)*facular + (sb_default-0.00066696)*sunspot"},
        "run_plan": {
            "control_first": {"cwd": "control", "command": [str(workspace / EXE_REL), "8", str(workspace / INPUT_REL), str(workspace / CURRENT_SW_REL), "1"],
                              "must_match_pinned_current_upstream_rsd_rsu_arrays_bitwise": True},
            "counterfactual_second": {"cwd": "old-solar-counterfactual", "command": [str(workspace / EXE_REL), "8", str(workspace / INPUT_REL), str(cf_coeff), "1"],
                                      "compare_rsd_rsu_to_published_atol": 1e-5, "rtol": 0},
            "max_invocations": 2,
            "timeout_each_seconds": 120,
            "do_not_run_until_root_reviews_staged_manifest": True,
        },
        "output_templates": staged_outputs,
        "limitations": [
            "This is a coefficient-only solar-spectrum counterfactual, not reconstruction of the exact historical CMIP6 code/data snapshot.",
            "No LW run is proposed; this isolates the existing SW RFMIP residual candidate.",
            "The existing current-coefficient control is expected to reproduce the pinned current upstream output exactly; that control check is a prerequisite before the second invocation.",
            "Published RFMIP absolute tolerance remains 1e-5 with rtol=0; it will not be relaxed.",
        ],
    }
    (output / "stage-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": manifest["status"], "counterfactual_sha256": manifest["counterfactual_coeff_sha256"],
                      "changed_variables": changed, "output": str(output)}, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=Path, default=Path("."))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    prepare(args.workspace, args.output)


if __name__ == "__main__":
    main()
