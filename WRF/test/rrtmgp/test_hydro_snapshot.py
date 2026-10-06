#!/usr/bin/env python3
"""Compile and exercise the real tile-local RRTMGP hydro snapshot writer."""
from __future__ import annotations

import csv
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
WRF_ROOT = HERE.parents[1]
AUDIT_SOURCE = WRF_ROOT / "phys" / "module_ra_rrtmgp_audit.F"
INPUT_SOURCE = WRF_ROOT / "phys" / "module_ra_rrtmgp_input.F"
FATAL_STUB = HERE / "standalone_wrf_error.f90"
SNAPSHOT_DRIVER = HERE / "test_hydro_snapshot.f90"
BUILDER_DRIVER = HERE / "test_udm_builder_negative.f90"
HEADER = ("kind,domain,step,seconds,lw,sw,species,negative_count,positive_count,"
          "nonfinite_count,path_invalid_count,min_q_kgkg,max_q_kgkg,min_i,min_j,min_k,"
          "sum_positive_path_gm2,max_positive_path_gm2,cf0_positive_path_gm2,"
          "sum_negative_path_gm2")
TILE1 = "hydro_d2_i10-11_j20-21.csv"
TILE2 = "hydro_d2_i12-13_j20-21.csv"


def fail(message: str) -> None:
    raise RuntimeError(message)


def run(command: list[str], *, env: dict[str, str], label: str,
        cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env, cwd=cwd, check=False)
    if result.returncode:
        fail(f"{label} failed ({result.returncode}):\n{result.stdout[-1800:]}")
    return result


def compile_fixture(build: Path) -> tuple[Path, Path]:
    compiler = shutil.which("gfortran")
    if not compiler:
        fail("gfortran is required for the standalone audit test")
    env = os.environ.copy()
    common = [compiler, "-fopenmp", "-ffree-form", "-ffree-line-length-none",
              "-fcheck=all", "-fbacktrace", "-J", str(build), "-I", str(build)]
    audit_obj = build / "module_ra_rrtmgp_audit.o"
    run(common + ["-cpp", "-c", str(AUDIT_SOURCE), "-o", str(audit_obj)],
        env=env, label="compile actual audit module", cwd=build)
    hydro_exe = build / "test_hydro_snapshot"
    run(common + [str(SNAPSHOT_DRIVER), str(FATAL_STUB), str(audit_obj), "-o", str(hydro_exe)],
        env=env, label="link hydro snapshot fixture", cwd=build)

    builder_exe = build / "test_udm_builder_negative"
    run(common + [str(INPUT_SOURCE), str(BUILDER_DRIVER), str(FATAL_STUB), "-o", str(builder_exe)],
        env=env, label="compile UDM builder negative fixture", cwd=build)
    return hydro_exe, builder_exe


def fixture_env(output: Path | None) -> dict[str, str]:
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith("WRF_RRTMGP_HYDRO_DIAG_DIR") or key.startswith("WRF_RRTMGP_AUDIT_"):
            env.pop(key)
    if output is not None:
        env["WRF_RRTMGP_HYDRO_DIAG_DIR"] = str(output)
    env["OMP_NUM_THREADS"] = "2"
    return env


def fortran_es(value: float) -> str:
    mantissa, exponent = f"{value:.15E}".split("E")
    sign, digits = exponent[0], exponent[1:]
    return f"{mantissa}E{sign}{int(digits):03d}"


def water_path(q: float) -> float:
    # Match the production expression and its REAL-to-real64 conversions.
    q64 = float(np.float32(q))
    dp64 = float(np.float32(10000.0))
    gravity64 = float(np.float32(10.0))
    return q64 * dp64 / gravity64 * 1000.0


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="ascii") as stream:
        if stream.readline().strip() != HEADER:
            fail(f"{path}: unexpected hydro CSV header")
        return list(csv.DictReader(stream, fieldnames=HEADER.split(",")))


