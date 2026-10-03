#!/usr/bin/env python3
"""Offline matrix plan, pairing, sidecar-mask and target-policy tests."""
from pathlib import Path
import importlib.util
import tempfile
import numpy as np

SCRIPT = Path(__file__).with_name("run_matrix32.py")
spec = importlib.util.spec_from_file_location("matrix32", SCRIPT)
runner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(runner)


def fixture():
    sec = {
        "MASK": np.zeros((1, 2, 1)),
        "GAS_COL_DRY": np.ones((1, 2, 1)),
        "GAS_TAU": np.ones((1, 2, 4)),
        "FROZEN_TAU": np.ones((1, 2, 3)),
        "FROZEN_SSA": np.ones((1, 2, 3)) * .5,
        "FROZEN_G": np.ones((1, 2, 3)) * .2,
        "GRAUPEL_TAU_ABS": np.ones((1, 2, 3)),
        "HAIL_TAU_ABS": np.ones((1, 2, 3)),
        "UP": np.ones((1, 3, 1)),
        "DN": np.ones((1, 3, 1)),
        "HR": np.ones((1, 2, 1)),
        "DI_USED": np.array([180., 100.]).reshape(1, 2, 1),
        "ICE_DIAMETER_RAW": np.array([200., 100.]).reshape(1, 2, 1),
        "CLOUD_TAU": np.ones((1, 2, 16)),
        "PRECIP_TAU": np.ones((1, 2, 16)) * 0.1,
    }
    return ("LW", 1, 2, sec)


def expect_failure(call, label):
    try:
        call()
    except (ValueError, RuntimeError):
        return
    raise AssertionError(f"{label} negative control passed")


