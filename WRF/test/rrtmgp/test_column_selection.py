#!/usr/bin/env python3
"""Build the real trace selector and test default, selected, and invalid contracts."""
from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import tempfile

import analyse_udm_physics_audit


def run(command: list[str], cwd: pathlib.Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wrf_root", type=pathlib.Path)
    parser.add_argument("--compiler", default=shutil.which("gfortran") or "gfortran")
    args = parser.parse_args()
    wrf = args.wrf_root.resolve()
    scratch_parent=wrf.parent / "build"
    scratch_parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rrtmgp-column-selection-",dir=scratch_parent) as td:
        root = pathlib.Path(td)
        capture = root / "capture"
        capture.mkdir()
        inc = ["-I", str(root), "-J", str(root)]
        stub = wrf / "test/rrtmgp/standalone_wrf_error.f90"
        trace = wrf / "phys/module_ra_rrtmgp_trace.F"
        driver = wrf / "test/rrtmgp/test_column_selection.f90"
        for source, output in ((stub, root / "error.o"), (trace, root / "trace.o")):
            command = [args.compiler, "-cpp", "-ffree-form", "-ffree-line-length-none", *inc,
                       "-c", str(source), "-o", str(output)]
            proc = run(command, root)
            if proc.returncode:
                raise RuntimeError(f"compile failed:\n{proc.stdout}")
        exe = root / "test_column_selection"
        command = [args.compiler, "-ffree-form", "-ffree-line-length-none", *inc, str(driver),
                   str(root / "trace.o"), str(root / "error.o"), "-o", str(exe)]
        proc = run(command, root)
        if proc.returncode:
            raise RuntimeError(f"link failed:\n{proc.stdout}")

        base = {k: v for k, v in os.environ.items()
                if not k.startswith("WRF_RRTMGP_COLUMN_") and k != "WRF_RRTMGP_CAPTURE_DIR"}
        base["WRF_RRTMGP_CAPTURE_DIR"] = str(capture)

        def expect_ok(label: str, mode: str, updates: dict[str, str]) -> None:
            env = dict(base); env.update(updates)
            result = run([str(exe), mode], root, env)
            if result.returncode or "column selection contract passed" not in result.stdout:
                raise AssertionError(f"{label}: expected PASS, got {result.returncode}\n{result.stdout}")

        def expect_fail(label: str, mode: str, updates: dict[str, str], diagnostic: str) -> None:
            env = dict(base); env.update(updates)
            result = run([str(exe), mode], root, env)
            if result.returncode == 0 or diagnostic not in result.stdout:
                raise AssertionError(f"{label}: expected {diagnostic}, got {result.returncode}\n{result.stdout}")

        expect_ok("legacy absent", "legacy", {})
        expect_ok("selected pair", "selected", {"WRF_RRTMGP_COLUMN_I": "169", "WRF_RRTMGP_COLUMN_J": "80"})
        expect_fail("missing J", "selected", {"WRF_RRTMGP_COLUMN_I": "169"},
                    "RRTMGP_COLUMN_SELECTION_PAIR_REQUIRED")
        expect_fail("missing I", "selected", {"WRF_RRTMGP_COLUMN_J": "80"},
                    "RRTMGP_COLUMN_SELECTION_PAIR_REQUIRED")
        for val in ("", "0", "-1", "+1", "1x", "2147483648"):
            expect_fail(f"invalid I {val!r}", "selected",
                        {"WRF_RRTMGP_COLUMN_I": val, "WRF_RRTMGP_COLUMN_J": "80"},
                        "RRTMGP_COLUMN_SELECTION_INVALID_I")
            expect_fail(f"invalid J {val!r}", "selected",
                        {"WRF_RRTMGP_COLUMN_I": "169", "WRF_RRTMGP_COLUMN_J": val},
                        "RRTMGP_COLUMN_SELECTION_INVALID_J")
        expect_ok("last physical column", "boundary",
                  {"WRF_RRTMGP_COLUMN_I": "200", "WRF_RRTMGP_COLUMN_J": "120"})
        expect_fail("I at staggered IDE edge", "out-i",
                    {"WRF_RRTMGP_COLUMN_I": "201", "WRF_RRTMGP_COLUMN_J": "80"},
                    "RRTMGP_COLUMN_SELECTION_OUT_OF_DOMAIN")
        expect_fail("J at staggered JDE edge", "out-j",
                    {"WRF_RRTMGP_COLUMN_I": "169", "WRF_RRTMGP_COLUMN_J": "121"},
                    "RRTMGP_COLUMN_SELECTION_OUT_OF_DOMAIN")
        common = {"phase": "lw", "domain": "1", "step": "1", "source_seconds": "10",
                  "metric": "SURFACE_DOWN", "radius_mode": "0"}
        selected_rows = [
            {**common, "i": "169", "j": "80", "scope": "selected_column"},
            {**common, "i": "0", "j": "0", "scope": "selected_column"},
        ]
        analyse_udm_physics_audit.validate_scope_rows(selected_rows, "selected fixture")
        legacy_rows = [
            {**common, "i": "169", "j": "80", "scope": "full_tile_cell"},
            {**common, "i": "0", "j": "0", "scope": "full_tile_mean"},
        ]
        analyse_udm_physics_audit.validate_scope_rows(legacy_rows, "legacy fixture")
        for bad_rows in (
            [selected_rows[0], selected_rows[0], selected_rows[1]],
            [selected_rows[0], {**selected_rows[0], "i": "170"}, selected_rows[1]],
            [selected_rows[0], {**selected_rows[1], "j": "1"}],
            [selected_rows[0], {**selected_rows[0], "i": "-1", "j": "-1"}, selected_rows[1]],
            [selected_rows[0], {**selected_rows[1], "scope": "full_tile_mean"}],
        ):
            try:
                analyse_udm_physics_audit.validate_scope_rows(bad_rows, "corrupt fixture")
            except ValueError:
                pass
            else:
                raise AssertionError("audit analyzer accepted inconsistent selected-scope rows")
        analyse_udm_physics_audit.validate_scope_rows([common], "pre-scope legacy fixture")
        print("PASS: paired selectors, legacy defaults, trace/tile filtering, malformed and out-of-domain rejection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
