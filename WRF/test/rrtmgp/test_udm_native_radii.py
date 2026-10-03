#!/usr/bin/env python3
"""Build and exercise the real outer UDM entry point with a missing-density negative control."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile
import sys
import time


FLAGS = [
    "-O0", "-g", "-ffree-form", "-ffree-line-length-none", "-fcheck=all",
    "-finit-real=snan", "-ffpe-trap=invalid,zero,overflow",
]


def run(command: list[str], *, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, check=False)


def build_and_run(wrf: pathlib.Path, directory: pathlib.Path, compiler: str, missing_density: bool) -> dict[str, object]:
    directory.mkdir(parents=True, exist_ok=True)
    source = wrf / "phys" / "module_mp_udm.F"
    source_text = source.read_text()
    if missing_density:
        assignment = "              den1d(k)= den(i,k,j)\n"
        if source_text.count(assignment) != 1:
            raise RuntimeError("expected exactly one native-density packing assignment for negative control")
        variant = directory / "module_mp_udm_missing_density.F"
        variant.write_text(source_text.replace(assignment, "", 1))
        source = variant
    else:
        # Compile from the current source snapshot copied into scratch so module
        # lookup and all outputs remain isolated from a WRF build tree.
        source = directory / "module_mp_udm.F"
        source.write_text(source_text)

    error_stub = directory / "module_wrf_error.f90"
    error_stub.write_text(
        "module module_wrf_error\n"
        "  implicit none\n"
        "contains\n"
        "  subroutine wrf_debug(level, text)\n"
        "  integer, intent(in) :: level\n"
        "  character(*), intent(in) :: text\n"
        "  end subroutine wrf_debug\n"
        "end module module_wrf_error\n"
    )
    include = ["-I", str(directory), "-J", str(directory)]
    commands = [
        [compiler, "-O0", "-ffixed-form", "-c", str(wrf / "phys" / "module_gfs_machine.F"), "-o", str(directory / "module_gfs_machine.o"), *include],
        [compiler, "-O0", "-ffree-form", "-ffree-line-length-none", "-c", str(error_stub), "-o", str(directory / "module_wrf_error.o"), *include],
        # Keep production radar routines, but omit global FPE traps for its
        # initialization tables. UDM and the driver retain strict instrumentation.
        [compiler, "-O0", "-ffree-form", "-ffree-line-length-none", "-c", str(wrf / "phys" / "module_mp_radar.F"), "-o", str(directory / "module_mp_radar.o"), *include],
        [compiler, *FLAGS, *include, "-c", str(source), "-o", str(directory / "module_mp_udm.o")],
    ]
    compile_log: list[dict[str, object]] = []
    for command in commands:
        result = run(command, cwd=directory)
        compile_log.append({"command": command, "returncode": result.returncode, "output": result.stdout})
        if result.returncode:
            raise RuntimeError(f"dependency/UDM compile failed:\n{result.stdout}")
    executable = directory / "test_udm_native_radii"
    driver = wrf / "test" / "rrtmgp" / "test_udm_native_radii.f90"
    command = [compiler, *FLAGS, *include, str(driver), str(directory / "module_mp_udm.o"),
               str(directory / "module_mp_radar.o"), str(directory / "module_wrf_error.o"), "-o", str(executable)]
    result = run(command, cwd=directory)
    if result.returncode:
        raise RuntimeError(f"UDM test link failed:\n{result.stdout}")
    executed = run([str(executable)], cwd=directory)
    return {"compile": compile_log, "link": {"command": command, "returncode": result.returncode, "output": result.stdout},
            "execution": {"command": [str(executable)], "returncode": executed.returncode, "output": executed.stdout}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wrf_root", type=pathlib.Path, help="WRF checkout root")
    parser.add_argument("--workdir", type=pathlib.Path, help="retain isolated build files here")
    parser.add_argument("--output", type=pathlib.Path, help="write JSON receipt (defaults to workdir/receipt.json when workdir is set)")
    parser.add_argument("--compiler", default=shutil.which("gfortran") or "gfortran")
    args = parser.parse_args()
    wrf = args.wrf_root.resolve()
    if not (wrf / "phys" / "module_mp_udm.F").is_file():
        parser.error(f"not a WRF root: {wrf}")
    if args.workdir:
        root = args.workdir.resolve()
        root.mkdir(parents=True, exist_ok=True)
        run_root = root
        cleanup = None
    else:
        cleanup = tempfile.TemporaryDirectory(prefix="udm-native-radii-")
        run_root = pathlib.Path(cleanup.name)
    try:
        # Repeated CTest runs are idempotent; only remove our two named scratch builds.
        for child in (run_root / "fixed", run_root / "missing-density"):
            if child.exists():
                shutil.rmtree(child)
        started = time.time()
        positive = build_and_run(wrf, run_root / "fixed", args.compiler, False)
        positive_run = positive["execution"]
        assert isinstance(positive_run, dict)
        positive_output = str(positive_run["output"])
        if int(positive_run["returncode"]):
            sys.stderr.write(positive_output)
            raise RuntimeError("fixed UDM outer-call path failed")
        if "UDM outer-call native-density and CF extent test passed" not in positive_output:
            raise RuntimeError("fixed UDM path did not report successful radius checks")
        print(positive_output, end="")

        negative = build_and_run(wrf, run_root / "missing-density", args.compiler, True)
        negative_run = negative["execution"]
        assert isinstance(negative_run, dict)
        diagnostic = str(negative_run["output"])
        if int(negative_run["returncode"]) == 0:
            raise RuntimeError("negative control unexpectedly passed without density packing")
        if "udm_mp_effective_radius" not in diagnostic:
            sys.stderr.write(diagnostic)
            raise RuntimeError("negative control failed outside the expected effective-radius use of rho")
        print("UDM missing-density negative control failed as expected inside udm_mp_effective_radius")
        receipt = {
            "status": "PASS",
            "test": "actual outer module_mp_udm.udm plus missing-density negative control",
            "wrf_root": str(wrf),
            "compiler": args.compiler,
            "flags": FLAGS,
            "source_sha256": hashlib.sha256((wrf / "phys" / "module_mp_udm.F").read_bytes()).hexdigest(),
            "driver_sha256": hashlib.sha256((wrf / "test" / "rrtmgp" / "test_udm_native_radii.f90").read_bytes()).hexdigest(),
            "positive": positive,
            "negative_control": negative,
            "expected_negative_control": "nonzero termination in udm_mp_effective_radius due to signaling-NaN den1d",
            "elapsed_seconds": time.time() - started,
        }
        output = args.output.resolve() if args.output else ((root / "receipt.json") if args.workdir else None)
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(receipt, indent=2) + "\n")
        else:
            print(json.dumps(receipt, indent=2))
        return 0
    finally:
        if cleanup is not None:
            cleanup.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