def check_negative_rows(rows: list[dict[str, str]], expected: set[tuple[str, int, int, int, float]]) -> None:
    got: Counter[tuple[int, str, int, int, int, float]] = Counter()
    for row in rows:
        if row["kind"] != "negative":
            continue
        identity = (int(row["step"]), row["species"], int(row["min_i"]),
                    int(row["min_j"]), int(row["min_k"]), float(row["min_q_kgkg"]))
        got[identity] += 1
        if row["max_q_kgkg"] != row["min_q_kgkg"]:
            fail("negative evidence row did not preserve its exact q value in both extrema")
    expected_rows = Counter((step, species, i, j, k, q)
                            for step in (6, 7) for species, i, j, k, q in expected)
    if got != expected_rows:
        fail(f"negative evidence mismatch; expected {expected_rows}, got {got}")


def check_summary_rows(rows: list[dict[str, str]], tile: int) -> None:
    by_step: dict[int, dict[str, dict[str, str]]] = {}
    for row in rows:
        if row["kind"] == "summary":
            by_step.setdefault(int(row["step"]), {})[row["species"]] = row
    if set(by_step) != {6, 7}:
        fail(f"expected two appended model steps 6 and 7, got {sorted(by_step)}")
    if any(set(step_rows) != {"QC", "QI", "QR", "QS", "QG", "QH"}
           for step_rows in by_step.values()):
        fail("each append must contain all six species summaries")

    zero = 0.0
    if tile == 1:
        expected = {
            "QC": (2, 2, 0, 0, -0.125, 0.25, 375000., 250000., 250000.,
                   water_path(-2.0**-100) + water_path(-0.125), (11, 21, 4)),
            "QI": (0, 1, 0, 0, zero, 0.0625, 62500., 62500., zero, zero, (10, 20, 3)),
            "QR": (0, 0, 0, 0, zero, zero, zero, zero, zero, zero, (10, 20, 3)),
            "QS": (0, 0, 0, 0, zero, zero, zero, zero, zero, zero, (10, 20, 3)),
            "QG": (0, 1, 0, 0, zero, 0.125, 125000., 125000., zero, zero, (11, 20, 3)),
            "QH": (0, 1, 0, 0, zero, 0.0625, 62500., 62500., 62500., zero, (10, 20, 3)),
        }
    else:
        expected = {
            "QC": (0, 1, 0, 0, zero, 0.125, 125000., 125000., zero, zero, (12, 20, 3)),
            "QI": (0, 1, 0, 0, zero, 0.0625, 62500., 62500., zero, zero, (12, 20, 3)),
            "QR": (1, 1, 0, 0, -0.0625, 0.03125, 31250., 31250., zero,
                   water_path(-0.0625), (12, 20, 3)),
            "QS": (1, 1, 0, 0, -(2.0**-90), 0.125, 125000., 125000., 125000.,
                   water_path(-(2.0**-90)), (12, 21, 4)),
            "QG": (0, 1, 0, 0, zero, 0.25, 250000., 250000., zero, zero, (12, 20, 3)),
            "QH": (0, 1, 0, 0, zero, 0.0625, 62500., 62500., zero, zero, (12, 20, 3)),
        }
    for step, summaries in by_step.items():
        for species, expected_values in expected.items():
            (nneg, npos, nnonfinite, npathinvalid, qmin, qmax, pathsum,
             pathmax, clearpath, negpath, min_location) = expected_values
            row = summaries[species]
            integer_expectations = {
                "negative_count": nneg, "positive_count": npos,
                "nonfinite_count": nnonfinite, "path_invalid_count": npathinvalid,
            }
            for field, value in integer_expectations.items():
                if int(row[field]) != value:
                    fail(f"tile {tile} step {step} {species} {field}: {row[field]} != {value}")
            real_expectations = {
                "min_q_kgkg": qmin, "max_q_kgkg": qmax,
                "sum_positive_path_gm2": pathsum,
                "max_positive_path_gm2": pathmax,
                "cf0_positive_path_gm2": clearpath,
                "sum_negative_path_gm2": negpath,
            }
            for field, value in real_expectations.items():
                if row[field].strip() != fortran_es(value):
                    fail(f"tile {tile} step {step} {species} {field}: "
                         f"{row[field].strip()} != exact {fortran_es(value)}")
            got_location = tuple(int(row[key]) for key in ("min_i", "min_j", "min_k"))
            if got_location != min_location:
                fail(f"tile {tile} step {step} {species} min location {got_location} != {min_location}")


