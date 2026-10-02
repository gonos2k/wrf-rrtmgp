#!/usr/bin/env python3
"""Require a specific fatal contract, rather than any incidental process failure."""
import subprocess
import sys
p = subprocess.run(sys.argv[1:5], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
if p.returncode == 0 or sys.argv[5] not in p.stdout:
    raise SystemExit(f"Expected rejection {sys.argv[5]!r}, status={p.returncode}: {p.stdout}")
print(p.stdout)
