#!/usr/bin/env python3
"""Verify the production RRTMGP fatal reporter flushes worker-thread context."""
from __future__ import annotations
import os
import subprocess
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: test_openmp_fatal_reason.py EXECUTABLE", file=sys.stderr)
        return 2
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "2", "OMP_DYNAMIC": "FALSE"})
    result = subprocess.run([sys.argv[1]], env=env, capture_output=True, text=True, timeout=15)
    output = result.stdout + result.stderr
    if result.returncode != 73:
        print(f"expected fatal abort after exact source/line forwarding (fixture rc=73), got rc={result.returncode}:\n{output}", file=sys.stderr)
        return 1
    if "RRTMGP_FATAL [worker-fixture.F90]: OMP_WORKER_FATAL_REASON_VISIBLE" not in output:
        print(f"worker fatal reason was not emitted (rc={result.returncode}):\n{output}", file=sys.stderr)
        return 1
    if "WRF_MASTER_ONLY_MESSAGE" in output:
        print(f"fixture did not exercise a non-master fatal thread:\n{output}", file=sys.stderr)
        return 1
    print(f"PASS: worker reason flushed before fatal abort (rc={result.returncode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
