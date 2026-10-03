#!/usr/bin/env python3
"""Compile actual module_mp_udm and verify cldf_diag's partial-write contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile


def run(command: list[str], cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, check=False)


def build_one(wrf: pathlib.Path, compiler: str, opt: str, build: pathlib.Path) -> dict[str, object]:
    build.mkdir(parents=True, exist_ok=True)
    include = ["-I", str(build), "-J", str(build)]
    strict = [opt, "-g", "-ffree-form", "-ffree-line-length-none", "-fcheck=all",
              "-finit-real=snan", "-ffpe-trap=invalid,zero,overflow"]
    commands = [
        [compiler, "-O0", "-ffixed-form", "-c", str(wrf / "phys/module_gfs_machine.F"),
         "-o", str(build / "machine.o"), *include],
    ]
    stub = build / "module_wrf_error.f90"
    stub.write_text("module module_wrf_error\nimplicit none\ncontains\n"
                    "subroutine wrf_debug(level,text)\ninteger,intent(in)::level\n"
                    "character(*),intent(in)::text\nend subroutine\nend module\n")
    commands.append([compiler, "-O0", "-ffree-form", "-ffree-line-length-none", "-c", str(stub),
                     "-o", str(build / "error.o"), *include])
    commands.append([compiler, "-O0", "-ffree-form", "-ffree-line-length-none", "-c",
                     str(wrf / "phys/module_mp_radar.F"), "-o", str(build / "radar.o"), *include])
    commands.append([compiler, *strict, *include, "-c", str(wrf / "phys/module_mp_udm.F"),
                     "-o", str(build / "udm.o")])
    logs = []
    for command in commands:
        result = run(command, build)
        logs.append({"command": command, "returncode": result.returncode, "output": result.stdout})
        if result.returncode:
            raise RuntimeError(f"compile failed ({command}):\n{result.stdout}")
    exe = build / "test_udm_cldf_extent"
    command = [compiler, *strict, *include, str(wrf / "test/rrtmgp/test_udm_cldf_extent.f90"),
               str(build / "udm.o"), str(build / "radar.o"), str(build / "error.o"),
               "-o", str(exe)]
    linked = run(command, build)
    if linked.returncode:
        raise RuntimeError(f"link failed:\n{linked.stdout}")
    executed = run([str(exe)], build)
    if executed.returncode or "UDM cldf partial-output contract passed" not in executed.stdout:
        raise RuntimeError(f"test failed at {opt}: rc={executed.returncode}\n{executed.stdout}")
    return {"optimization": opt, "compile": logs,
            "link": {"command": command, "returncode": linked.returncode, "output": linked.stdout},
            "execution": {"returncode": executed.returncode, "output": executed.stdout}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wrf_root", type=pathlib.Path)
    parser.add_argument("--compiler", default=shutil.which("gfortran") or "gfortran")
    parser.add_argument("--workdir", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    wrf = args.wrf_root.resolve()
    if not (wrf / "phys/module_mp_udm.F").is_file():
        parser.error(f"not a WRF root: {wrf}")
    if args.workdir:
        root = args.workdir.resolve()
        root.mkdir(parents=True, exist_ok=True)
        cleanup = None
    else:
        cleanup = tempfile.TemporaryDirectory(prefix="udm-cldf-extent-")
        root = pathlib.Path(cleanup.name)
    try:
        results = [build_one(wrf, args.compiler, opt, root / opt) for opt in ("-O0", "-O2", "-O3")]
        receipt = {"status": "PASS", "test": "actual UDM cldf_diag partial output at O0/O2/O3",
                   "wrf_root": str(wrf), "compiler": args.compiler,
                   "module_sha256": hashlib.sha256((wrf / "phys/module_mp_udm.F").read_bytes()).hexdigest(),
                   "driver_sha256": hashlib.sha256((wrf / "test/rrtmgp/test_udm_cldf_extent.f90").read_bytes()).hexdigest(),
                   "results": results}
        print(json.dumps(receipt, indent=2))
        if args.output:
            output = args.output.resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(receipt, indent=2) + "\n")
        return 0
    finally:
        if cleanup:
            cleanup.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
