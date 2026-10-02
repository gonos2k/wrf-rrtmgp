#!/usr/bin/env python3
"""Check WRF's UDM module prerequisites and parallel make ordering."""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path


def dependency_rules(path: Path) -> dict[str, set[str]]:
    rules: dict[str, set[str]] = {}
    logical_lines: list[str] = []
    pending = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        pending += " " + line.rstrip("\\").strip()
        if line.endswith("\\"):
            continue
        logical_lines.append(pending.strip())
        pending = ""
    if pending:
        logical_lines.append(pending.strip())
    for line in logical_lines:
        if ":" not in line:
            continue
        targets, prerequisites = line.split(":", 1)
        prereq_names = {token for token in prerequisites.split()
                        if token.endswith(".o") and "$" not in token}
        for target in targets.split():
            if target.endswith(".o"):
                rules.setdefault(target, set()).update(prereq_names)
    return rules


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("depend_common", type=Path)
    args = parser.parse_args()
    rules = dependency_rules(args.depend_common)
    required = {
        "module_mp_udm.o": {"module_mp_radar.o", "module_gfs_machine.o"},
        "module_physics_init.o": {"module_mp_udm.o"},
        "module_microphysics_driver.o": {"module_mp_udm.o"},
        "module_ra_rrtmg_lw.o": {"module_mp_udm.o"},
        "module_ra_rrtmg_sw.o": {"module_mp_udm.o"},
    }
    for target, dependencies in required.items():
        missing = dependencies - rules.get(target, set())
        if missing:
            raise SystemExit(f"{target} is missing Make prerequisites: {', '.join(sorted(missing))}")

    # Exercise GNU Make's parallel scheduler using the exact edges checked above.
    # Artificial compile recipes log completion, so a missing edge is observable.
    nodes = set(required)
    for deps in required.values():
        nodes.update(deps)
    with tempfile.TemporaryDirectory(prefix="wrf-udm-dependencies-") as tmp:
        root = Path(tmp)
        log = root / "order.log"
        makefile = root / "Makefile"
        lines = [f"LOG := {log}", ".PHONY: all " + " ".join(sorted(nodes)),
                 "all: module_physics_init.o module_microphysics_driver.o module_ra_rrtmg_lw.o module_ra_rrtmg_sw.o"]
        for target in sorted(nodes):
            prereqs = required.get(target, set())
            lines.append(f"{target}: {' '.join(sorted(prereqs))}".rstrip())
            lines.append(f"\t@sleep 0.01; echo {target} >> $(LOG)")
        makefile.write_text("\n".join(lines) + "\n", encoding="utf-8")
        proc = subprocess.run(["make", "--no-print-directory", "-j8", "-f", str(makefile), "all"],
                              cwd=root, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, check=False)
        if proc.returncode:
            raise SystemExit(f"parallel dependency scheduling failed: {proc.stdout}")
        completed = log.read_text(encoding="utf-8").splitlines()
        positions = {name: completed.index(name) for name in completed}
        for consumer in required:
            for dependency in required[consumer]:
                if positions[dependency] >= positions[consumer]:
                    raise SystemExit(f"Make scheduled {consumer} before {dependency}: {completed}")
    print("WRF_UDM_DEPENDENCY_GRAPH_OK_PARALLEL_ORDER_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
