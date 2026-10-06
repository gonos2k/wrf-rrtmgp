#!/usr/bin/env python3
"""Exercise verbatim native sedimentation and original/candidate outer UDM.

Only isolated fixture compiles are performed. Existing work directories are
never reused. A child PID and actual RC are durably recorded before log parsing.
The sedimentation budget excludes every other UDM microphysical process.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import struct
import subprocess
import sys
import time

BASELINE = "16fb5415cc30ec124f9d9871a236009f1a472c07"
EPS32 = 2.0**-23


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pin(path):
    data = path.read_bytes()
    return {"path": str(path), "size_bytes": len(data), "sha256": digest(data)}


def atomic(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def native_block(data):
    text = data.decode()
    match = re.search(r"(?im)^\s*subroutine semi_lagrangian\([^\n]*[\s\S]*?^end subroutine semi_lagrangian[^\n]*\n", text)
    if match is None:
        raise ValueError("native semi_lagrangian block not found")
    return match.group().encode()


def sedimentation_parse(text):
    records = {}
    current = None
    for line in text.splitlines():
        tokens = line.split()
        if not tokens:
            continue
        if tokens[0] == "SED":
            if len(tokens) != 4:
                raise ValueError("malformed SED header")
            key = (int(tokens[1]), int(tokens[2]))
            if key in records:
                raise ValueError("duplicate sedimentation case")
            current = {"precip_kg_m2": float(tokens[3]), "rows": []}
            records[key] = current
        elif tokens[0] == "ROW" and current is not None:
            if len(tokens) != 9 or int(tokens[1]) != len(current["rows"]) + 1:
                raise ValueError("malformed sedimentation row")
            values = list(map(float, tokens[2:]))
            if not all(map(math.isfinite, values)):
                raise ValueError("nonfinite sedimentation state")
            current["rows"].append(dict(zip(("dry_density", "weight", "dz", "qv", "q_initial", "q_final", "rql_final"), values)))
        else:
            raise ValueError("unexpected sedimentation output")
    if set(records) != {(m, b) for m in range(2) for b in range(2)}:
        raise ValueError("incomplete sedimentation case roster")
    if any(len(v["rows"]) != 6 for v in records.values()):
        raise ValueError("incorrect native layer count")
    return records


def sedimentation_check(records):
    reports = []
    for (moisture, basis), record in sorted(records.items()):
        rows = record["rows"]
        precip = record["precip_kg_m2"]
        if not math.isfinite(precip) or precip <= 0 or any(r["weight"] <= 0 or r["dry_density"] <= 0 or r["q_final"] < 0 for r in rows):
            raise ValueError("invalid sedimentation output")
        before = math.fsum(r["weight"]*r["q_initial"]*r["dz"] for r in rows)
        after = math.fsum(r["weight"]*r["q_final"]*r["dz"] for r in rows)
        dry_before = math.fsum(r["dry_density"]*r["q_initial"]*r["dz"] for r in rows)
        dry_after = math.fsum(r["dry_density"]*r["q_final"]*r["dz"] for r in rows)
        # Declared default-REAL fixture bound, not a universal PPM error bound.
        tolerance = 64*EPS32*max(before, dry_before)
        own_residual = after + precip - before
        dry_residual = dry_after + precip - dry_before
        if abs(own_residual) > tolerance:
            raise ValueError("native own-weight sedimentation budget failed")
        if (basis == 1 or moisture == 0) and abs(dry_residual) > tolerance:
            raise ValueError("dry-density sedimentation budget failed")
        if basis == 0 and moisture == 1 and abs(dry_residual) <= 20*tolerance:
            raise ValueError("moist-gradient fixture does not distinguish density weights")
        reports.append({"moisture_case": moisture, "density_basis": "legacy_DEND" if basis == 0 else "dry_DEN",
                        "initial_weighted_mass_kg_m2": before, "final_weighted_mass_kg_m2": after,
                        "initial_dry_mass_kg_m2": dry_before, "final_dry_mass_kg_m2": dry_after,
                        "bottom_precip_kg_m2": precip, "own_weight_residual_kg_m2": own_residual,
                        "dry_weight_residual_kg_m2": dry_residual, "tolerance_kg_m2": tolerance})
    zero_legacy, zero_dry = records[(0, 0)], records[(0, 1)]
    if zero_legacy != zero_dry:
        raise ValueError("constructed exact qv=0 fixture differs by density mode")
    return reports


def outer_parse(text, modes):
    lines = text.splitlines()
    result = {}
    index = 0
    while index < len(lines):
        tokens = lines[index].split()
        if tokens and tokens[0] == "OUTER":
            if len(tokens) != 5 or index + 2 >= len(lines):
                raise ValueError("malformed outer case header")
            key = tuple(map(int, tokens[1:4]))
            words = lines[index+1].split()
            tags = lines[index+2].split()
            if key in result or len(words) != int(tokens[4]) or int(tokens[4]) != 105:
                raise ValueError("duplicate or wrong outer state shape")
            if any(re.fullmatch(r"[0-9A-F]{8}", w) is None for w in words) or len(tags) != 3 or tags[0] != "TAGS":
                raise ValueError("malformed binary32 state or tags")
            if not all(math.isfinite(struct.unpack("!f", bytes.fromhex(w))[0]) for w in words):
                raise ValueError("nonfinite outer state")
            result[key] = {"binary32_words": words, "diagnostic_step_top": list(map(int, tags[1:]))}
            index += 3
        else:
            # UDM setup may print informational messages; case records are exact.
            index += 1
    expected = {(m, b, mode) for m in range(2) for b in range(1, 4) for mode in modes}
    if set(result) != expected:
        raise ValueError("outer UDM case roster mismatch")
    return result


def outer_check(baseline, candidate):
    reports = []
    for moisture in range(2):
        for branch in range(1, 4):
            original = baseline[(moisture, branch, 0)]
            omitted = candidate[(moisture, branch, 0)]
            false = candidate[(moisture, branch, 1)]
            true = candidate[(moisture, branch, 2)]
            if original != omitted or original != false:
                raise ValueError("original/omitted/FALSE outer output changed")
            changed = sum(a != b for a, b in zip(original["binary32_words"], true["binary32_words"]))
            if moisture == 0 and original != true:
                raise ValueError("constructed exact qv=0 outer TRUE output changed")
            if moisture == 1 and changed == 0:
                raise ValueError("moist outer TRUE case did not exercise density change")
            reports.append({"moisture_case": moisture, "forward_branch": branch,
                            "original_omitted_FALSE_bitwise_equal": True,
                            "TRUE_changed_binary32_values": changed,
                            "qv0_TRUE_bitwise_equal": moisture == 0})
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wrf_root", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compiler", default="gfortran")
    parser.add_argument("--baseline-revision", default=BASELINE)
    args = parser.parse_args()
    wrf = args.wrf_root.resolve()
    work = args.workdir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    output = args.output.resolve() if args.output else work / "receipt.json"
    if output.exists():
        raise FileExistsError(output)
    compiler = Path(shutil.which(args.compiler) or args.compiler).resolve(strict=True)
    records = []
    report = {"schema": "udm-sedimentation-density-fixture-v1", "status": "RUNNING", "processes": records,
              "WRF_forecasts": 0, "REAL_calls": 0, "RTE_calls": 0, "full_WRF_builds": 0,
              "baseline_revision": args.baseline_revision, "compiler": pin(compiler)}
    atomic(output, report)

    def run(command, cwd, role):
        number = len(records)+1
        log = work / f"process-{number:03d}.log"
        receipt = work / f"process-{number:03d}.json"
        record = {"role": role, "command": command, "cwd": str(cwd), "timeout_seconds": 120}
        records.append(record)
        timed_out = False
        process = None
        try:
            with log.open("xb") as stream:
                process = subprocess.Popen(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                           start_new_session=True, env={**os.environ, "LC_ALL": "C", "OMP_NUM_THREADS": "1"})
                record.update(pid=process.pid, status="RUNNING")
                atomic(receipt, record)
                try:
                    rc = process.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    os.killpg(process.pid, signal.SIGKILL)
                    rc = process.wait()
                except BaseException:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                    rc = process.wait()
                    record.update(actual_returncode=rc, status="INTERRUPTED")
                    atomic(receipt, record)
                    raise
                stream.flush()
                os.fsync(stream.fileno())
            record.update(actual_returncode=rc, timed_out=timed_out, status="TERMINAL")
            atomic(receipt, record)  # Actual RC is durable before hashing/reading.
            record["log"] = pin(log)
            atomic(receipt, record)
            atomic(output, report)
            if rc != 0 or timed_out:
                raise RuntimeError(f"{role} failed: actual RC {rc}; preserved {receipt}")
            return log.read_text()
        except BaseException:
            if process is None:
                record["status"] = "NOT_LAUNCHED"
                atomic(receipt, record)
            raise

    try:
        repository = wrf.parent
        paths = [wrf/"phys"/name for name in ("module_mp_udm.F", "module_mp_radar.F", "module_gfs_machine.F")]
        paths += [Path(__file__).resolve(), Path(__file__).with_suffix(".f90").resolve()]
        before = [pin(p) for p in paths]
        report["source_pins_before"] = before
        baseline_sources = {}
        for path in paths[:3]:
            relative = path.relative_to(repository).as_posix()
            data = subprocess.check_output(["git", "show", f"{args.baseline_revision}:{relative}"], cwd=repository)
            baseline_sources[path.name] = data
            if path.name != "module_mp_udm.F" and data != path.read_bytes():
                raise ValueError("original/candidate module dependency differs")
        current = paths[0].read_bytes()
        block = native_block(current)
        if block != native_block(baseline_sources["module_mp_udm.F"]):
            raise ValueError("native semi_lagrangian changed versus baseline")
        report["baseline_source_sha256"] = digest(baseline_sources["module_mp_udm.F"])
        report["native_sedimentation_block_sha256"] = digest(block)
        report["native_sedimentation_block_bytes"] = len(block)
        source_snapshot = work/"candidate-module_mp_udm.F"
        source_snapshot.write_bytes(current)
        original_snapshot = work/"baseline-module_mp_udm.F"
        original_snapshot.write_bytes(baseline_sources["module_mp_udm.F"])
        helper = work/"native_sedimentation.f90"
        helper.write_bytes(b"module native_sedimentation\nimplicit none\ncontains\n" + block + b"end module native_sedimentation\n")
        driver = paths[-1]
        results = {}
        for opt in ("-O0", "-O2"):
            flags = [opt, "-g", "-ffree-form", "-ffree-line-length-none", "-fcheck=all", "-finit-real=snan", "-ffpe-trap=invalid,zero,overflow"]
            sed_dir = work/opt[1:]/"sedimentation"
            sed_dir.mkdir(parents=True)
            sed_exe = sed_dir/"sedimentation"
            run([str(compiler), *flags, "-cpp", "-J", str(sed_dir), "-I", str(sed_dir), str(helper), str(driver), "-o", str(sed_exe)], sed_dir, "fixture_compile")
            sed_output = run([str(sed_exe)], sed_dir, "sedimentation_fixture_execution")
            sed = sedimentation_parse(sed_output)
            sed_reports = sedimentation_check(sed)
            negative = copy.deepcopy(sed)
            negative[(1, 1)]["precip_kg_m2"] += 1.e-3
            try:
                sedimentation_check(negative)
            except ValueError:
                bottom_precip_mutation_rejected = True
            else:
                raise ValueError("bottom precipitation negative control accepted")
            outer = {}
            for variant, snapshot in (("baseline", original_snapshot), ("candidate", source_snapshot)):
                directory = work/opt[1:]/variant
                directory.mkdir(parents=True)
                stub = directory/"module_wrf_error.f90"
                stub.write_text("module module_wrf_error\ncontains\nsubroutine wrf_debug(level,text)\ninteger,intent(in)::level\ncharacter(*),intent(in)::text\nend subroutine\nend module\n")
                include = ["-I", str(directory), "-J", str(directory)]
                objects = []
                for source, extra in ((paths[2], ["-ffixed-form"]), (stub, ["-ffree-form", "-ffree-line-length-none"]),
                                      (paths[1], ["-ffree-form", "-ffree-line-length-none"]), (snapshot, flags[1:])):
                    obj = directory/(source.stem+".o")
                    run([str(compiler), opt, *extra, *include, "-c", str(source), "-o", str(obj)], directory, "fixture_compile")
                    objects.append(obj)
                executable = directory/"outer_udm"
                defines = ["-DOUTER_UDM"] + (["-DBASELINE_UDM"] if variant == "baseline" else [])
                run([str(compiler), *flags, "-cpp", *defines, *include, str(driver), *map(str, objects), "-o", str(executable)], directory, "fixture_compile")
                raw = run([str(executable)], directory, "outer_UDM_fixture_execution")
                outer[variant] = outer_parse(raw, [0] if variant == "baseline" else [0, 1, 2])
            outer_reports = outer_check(outer["baseline"], outer["candidate"])
            results[opt] = {"sedimentation": sed_reports, "bottom_precip_mutation_rejected": bottom_precip_mutation_rejected,
                            "outer_UDM_compatibility": outer_reports, "outer_UDM_calls": 24, "native_sedimentation_calls": 4}
        after = [pin(p) for p in paths]
        if after != before:
            raise ValueError("input source changed during fixture")
        report.update(status="PASS_SCOPED_NATIVE_SEDIMENTATION_AND_COMPATIBILITY", results=results, source_pins_after=after,
                      counts={"compiler_processes": sum(r["role"] == "fixture_compile" for r in records),
                              "fixture_executable_processes": sum(r["role"].endswith("_execution") for r in records),
                              "outer_UDM_calls": 48, "isolated_native_sedimentation_calls": 8,
                              "WRF_forecasts": 0, "RTE_calls": 0},
                      limits=["Isolated semi_lagrangian preserves its caller-weighted rql, not a complete UDM water budget.",
                              "Outer UDM comparisons exercise all three optional diagnostic forwarding branches; other processes are active.",
                              "Exact qv=0 equivalence uses deliberately exact binary32 EOS inputs, not a general bitwise theorem.",
                              "Density-basis response is conditional on dry-density/mixing-ratio inputs; no number-unit, optics, PSD or accuracy gate is closed."])
        atomic(output, report)
        print(json.dumps({"status": report["status"], "receipt": pin(output), "counts": report["counts"]}, indent=2))
        return 0
    except BaseException as error:
        report.update(status="FAIL_PRESERVED_STOPPED", error=f"{type(error).__name__}: {error}")
        report["counts"] = {"compiler_processes": sum(r.get("pid") is not None and r["role"] == "fixture_compile" for r in records),
                            "fixture_executable_processes": sum(r.get("pid") is not None and r["role"].endswith("_execution") for r in records),
                            "WRF_forecasts": 0, "RTE_calls": 0}
        atomic(output, report)
        print(json.dumps({"status": report["status"], "error": report["error"], "receipt": pin(output)}, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
