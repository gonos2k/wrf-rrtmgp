#!/usr/bin/env python3
"""Compile real outer UDM and verify per-row SR reset plus a reverted-bug control."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import time


FLAGS = ["-O0", "-g", "-ffree-form", "-ffree-line-length-none", "-fcheck=all",
         "-finit-real=snan", "-ffpe-trap=invalid,zero,overflow"]
SUCCESS = "UDM_SR_ROWS_RESET"
BUG = "legacy UDM path failed to reset SR row"


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, check=False)


def compile_and_run(wrf: pathlib.Path, directory: pathlib.Path, compiler: str,
                    reverted_bug: bool) -> dict[str, object]:
    directory.mkdir(parents=True)
    original = (wrf / "phys/module_mp_udm.F").read_text()
    source = directory / "module_mp_udm.F"
    if reverted_bug:
        marker = ",sr(ims,j)"
        if original.count(marker) != 3:
            raise RuntimeError("expected three row-specific SR arguments in UDM calls")
        index = original.rfind(marker)
        source.write_text(original[:index] + ",sr" + original[index + len(marker):])
    else:
        source.write_text(original)

    stub = directory / "module_wrf_error.f90"
    stub.write_text(
        "module module_wrf_error\n  implicit none\ncontains\n"
        "  subroutine wrf_debug(level,text)\n    integer,intent(in)::level\n"
        "    character(*),intent(in)::text\n  end subroutine\nend module\n")
    include = ["-I", str(directory), "-J", str(directory)]
    compile_commands = [
        [compiler, "-O0", "-ffixed-form", "-c", str(wrf / "phys/module_gfs_machine.F"),
         "-o", str(directory / "module_gfs_machine.o"), *include],
        [compiler, "-O0", "-ffree-form", "-ffree-line-length-none", "-c", str(stub),
         "-o", str(directory / "module_wrf_error.o"), *include],
        [compiler, "-O0", "-ffree-form", "-ffree-line-length-none", "-c",
         str(wrf / "phys/module_mp_radar.F"), "-o", str(directory / "module_mp_radar.o"), *include],
        [compiler, *FLAGS, *include, "-c", str(source), "-o", str(directory / "module_mp_udm.o")],
    ]
    compile_results = []
    for command in compile_commands:
        result = run(command, directory)
        compile_results.append({"command": command, "returncode": result.returncode,
                                "output": result.stdout})
        if result.returncode:
            raise RuntimeError(f"UDM dependency compile failed: {result.stdout[-2000:]}")

    executable = directory / "test_udm_sr_rows"
    driver = wrf / "test/rrtmgp/test_udm_sr_rows.f90"
    command = [compiler, *FLAGS, *include, str(driver), str(directory / "module_mp_udm.o"),
               str(directory / "module_mp_radar.o"), str(directory / "module_wrf_error.o"),
               "-o", str(executable)]
    linked = run(command, directory)
    if linked.returncode:
        raise RuntimeError(f"UDM SR test link failed: {linked.stdout[-2000:]}")
    executed = run([str(executable)], directory)
    return {"source_sha256": digest(source), "compile": compile_results,
            "link": {"returncode": linked.returncode, "output": linked.stdout},
            "execution": {"returncode": executed.returncode, "output": executed.stdout}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wrf_root", type=pathlib.Path)
    parser.add_argument("--workdir", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--compiler", default=shutil.which("gfortran") or "gfortran")
    args = parser.parse_args()
    wrf = args.wrf_root.resolve()
    if not (wrf / "phys/module_mp_udm.F").is_file():
        parser.error(f"not a WRF root: {wrf}")
    work_root = args.workdir.resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    run_root = work_root / f"run-{stamp}-{time.time_ns()}"
    run_root.mkdir()
    work = run_root
    started = time.time()
    fixed = compile_and_run(wrf, work / "fixed", args.compiler, False)
    if fixed["execution"]["returncode"] != 0 or SUCCESS not in fixed["execution"]["output"]:
        raise RuntimeError(f"fixed outer UDM did not reset every SR row: {fixed['execution']}")
    reverted = compile_and_run(wrf, work / "reverted-sr-row", args.compiler, True)
    reverted_output = reverted["execution"]["output"]
    if reverted["execution"]["returncode"] == 0 or BUG not in reverted_output:
        raise RuntimeError(f"reverted SR row bug was not caught: {reverted['execution']}")
    result = {
        "schema": "UDM_SR_ROW_TEST_V1",
        "status": "PASS",
        "test": "actual outer UDM legacy has_req*=0, two active j rows, clear columns",
        "source_provenance": {
            "base_commit": subprocess.run(["git", "-C", str(wrf), "rev-parse", "HEAD"],
                                           check=True, text=True, capture_output=True).stdout.strip(),
            "production_source_sha256": digest(wrf / "phys/module_mp_udm.F"),
            "driver_sha256": digest(wrf / "test/rrtmgp/test_udm_sr_rows.f90"),
            "runner_sha256": digest(pathlib.Path(__file__).resolve()),
        },
        "wrf_root": str(wrf), "compiler": args.compiler, "flags": FLAGS,
        "production_source_sha256": digest(wrf / "phys/module_mp_udm.F"),
        "driver_sha256": digest(wrf / "test/rrtmgp/test_udm_sr_rows.f90"),
        "fixed": fixed,
        "reverted_bug_control": {
            **reverted,
            "expected_failure": "second j row retains distinct initial SR sentinels",
        },
        "physics_fixture": {
            "active_j_rows": 2, "active_i_columns": 2, "k_layers": 2,
            "has_reqc_reqi_reqs": [0, 0, 0], "hydrometeor_state": "clear",
            "initial_sr_by_j": [[11.0, 12.0], [21.0, 22.0]],
            "expected_sr_by_j_after_udm": [[0.0, 0.0], [0.0, 0.0]],
        },
        "elapsed_seconds": time.time() - started,
    }
    output = args.output.resolve() if args.output else run_root / "receipt.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print("Actual outer UDM SR row test passed; reverted-rank bug rejected")
    print(f"receipt={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
