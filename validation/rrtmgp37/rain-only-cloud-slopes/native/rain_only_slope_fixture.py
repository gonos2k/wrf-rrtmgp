#!/usr/bin/env python3
"""Bounded standalone regression for undefined cloud slopes in rain-only columns.

This compiles the retained pre-fix UDM source and the candidate UDM source at
O0/O2 with signaling-NaN initialization and floating-point traps. No WRF
forecast, REAL, or radiation solver is launched. A test-only candidate copy
adds read-only slope-vector markers to prove whether a shrinking cloud top
retains already initialized values between the two cloud-slope calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys


PARENT_REVISION = "e3b9e52c2a20811830a27d34420721ca89b62e59"
PARENT_UDM_SHA256 = "7998df8f1f6a3b9f63f285a60016447cbbcf4802b7a31a711442c90b8c59a8fc"
PROFILES = {1: "rain_only", 2: "rain_above_cloud", 3: "cloud_only", 4: "full_overlap", 5: "trace_cloud_top_control"}
CONTROL_PROFILES = (3, 4, 5)
TRAP_PROFILES = (1, 2)
STRICT = ["-g", "-ffree-form", "-ffree-line-length-none", "-fcheck=all",
          "-finit-real=snan", "-ffpe-trap=invalid,zero,overflow", "-fbacktrace", "-fno-fast-math"]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pin(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {"path": str(path.resolve()), "size_bytes": len(data), "sha256": sha(data)}


def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def run(command: list[str], cwd: Path, log: Path, records: list[dict[str, object]], role: str,
        timeout: int = 180, expected_failure: bool = False) -> dict[str, object]:
    record: dict[str, object] = {"role": role, "command": command, "cwd": str(cwd), "timeout_seconds": timeout}
    records.append(record)
    process = None
    timed_out = False
    try:
        with log.open("xb") as output:
            process = subprocess.Popen(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True, env={**os.environ, "LC_ALL": "C", "OMP_NUM_THREADS": "1"})
            record.update(pid=process.pid, status="RUNNING", log_path=str(log))
            try:
                rc = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGKILL)
                rc = process.wait()
            except BaseException:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                rc = process.wait()
                record.update(actual_returncode=rc, status="INTERRUPTED")
                atomic(log.with_suffix(log.suffix + ".process.json"), record)
                raise
            output.flush()
            os.fsync(output.fileno())
        record.update(actual_returncode=rc, timed_out=timed_out,
                      status="EXPECTED_NONZERO" if expected_failure and rc != 0 else "TERMINAL")
        # The actual RC is durable before any log classification or parsing.
        atomic(log.with_suffix(log.suffix + ".process.json"), record)
        record["log_sha256"] = sha(log.read_bytes())
        if timed_out:
            raise RuntimeError(f"{role} timed out; retained log {log}")
        if expected_failure:
            if rc == 0:
                raise RuntimeError(f"{role} unexpectedly returned zero; retained log {log}")
        elif rc != 0:
            raise RuntimeError(f"{role} returned {rc}; retained log {log}")
        record["log_sha256"] = sha(log.read_bytes())
        return record
    except BaseException:
        if process is None:
            record["status"] = "NOT_LAUNCHED"
            atomic(log.with_suffix(log.suffix + ".process.json"), record)
        raise


def instrument_candidate(source: bytes) -> bytes:
    """Add test-only slope vector records around both cloud-slope calls."""
    call = (b"   call slope_cloud(1,kdim,ktop,qci(:,i,1),ncr(:,i,2),den(:,i),denfac(:,i),    &\n"
            b"        t(:,i),qcmin,rslopec(:),rslopec2(:),rslopec3(:))")
    if source.count(call) != 2:
        raise ValueError("expected exactly two udm2d cloud-slope call anchors")
    result = source
    for site in (1, 2):
        marker = (f"   write(*,'(A,4(1X,I0),*(1X,ES25.16E3))') 'SLOPEV',loop,{site},0,ktopqc,rslopec2(:)\n".encode()
                  + call + b"\n"
                  + f"   write(*,'(A,4(1X,I0),*(1X,ES25.16E3))') 'SLOPEV',loop,{site},1,ktopqc,rslopec2(:)\n".encode())
        result = result.replace(call, marker, 1)
    return result


def parse_output(text: str, profile: int, require_slope_trace: bool) -> tuple[dict[tuple[int, int], dict[str, object]], list[dict[str, object]]]:
    results: dict[tuple[int, int], dict[str, object]] = {}
    traces: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    lines = text.splitlines()
    i = 0
    last_key: tuple[int, int] | None = None
    while i < len(lines):
        tokens = lines[i].split()
        if not tokens:
            i += 1
            continue
        if tokens[0] == "CALL":
            if len(tokens) != 4 or tuple(map(int, tokens[1:2])) != (profile,):
                raise ValueError("malformed/mismatched CALL record")
            current = {"branch": int(tokens[2]), "mode": int(tokens[3]), "slope_trace": []}
        elif tokens[0] == "SLOPEV":
            if current is None or len(tokens) < 6:
                raise ValueError("unscoped slope trace")
            trace = {"loop": int(tokens[1]), "site": int(tokens[2]), "phase": int(tokens[3]),
                     "cloud_top": int(tokens[4]), "rslopec2": [float(x) for x in tokens[5:]],
                     "branch": int(current["branch"]), "mode": int(current["mode"])}
            if not all(math.isfinite(x) for x in trace["rslopec2"]):
                raise ValueError("nonfinite cloud slope marker")
            traces.append(trace)
            current["slope_trace"].append(trace)
        elif tokens[0] == "RESULT":
            if current is None or len(tokens) != 5:
                raise ValueError("malformed/unscoped result header")
            key = (int(tokens[2]), int(tokens[3]))
            count = int(tokens[4])
            if int(tokens[1]) != profile or key in results or i+1 >= len(lines):
                raise ValueError("duplicate/mismatched result key")
            words = lines[i+1].split()
            if count != 16*7+9 or len(words) != count or any(len(w) != 8 or any(c not in "0123456789ABCDEF" for c in w) for w in words):
                raise ValueError("malformed binary32 output words")
            results[key] = {"words": words, "trace": current["slope_trace"]}
            last_key = key
            current = None
            i += 1
        elif tokens[0] == "DIAG":
            if last_key is None or len(tokens) != 3 or last_key not in results or "diag" in results[last_key]:
                raise ValueError("malformed/unpaired optional-diagnostic record")
            results[last_key]["diag"] = [int(tokens[1]), int(tokens[2])]
        i += 1
    if results and set(results) != {(branch, mode) for branch in range(1, 4) for mode in range(3)}:
        raise ValueError("incomplete branch/density-mode output roster")
    if require_slope_trace and not traces:
        raise ValueError("missing test-only slope trace")
    return results, traces


def shrink_retention_control(traces: list[dict[str, object]]) -> dict[str, object]:
    grouped: dict[tuple[int, int, int], dict[tuple[int, int], dict[str, object]]] = {}
    for row in traces:
        call = (int(row["branch"]), int(row["mode"]), int(row["loop"]))
        grouped.setdefault(call, {})[(int(row["site"]), int(row["phase"]))] = row
    for (branch, mode, loop), points in sorted(grouped.items()):
        first = points.get((1, 1))
        second = points.get((2, 0))
        if not first or not second or int(second["cloud_top"]) >= int(first["cloud_top"]):
            continue
        a, b = first["rslopec2"], second["rslopec2"]
        old_top, new_top = int(first["cloud_top"]), int(second["cloud_top"])
        # Require a finite, non-default value above the shrunken top and exact
        # retention from first-call output to second-call input in this substep.
        retained = [k for k in range(new_top + 1, old_top + 1) if a[k-1] == b[k-1] and math.isfinite(a[k-1])]
        before = points.get((1, 0))
        if retained and before and any(a[k-1] != before["rslopec2"][k-1] for k in retained):
            return {"observed": True, "substep": loop, "first_cloud_top": old_top,
                    "second_cloud_top": new_top, "retained_levels_1based": retained,
                    "same_substep_values_preserved": True, "forward_branch": branch, "density_mode": mode}
    return {"observed": False, "reason": "no within-substep cloud-top shrink with a changed retained slope value was observed"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wrf_root", type=Path, help="frozen authoring WRF tree")
    parser.add_argument("--workdir", type=Path, required=True, help="new empty isolated output directory")
    parser.add_argument("--compiler", default=shutil.which("gfortran") or "gfortran")
    parser.add_argument("--baseline-revision", default=PARENT_REVISION)
    args = parser.parse_args()
    wrf = args.wrf_root.resolve()
    work = args.workdir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    compiler = Path(shutil.which(args.compiler) or args.compiler).resolve(strict=True)
    driver = Path(__file__).with_suffix(".f90").resolve()
    repo = wrf.parent
    source_path = wrf / "phys/module_mp_udm.F"
    deps = [wrf / "phys/module_mp_radar.F", wrf / "phys/module_gfs_machine.F"]
    stub_text = ("module module_wrf_error\ncontains\n"
                 "subroutine wrf_debug(level,text)\ninteger,intent(in)::level\ncharacter(*),intent(in)::text\nend subroutine\n"
                 "end module\n")
    stub_source = work / "module_wrf_error.f90"
    stub_source.write_text(stub_text, encoding="ascii")
    current_source = source_path.read_bytes()
    baseline_source = subprocess.check_output(["git", "show", f"{args.baseline_revision}:WRF/phys/module_mp_udm.F"], cwd=repo)
    if sha(baseline_source) != PARENT_UDM_SHA256:
        raise ValueError("baseline UDM source hash differs from the reviewed pre-fix snapshot")
    source_pins_before = {"candidate": pin(source_path), "driver": pin(driver),
                          "dependencies": [pin(p) for p in deps], "compiler": pin(compiler),
                          "repository_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()}
    report: dict[str, object] = {"schema": "udm-rain-only-cloud-slope-fixture-v1", "status": "RUNNING",
        "counts": {"WRF_forecasts": 0, "REAL_calls": 0, "RTE_calls": 0},
        "baseline_revision": args.baseline_revision, "baseline_udm_sha256": sha(baseline_source),
        "candidate_source_sha256": sha(current_source), "driver_sha256": sha(driver.read_bytes()),
        "compiler": pin(compiler), "source_pins_before": source_pins_before, "processes": [], "results": {}}
    receipt = work / "receipt.json"
    atomic(receipt, report)
    records: list[dict[str, object]] = report["processes"]  # type: ignore[assignment]

    try:
        outputs: dict[str, dict[str, object]] = {}
        for optimization in ("O0", "O2"):
            flags = [f"-{optimization}", *STRICT]
            for variant in ("baseline", "candidate"):
                directory = work / optimization / variant
                directory.mkdir(parents=True)
                include = ["-I", str(directory), "-J", str(directory)]
                udm_bytes = baseline_source if variant == "baseline" else instrument_candidate(current_source)
                udm_file = directory / "module_mp_udm.F"
                udm_file.write_bytes(udm_bytes)
                report.setdefault("instrumented_source", {})
                if variant == "candidate":
                    report["instrumented_source"][optimization] = {"sha256": sha(udm_bytes), "size_bytes": len(udm_bytes)}
                sources = [deps[1], stub_source, deps[0], udm_file]
                objects: list[Path] = []
                for source in sources:
                    obj = directory / (source.stem + ".o")
                    extra = ["-ffixed-form"] if source.name == "module_gfs_machine.F" else ["-ffree-form", "-ffree-line-length-none"]
                    compile_flags = flags if source == udm_file else [f"-{optimization}", "-g", *extra]
                    command = [str(compiler), *compile_flags, *include, "-cpp", "-c", str(source), "-o", str(obj)]
                    run(command, directory, directory / f"compile-{source.stem}.log", records, "compile")
                    objects.append(obj)
                executable = directory / "slope_fixture"
                command = [str(compiler), *flags, "-cpp", *include, str(driver), *map(str, objects), "-o", str(executable)]
                run(command, directory, directory / "link.log", records, "link")
                for profile, name in PROFILES.items():
                    expected_failure = variant == "baseline" and profile in TRAP_PROFILES
                    # The old source is expected to expose the undefined-read
                    # trap; candidate controls must complete in both builds.
                    command = [str(executable), str(profile)]
                    log = directory / f"run-{profile}-{name}.log"
                    record = run(command, directory, log, records, f"{variant}_{optimization}_{name}",
                                 expected_failure=expected_failure)
                    if expected_failure:
                        text = log.read_text(errors="replace")
                        fpe = any(token in text.lower() for token in ("floating-point exception", "sigfpe", "invalid operation"))
                        record["expected_historical_trap_observed"] = fpe
                        record["trap_diagnostic_excerpt"] = "\n".join(text.splitlines()[-8:])
                        if not fpe:
                            raise RuntimeError(f"{variant}/{optimization}/{name} terminated nonzero without an FPE marker")
                        report["results"].setdefault(optimization, {}).setdefault(variant, {})[name] = {
                            "expected_nonzero": True, "actual_returncode": record["actual_returncode"],
                            "trap_marker_observed": fpe, "log_sha256": record["log_sha256"]}
                        continue
                    text = log.read_text(errors="replace")
                    parsed, traces = parse_output(text, profile, require_slope_trace=(variant == "candidate" and profile == 5))
                    if variant == "candidate" and profile == 1:
                        if len(parsed) != 9:
                            raise ValueError("rain-only candidate mode/branch roster incomplete")
                    outputs[f"{optimization}/{variant}/{name}"] = {"records": parsed, "traces": traces,
                        "log": pin(log), "expected_nonzero": False}
                    report["results"].setdefault(optimization, {}).setdefault(variant, {})[name] = {
                        "result_keys": [list(k) for k in sorted(parsed)], "log_sha256": sha(log.read_bytes()),
                        "shrink_retention": shrink_retention_control(traces) if variant == "candidate" and profile == 5 else None}
                    atomic(receipt, report)
        # Compare original and candidate on initialized profiles at identical
        # optimization/mode/forwarding branch. Hazard inputs are not parity gates.
        comparisons = []
        for optimization in ("O0", "O2"):
            for profile in CONTROL_PROFILES:
                name = PROFILES[profile]
                base = outputs[f"{optimization}/baseline/{name}"]["records"]
                cand = outputs[f"{optimization}/candidate/{name}"]["records"]
                differing = []
                for key in sorted(base):
                    word_delta = sum(a != b for a,b in zip(base[key]["words"],cand[key]["words"]))
                    diagnostic_delta = base[key].get("diag") != cand[key].get("diag")
                    if word_delta or diagnostic_delta:
                        differing.append({"branch_mode": list(key), "different_binary32_words": word_delta,
                                          "optional_diagnostic_pair_differs": diagnostic_delta})
                if differing:
                    raise ValueError(f"initialized {name} control differs original/candidate: {differing[:2]}")
                comparisons.append({"optimization": optimization, "profile": name,
                                    "all_three_branches_and_density_modes_bitwise_equal": True,
                                    "comparisons": len(base)})
        candidate_hazards = []
        for optimization in ("O0", "O2"):
            for profile in TRAP_PROFILES:
                name = PROFILES[profile]
                records_out = outputs[f"{optimization}/candidate/{name}"]["records"]
                candidate_hazards.append({"optimization": optimization, "profile": name,
                                          "finite_branch_mode_records": len(records_out),
                                          "all_outputs_finite": True,
                                          "rain_only_no_cloud_assertion": profile == 1})
        shrink_reports = [report["results"][o]["candidate"]["trace_cloud_top_control"]["shrink_retention"] for o in ("O0", "O2")]
        after = {"candidate": pin(source_path), "driver": pin(driver),
                 "dependencies": [pin(p) for p in deps]}
        if after["candidate"] != source_pins_before["candidate"] or after["driver"] != source_pins_before["driver"] or after["dependencies"] != source_pins_before["dependencies"]:
            raise ValueError("authoritative source/test/dependency changed during isolated fixture")
        report.update(status="PASS_SCOPED_RAIN_ONLY_SLOPE_INITIALIZATION", source_pins_after=after,
                      comparisons=comparisons, candidate_hazard_profiles=candidate_hazards,
                      shrink_retention_controls=shrink_reports,
                      counts={"compile_link_processes": sum(r["role"] in ("compile", "link") for r in records),
                              "fixture_executions": sum(r["role"].startswith(("baseline_", "candidate_")) for r in records),
                              "WRF_forecasts": 0, "REAL_calls": 0, "RTE_calls": 0},
                      limitations=["The large-drop rain-only profile is a synthetic control selected to avoid later physical rain-to-cloud conversion; it is not a meteorological case.",
                                   "Rain-only/no-cloud assertion applies only to that warm, subsaturated profile; later rain-to-cloud conversion can legitimately form cloud in other states.",
                                   "The baseline nonzero termination is a compiler/runtime exposure of an undefined-read hazard, not a portable promise that every build traps.",
                                   "The trace-cloud-top input completed as a finite initialized control, but no within-substep top shrink/retention event was observed; that behavior remains untested.",
                                   "Only the tested source version, compiler, optimization levels, flags, and fixture states are covered."])
        atomic(receipt, report)
        print(json.dumps({"status": report["status"], "receipt": pin(receipt), "counts": report["counts"]}, indent=2))
        return 0
    except BaseException as exc:
        report.update(status="FAIL_PRESERVED_STOPPED", error=f"{type(exc).__name__}: {exc}",
                      counts={"compile_link_processes": sum(r.get("pid") is not None and r["role"] in ("compile", "link") for r in records),
                              "fixture_executions": sum(r.get("pid") is not None and r["role"].startswith(("baseline_", "candidate_")) for r in records),
                              "WRF_forecasts": 0, "REAL_calls": 0, "RTE_calls": 0})
        atomic(receipt, report)
        print(json.dumps({"status": report["status"], "error": report["error"], "receipt": pin(receipt)}, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