def check_invalid_fixture(rows: list[dict[str, str]]) -> None:
    summaries = {row["species"]: row for row in rows if row["kind"] == "summary"}
    if set(summaries) != {"QC", "QI", "QR", "QS", "QG", "QH"}:
        fail("invalid-value fixture did not produce six summaries")
    for species, row in summaries.items():
        expected_nonfinite = 1 if species == "QI" else 0
        if int(row["nonfinite_count"]) != expected_nonfinite:
            fail(f"{species}: nonfinite count {row['nonfinite_count']} != {expected_nonfinite}")
        if int(row["path_invalid_count"]) != 1:
            fail(f"{species}: invalid pressure count {row['path_invalid_count']} != 1")
        if int(row["negative_count"]) != 0 or int(row["positive_count"]) != 0:
            fail(f"{species}: unexpected signed finite q in invalid-value fixture")
        for field in ("min_q_kgkg", "max_q_kgkg", "sum_positive_path_gm2",
                      "max_positive_path_gm2", "cf0_positive_path_gm2",
                      "sum_negative_path_gm2"):
            if row[field].strip() != fortran_es(0.0):
                fail(f"{species}: {field} should be exact zero, got {row[field].strip()}")
        expected_min = (11, 20, 3) if species == "QI" else (10, 20, 3)
        got_min = tuple(int(row[key]) for key in ("min_i", "min_j", "min_k"))
        if got_min != expected_min:
            fail(f"{species}: finite-value minimum location {got_min} != {expected_min}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rrtmgp-hydro-test-",
                                     dir=WRF_ROOT.parent / "build") as temporary:
        root = Path(temporary)
        build = root / "build"
        build.mkdir()
        hydro_exe, builder_exe = compile_fixture(build)

        enabled_dir = root / "enabled"
        enabled_dir.mkdir()
        result = run([str(hydro_exe), "valid"], env=fixture_env(enabled_dir), label="valid tiled hydro fixture")
        if "HYDRO_FIXTURE_PASS" not in result.stdout:
            fail("valid fixture did not reach its pass marker")
        file1, file2 = enabled_dir / TILE1, enabled_dir / TILE2
        if not file1.is_file() or not file2.is_file():
            fail(f"expected independent tile CSV files; got {sorted(p.name for p in enabled_dir.iterdir())}")
        rows1, rows2 = read_rows(file1), read_rows(file2)
        if len(rows1) != 16 or len(rows2) != 16:
            fail(f"two-step append expected 16 data rows per tile, got {len(rows1)} and {len(rows2)}")
        check_summary_rows(rows1, 1)
        check_summary_rows(rows2, 2)
        check_negative_rows(rows1, {
            ("QC", 10, 20, 3, float(np.float32(-(2.0**-100)))),
            ("QC", 11, 21, 4, -0.125),
        })
        check_negative_rows(rows2, {
            ("QR", 12, 20, 3, -0.0625),
            ("QS", 12, 21, 4, float(np.float32(-(2.0**-90)))),
        })

        invalid_dir = root / "invalid"
        invalid_dir.mkdir()
        result = run([str(hydro_exe), "invalid"], env=fixture_env(invalid_dir),
                     label="nonfinite/invalid-pressure fixture")
        if "HYDRO_FIXTURE_PASS" not in result.stdout:
            fail("invalid-value fixture did not reach its pass marker")
        check_invalid_fixture(read_rows(invalid_dir / TILE1))

        disabled_dir = root / "disabled"
        disabled_dir.mkdir()
        result = run([str(hydro_exe), "disabled"], env=fixture_env(None),
                     label="disabled hydro fixture", cwd=disabled_dir)
        if "HYDRO_FIXTURE_PASS" not in result.stdout or list(disabled_dir.iterdir()):
            fail("hydro diagnostics disabled in the environment but output was written")

        fatal = subprocess.run([str(builder_exe)], text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, check=False, env=os.environ.copy())
        expected = re.compile(
            r"column=d01:i=19:j=8 RRTMGP_INPUT_UDM_QG_NEGATIVE "
            r"value_kgkg=-1\.250000000000000E-001 layer=2"
        )
        if fatal.returncode == 0 or not expected.search(fatal.stdout):
            fail("builder negative fixture did not report exact species, q value, context, and layer: "
                 f"rc={fatal.returncode}\n{fatal.stdout[-1200:]}")

    print("PASS: actual audit module preserves tile-local water paths, negative evidence, input bits, "
          "append semantics, disabled behavior, invalid-value counts, and builder fatal context")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
