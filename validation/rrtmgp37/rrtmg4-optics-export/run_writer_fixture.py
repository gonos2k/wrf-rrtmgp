#!/usr/bin/env python3
"""Compile the actual observer module and exercise its text writer only."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
OBSERVER = ROOT / "WRF/phys/module_ra_rrtmgp_audit.F"
HERE = Path(__file__).resolve().parent
EXPORT_ENV = "WRF_RRTMGP_RRTMG4_EXPORT_DIR"
sys.path.insert(0, str(HERE))
from read_export import read_export


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kwargs)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compiler", default=shutil.which("gfortran"))
    args = ap.parse_args()
    if not args.compiler:
        raise SystemExit("gfortran not found; pass --compiler")
    source = OBSERVER.read_text(encoding="utf-8")
    start = source.index("MODULE module_rrtmg4_optics_export")
    end = source.index("END MODULE module_rrtmg4_optics_export", start)
    observer = source[start:end + len("END MODULE module_rrtmg4_optics_export")] + "\n"
    (ROOT / "build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rrtmg4-export-writer-", dir=ROOT / "build") as td:
        tmp = Path(td)
        (tmp / "observer.f90").write_text(observer)
        moddir = tmp / "mod"
        moddir.mkdir()
        exe = tmp / "writer"
        run([args.compiler, "-cpp", "-ffree-line-length-none", "-J", str(moddir),
             "-c", str(tmp / "observer.f90"), "-o", str(tmp / "observer.o")])
        run([args.compiler, "-cpp", "-ffree-line-length-none", "-J", str(moddir),
             "-I", str(moddir), str(HERE / "writer_fixture.f90"),
             str(HERE / "wrf_error_fatal_stub.f90"), str(tmp / "observer.o"),
             "-o", str(exe)])
        env = os.environ.copy()
        env.pop(EXPORT_ENV, None)
        run([str(exe), "disabled"], cwd=tmp, env=env)
        if list(tmp.glob("rrtmg4_d01_i24_j55_step2161_*.txt")):
            raise ValueError("disabled writer created an output file")
        out = tmp / "enabled"
        out.mkdir()
        env[EXPORT_ENV] = str(out)
        run([str(exe)], cwd=tmp, env=env)
        lw = read_export(out / "rrtmg4_d01_i24_j55_step2161_lw.txt", expected_phase="LW")
        sw = read_export(out / "rrtmg4_d01_i24_j55_step2161_sw.txt", expected_phase="SW")
        for fields in (lw, sw):
            if fields["stage_order"] != ["INPUT", "CLOUD", "GAS", "RESULT"]:
                raise ValueError("stage order mismatch")
            if fields["fields"]["INPUT", "PROFILE"].values != (1.25, -2.5, 3.75):
                raise ValueError("rank-1 REAL payload mismatch")
            if fields["fields"]["INPUT", "FLAGS"].units != "1" or \
               fields["fields"]["INPUT", "FLAGS"].values != (4.0, 9.0):
                raise ValueError("integer payload/unit mismatch")
            tau = fields["fields"]["CLOUD", "TAU"]
            if tau.shape != (2, 3) or tau.values != (1., 2., 3., 4., 5., 6.):
                raise ValueError("rank-2 REAL Fortran-order payload mismatch")

        # Compile the observer's OpenMP branch and ensure an opted-in
        # multi-thread run is rejected before it creates either phase file.
        omp_moddir = tmp / "omp-mod"
        omp_moddir.mkdir()
        omp_obj = tmp / "observer-omp.o"
        omp_exe = tmp / "writer-omp"
        run([args.compiler, "-cpp", "-fopenmp", "-ffree-line-length-none", "-J", str(omp_moddir),
             "-c", str(tmp / "observer.f90"), "-o", str(omp_obj)])
        run([args.compiler, "-cpp", "-fopenmp", "-ffree-line-length-none", "-J", str(omp_moddir),
             "-I", str(omp_moddir), str(HERE / "writer_fixture.f90"),
             str(HERE / "wrf_error_fatal_stub.f90"), str(omp_obj), "-o", str(omp_exe)])
        guard_dir = tmp / "omp-guard"
        guard_dir.mkdir()
        env[EXPORT_ENV] = str(guard_dir)
        env["OMP_NUM_THREADS"] = "2"
        failed = subprocess.run([str(omp_exe)], cwd=tmp, env=env, text=True,
                                capture_output=True, check=False)
        if failed.returncode == 0 or "RRTMG4_EXPORT_REQUIRES_ONE_OPENMP_THREAD" not in failed.stdout:
            raise ValueError("requested OpenMP batch was not rejected by the observer")
        if list(guard_dir.glob("rrtmg4_d01_i24_j55_step2161_*.txt")):
            raise ValueError("OpenMP rejection occurred after output creation")
        print("writer_fixture PASS: disabled no-output; enabled LW/SW text roundtrip; OpenMP guard")


if __name__ == "__main__":
    main()
