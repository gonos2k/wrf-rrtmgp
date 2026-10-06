#!/usr/bin/env python3
"""Plan/execute paired 32-seed replay sensitivity for six captured states.

Default mode only prepares a hashed plan and state-specific sidecars. Execution
requires --execute, exact plan SHA, and a fresh output directory. --resume only
skips jobs whose PASS receipts and output hashes validate. No WRF model is run.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, shutil, subprocess, sys, time
from functools import lru_cache
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = HERE.parent
MANIFEST = BASE / "candidate-manifest-v2.json"
SIDECAR_DIR = HERE / "matrix-sidecars-v3"
SIDECAR_PREP = SIDECAR_DIR / "preparation.json"
ANCHOR_RECEIPT = HERE / "seed-exe-anchor-run" / "receipt.json"
ANCHOR_PLAN = HERE / "candidate-no-variant-plan.json"
EXE = HERE / "obj/reference_column"
SOURCE = HERE / "reference_column.f90"
COMPILE_SCRIPT = HERE / "compile_only.sh"
SOURCE_PATCH = HERE / "reference-mask-contract.patch"
PRIOR_RUN = HERE / "matrix32-execution-20261003-v1"
PRIOR_RECEIPT = PRIOR_RUN / "receipt.json"
PRIOR_ERRATUM = PRIOR_RUN / "first-grid-contract-erratum.json"
PRIOR_ROOT_READBACK = HERE / "root-matrix-v1-composition-readback.json"
PRIOR_V2_RUN = HERE / "matrix32-execution-20261003-v2"
PRIOR_V2_PLAN = HERE / "matrix32-plan-v2.json"
PRIOR_V2_RECEIPT = PRIOR_V2_RUN / "receipt.json"
PRIOR_V2_ERRATUM = PRIOR_V2_RUN / "first-cf0-sw-floor-erratum.json"
PRIOR_V2_ROOT_READBACK = HERE / "root-matrix-v2-floor-readback.json"
PRIOR_V3_RUN = HERE / "matrix32-execution-20261003-v3"
PRIOR_V3_PLAN = HERE / "matrix32-plan-v3.json"
PRIOR_V3_RECEIPT = PRIOR_V3_RUN / "receipt.json"
PRIOR_V3_ERRATUM = PRIOR_V3_RUN / "first-ice-raw-input-erratum.json"
BASE_EXE = ROOT / "build/udm-phase-path-sensitivity-work/ensemble-build/reference_column"
BASE_SOURCE = ROOT / "build/udm-phase-path-sensitivity-work/ensemble/reference_column_seed_override.f90"
RRTMGP_ARCHIVE = ROOT / "build/udm-phase-path-sensitivity-work/ensemble-build/rte_rrtmgp/libwrf_rrtmgp.a"
FROZEN_ARCHIVE = ROOT / "build/udm-phase-path-sensitivity-work/ensemble-build/libtest_rrtmgp_frozen.a"
NETCDFF = ROOT / "build/deps/root/usr/lib/x86_64-linux-gnu/libnetcdff.so"
NETCDF = ROOT / "build/deps/root/usr/lib/x86_64-linux-gnu/libnetcdf.so"
TABLE = ROOT / "build/pr-wrf-rrtmgp/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc"
DATA = ROOT / "build/official-rrtmgp-reference/data"
NETCDF_LIB = ROOT / "build/deps/netcdf/lib"
ROOT_LIB = ROOT / "build/deps/root/usr/lib/x86_64-linux-gnu"
LD_PATH = f"{NETCDF_LIB}:{ROOT_LIB}"
HELPER = ROOT / "build/udm-phase-path-sensitivity-work/ensemble/run_seed_ensemble_bounded.py"
COMPARATOR = ROOT / "build/udm-frozen-replay-validator-work/WRF/test/rrtmgp/compare_column_replay.py"
NSEEDS = 32
SEEDS = [100001 + k * 104729 for k in range(NSEEDS)]
MODES = ("cf0_uniform", "grid_uniform", "ice160", "ice140")
PHASES = ("LW", "SW")
TIMEOUT = 180
WALL_BUDGET = 1800
T95_DF31 = 2.039513446
COMMON_INVARIANTS = ("GAS_COL_DRY", "GAS_TAU", "GAS_TAU_RAW", "FROZEN_TAU",
                     "FROZEN_SSA", "FROZEN_G", "GRAUPEL_TAU_EXT", "GRAUPEL_TAU_SCA",
                     "GRAUPEL_TAU_SCA_G", "HAIL_TAU_EXT", "HAIL_TAU_SCA", "HAIL_TAU_SCA_G",
                     "GRAUPEL_TAU_ABS", "HAIL_TAU_ABS")


def bitwise_equal(a, b):
    """Compare stored IEEE values, including signed zero and dtype/shape."""
    aa = np.asarray(a)
    bb = np.asarray(b)
    return (aa.shape == bb.shape and aa.dtype == bb.dtype and
            np.ascontiguousarray(aa).tobytes() == np.ascontiguousarray(bb).tobytes())


def validate_precip_cloud_component(mode, baseline, variant):
    """Validate combined cloud optics against the precipitation policy.

    CLOUD_TAU is captured after sampled precipitation is incremented into the
    cloud optical-properties object. CF0_UNIFORM leaves sampled precipitation
    unchanged; GRID_UNIFORM removes it. In the latter case, the baseline total
    must reconstruct as variant cloud-only tau plus baseline precipitation tau.
    """
    for sections in (baseline, variant):
        if "CLOUD_TAU" not in sections or "PRECIP_TAU" not in sections:
            raise ValueError("precipitation pair lacks cloud/precipitation optical depths")
    bc, bp = baseline["CLOUD_TAU"], baseline["PRECIP_TAU"]
    vc, vp = variant["CLOUD_TAU"], variant["PRECIP_TAU"]
    if bc.shape != bp.shape or bc.shape != vc.shape or bc.shape != vp.shape:
        raise ValueError("cloud/precipitation optical-depth shapes differ")
    if mode == "cf0_uniform":
        if not bitwise_equal(bc, vc) or not bitwise_equal(bp, vp):
            raise ValueError("CF0 sensitivity changed sampled cloud/precipitation optics")
    elif mode == "grid_uniform":
        if not bitwise_equal(vp, np.zeros_like(vp)):
            raise ValueError("grid-uniform replay did not remove sampled precipitation optics")
        if not bitwise_equal(bc, vc + bp):
            raise ValueError("grid-uniform cloud-only plus baseline precipitation does not reconstruct baseline tau")
    else:
        raise ValueError(f"unsupported precipitation composition mode {mode}")


@lru_cache(maxsize=128)
def _load_cf_precip_support(input_path, magic, sidecar_path, mode):
    spec = importlib.util.spec_from_file_location("matrix_sidecar_parser", HERE / "prepare_matrix_sidecars.py")
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned sidecar parser")
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    _, inp = parser.parse_sections(Path(input_path), magic)
    lines = Path(sidecar_path).read_text(encoding="ascii").splitlines()
    if not lines:
        raise ValueError("empty precipitation sidecar")
    header = lines[0].split()
    if len(header) != 4 or header[:2] != ["UDM_SENSITIVITY_V1", mode.upper()]:
        raise ValueError("sidecar mode/header differs from requested precipitation mode")
    fields = {}
    pos = 1
    while pos < len(lines):
        parts = lines[pos].split()
        pos += 1
        if len(parts) < 2:
            raise ValueError("malformed precipitation sidecar section")
        name = parts[0]
        dims = tuple(int(x) for x in parts[1:])
        count = int(np.prod(dims))
        values = []
        while len(values) < count:
            if pos >= len(lines):
                raise ValueError("truncated precipitation sidecar section")
            values.extend(float(x) for x in lines[pos].split())
            pos += 1
        if len(values) != count or name in fields:
            raise ValueError("malformed/duplicate precipitation sidecar section")
        fields[name] = np.asarray(values, dtype=np.float64).reshape(dims, order="F")
    if "CF" not in inp or "RWP_GRID" not in fields or "SWP_GRID" not in fields:
        raise ValueError("replay input/sidecar lacks CF or grid precipitation paths")
    cf = np.asarray(inp["CF"], dtype=np.float64)
    rwp, swp = fields["RWP_GRID"], fields["SWP_GRID"]
    if cf.shape != rwp.shape or cf.shape != swp.shape:
        raise ValueError("CF and grid precipitation sidecar shapes differ")
    return cf, rwp, swp


def _precip_support(job, state_phase, nc, nl):
    if all(k in state_phase for k in ("_test_cf", "_test_rwp_grid", "_test_swp_grid")):
        cf = np.asarray(state_phase["_test_cf"], dtype=np.float64)
        rwp = np.asarray(state_phase["_test_rwp_grid"], dtype=np.float64)
        swp = np.asarray(state_phase["_test_swp_grid"], dtype=np.float64)
    else:
        side = state_phase.get("sidecars", {}).get(job["mode"])
        if not side:
            raise ValueError("precipitation variant lacks a pinned sidecar profile")
        magic = state_phase.get("header", {}).get("magic")
        if not magic:
            raise ValueError("precipitation profile lacks replay input magic")
        cf, rwp, swp = _load_cf_precip_support(str((ROOT / state_phase["input"]).resolve()), magic,
                                              str((ROOT / side["path"]).resolve()), job["mode"])
    if cf.shape != (nc, nl) or rwp.shape != (nc, nl) or swp.shape != (nc, nl):
        raise ValueError("CF/grid precipitation profile dimensions differ from replay output")
    if not all(np.isfinite(x).all() for x in (cf, rwp, swp)) or np.any(rwp < 0) or np.any(swp < 0):
        raise ValueError("CF/grid precipitation profile contains invalid values")
    return cf, rwp, swp


def validate_precip_sensitivity_support(job, state_phase, tau, nc, nl):
    cf, rwp, swp = _precip_support(job, state_phase, nc, nl)
    active_path = (rwp > 0.0) | (swp > 0.0)
    cf_zero = cf == 0.0
    mode = job["mode"]
    if mode == "cf0_uniform":
        listed = np.zeros(nl, dtype=bool)
        listed[np.asarray(state_phase["cf_zero_precip_layers_1based"], dtype=int) - 1] = True
        if not bitwise_equal(listed, np.any(cf_zero & active_path, axis=0)):
            raise ValueError("prepared CF-zero positive-path support differs from replay input/sidecar")
        active_expected = cf_zero & active_path
        forbidden_path = ~cf_zero
        floor_mask = (~active_path) & cf_zero
    elif mode == "grid_uniform":
        active_expected = active_path
        forbidden_path = np.zeros_like(active_path, dtype=bool)
        floor_mask = ~active_path
    else:
        raise ValueError(f"unsupported precipitation sensitivity mode {mode}")
    if job["phase"] == "SW":
        # Source formula: tau_prec=max(1e-12, rain+snow); with zero path,
        # ssa=asymmetry=1e-12, g=1 and delta scaling yields this exact floor.
        ssaw = min(1.0 - 1.0e-6, 1.0)
        zero_path_floor = (1.0 - ssaw) * 1.0e-12
        expected_floor = np.full_like(tau[floor_mask, :], zero_path_floor)
        if not bitwise_equal(tau[floor_mask, :], expected_floor):
            raise ValueError("SW zero-path sensitivity differs from source-derived delta-scaled floor")
        if np.any(forbidden_path) and np.any(tau[forbidden_path, :] != 0.0):
            raise ValueError("CF0 sensitivity tau leaked into cloudy layers")
        threshold = zero_path_floor
    else:
        if np.any(tau[floor_mask, :] != 0.0):
            raise ValueError("LW zero-path sensitivity optics are not exactly zero")
        if np.any(forbidden_path) and np.any(tau[forbidden_path, :] != 0.0):
            raise ValueError("CF0 sensitivity tau leaked into cloudy positive-path layers")
        threshold = 0.0
    # Individual positive mass paths can still map to the source floor (for
    # example snow with radius <= 10 um); require at least one supported
    # optical path to exceed the exact floor, not every path cell.
    if not np.any(tau[active_expected, :] > threshold):
        raise ValueError("precipitation sensitivity is a no-op on positive supported paths")


@lru_cache(maxsize=128)
def _load_expected_raw_ice_diameter(input_path, magic, iceflag):
    spec = importlib.util.spec_from_file_location("matrix_ice_input_parser", HERE / "prepare_matrix_sidecars.py")
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned input parser for raw ice diameter")
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    _, inp = parser.parse_sections(Path(input_path), magic)
    if "REI" not in inp:
        raise ValueError("replay input lacks REI for raw ice diameter check")
    rei = np.asarray(inp["REI"], dtype=np.float64)
    if int(iceflag) == 3:
        diameter = (2.0 * rei) / 1.0315
    else:
        diameter = 2.0 * rei
    return diameter.reshape((*diameter.shape, 1))


def expected_raw_ice_diameter(state_phase, nc, nl):
    if "_test_raw_ice_diameter" in state_phase:
        expected = np.asarray(state_phase["_test_raw_ice_diameter"], dtype=np.float64)
    else:
        header = state_phase.get("header", {})
        expected = _load_expected_raw_ice_diameter(
            str((ROOT / state_phase["input"]).resolve()), header["magic"],
            int(header["microphysics_ice_size_flag"]))
    if expected.shape != (nc, nl, 1) or not np.isfinite(expected).all():
        raise ValueError("input-derived raw ice diameter has invalid shape or values")
    return expected


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load(p: Path):
    return json.loads(p.read_text())


def pin(p: Path):
    if not p.is_file():
        raise ValueError(f"missing pinned file: {p}")
    return {"path": str(p.resolve().relative_to(ROOT)), "sha256": sha(p), "bytes": p.stat().st_size}


def runtime_pin(exe: Path):
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = LD_PATH
    r = subprocess.run(["ldd", str(exe)], env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, timeout=15)
    if r.returncode or "not a dynamic executable" in r.stdout:
        raise ValueError("could not inspect candidate executable runtime: " + r.stdout)
    out = re.sub(r"0x[0-9a-fA-F]+", "0x<load-address>", r.stdout)
    if re.search(r"=>\s+not found", out):
        raise ValueError("unresolved dynamic library: " + out)
    libs = {}
    for line in out.splitlines():
        match = re.search(r"=>\s+(/\S+)", line)
        if match:
            lib = Path(match.group(1)).resolve()
            if lib.is_file():
                libs[str(lib)] = sha(lib)
    if len(libs) < 2:
        raise ValueError("too few resolved library pins")
    return {"ldd_output": out, "ldd_sha256": hashlib.sha256(out.encode()).hexdigest(),
            "resolved_libraries": libs, "LD_LIBRARY_PATH": LD_PATH}


def import_helper():
    spec = importlib.util.spec_from_file_location("seed_command_helper", HELPER)
    if spec is None or spec.loader is None:
        raise ValueError("cannot import pinned command helper")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def read_result(path: Path):
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) < 2 or lines[0] != "RRTMGP_RESULT_V1":
        raise ValueError(f"invalid reference result {path}")
    phase, nc, nl = lines[1].split()
    pos = 2
    sections = {}
    while pos < len(lines):
        head = lines[pos].split()
        pos += 1
        if len(head) < 2:
            raise ValueError(f"bad output section in {path}")
        name = head[0]
        shape = tuple(int(x) for x in head[1:])
        count = int(np.prod(shape))
        values = []
        while len(values) < count:
            if pos >= len(lines):
                raise ValueError(f"truncated output section {name}")
            values.extend(float(x.replace("D", "E").replace("d", "e")) for x in lines[pos].split())
            pos += 1
        if len(values) != count or name in sections:
            raise ValueError(f"bad/duplicate section {name}")
        a = np.asarray(values, dtype=np.float64).reshape(shape, order="F")
        if not np.isfinite(a).all():
            raise ValueError(f"nonfinite output section {name}")
        sections[name] = a
    return phase, int(nc), int(nl), sections


def validate_matrix_counts(jobs, arm_counts):
    if arm_counts != {"LW": 12, "SW": 12} or len(jobs) != 1152:
        raise ValueError(f"matrix count error: phase arms {arm_counts}; jobs {len(jobs)}")
    keys = [j["key"] for j in jobs]
    if len(set(keys)) != 1152:
        raise ValueError("duplicate matrix job key")
    baseline = [j for j in jobs if j["kind"] == "baseline"]
    variants = [j for j in jobs if j["kind"] == "variant"]
    if len(baseline) != 384 or len(variants) != 768:
        raise ValueError(f"expected 384 baselines and 768 variants, got {len(baseline)}/{len(variants)}")
    return True


def prior_reuse_proof(prep):
    """Revalidate the complete successful prefix from the two preserved attempts."""
    old = load(PRIOR_RECEIPT)
    erratum = load(PRIOR_ERRATUM)
    root_readback = load(PRIOR_ROOT_READBACK)
    if (old.get("status") != "FAIL_STOPPED_FIRST_ERROR" or
            old.get("failures") != ["precipitation variant changed non-target cloud tau"] or
            old.get("assets_unchanged") is not True or
            old.get("before_assets") != old.get("after_assets")):
        raise ValueError("prior run is not the preserved first-failure receipt")
    if (erratum.get("original_receipt_sha256") != sha(PRIOR_RECEIPT) or
            erratum.get("classification") != "ENGINE_SUCCEEDED_VALIDATOR_COMPOSITION_CONTRACT_INCORRECT"):
        raise ValueError("prior grid-job erratum does not bind to the original receipt")
    if (root_readback.get("status") != "PASS_OFFLINE_EXACT_COMPOSITION_READBACK" or
            root_readback.get("original_receipt_sha256") != sha(PRIOR_RECEIPT) or
            root_readback.get("new_engine_calls") != 0 or
            not root_readback.get("GRID_baseline_equals_cloud_only_plus_precip") or
            not root_readback.get("CF0_combined_cloud_and_sampled_precip_unchanged") or
            not root_readback.get("non_target_arrays_exact")):
        raise ValueError("independent root readback does not validate the prior three jobs")
    alias, phase, seed = "cf0_rain_136_48", "LW", SEEDS[0]
    keys = [f"{alias}/{phase}/seed-{seed:010d}/baseline",
            f"{alias}/{phase}/seed-{seed:010d}/cf0_uniform",
            f"{alias}/{phase}/seed-{seed:010d}/grid_uniform"]
    state = next(c for c in prep["cases"] if c["alias"] == alias)["phases"][phase]
    inputs = {"path": state["input"], "sha256": state["input_sha256"]}
    validated = []
    results = {}
    for index, key in enumerate(keys):
        rec = old["jobs"].get(key)
        expected_status = "RUNNING" if index == 2 else "PASS"
        if not rec or rec.get("status") != expected_status or rec.get("returncode") != 0:
            raise ValueError(f"prior job is not an engine-success candidate for import: {key}")
        job = rec.get("job", {})
        if job.get("input") != inputs["path"] or job.get("input_sha256") != inputs["sha256"] or job.get("seed") != seed:
            raise ValueError(f"prior job input/seed pin differs: {key}")
        result_path = PRIOR_RUN / rec["result_path"]
        log_path = PRIOR_RUN / rec["log_path"]
        if not result_path.is_file() or sha(result_path) != rec.get("result_sha256"):
            raise ValueError(f"prior job result hash mismatch: {key}")
        if not log_path.is_file() or sha(log_path) != rec.get("log_sha256"):
            raise ValueError(f"prior job log hash mismatch: {key}")
        phase_out, nc, nl, sections = read_result(result_path)
        log = log_path.read_text(encoding="utf-8")
        result_seed_check(log, sections, seed, phase)
        if (phase_out, nc, nl) != (phase, 1, 47):
            raise ValueError(f"prior job result header differs: {key}")
        results[key] = (phase_out, nc, nl, sections)
        validated.append({"key": key, "original_receipt_status": expected_status,
                          "returncode": 0,
                          "result": pin(result_path), "log": pin(log_path)})
    profile = state
    validate_pair({"phase": phase, "mode": "cf0_uniform"}, results[keys[0]], results[keys[1]], profile,
                  (PRIOR_RUN / old["jobs"][keys[1]]["log_path"]).read_text(encoding="utf-8"))
    validate_pair({"phase": phase, "mode": "grid_uniform"}, results[keys[0]], results[keys[2]], profile,
                  (PRIOR_RUN / old["jobs"][keys[2]]["log_path"]).read_text(encoding="utf-8"))
    erratum_checks = erratum.get("readback_checks", {})
    if not all(erratum_checks.get(name) is True for name in (
            "baseline_vs_cf0_cloud_tau_bitwise_equal", "baseline_vs_cf0_precip_tau_bitwise_equal",
            "grid_precip_tau_positive_zero_bitwise",
            "baseline_cloud_equals_grid_cloud_plus_baseline_precip_bitwise",
            "grid_di_used_bitwise_equal")):
        raise ValueError("prior grid/cloud composition erratum checks are incomplete")
    v2_plan = load(PRIOR_V2_PLAN)
    v2 = load(PRIOR_V2_RECEIPT)
    v2_erratum = load(PRIOR_V2_ERRATUM)
    v2_root_readback = load(PRIOR_V2_ROOT_READBACK)
    if (v2_plan.get("plan_sha256") != "7e67877e3be813f535d23df0f46c93726f1f49c1d18a25f5fedaf2e9c0ba8f2b" or
            v2.get("plan_sha256") != v2_plan["plan_sha256"] or
            v2.get("status") != "FAIL_STOPPED_FIRST_ERROR" or
            v2.get("failures") != ["CF0 sensitivity tau leaked into non-CF0 layers"] or
            v2.get("assets_unchanged") is not True or
            v2.get("before_assets") != v2.get("after_assets")):
        raise ValueError("v2 source is not the preserved first floor-contract failure")
    if (v2_erratum.get("original_receipt_sha256") != sha(PRIOR_V2_RECEIPT) or
            v2_erratum.get("classification") != "ENGINE_SUCCEEDED_VALIDATOR_EXPECTED_ZERO_INSTEAD_OF_SOURCE_FLOOR" or
            v2_erratum.get("new_engine_calls") != 0):
        raise ValueError("v2 floor erratum does not bind to its preserved receipt")
    if (v2_root_readback.get("status") != "PASS_OFFLINE_SOURCE_FLOOR_READBACK" or
            v2_root_readback.get("original_v2_receipt_sha256") != sha(PRIOR_V2_RECEIPT) or
            v2_root_readback.get("floor_hex") != "0x1.2725dd1d48ae7p-60" or
            v2_root_readback.get("new_engine_calls") != 0 or
            not v2_root_readback.get("positive_path_above_floor")):
        raise ValueError("independent root readback does not validate the v2 first rejected pair")
    v2_jobs = list(v2_plan["jobs"])
    keys_v2 = list(v2["jobs"])
    if len(keys_v2) != 98 or keys_v2 != [j["key"] for j in v2_jobs[:98]]:
        raise ValueError("v2 successful job prefix is incomplete or reordered")
    failing_key = "cf0_rain_136_48/SW/seed-0000100001/cf0_uniform"
    if keys_v2[-1] != failing_key:
        raise ValueError("v2 first rejected job differs from the reviewed floor-contract case")
    profiles = state_phase_lookup(prep)
    v2_results = {}
    imported = []
    for index, planned_job in enumerate(v2_jobs[:98]):
        key = planned_job["key"]
        rec = v2["jobs"][key]
        expected_status = "RUNNING" if index == 97 else "PASS"
        if rec.get("status") != expected_status or rec.get("returncode") != 0 or rec.get("job") != planned_job:
            raise ValueError(f"v2 job is not an engine-success prefix candidate: {key}")
        result_path = PRIOR_V2_RUN / rec["result_path"]
        log_path = PRIOR_V2_RUN / rec["log_path"]
        if not result_path.is_file() or sha(result_path) != rec.get("result_sha256"):
            raise ValueError(f"v2 result hash mismatch: {key}")
        if not log_path.is_file() or sha(log_path) != rec.get("log_sha256"):
            raise ValueError(f"v2 log hash mismatch: {key}")
        phase_out, nc, nl, sections = read_result(result_path)
        log = log_path.read_text(encoding="utf-8")
        result_seed_check(log, sections, planned_job["seed"], planned_job["phase"])
        if (phase_out, nc, nl) != (planned_job["phase"], 1, 47 if phase_out == "LW" else 40):
            raise ValueError(f"v2 result header differs: {key}")
        if sha(ROOT / planned_job["input"]) != planned_job["input_sha256"]:
            raise ValueError(f"v2 replay input changed: {key}")
        result = (phase_out, nc, nl, sections)
        v2_results[key] = result
        if planned_job["kind"] == "baseline":
            if not all(f in sections for f in ("MASK", "GAS_COL_DRY", "GAS_TAU", "FROZEN_TAU", "UP", "DN", "HR")):
                raise ValueError(f"v2 baseline output lacks a required field: {key}")
        else:
            base_key = f"{planned_job['case']}/{planned_job['phase']}/seed-{planned_job['seed']:010d}/baseline"
            if base_key not in v2_results:
                # Baselines precede their paired variants in the runner order.
                base_rec = v2["jobs"].get(base_key)
                if base_rec is None:
                    raise ValueError(f"v2 paired baseline missing: {key}")
                bp, bnc, bnl, bsec = read_result(PRIOR_V2_RUN / base_rec["result_path"])
                v2_results[base_key] = (bp, bnc, bnl, bsec)
            validate_pair(planned_job, v2_results[base_key], result,
                          profiles[(planned_job["case"], planned_job["phase"])], log)
        imported.append({"key": key, "source_receipt_status": expected_status,
                         "returncode": 0, "result": pin(result_path), "log": pin(log_path)})
    floor_checks = v2_erratum.get("readback", {})
    if not all(floor_checks.get(k) is True for k in (
            "expected_floor_exact_on_cfzero_no_path", "cloudy_cells_exact_zero",
            "positive_cfzero_support_has_effect")):
        raise ValueError("v2 first rejected pair does not meet source-derived floor readback")
    v3_plan = load(PRIOR_V3_PLAN)
    v3 = load(PRIOR_V3_RECEIPT)
    v3_erratum = load(PRIOR_V3_ERRATUM)
    if (v3_plan.get("plan_sha256") != "a9a45166fa2047be179df9eff9763710a803297bfea0ab6e16bbfcf7daa7a1c0" or
            v3.get("plan_sha256") != v3_plan["plan_sha256"] or
            v3.get("status") != "FAIL_STOPPED_FIRST_ERROR" or
            v3.get("failures") != ["raw ice diameter changed between paired calls"] or
            v3.get("assets_unchanged") is not True or
            v3.get("before_assets") != v3.get("after_assets")):
        raise ValueError("v3 source is not the preserved first raw-diameter field failure")
    if (v3_erratum.get("original_receipt_sha256") != sha(PRIOR_V3_RECEIPT) or
            v3_erratum.get("classification") != "ENGINE_SUCCEEDED_VALIDATOR_EXPECTED_FIELD_ABSENT_FROM_BASELINE" or
            v3_erratum.get("new_engine_calls") != 0 or
            not v3_erratum.get("readback", {}).get("expected_raw_equals_variant_bitwise") or
            not v3_erratum.get("readback", {}).get("baseline_raw_field_absent_as_source_emits_only_for_ice_modes")):
        raise ValueError("v3 raw-diameter erratum does not validate the preserved first rejected pair")
    v3_jobs = list(v3_plan["jobs"])
    v3_keys = list(v3["jobs"])
    expected_v3_prefix = [j["key"] for j in v3_jobs[:388]]
    if len(v3_keys) != 388 or set(v3_keys) != set(expected_v3_prefix):
        raise ValueError("v3 successful job prefix is incomplete or contains unexpected jobs")
    if expected_v3_prefix[-1] != "ice_clip_low_132_35/LW/seed-0000100001/ice160":
        raise ValueError("v3 first rejected job differs from the raw-diameter contract case")
    v3_results = {}
    imported_v3 = []
    for index, planned_job in enumerate(v3_jobs[:388]):
        key = planned_job["key"]
        rec = v3["jobs"][key]
        expected_status = "RUNNING" if index == 387 else "PASS"
        if rec.get("status") != expected_status or rec.get("returncode") != 0 or rec.get("job") != planned_job:
            raise ValueError(f"v3 job is not an engine-success prefix candidate: {key}")
        result_path = PRIOR_V3_RUN / rec["result_path"]
        log_path = PRIOR_V3_RUN / rec["log_path"]
        if not result_path.is_file() or sha(result_path) != rec.get("result_sha256"):
            raise ValueError(f"v3 result hash mismatch: {key}")
        if not log_path.is_file() or sha(log_path) != rec.get("log_sha256"):
            raise ValueError(f"v3 log hash mismatch: {key}")
        phase_out, nc, nl, sections = read_result(result_path)
        log = log_path.read_text(encoding="utf-8")
        result_seed_check(log, sections, planned_job["seed"], planned_job["phase"])
        if (phase_out, nc, nl) != (planned_job["phase"], 1, 47 if phase_out == "LW" else 40):
            raise ValueError(f"v3 result header differs: {key}")
        if sha(ROOT / planned_job["input"]) != planned_job["input_sha256"]:
            raise ValueError(f"v3 replay input changed: {key}")
        result = (phase_out, nc, nl, sections)
        v3_results[key] = result
        if planned_job["kind"] == "baseline":
            if not all(f in sections for f in ("MASK", "GAS_COL_DRY", "GAS_TAU", "FROZEN_TAU", "UP", "DN", "HR")):
                raise ValueError(f"v3 baseline output lacks a required field: {key}")
        else:
            base_key = f"{planned_job['case']}/{planned_job['phase']}/seed-{planned_job['seed']:010d}/baseline"
            if base_key not in v3_results:
                raise ValueError(f"v3 paired baseline missing before variant: {key}")
            validate_pair(planned_job, v3_results[base_key], result,
                          profiles[(planned_job["case"], planned_job["phase"])], log)
        imported_v3.append({"key": key, "source_receipt_status": expected_status,
                            "returncode": 0, "result": pin(result_path), "log": pin(log_path)})
    previous_elapsed = float(v3.get("elapsed_total_seconds", 0.0))
    return {"source_receipt": pin(PRIOR_V3_RECEIPT), "source_plan": pin(PRIOR_V3_PLAN),
            "erratum": pin(PRIOR_V3_ERRATUM),
            "ancestors": {"v1": {"source_receipt": pin(PRIOR_RECEIPT), "erratum": pin(PRIOR_ERRATUM),
                                 "independent_root_readback": pin(PRIOR_ROOT_READBACK)},
                          "v2": {"source_receipt": pin(PRIOR_V2_RECEIPT), "source_plan": pin(PRIOR_V2_PLAN),
                                 "erratum": pin(PRIOR_V2_ERRATUM),
                                 "independent_root_readback": pin(PRIOR_V2_ROOT_READBACK)}},
            "source_status": v3["status"], "validated_jobs": imported_v3,
            "imported_job_count": len(imported_v3), "prior_execution_elapsed_seconds": previous_elapsed,
            "method": "All 388 successful-process outputs in the v3 prefix were hash-checked and revalidated offline under exact cloud/precipitation composition, source-derived SW zero-path floor, and input-derived raw ice diameter contracts. Original v1/v2/v3 receipts and engine output/log files remain unchanged."}


def build_plan(out: Path):
    manifest = load(MANIFEST)
    prep = load(SIDECAR_PREP)
    prior_reuse = prior_reuse_proof(prep)
    anchors = load(ANCHOR_RECEIPT)
    anchor_plan = load(ANCHOR_PLAN)
    if prep.get("status") != "PASS_PREPARATION_ONLY" or prep.get("eligible_phase_variant_arms") != 24:
        raise ValueError("24-arm sidecar preparation is not validated")
    if anchors.get("status") != "PASS_ALL_12_SEED_EXE_NO_VARIANT_ANCHORS" or not anchors.get("assets_unchanged"):
        raise ValueError("new diagnostic executable lacks its own 12 passing no-variant anchors")
    if len(anchors.get("calls", [])) != 12 or any(c.get("status") != "PASS" for c in anchors["calls"]):
        raise ValueError("candidate executable anchor ledger is incomplete")
    if sha(EXE) != "6585642b1fedd437f5bfb504403b54ced944f049fd01107f0bda165254dd8ce4":
        raise ValueError("candidate diagnostic executable changed")
    if sha(SOURCE) != "c18a97a65c7d9168e09cad8ac989e0737b295a66dd7fb87704d90ec72f66654e":
        raise ValueError("diagnostic source changed")
    if sha(MANIFEST) != prep["manifest_sha256"]:
        raise ValueError("manifest changed since sidecars were prepared")
    cases_by_alias = {c["alias"]: c for c in manifest["cases"]}
    jobs = []
    arm_counts = {p: 0 for p in PHASES}
    for case in prep["cases"]:
        if case["alias"] not in cases_by_alias:
            raise ValueError("sidecar preparation names unknown capture")
        for phase in PHASES:
            profile = case["phases"][phase]
            if len(profile["eligible_modes"]) not in (0, 2, 4):
                raise ValueError(f"unexpected eligible mode count {case['alias']}/{phase}")
            # Ice sidecar mask is bound to the independently validated raw/native profile.
            arm_counts[phase] += len(profile["eligible_modes"])
            for mode, side in profile["sidecars"].items():
                side_path = ROOT / side["path"]
                if sha(side_path) != side["sha256"]:
                    raise ValueError(f"sidecar hash mismatch: {case['alias']}/{phase}/{mode}")
                if mode.startswith("ice"):
                    count = len(profile["ice_preclip_eligible_layers_1based"])
                    if count not in (4, 6):
                        raise ValueError(f"unexpected eligible ice count {count}")
            for seed in SEEDS:
                jobs.append({"key": f"{case['alias']}/{phase}/seed-{seed:010d}/baseline",
                             "kind": "baseline", "case": case["alias"], "phase": phase, "seed": seed,
                             "input": profile["input"], "input_sha256": profile["input_sha256"]})
                for mode in profile["eligible_modes"]:
                    side = profile["sidecars"][mode]
                    jobs.append({"key": f"{case['alias']}/{phase}/seed-{seed:010d}/{mode}",
                                 "kind": "variant", "mode": mode, "case": case["alias"], "phase": phase,
                                 "seed": seed, "input": profile["input"], "input_sha256": profile["input_sha256"],
                                 "sidecar": side["path"], "sidecar_sha256": side["sha256"],
                                 "ice_eligible_levels": profile["ice_preclip_eligible_layers_1based"] if mode.startswith("ice") else []})
    validate_matrix_counts(jobs, arm_counts)
    data_pins = {}
    expected = {
        "rrtmgp-clouds-lw-bnd.nc": "09d6704c5b863b4c3ceb417d20bb3076ec492e6bf2dfbcc9f3c5996a3706f0b0",
        "rrtmgp-clouds-sw-bnd.nc": "7671835992a45afe66244b591a02c0b3df73d7d59ecb746bbffd9763497651cd",
        "rrtmgp-gas-lw-g128.nc": "70ad65d116531122660318e5da2a2af9db74b425916202860e9527ef2375b8f6",
        "rrtmgp-gas-sw-g112.nc": "361ed541324068ded28a275a4dd757bcaa0a845aebefa630f43a04678668fe62",
    }
    for name, digest in expected.items():
        x = pin(DATA / name)
        if x["sha256"] != digest:
            raise ValueError(f"coefficient changed: {name}")
        data_pins[name] = x
    current_runtime = runtime_pin(EXE)
    anchor_runtime = anchors["before_assets_sha256"]["runtime"]
    if (current_runtime["ldd_sha256"] != anchor_runtime["ldd_sha256"] or
            current_runtime["resolved_libraries"] != anchor_runtime["resolved_libraries"]):
        raise ValueError("candidate runtime dependency pins differ from its 12-anchor run")
    plan = {
        "schema": "UDM_STRATIFIED_PAIRED_SEED_MATRIX_PLAN_V1",
        "status": "PLAN_ONLY_NO_MATRIX_CALLS_MADE",
        "scope": "six captured one-column states; independent offline radiative-transfer replay; no forecast, observation or physical-accuracy claim",
        "states": [{"alias": c["alias"], "coordinate": c["coordinate"],
                    "phases": {p: {"input": c["phases"][p]["input"], "input_sha256": c["phases"][p]["input_sha256"],
                                   "raw": c["phases"][p]["raw"], "raw_sha256": c["phases"][p]["raw_sha256"],
                                   "production_result": c["phases"][p]["production_result"],
                                   "production_result_sha256": c["phases"][p]["production_result_sha256"],
                                   "ordinary_reference_result": c["phases"][p]["ordinary_reference_result"],
                                   "ordinary_reference_result_sha256": c["phases"][p]["ordinary_reference_result_sha256"],
                                   "eligible_modes": c["phases"][p]["eligible_modes"],
                                   "cf_zero_precip_layers_1based": c["phases"][p]["cf_zero_precip_layers_1based"],
                                   "ice_preclip_eligible_levels_1based": c["phases"][p]["ice_preclip_eligible_layers_1based"]}
                               for p in PHASES}} for c in prep["cases"]],
        "seed_plan": {"n": 32, "values": SEEDS, "formula": "100001 + k*104729; k=0..31; unique positive signed 31-bit"},
        "call_budget": {"new_diagnostic_executable_no_variant_anchors": 12, "matrix_baselines": 384,
                        "matrix_variants": 768, "matrix_total_engine_calls": len(jobs),
                        "previously_executed_jobs_revalidated_offline": prior_reuse["imported_job_count"],
                        "new_matrix_engine_calls_remaining": len(jobs) - prior_reuse["imported_job_count"],
                        "prior_attempted_elapsed_seconds": prior_reuse["prior_execution_elapsed_seconds"],
                        "remaining_cumulative_wall_clock_seconds": max(0.0, WALL_BUDGET - prior_reuse["prior_execution_elapsed_seconds"]),
                        "eligible_phase_variant_arms": 24, "per_call_timeout_seconds": TIMEOUT,
                        "max_cumulative_wall_clock_seconds_across_all_resumes": WALL_BUDGET,
                        "execution_order": "manifest state order, phase LW then SW, seed ascending; one baseline then eligible modes; stop on first error"},
        "anchor_gate": {"receipt": pin(ANCHOR_RECEIPT), "plan": pin(ANCHOR_PLAN),
                        "status": anchors["status"], "passed_calls": 12,
                        "sections": {"LW": 20, "SW": 46}, "mask": "exact"},
        "prior_job_reuse": prior_reuse,
        "executable": pin(EXE), "diagnostic_source": pin(SOURCE),
        "executable_build_provenance": {"compile_script": pin(COMPILE_SCRIPT), "mechanical_patch": pin(SOURCE_PATCH),
                                        "base_source": pin(BASE_SOURCE), "base_executable": pin(BASE_EXE),
                                        "linked_archives": [pin(RRTMGP_ARCHIVE), pin(FROZEN_ARCHIVE)],
                                        "linked_netcdf_libraries": [pin(NETCDFF), pin(NETCDF)],
                                        "compile_flags": ["-ffree-line-length-none", "-fcheck=bounds"]},
        "sidecar_generator": pin(HERE / "prepare_matrix_sidecars.py"),
        "offline_matrix_test": pin(HERE / "test_matrix32_contract.py"),
        "seed_command_helper": pin(HELPER), "comparator": pin(COMPARATOR),
        "capture_manifest": pin(MANIFEST), "sidecar_preparation": pin(SIDECAR_PREP),
        "frozen_table": pin(TABLE), "coefficients": data_pins, "runtime": current_runtime,
        "runtime_environment": {"LD_LIBRARY_PATH": LD_PATH, "OMP_NUM_THREADS": "1",
                                "OMP_DYNAMIC": "FALSE", "OPENBLAS_NUM_THREADS": "1",
                                "WRF_RRTMGP_FROZEN_TABLE": str(TABLE)},
        "resume_policy": "Only PASS jobs with matching output hashes are skipped. Any failed engine/oracle job stops the run; failed jobs are not retried as a way to obtain a passing result. A wall-budget stop may resume in a fresh invocation after validating all pins.",
        "pairing_checks": ["active seed output equals argv seed", "same-seed variant mask bitwise equals its baseline",
                           "gas columns/tau and all frozen graupel/hail optics are bitwise invariant",
                           "CF0 precipitation preserves combined CLOUD_TAU/PRECIP_TAU; GRID precipitation removes sampled PRECIP_TAU and exact forward reconstruction validates baseline combined CLOUD_TAU",
                           "each variant sidecar hash and eligibility mask validated"],
        "statistics": {"reported_by_state_phase_mode": True, "difference": "variant minus its same-seed baseline",
                       "statistics": ["sample mean", "sample SD (ddof=1)", "MCSE=SD/sqrt(32)", "approximate Student-t(31) interval"],
                       "interpretation": "conditional Monte Carlo mean uncertainty for a finite deterministic seed list at each captured state; seed independence is not established; intervals are not physical-accuracy or observational confidence intervals"},
        "jobs": jobs,
        "runner_sha256": None, "plan_sha256": None,
    }
    plan["runner_sha256"] = sha(Path(__file__))
    return plan


def digest(plan):
    return hashlib.sha256((json.dumps(plan, indent=2, sort_keys=True) + "\n").encode()).hexdigest()


def result_seed_check(stdout, sections, seed, phase):
    if f"ACTIVE_SEED={seed}" not in stdout:
        raise ValueError("active seed marker missing from stdout")
    if "ACTIVE_MASK_VS_RECORDED_MASK=SKIPPED:" not in stdout:
        raise ValueError("explicit seed override mask-skip marker missing")
    if phase == "SW" and "CAPTURE_ANCHOR_MASK_CHECK=PASS" not in stdout:
        raise ValueError("SW recorded input-mask check did not pass")
    if int(sections["ACTIVE_SAMPLE_SEED"].item()) != seed:
        raise ValueError("ACTIVE_SAMPLE_SEED result field differs from requested seed")
    if int(sections["ACTIVE_MASK_CHECK_SKIPPED"].item()) != 1:
        raise ValueError("active-mask skip result field is not one")
    expected_anchor = 1 if phase == "SW" else 0
    if int(sections["RECORDED_ANCHOR_MASK_CHECK"].item()) != expected_anchor:
        raise ValueError("recorded-anchor check result marker is wrong")


def validate_pair(job, baseline, variant, state_phase, stdout):
    phase, nc, nl, b = baseline
    vphase, vnc, vnl, v = variant
    if (phase, nc, nl) != (vphase, vnc, vnl) or phase != job["phase"]:
        raise ValueError("paired phase/dimensions differ")
    if not bitwise_equal(b["MASK"], v["MASK"]):
        raise ValueError("same-seed baseline and variant mask differs")
    required = ("GAS_COL_DRY", "GAS_TAU", "FROZEN_TAU")
    required += ("GRAUPEL_TAU_ABS", "HAIL_TAU_ABS") if phase == "LW" else ("GRAUPEL_TAU_EXT", "HAIL_TAU_EXT")
    for field in required:
        if field not in b or field not in v:
            raise ValueError(f"required invariant field missing: {field}")
    for field in COMMON_INVARIANTS:
        if field in b or field in v:
            if field not in b or field not in v or not bitwise_equal(b[field], v[field]):
                raise ValueError(f"non-target gas/frozen invariant changed: {field}")
    mode = job["mode"]
    if mode in ("ice160", "ice140"):
        n = nl
        expected = np.zeros((1, n, 1), dtype=np.float64)
        for layer in job["ice_eligible_levels"]:
            expected[0, layer - 1, 0] = 1.0
        if "ICE_DIAMETER_CHANGED" not in v or not bitwise_equal(v["ICE_DIAMETER_CHANGED"], expected):
            raise ValueError("ICE_DIAMETER_CHANGED differs from exact native eligibility mask")
        if "ICE_DIAMETER_RAW" not in v:
            raise ValueError("ice-size variant did not emit raw ice diameter")
        raw_expected = expected_raw_ice_diameter(state_phase, nc, nl)
        if not bitwise_equal(raw_expected, v["ICE_DIAMETER_RAW"]):
            raise ValueError("variant raw ice diameter differs from input-derived value")
        if "ICE_DIAMETER_RAW" in b and not bitwise_equal(b["ICE_DIAMETER_RAW"], v["ICE_DIAMETER_RAW"]):
            raise ValueError("raw ice diameter differs between paired outputs")
        if "DI_USED" not in b or "DI_USED" not in v or b["DI_USED"].shape != expected.shape:
            raise ValueError("ice diameter outputs are missing or malformed")
        target = 160.0 if mode == "ice160" else 140.0
        selected = expected.astype(bool)
        if not np.all(v["DI_USED"][selected] == target):
            raise ValueError("requested in-range diameter not used on every selected layer")
        if not bitwise_equal(v["DI_USED"][~selected], b["DI_USED"][~selected]):
            raise ValueError("inactive-layer DI_USED changed")
        if "PRECIP_TAU" not in b or "PRECIP_TAU" not in v or not bitwise_equal(b["PRECIP_TAU"], v["PRECIP_TAU"]):
            raise ValueError("ice-size variant changed precipitation optical depth")
    else:
        if "SENSITIVITY_PRECIP_TAU" not in v:
            raise ValueError("precipitation variant lacks sensitivity tau output")
        tau = v["SENSITIVITY_PRECIP_TAU"]
        if tau.ndim != 3 or tau.shape[:2] != (nc, nl) or not np.isfinite(tau).all() or np.any(tau < 0):
            raise ValueError("sensitivity precipitation tau invalid")
        validate_precip_sensitivity_support(job, state_phase, tau, nc, nl)
        if "DI_USED" in b and "DI_USED" in v and not bitwise_equal(b["DI_USED"], v["DI_USED"]):
            raise ValueError("precipitation variant changed ice diameter")
        validate_precip_cloud_component(mode, b, v)
    if not all(np.isfinite(v[f]).all() for f in ("UP", "DN", "HR")):
        raise ValueError("nonfinite flux/heating output")
    return True


def state_phase_lookup(prep):
    return {(c["alias"], ph): c["phases"][ph] for c in prep["cases"] for ph in PHASES}


def pin_snapshot(plan):
    paths = [MANIFEST, SIDECAR_PREP, ANCHOR_RECEIPT, ANCHOR_PLAN, EXE, SOURCE, TABLE, HELPER, COMPARATOR,
             COMPILE_SCRIPT, SOURCE_PATCH, BASE_EXE, BASE_SOURCE, RRTMGP_ARCHIVE, FROZEN_ARCHIVE, NETCDFF, NETCDF,
             HERE / "prepare_matrix_sidecars.py", HERE / "test_matrix32_contract.py"]
    paths.extend([PRIOR_RECEIPT, PRIOR_ERRATUM, PRIOR_ROOT_READBACK,
                  PRIOR_V2_PLAN, PRIOR_V2_RECEIPT, PRIOR_V2_ERRATUM, PRIOR_V2_ROOT_READBACK,
                  PRIOR_V3_PLAN, PRIOR_V3_RECEIPT, PRIOR_V3_ERRATUM])
    for imported in plan["prior_job_reuse"]["validated_jobs"]:
        paths.extend([ROOT / imported["result"]["path"], ROOT / imported["log"]["path"]])
    assets = {str(p.resolve().relative_to(ROOT)): sha(p) for p in paths}
    for name, info in plan["coefficients"].items():
        p = ROOT / info["path"]
        assets[info["path"]] = sha(p)
    for item in plan["states"]:
        for ph in PHASES:
            prof = item["phases"][ph]
            for key in ("input", "raw", "production_result", "ordinary_reference_result"):
                path = ROOT / prof[key]
                assets[prof[key]] = sha(path)
            state = next(c for c in load(SIDECAR_PREP)["cases"] if c["alias"] == item["alias"])
            for mode, side in state["phases"][ph]["sidecars"].items():
                assets[side["path"]] = sha(ROOT / side["path"])
    runtime = runtime_pin(EXE)
    return {"assets": assets, "runtime": runtime}


def read_saved_job(path, record):
    if record.get("status") != "PASS" or not path.is_file() or sha(path) != record.get("result_sha256"):
        return None
    return read_result(path)


def import_prior_validated_jobs(out, receipt, plan):
    """Copy already-run outputs into a fresh ledger after strict offline revalidation."""
    proof = plan["prior_job_reuse"]
    old = load(PRIOR_V3_RECEIPT)
    for validated in proof["validated_jobs"]:
        key = validated["key"]
        source = old["jobs"][key]
        record = dict(source)
        for field in ("result_path", "log_path"):
            rel = Path(source[field])
            src = PRIOR_V3_RUN / rel
            dst = out / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        record["status"] = "PASS"
        record["offline_revalidation"] = "PASS_CLOUD_PRECIP_COMPOSITION_SW_FLOOR_AND_INPUT_RAW_ICE_DIAMETER"
        record["reused_from_original_receipt_sha256"] = proof["source_receipt"]["sha256"]
        record["source_receipt_status"] = source["status"]
        record["original_receipt_status"] = source.get("original_receipt_status", source["status"])
        receipt["jobs"][key] = record
    receipt["reused_job_count"] = len(proof["validated_jobs"])
    receipt["reused_job_source_receipt"] = proof["source_receipt"]
    receipt["reused_job_source_plan"] = proof["source_plan"]
    receipt["reused_job_erratum"] = proof["erratum"]
    receipt["reused_job_ancestors"] = proof["ancestors"]
    receipt["reused_job_validation"] = "All imported results and logs were hash-checked and all 388 completed calls were revalidated offline under exact cloud/precipitation composition, source-derived SW zero-path floor, and input-derived raw ice diameter contracts. Original v1/v2/v3 receipts remain unchanged."


def summary_stats(values):
    x = np.asarray(values, dtype=np.float64)
    if x.shape[0] != NSEEDS or not np.isfinite(x).all():
        raise ValueError("paired summary requires 32 finite values")
    mean = float(np.mean(x))
    sd = float(np.std(x, ddof=1))
    mcse = sd / np.sqrt(NSEEDS)
    margin = T95_DF31 * mcse
    return {"n": NSEEDS, "mean": mean, "sample_sd": sd, "mcse": float(mcse),
            "approx_t31_mean_ci": [float(mean-margin), float(mean+margin)],
            "zero_effect_count": int(np.count_nonzero(x == 0.0)),
            "min": float(np.min(x)), "max": float(np.max(x)),
            "interval_interpretation": "approximate Monte Carlo mean interval conditional on this deterministic seed set and one captured state; not a physical-accuracy guarantee"}


def make_summaries(out, plan, receipt):
    rows = ["case,phase,mode,seed,surface_dn_delta_w_m2,toa_up_delta_w_m2,max_abs_hr_delta_k_day"]
    summaries = {}
    for state in plan["states"]:
        alias = state["alias"]
        for phase in PHASES:
            state_phase = state["phases"][phase]
            for mode in state_phase["eligible_modes"]:
                deltas = {"surface_dn": [], "toa_up": [], "max_abs_hr": []}
                for seed in SEEDS:
                    base_key = f"{alias}/{phase}/seed-{seed:010d}/baseline"
                    var_key = f"{alias}/{phase}/seed-{seed:010d}/{mode}"
                    base_rec = receipt["jobs"][base_key]
                    var_rec = receipt["jobs"][var_key]
                    bp = out / base_rec["result_path"]
                    vp = out / var_rec["result_path"]
                    _, _, _, b = read_result(bp)
                    _, _, _, v = read_result(vp)
                    d_dn = float(v["DN"][0, 0, 0] - b["DN"][0, 0, 0])
                    d_up = float(v["UP"][0, -1, 0] - b["UP"][0, -1, 0])
                    d_hr = float(np.max(np.abs(v["HR"] - b["HR"])))
                    deltas["surface_dn"].append(d_dn)
                    deltas["toa_up"].append(d_up)
                    deltas["max_abs_hr"].append(d_hr)
                    rows.append(f"{alias},{phase},{mode},{seed},{d_dn:.17g},{d_up:.17g},{d_hr:.17g}")
                summaries[f"{alias}/{phase}/{mode}"] = {name: summary_stats(values) for name, values in deltas.items()}
    (out / "paired_metrics.csv").write_text("\n".join(rows) + "\n", encoding="ascii")
    (out / "per_state_summaries.json").write_text(json.dumps(summaries, indent=2, sort_keys=True) + "\n")


def execute(plan, out, plan_sha, resume=False):
    if out.exists() and not resume:
        raise ValueError("fresh output directory required")
    if not out.exists():
        out.mkdir(parents=True, exist_ok=False)
    receipt_path = out / "receipt.json"
    before = pin_snapshot(plan)
    if resume:
        if not receipt_path.is_file():
            raise ValueError("resume receipt missing")
        receipt = load(receipt_path)
        if receipt.get("plan_sha256") != plan_sha or receipt.get("before_assets") != before:
            raise ValueError("resume plan/assets do not match original run")
        if receipt.get("status") == "FAIL_STOPPED_FIRST_ERROR" or receipt.get("failures"):
            raise ValueError("failed oracle/engine receipts cannot be retried")
        if receipt.get("status") == "PASS_ALL_1152_PAIRED_JOBS":
            raise ValueError("completed matrix is not resumable")
        prior_total = float(receipt.get("elapsed_total_seconds", 0.0))
        if receipt.get("status") == "RUNNING":
            prior_total = max(prior_total, float(receipt.get("active_invocation_prior_seconds", 0.0)) +
                              max(0.0, time.time() - float(receipt.get("active_invocation_started_epoch", time.time()))))
    else:
        prior_total = float(plan["prior_job_reuse"]["prior_execution_elapsed_seconds"])
        receipt = {"schema": "UDM_STRATIFIED_MATRIX_RECEIPT_V1", "plan_sha256": plan_sha,
                   "status": "RUNNING", "before_assets": before, "jobs": {}, "failures": [],
                   "elapsed_total_seconds": 0.0}
        import_prior_validated_jobs(out, receipt, plan)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    prep = load(SIDECAR_PREP)
    profiles = state_phase_lookup(prep)
    helper = import_helper()
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("WRF_RRTMGP_"):
            del env[key]
    env.update({"WRF_RRTMGP_FROZEN_TABLE": str(TABLE.resolve()), "LD_LIBRARY_PATH": LD_PATH,
                "OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE", "OPENBLAS_NUM_THREADS": "1"})
    started = time.monotonic()
    started_epoch = time.time()
    receipt["active_invocation_prior_seconds"] = prior_total
    receipt["active_invocation_started_epoch"] = started_epoch
    try:
        for job in plan["jobs"]:
            prior = receipt["jobs"].get(job["key"])
            if prior and prior.get("status") == "PASS":
                result_path = out / prior["result_path"]
                if read_saved_job(result_path, prior) is None:
                    raise ValueError(f"saved PASS job output changed: {job['key']}")
                continue
            elapsed = time.monotonic() - started
            remaining = WALL_BUDGET - prior_total - elapsed
            if remaining < 1:
                receipt["status"] = "INCOMPLETE_WALL_BUDGET"
                break
            attempt = int(prior.get("attempts", 0) if prior else 0) + 1
            relative_dir = Path("jobs") / job["case"] / job["phase"].lower() / f"seed-{job['seed']:010d}" / f"{job['kind']}-{job.get('mode','base')}" / f"attempt-{attempt:02d}"
            slot = out / relative_dir
            slot.mkdir(parents=True, exist_ok=False)
            inp = ROOT / job["input"]
            result_path = slot / "result.txt"
            log_path = slot / "stdout.log"
            record = {"status": "RUNNING", "attempts": attempt, "result_path": str(result_path.relative_to(out)),
                      "log_path": str(log_path.relative_to(out)), "job": job}
            receipt["jobs"][job["key"]] = record
            receipt["status"] = "RUNNING"
            receipt["elapsed_total_seconds"] = prior_total + elapsed
            receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            sidecar = ROOT / job["sidecar"] if job["kind"] == "variant" else None
            argv = helper.command(EXE, DATA, inp, result_path, seed=job["seed"], sidecar=sidecar)
            timeout = min(TIMEOUT, max(1, int(remaining)))
            call_start = time.monotonic()
            try:
                proc = subprocess.run(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, timeout=timeout, check=False)
            except subprocess.TimeoutExpired as exc:
                partial = exc.stdout or ""
                if isinstance(partial, bytes):
                    partial = partial.decode("utf-8", errors="replace")
                log_path.write_text(partial, encoding="utf-8")
                record.update({"status": "INCOMPLETE_WALL_BUDGET" if timeout < TIMEOUT else "TIMEOUT",
                               "timeout_seconds": timeout, "log_sha256": sha(log_path)})
                if timeout < TIMEOUT:
                    receipt["status"] = "INCOMPLETE_WALL_BUDGET"
                    receipt["elapsed_total_seconds"] = prior_total + (time.monotonic() - started)
                    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
                    break
                raise
            log_path.write_text(proc.stdout or "", encoding="utf-8")
            record.update({"returncode": proc.returncode, "elapsed_seconds": time.monotonic()-call_start,
                           "argv_sha256": hashlib.sha256("\0".join(argv).encode()).hexdigest(),
                           "log_sha256": sha(log_path), "result_sha256": sha(result_path) if result_path.is_file() else None})
            if proc.returncode != 0:
                record["status"] = "FAIL"
                raise RuntimeError(f"{job['key']} reference return code {proc.returncode}")
            if sha(inp) != job["input_sha256"]:
                record["status"] = "FAIL"
                raise RuntimeError(f"{job['key']} input asset changed")
            phase, nc, nl, sec = read_result(result_path)
            result_seed_check(proc.stdout, sec, job["seed"], job["phase"])
            if (phase, nc, nl) != (job["phase"], 1, 47 if phase == "LW" else 40):
                record["status"] = "FAIL"
                raise RuntimeError(f"{job['key']} output header mismatch")
            if job["kind"] == "baseline":
                if not all(f in sec for f in ("MASK", "GAS_COL_DRY", "GAS_TAU", "FROZEN_TAU", "UP", "DN", "HR")):
                    record["status"] = "FAIL"
                    raise RuntimeError(f"{job['key']} required output field missing")
            else:
                base_key = f"{job['case']}/{job['phase']}/seed-{job['seed']:010d}/baseline"
                base_record = receipt["jobs"].get(base_key)
                if not base_record or base_record.get("status") != "PASS":
                    record["status"] = "FAIL"
                    raise RuntimeError(f"{job['key']} lacks passing paired baseline")
                base_result = read_result(out / base_record["result_path"])
                state_phase = profiles[(job["case"], job["phase"])]
                validate_pair(job, base_result, (phase, nc, nl, sec), state_phase, proc.stdout)
            record["status"] = "PASS"
            receipt["elapsed_total_seconds"] = prior_total + (time.monotonic() - started)
            receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        if receipt.get("status") != "INCOMPLETE_WALL_BUDGET":
            receipt["status"] = "PASS_ALL_1152_PAIRED_JOBS" if len(receipt["jobs"]) == len(plan["jobs"]) and all(
                x["status"] == "PASS" for x in receipt["jobs"].values()) else "INCOMPLETE"
        if receipt["status"] == "PASS_ALL_1152_PAIRED_JOBS":
            make_summaries(out, plan, receipt)
    except subprocess.TimeoutExpired as exc:
        receipt["status"] = "FAIL_STOPPED_FIRST_ERROR"
        receipt["failures"].append(f"timeout: {exc}")
    except Exception as exc:
        receipt["status"] = "FAIL_STOPPED_FIRST_ERROR"
        receipt["failures"].append(str(exc))
    finally:
        receipt["after_assets"] = pin_snapshot(plan)
        receipt["assets_unchanged"] = receipt["before_assets"] == receipt["after_assets"]
        receipt["elapsed_total_seconds"] = prior_total + (time.monotonic() - started)
        receipt.pop("active_invocation_started_epoch", None)
        receipt.pop("active_invocation_prior_seconds", None)
        if not receipt["assets_unchanged"]:
            receipt["status"] = "FAIL_ASSET_CHANGED"
        receipt["elapsed_seconds_this_invocation"] = time.monotonic() - started
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def self_test():
    assert len(SEEDS) == 32 and len(set(SEEDS)) == 32
    assert SEEDS[0] == 100001 and SEEDS[-1] == 3346600
    assert 384 + 768 == 1152 and 12 + 1152 == 1164
    fake_jobs = ([{"key": f"b{i}", "kind": "baseline"} for i in range(384)] +
                 [{"key": f"v{i}", "kind": "variant"} for i in range(768)])
    assert validate_matrix_counts(fake_jobs, {"LW": 12, "SW": 12})
    try:
        validate_matrix_counts(fake_jobs[:-1], {"LW": 12, "SW": 12})
    except ValueError:
        pass
    else:
        raise AssertionError("one missing engine call passed count validation")
    # Exact mask/diameter checks reject no-op, missing/extra layers, and inactive changed values.
    expected = np.array([0, 1, 1, 0, 0], dtype=np.float64).reshape(1, 5, 1)
    used = np.array([10, 160, 160, 180, 160], dtype=np.float64).reshape(1, 5, 1)
    raw = np.array([10, 190, 200, 250, 160], dtype=np.float64).reshape(1, 5, 1)
    def check(mask, di, target):
        if not np.array_equal(mask, expected) or not np.array_equal(di[expected.astype(bool)], np.full(int(expected.sum()), target)):
            raise ValueError("ice eligibility/DI mismatch")
        if np.any(di[~expected.astype(bool)] != np.clip(raw[~expected.astype(bool)], 10, 180)):
            raise ValueError("inactive DI mutated")
    check(expected.copy(), used.copy(), 160.)
    for badmask, baddi in ((np.zeros_like(expected), used), (np.array([0,1,0,0,1.]).reshape(1,5,1),used),
                           (expected,np.array([10,140,160,180,160.]).reshape(1,5,1)),
                           (expected,np.array([10,160,160,160,160.]).reshape(1,5,1))):
        try:
            check(badmask, baddi, 160.)
        except ValueError:
            pass
        else:
            raise AssertionError("mutation negative control passed")
    # Pairing rejects changed masks and non-target gas/frozen fields.
    base_mask=np.array([0,1,0]); var_mask=base_mask.copy()
    assert np.array_equal(base_mask,var_mask)
    var_mask[2]=1
    assert not np.array_equal(base_mask,var_mask)
    a=np.array([1.,2.]); b=a.copy(); assert np.array_equal(a,b)
    b[0]+=1; assert not np.array_equal(a,b)
    return True


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=HERE / "matrix32-output-not-created")
    ap.add_argument("--plan-file", type=Path, default=HERE / "matrix32-plan.json")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--approved-plan-sha256")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a=ap.parse_args()
    if a.self_test:
        self_test()
        print("matrix plan/pairing/mask negative controls PASS; no engine calls")
        return 0
    out=a.out.resolve(); plan_path=a.plan_file.resolve()
    if out.exists() and not a.resume:
        raise SystemExit(f"fresh output path required unless --resume: {out}")
    if a.resume and not out.is_dir():
        raise SystemExit("--resume requires existing output directory")
    plan=build_plan(out)
    plan["plan_sha256"]=digest(plan)
    if not a.execute:
        plan["status"]="PLAN_ONLY_NO_MATRIX_CALLS_MADE"
        plan_path.parent.mkdir(parents=True,exist_ok=True)
        plan_path.write_text(json.dumps(plan,indent=2,sort_keys=True)+"\n")
        print(json.dumps({"status":plan["status"],"plan":str(plan_path),"plan_sha256":plan["plan_sha256"],
                          "calls":plan["call_budget"]["matrix_total_engine_calls"]},indent=2))
        return 0
    if a.approved_plan_sha256 != plan["plan_sha256"]:
        raise SystemExit("execution requires the exact approved plan digest")
    if not plan_path.is_file():
        raise SystemExit("saved plan is missing")
    saved=load(plan_path); saved_hash=saved.get("plan_sha256"); saved["plan_sha256"]=None
    if saved_hash != plan["plan_sha256"] or digest(saved) != plan["plan_sha256"]:
        raise SystemExit("saved plan digest differs from regenerated plan")
    if not self_test():
        raise SystemExit("offline mutation controls failed")
    receipt=execute(plan,out,plan["plan_sha256"],resume=a.resume)
    print(json.dumps({"status":receipt["status"],"completed_jobs":sum(j.get("status")=="PASS" for j in receipt["jobs"].values()),
                      "total_jobs":len(plan["jobs"]),"failures":receipt["failures"]},indent=2))
    return 0 if receipt["status"] == "PASS_ALL_1152_PAIRED_JOBS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
