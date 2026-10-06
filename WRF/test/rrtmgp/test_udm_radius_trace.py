#!/usr/bin/env python3
"""Focused compile-and-run contract test for the optional UDM radius trace."""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ENV_PREFIXES = ("WRF_RRTMGP_CAPTURE", "WRF_RRTMGP_COLUMN_")


def clean_env(updates: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if not any(k.startswith(prefix) for prefix in ENV_PREFIXES)}
    if updates:
        env.update(updates)
    return env


def run(argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, check=False)


def expect_failure(exe: Path, cwd: Path, env: dict[str, str], mode: str, marker: str) -> None:
    proc = run([str(exe), mode], cwd, env)
    if proc.returncode == 0 or marker not in proc.stdout:
        raise AssertionError(f"{mode}: expected {marker}, rc={proc.returncode}\n{proc.stdout}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wrf-root", type=Path, required=True)
    ap.add_argument("--compiler", default=shutil.which("gfortran") or "gfortran")
    args = ap.parse_args()
    wrf = args.wrf_root.resolve()
    src = wrf / "phys/module_ra_rrtmgp_trace.F"
    fixture = wrf / "test/rrtmgp/test_udm_radius_trace.f90"
    stub = wrf / "test/rrtmgp/standalone_wrf_error.f90"
    if not all(p.is_file() for p in (src, fixture, stub)):
        raise FileNotFoundError("missing trace source or fixture")
    scratch_parent = wrf.parent / "build"
    scratch_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="udm-radius-trace-", dir=scratch_parent) as temp:
        td = Path(temp)
        inc = ["-I", str(td), "-J", str(td)]
        for source, obj in ((stub, td / "error.o"), (src, td / "trace.o")):
            p = run([args.compiler, "-cpp", "-ffree-form", "-ffree-line-length-none", *inc,
                     "-c", str(source), "-o", str(obj)], td, clean_env())
            if p.returncode:
                raise RuntimeError(f"compile failed for {source}:\n{p.stdout}")
        exe = td / "radius-trace-test"
        p = run([args.compiler, "-ffree-form", "-ffree-line-length-none", *inc,
                 str(fixture), str(td / "trace.o"), str(td / "error.o"), "-o", str(exe)], td, clean_env())
        if p.returncode:
            raise RuntimeError(f"fixture link failed:\n{p.stdout}")

        cap = td / "capture"
        cap.mkdir()
        base = {"WRF_RRTMGP_CAPTURE_DIR": str(cap)}
        p = run([str(exe), "disabled"], td, clean_env(base))
        if p.returncode or list(cap.iterdir()):
            raise AssertionError(f"unset radius selector must be a no-op: rc={p.returncode}\n{p.stdout}")

        enabled = {**base, "WRF_RRTMGP_CAPTURE_UDM_RADII": "1",
                   "WRF_RRTMGP_COLUMN_I": "2", "WRF_RRTMGP_COLUMN_J": "3"}
        p = run([str(exe), "selected"], td, clean_env(enabled))
        if p.returncode:
            raise AssertionError(f"selected capture failed:\n{p.stdout}")
        files = list(cap.iterdir())
        expected = cap / "udm_radius_d1_i2_j3_step123.raw"
        if files != [expected] or not expected.is_file():
            raise AssertionError(f"only the selected point should write one file: {files}")
        lines = expected.read_text().splitlines()
        if lines[0] != "RRTMGP_UDM_RADIUS_V1" or [int(x) for x in lines[1].split()] != [1, 123, 2, 3, 10, 11]:
            raise AssertionError("radius packet magic/header mismatch")
        names = ("SOURCE_T", "SOURCE_QC", "SOURCE_QI", "SOURCE_QS", "SOURCE_QNC", "SOURCE_RHO",
                 "SOURCE_RE_CLOUD", "SOURCE_RE_ICE", "SOURCE_RE_SNOW", "UDM_CF_USED",
                 "UDM_CF_STEP", "UDM_CF_TOP", "QMIN", "T0C", "RHO_WATER", "RHO_SNOW",
                 "SOURCE_TIME_PRESENT", "SOURCE_TIME_SECONDS")
        got = []
        cursor = 2
        for name in names:
            header = lines[cursor].split()
            if header[0] != name:
                raise AssertionError(f"record order/name: expected {name}, got {header}")
            count = int(header[1]); cursor += 1
            vals = [float(x) for x in lines[cursor:cursor+count]]; cursor += count
            if count not in (1, 2):
                raise AssertionError(f"invalid record length for {name}: {count}")
            got.append((name, vals))
        if cursor != len(lines) or len(got) != 18:
            raise AssertionError("extra or missing records")
        if (got[0][1] != [250.0, 251.0] or
                not all(math.isclose(a, b, rel_tol=0.0, abs_tol=1e-7)
                        for a, b in zip(got[9][1], [0.4, 0.5])) or got[-4][1] != [1000.0] or
                got[-3][1] != [100.0] or
                got[10][1] != [1.0] or got[11][1] != [2.0] or
                got[-2][1] != [1.0] or got[-1][1] != [3600.0]):
            raise AssertionError("record values were not preserved")

        expect_failure(exe, td, {**base, "WRF_RRTMGP_CAPTURE_UDM_RADII": "true"}, "disabled",
                       "RRTMGP_TRACE_UDM_RADIUS_INVALID")
        expect_failure(exe, td, {"WRF_RRTMGP_CAPTURE_UDM_RADII": "1"}, "selected",
                       "RRTMGP_TRACE_UDM_RADIUS_REQUIRES_CAPTURE_DIR")
        expect_failure(exe, td, enabled, "badshape", "RRTMGP_TRACE_UDM_RADIUS_SHAPE")
        expect_failure(exe, td, enabled, "duplicate", "RRTMGP_TRACE_UDM_RADIUS_IO_ERROR")
        print("PASS: opt-in/no-op, selected-point filtering, packet schema, shape and duplicate guards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
