#!/usr/bin/env python3
"""Require the generated adapter fault to reach the finite-output guard."""
import subprocess
import sys


EXPECTED = {
    "lw_clear_flux_nan": "RRTMGP_OUTPUT_NOT_FINITE phase=LW stage=clear field=UP column=2 interface=1 precision=wp",
    "sw_allsky_heat_nan": "RRTMGP_OUTPUT_NOT_FINITE phase=SW stage=allsky field=HEAT column=2 layer=2 precision=wp",
    "lw_allsky_default_overflow": "RRTMGP_OUTPUT_NOT_FINITE phase=LW stage=allsky field=UP column=2 interface=1 precision=default-real",
}
SKIP_MARKER = "OUTPUT_FINITE_TEST_SKIPPED_DEFAULT_REAL_NOT_NARROWER_THAN_WP"


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: test_output_finite_fault.py EXECUTABLE CASE DATA_DIRECTORY", file=sys.stderr)
        return 2
    executable, case_name, data_dir = sys.argv[1:]
    if case_name not in EXPECTED:
        print(f"unknown output-finite fault case: {case_name}", file=sys.stderr)
        return 2
    result = subprocess.run(
        [executable, data_dir, case_name], stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, check=False,
    )
    if case_name == "lw_allsky_default_overflow" and result.returncode == 77 and SKIP_MARKER in result.stdout:
        print(f"SKIP: {case_name} requires default REAL to have a narrower range than wp")
        return 77
    expected = EXPECTED[case_name]
    if result.returncode == 0 or expected not in result.stdout:
        print(f"FAIL: {case_name} returned {result.returncode}; expected guard diagnostic {expected!r}", file=sys.stderr)
        print(result.stdout, file=sys.stderr, end="")
        return 1
    print(f"PASS: {case_name} reached guard with expected location diagnostic")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
