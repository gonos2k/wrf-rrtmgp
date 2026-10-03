#!/usr/bin/env python3
"""Strict GOMP observer analyzer; proves the radiation callback on every MPI rank."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path


RADIATION_SYMBOL = "__module_radiation_driver_MOD_radiation_driver._omp_fn.1"
LINE = re.compile(r"^(ENTER|EXIT) pid=(\d+) tid=(\d+) worker=(\d+) team=(\d+) callback=(0x[0-9a-fA-F]+) base=(0x[0-9a-fA-F]+) cpu_ns=(\d+)$")


def analyze_records(lines: list[str], symbol_addresses: dict[int, str], is_pie: bool,
                    expected_ranks: int, has_both_engines: bool = True) -> dict:
    if not has_both_engines:
        raise RuntimeError("current radiation callback disassembly lacks LW and SW wrapper calls")
    if RADIATION_SYMBOL not in symbol_addresses.values():
        raise RuntimeError("current radiation callback symbol is absent from executable symbol table")
    open_events = {}
    last_cpu_by_thread = {}
    groups = defaultdict(lambda: {"workers": set(), "teams": set(), "events": {"ENTER": 0, "EXIT": 0}, "cpu_ns": defaultdict(int), "pairs": 0})
    all_records = 0
    records = lines
    if not records:
        raise RuntimeError("observer log is empty")
    for line_no, line in enumerate(records, 1):
        match = LINE.fullmatch(line)
        if not match:
            raise RuntimeError(f"malformed/truncated observer record at line {line_no}")
        event, pid_s, tid_s, worker_s, team_s, callback_s, base_s, cpu_s = match.groups()
        pid, tid, worker, team = int(pid_s), int(tid_s), int(worker_s), int(team_s)
        callback, base, cpu = int(callback_s, 16), int(base_s, 16), int(cpu_s)
        rel = callback - base if is_pie else callback
        symbol = symbol_addresses.get(rel, "unresolved")
        if symbol != RADIATION_SYMBOL:
            continue
        thread_key = (pid, tid)
        if thread_key in last_cpu_by_thread and cpu < last_cpu_by_thread[thread_key]:
            raise RuntimeError(f"out-of-order thread CPU clock for {thread_key} at line {line_no}")
        last_cpu_by_thread[thread_key] = cpu
        key = (pid, tid, callback)
        if event == "ENTER":
            if key in open_events:
                raise RuntimeError(f"duplicate/unbalanced ENTER for {key} at line {line_no}")
            open_events[key] = (worker, team, cpu)
        else:
            if key not in open_events:
                raise RuntimeError(f"unmatched EXIT for {key} at line {line_no}")
            start_worker, start_team, start_cpu = open_events.pop(key)
            if (worker, team) != (start_worker, start_team) or cpu < start_cpu:
                raise RuntimeError(f"worker/team/clock changed within callback pair {key}")
            g = groups[pid]
            g["workers"].add(worker)
            g["teams"].add(team)
            g["events"]["ENTER"] += 1
            g["events"]["EXIT"] += 1
            g["cpu_ns"][worker] += cpu - start_cpu
            g["pairs"] += 1
        all_records += 1
    if open_events:
        raise RuntimeError(f"unmatched callback ENTER events: {len(open_events)}")
    if len(groups) != expected_ranks:
        raise RuntimeError(f"expected radiation callback on {expected_ranks} MPI PIDs, found {len(groups)}")
    per_pid = {}
    for pid, g in sorted(groups.items()):
        if g["workers"] != {0, 1} or g["teams"] != {2} or g["pairs"] < 2:
            raise RuntimeError(f"PID {pid} did not show both workers/team2 with paired callbacks")
        if any(g["cpu_ns"].get(w, 0) <= 1_000_000 for w in (0, 1)):
            raise RuntimeError(f"PID {pid} worker callback CPU is not >1ms for both workers")
        per_pid[str(pid)] = {"workers": sorted(g["workers"]), "teams": sorted(g["teams"]),
                             "paired_callbacks": g["pairs"], "worker_cpu_ns": dict(g["cpu_ns"]),
                             "balanced": g["events"]["ENTER"] == g["events"]["EXIT"]}
    return {"status": "PASS_ALL_RANKS_RADIATION_WORKERS", "pie": is_pie,
            "symbol": RADIATION_SYMBOL, "contains_lw_and_sw_calls": has_both_engines,
            "expected_mpi_ranks": expected_ranks, "observed_pids": per_pid, "radiation_records": all_records,
            "verified_all_rank_radiation_workers": True}


def analyze(exe: Path, log: Path, expected_ranks: int) -> dict:
    nm_lines = subprocess.check_output(["nm", "-an", str(exe)], text=True).splitlines()
    symbol_addresses = {}
    for line in nm_lines:
        fields = line.split()
        if len(fields) == 3 and "._omp_fn." in fields[2]:
            symbol_addresses[int(fields[0], 16)] = fields[2]
    if RADIATION_SYMBOL not in symbol_addresses.values():
        raise RuntimeError("current radiation callback symbol is absent from executable symbol table")
    disassembly = subprocess.check_output(["objdump", "-d", "--disassemble=" + RADIATION_SYMBOL, str(exe)], text=True)
    has_both_engines = ("__module_ra_rrtmg_lw_MOD_rrtmg_lwrad" in disassembly and
                        "__module_ra_rrtmg_sw_MOD_rrtmg_swrad" in disassembly)
    elf = subprocess.check_output(["readelf", "-h", str(exe)], text=True)
    is_pie = bool(re.search(r"Type:\s+DYN", elf))
    lines = log.read_text(errors="strict").splitlines()
    result = analyze_records(lines, symbol_addresses, is_pie, expected_ranks, has_both_engines)
    import hashlib
    result.update({"executable": str(exe.resolve()), "executable_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
                   "log": str(log.resolve()), "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()})
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", type=Path, required=True)
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--ranks", type=int, default=4)
    a = ap.parse_args()
    result = analyze(a.exe, a.log, a.ranks)
    a.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "observed_pids"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
