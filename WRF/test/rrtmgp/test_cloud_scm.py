#!/usr/bin/env python3
"""Run one real LSM2/37-37 SCM case and verify excluded clear-condensate traces."""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import test_surface_scm


WRF_ROOT = test_surface_scm.WRF_ROOT
TEMPLATE = test_surface_scm.TEMPLATE
VALIDATOR = TEMPLATE.parent / "validate_scm.py"
SUCCESS_TOKEN = "SUCCESS COMPLETE WRF"
DIAGNOSTIC_TOKEN = "RRTMGP_CLEAR_CONDENSATE_EXCLUDED"
DIAGNOSTIC = re.compile(
    r"\b(?P<phase>LW|SW)\s+i=\s*\d+\s+j=\s*\d+:\s+"
    r"RRTMGP_CLEAR_CONDENSATE_EXCLUDED\s+layer=\s*(?P<layer>\d+)\s+"
    r"reason=\s*(?P<reason>\d+)\s+grid_path_g_m2=\s*"
    r"(?P<path>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?)"
)


def fail(message: str) -> None:
    raise RuntimeError(message)


def original_lsm2_namelist() -> str:
    text = TEMPLATE.read_text()
    if re.search(r"(?im)^\s*debug_level\s*=", text):
        text, count = re.subn(
            r"(?im)^(\s*debug_level\s*=\s*)[^,\n]+,",
            r"\g<1>100,",
            text,
            count=1,
        )
    else:
        text, count = re.subn(
            r"(?im)^(\s*&time_control\s*)$",
            r"\g<1>\n debug_level                         = 100,",
            text,
            count=1,
        )
    if count != 1:
        fail("could not set debug_level=100 in the original SCM template")
    if not re.search(r"(?im)^\s*sf_surface_physics\s*=\s*2\s*,", text):
        fail("the original SCM template must retain sf_surface_physics=2")
    return text


def parse_diagnostics(log_text: str) -> dict:
    raw_count = log_text.count(DIAGNOSTIC_TOKEN)
    entries = list(DIAGNOSTIC.finditer(log_text))
    if raw_count != len(entries):
        fail(f"found {raw_count} condensate diagnostic token(s), parsed {len(entries)}")
    result = {
        phase: {"count": 0, "max_grid_path_g_m2": 0.0, "layers": []}
        for phase in ("LW", "SW")
    }
    for match in entries:
        phase = match.group("phase").upper()
        layer = int(match.group("layer"))
        reason = int(match.group("reason"))
        path = float(match.group("path").replace("D", "E").replace("d", "e"))
        if reason != 6:
            fail(f"{phase} layer {layer}: expected omitted-cloud reason 6, got {reason}")
        if not math.isfinite(path) or path <= 0.0:
            fail(f"{phase} layer {layer}: expected finite positive omitted path, got {path}")
        phase_result = result[phase]
        phase_result["count"] += 1
        phase_result["max_grid_path_g_m2"] = max(phase_result["max_grid_path_g_m2"], path)
        phase_result["layers"].append(layer)
    for phase in ("LW", "SW"):
        if result[phase]["count"] < 1:
            fail(f"no real {phase} clear-condensate exclusion diagnostic was logged")
    return result


def validate_case(case_dir: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(case_dir), "--expected-options", "37"],
        cwd=WRF_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        fail(f"validate_scm.py failed ({result.returncode}):\n{result.stdout[-5000:]}")
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        fail(f"validate_scm.py returned invalid JSON: {exc}\n{result.stdout[-2000:]}")
    key = str(case_dir)
    if key not in report:
        fail(f"validate_scm.py JSON omitted case {key}")
    return report[key]


def run_case(case_dir: Path) -> dict:
    # prepare_case creates the isolated inputs and symlinks, then restore the
    # original namelist so the normal LSM2 configuration remains active.
    test_surface_scm.prepare_case(case_dir, swint_opt=0)
    (case_dir / "namelist.input").write_text(original_lsm2_namelist())

    ideal_exe = WRF_ROOT / "main/ideal.exe"
    wrf_exe = WRF_ROOT / "main/wrf.exe"
    ideal = test_surface_scm.run_logged(ideal_exe, case_dir, "ideal.log")
    if ideal.returncode != 0 or not (case_dir / "wrfinput_d01").is_file():
        fail(f"{case_dir}: ideal.exe failed; inspect ideal.log")

    wrf = test_surface_scm.run_logged(wrf_exe, case_dir, "wrf.log")
    if wrf.returncode != 0:
        fail(f"{case_dir}: wrf.exe returned {wrf.returncode}; inspect wrf.log")
    log_text = (case_dir / "wrf.log").read_text(errors="replace")
    if SUCCESS_TOKEN not in log_text:
        fail(f"{case_dir}: WRF success marker missing")

    validation = validate_case(case_dir)
    diagnostics = parse_diagnostics(log_text)
    max_omitted = max(
        diagnostics[phase]["max_grid_path_g_m2"] for phase in ("LW", "SW")
    )
    return {
        "case": str(case_dir),
        "status": "PASS",
        "token": SUCCESS_TOKEN,
        "radiation_options": [validation["radiation_option_lw"], validation["radiation_option_sw"]],
        "history_file": validation["history_file"],
        "time_count": validation["time_count"],
        "diagnostic_counts": {phase: diagnostics[phase]["count"] for phase in ("LW", "SW")},
        "max_omitted_grid_path_g_m2": max_omitted,
        "diagnostics": diagnostics,
        "checks": validation["checks"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_case_directory", type=Path,
                        help="new, nonexistent directory for the isolated SCM integration case")
    args = parser.parse_args()
    case_dir = args.new_case_directory.expanduser().resolve()
    if case_dir.exists():
        parser.error(f"refusing existing case directory: {case_dir}")
    if not case_dir.parent.is_dir():
        parser.error(f"case parent directory does not exist: {case_dir.parent}")
    for executable in (WRF_ROOT / "main/ideal.exe", WRF_ROOT / "main/wrf.exe"):
        if not executable.is_file() or not executable.stat().st_mode & 0o111:
            parser.error(f"missing executable {executable}; build em_scm_xy first")
    if not VALIDATOR.is_file():
        parser.error(f"missing SCM validator {VALIDATOR}")

    try:
        print(json.dumps(run_case(case_dir), indent=2))
        return 0
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
