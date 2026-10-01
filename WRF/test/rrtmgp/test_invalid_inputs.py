#!/usr/bin/env python3
"""Run one invalid cloud-input case and require its diagnostic and failure status."""
import argparse
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", help="compiled test_rrtmgp_cloud_inputs program")
    parser.add_argument("case", help="invalid case passed to the Fortran driver")
    parser.add_argument("expected_substring", help="required diagnostic in combined stdout/stderr")
    parser.add_argument("--data-path", help="optional coefficient directory for adapter cases")
    args = parser.parse_args()
    if not args.expected_substring.strip() or args.expected_substring.strip().upper() in {
        "ERROR STOP", "STOP", "ERROR STOP 1", "ERROR STOP 2"
    }:
        parser.error("expected_substring must identify the specific invalid-input diagnostic")

    command = [args.executable]
    if args.data_path:
        command.append(args.data_path)
    command.append(args.case)
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    output = result.stdout
    if result.returncode == 0:
        print(f"FAIL: {args.case} unexpectedly exited successfully", file=sys.stderr)
        print(output, file=sys.stderr, end="")
        return 1
    if args.expected_substring not in output:
        print(
            f"FAIL: {args.case} exited {result.returncode}, but output did not contain "
            f"{args.expected_substring!r}",
            file=sys.stderr,
        )
        print(output, file=sys.stderr, end="")
        return 1
    print(f"PASS: {args.case} failed with expected diagnostic {args.expected_substring!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