def main():
    runner.self_test()
    plan = runner.build_plan(Path("unused-output"))
    plan2 = runner.build_plan(Path("unused-output"))
    assert runner.digest(plan) == runner.digest(plan2)
    assert len(plan["jobs"]) == 1152
    assert plan["call_budget"]["matrix_baselines"] == 384
    assert plan["call_budget"]["matrix_variants"] == 768
    assert plan["call_budget"]["new_diagnostic_executable_no_variant_anchors"] == 12
    assert plan["call_budget"]["max_cumulative_wall_clock_seconds_across_all_resumes"] == 1800
    assert plan["call_budget"]["previously_executed_jobs_revalidated_offline"] == 388
    assert plan["call_budget"]["new_matrix_engine_calls_remaining"] == 764
    assert plan["call_budget"]["prior_attempted_elapsed_seconds"] > 0
    assert plan["call_budget"]["remaining_cumulative_wall_clock_seconds"] < 1800
    assert len(plan["prior_job_reuse"]["validated_jobs"]) == 388
    assert plan["runtime"]["resolved_libraries"] and "not found" not in plan["runtime"]["ldd_output"]
    anchor = runner.load(runner.ANCHOR_RECEIPT)
    assert plan["runtime"]["resolved_libraries"] == anchor["before_assets_sha256"]["runtime"]["resolved_libraries"]
    assert all(len(st["phases"][ph]["eligible_modes"]) in (0, 2, 4)
               for st in plan["states"] for ph in ("LW", "SW"))
    assert [len(st["phases"]["LW"]["ice_preclip_eligible_levels_1based"])
            for st in plan["states"]] == [0, 0, 4, 6, 0, 0]
    with tempfile.TemporaryDirectory(prefix="matrix32-import-check-") as temp:
        out = Path(temp) / "fresh"
        out.mkdir()
        receipt = {"jobs": {}}
        runner.import_prior_validated_jobs(out, receipt, plan)
        assert len(receipt["jobs"]) == 388 and receipt["reused_job_count"] == 388
        assert receipt["jobs"]["cf0_rain_136_48/LW/seed-0000100001/grid_uniform"]["status"] == "PASS"
        assert receipt["jobs"]["cf0_rain_136_48/LW/seed-0000100001/grid_uniform"]["original_receipt_status"] == "RUNNING"
        for record in receipt["jobs"].values():
            for field in ("result_path", "log_path"):
                assert (out / record[field]).is_file()

    prep = runner.load(runner.SIDECAR_PREP)
    for state in prep["cases"]:
        for phase in ("LW", "SW"):
            profile = state["phases"][phase]
            raw_path = runner.ROOT / profile["raw"]
            _, raw = __import__("prepare_matrix_sidecars").parse_sections(raw_path, "RRTMGP_RAW_V1")
            n_native = 39
            nl = profile["header"]["nl"]
            for mode, info in profile["sidecars"].items():
                side = (runner.ROOT / info["path"]).read_text(encoding="ascii").splitlines()
                head = side[0].split()
                assert head == ["UDM_SENSITIVITY_V1", mode.upper(),
                                str(next(s["coordinate"]["i"] for s in plan["states"] if s["alias"] == state["alias"])),
                                str(next(s["coordinate"]["j"] for s in plan["states"] if s["alias"] == state["alias"]))]
                pos=1; sections={}
                while pos < len(side):
                    name,*dims=side[pos].split();pos+=1;n=int(np.prod(list(map(int,dims))))
                    vals=[]
                    while len(vals)<n: vals.extend(float(x) for x in side[pos].split());pos+=1
                    sections[name]=np.asarray(vals,dtype=np.float32)
                expected_rwp=np.zeros(nl,dtype=np.float32);expected_rwp[:n_native]=raw["RWP_GRID"].reshape(-1).astype(np.float32)
                expected_swp=np.zeros(nl,dtype=np.float32);expected_swp[:n_native]=raw["SWP_GRID"].reshape(-1).astype(np.float32)
                assert np.array_equal(sections["RWP_GRID"],expected_rwp)
                assert np.array_equal(sections["SWP_GRID"],expected_swp)
                if mode.startswith("ice"):
                    expected_mask=np.zeros(nl,dtype=np.float32)
                    expected_mask[np.asarray(profile["ice_preclip_eligible_layers_1based"],dtype=int)-1]=1
                    assert np.array_equal(sections["ICE_EXPECTED_MASK"],expected_mask)
    baseline = fixture()
    base_sec = baseline[3]
    ice = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in base_sec.items()}
    ice["ICE_DIAMETER_CHANGED"] = np.array([1., 0.]).reshape(1, 2, 1)
    ice["DI_USED"][0, 0, 0] = 160.
    job = {"phase": "LW", "mode": "ice160", "ice_eligible_levels": [1]}
    ice_profile = {"_test_raw_ice_diameter": np.array([200., 100.]).reshape(1, 2, 1)}
    runner.validate_pair(job, baseline, ("LW", 1, 2, ice), ice_profile, "")
    bad = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in ice.items()}
    bad["DI_USED"][0, 1, 0] = 110.
    expect_failure(lambda: runner.validate_pair(job, baseline, ("LW", 1, 2, bad), ice_profile, ""),
                   "inactive-layer DI mutation")
    bad = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in ice.items()}
    bad["ICE_DIAMETER_CHANGED"][0, 1, 0] = 1.
    expect_failure(lambda: runner.validate_pair(job, baseline, ("LW", 1, 2, bad), ice_profile, ""),
                   "extra changed ice layer")
    bad = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in ice.items()}
    bad["ICE_DIAMETER_RAW"][0, 0, 0] += 1.
    expect_failure(lambda: runner.validate_pair(job, baseline, ("LW", 1, 2, bad), ice_profile, ""),
                   "raw ice diameter input-provenance mutation")
    bad = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in ice.items()}
    bad["GAS_TAU"][0, 0, 0] += 1.
    expect_failure(lambda: runner.validate_pair(job, baseline, ("LW", 1, 2, bad), {}, ""),
                   "non-target gas optics mutation")
    bad = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in ice.items()}
    bad["GRAUPEL_TAU_ABS"][0, 0, 0] += 1.
    expect_failure(lambda: runner.validate_pair(job, baseline, ("LW", 1, 2, bad), {}, ""),
                   "non-target LW graupel absorption mutation")
    bad = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in ice.items()}
    bad["MASK"][0, 0, 0] = 1.
    expect_failure(lambda: runner.validate_pair(job, baseline, ("LW", 1, 2, bad), {}, ""),
                   "paired mask mutation")
    # Numeric equality treats these as equal, but a recorded IEEE invariant must not.
    assert np.array_equal(np.array([0.0]), np.array([-0.0]))
    assert not runner.bitwise_equal(np.array([0.0]), np.array([-0.0]))
    bad = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in ice.items()}
    bad["MASK"][0, 0, 0] = -0.0
    expect_failure(lambda: runner.validate_pair(job, baseline, ("LW", 1, 2, bad), {}, ""),
                   "paired mask signed-zero bit mutation")

    precip = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in base_sec.items()}
    precip["SENSITIVITY_PRECIP_TAU"] = np.zeros((1, 2, 16))
    precip["SENSITIVITY_PRECIP_TAU"][0, 0, :] = 0.02
    precip_profile = {"cf_zero_precip_layers_1based": [1],
                      "_test_cf": np.array([[0., 1.]]),
                      "_test_rwp_grid": np.array([[1., 0.]]),
                      "_test_swp_grid": np.zeros((1, 2))}
    job = {"phase": "LW", "mode": "cf0_uniform"}
    runner.validate_pair(job, baseline, ("LW", 1, 2, precip), precip_profile, "")
    bad = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in precip.items()}
    bad["SENSITIVITY_PRECIP_TAU"][0, 1, 0] = .01
    expect_failure(lambda: runner.validate_pair(job, baseline, ("LW", 1, 2, bad),
                                                precip_profile, ""),
                   "CF0 tau leak into cloudy layer")
    bad = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in precip.items()}
    bad["SENSITIVITY_PRECIP_TAU"][:] = 0.
    expect_failure(lambda: runner.validate_pair(job, baseline, ("LW", 1, 2, bad),
                                                precip_profile, ""),
                   "CF0 sensitivity no-op")
    bad = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in precip.items()}
    bad["HAIL_TAU_ABS"][0, 0, 0] += 1.
    expect_failure(lambda: runner.validate_pair(job, baseline, ("LW", 1, 2, bad),
                                                precip_profile, ""),
                   "non-target LW hail absorption mutation")

    # GRID_UNIFORM removes sampled precipitation from the combined cloud tau;
    # the unmodified baseline must reconstruct by adding that component back.
    grid_base = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in base_sec.items()}
    grid_base["CLOUD_TAU"][:] = 1.5
    grid_base["PRECIP_TAU"][:] = 0.5
    grid_var = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in grid_base.items()}
    grid_var["CLOUD_TAU"][:] = 1.0
    grid_var["PRECIP_TAU"][:] = 0.0
    grid_var["SENSITIVITY_PRECIP_TAU"] = np.zeros((1, 2, 16))
    grid_var["SENSITIVITY_PRECIP_TAU"][0, 0, :] = 0.02
    grid_job = {"phase": "LW", "mode": "grid_uniform"}
    runner.validate_pair(grid_job, ("LW", 1, 2, grid_base), ("LW", 1, 2, grid_var), precip_profile, "")
    bad = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in grid_var.items()}
    bad["CLOUD_TAU"][0, 0, 0] = 1.25
    expect_failure(lambda: runner.validate_pair(grid_job, ("LW", 1, 2, grid_base), ("LW", 1, 2, bad), precip_profile, ""),
                   "grid cloud-plus-precip reconstruction mutation")
    bad = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in grid_var.items()}
    bad["PRECIP_TAU"][0, 0, 0] = -0.0
    expect_failure(lambda: runner.validate_pair(grid_job, ("LW", 1, 2, grid_base), ("LW", 1, 2, bad), precip_profile, ""),
                   "grid precipitation signed-zero mutation")

    # SW delta scaling turns the source's MAX(1e-12, 0) floor into an exact
    # 1e-18 tau only on zero-path cells that remain in the sensitivity mask.
    sw_support = {"cf_zero_precip_layers_1based": [1],
                  "_test_cf": np.array([[0., 1., 0.]]),
                  "_test_rwp_grid": np.array([[1., 0., 0.]]),
                  "_test_swp_grid": np.zeros((1, 3))}
    sw_tau = np.zeros((1, 3, 14))
    sw_tau[0, 0, :] = .02
    sw_tau[0, 2, :] = (1.0 - min(1.0 - 1.0e-6, 1.0)) * 1.0e-12
    runner.validate_precip_sensitivity_support({"phase": "SW", "mode": "cf0_uniform"},
                                               sw_support, sw_tau, 1, 3)
    bad_tau = sw_tau.copy(); bad_tau[0, 2, 0] = 1.e-12
    expect_failure(lambda: runner.validate_precip_sensitivity_support(
        {"phase": "SW", "mode": "cf0_uniform"}, sw_support, bad_tau, 1, 3),
        "SW zero-path floor mutation")
    print("matrix32 plan and pair invariance/target negative controls PASS; no engine calls")


if __name__ == "__main__":
    main()
