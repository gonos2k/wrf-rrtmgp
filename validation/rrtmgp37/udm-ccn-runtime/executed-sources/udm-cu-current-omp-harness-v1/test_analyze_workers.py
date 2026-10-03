#!/usr/bin/env python3
"""Offline negative controls for the per-rank GOMP worker proof."""
from __future__ import annotations

import runpy
import argparse
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ns = runpy.run_path(str(HERE / "analyze_workers.py"))
analyze_records = ns["analyze_records"]
analyze_executable = ns["analyze"]
SYMBOL = ns["RADIATION_SYMBOL"]
ADDR = 0x115BD40
BASE = 0x70000000


def line(event: str, pid: int, worker: int, team: int = 2, cpu: int = 100, addr: int = ADDR) -> str:
    return (f"{event} pid={pid} tid={pid * 10 + worker} worker={worker} team={team} "
            f"callback=0x{BASE + addr:x} base=0x{BASE:x} cpu_ns={cpu}")


def valid_rows() -> list[str]:
    rows = []
    for pid in range(1001, 1005):
        for worker in (0, 1):
            for n in range(2):
                start = 1_000_000 + n * 2_000_000
                rows.extend((line("ENTER", pid, worker, cpu=start),
                             line("EXIT", pid, worker, cpu=start + 1_100_000)))
    return rows


def must_fail(label: str, rows: list[str], **kwargs) -> None:
    try:
        analyze_records(rows, {ADDR: SYMBOL}, True, 4, True)
    except RuntimeError:
        return
    raise AssertionError(f"negative control accepted: {label}")


def main() -> None:
    global ADDR
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, help="also verify real executable symbol/disassembly against synthetic observer records")
    args = parser.parse_args()
    if args.exe:
        rows_nm = subprocess.check_output(["nm", "-an", str(args.exe)], text=True).splitlines()
        matches = [int(line.split()[0], 16) for line in rows_nm if len(line.split()) == 3 and line.split()[2] == SYMBOL]
        assert len(matches) == 1, "expected one exact radiation callback symbol"
        ADDR = matches[0]
    result = analyze_records(valid_rows(), {ADDR: SYMBOL}, True, 4, True)
    assert result["verified_all_rank_radiation_workers"] and len(result["observed_pids"]) == 4

    # A global accumulator would see both worker IDs, but no individual MPI PID does.
    rows = []
    for pid in range(1001, 1005):
        worker = (pid - 1001) % 2
        rows.extend((line("ENTER", pid, worker), line("EXIT", pid, worker, cpu=1_100_100)))
    must_fail("workers pooled across MPI PIDs", rows)

    rows = valid_rows()
    rows.insert(1, rows[0])
    must_fail("duplicate ENTER before matching EXIT", rows)

    rows = valid_rows()
    rows.insert(0, line("EXIT", 1001, 0))
    must_fail("unmatched EXIT", rows)

    rows = valid_rows()
    rows[1] = line("EXIT", 1001, 0, cpu=999_999)
    must_fail("out-of-order thread CPU event", rows)

    rows = valid_rows()
    rows[-1] = rows[-1][:-7]
    must_fail("truncated final record", rows)

    rows = [line("ENTER", 1001, 0, team=4), line("EXIT", 1001, 0, team=4)]
    for pid in range(1002, 1005):
        for worker in (0, 1):
            rows.extend((line("ENTER", pid, worker), line("EXIT", pid, worker, cpu=1_100_100)))
    must_fail("wrong team size", rows)

    rows = [line("ENTER", pid, worker, cpu=100) for pid in range(1001, 1005) for worker in (0, 1)]
    rows += [line("EXIT", pid, worker, cpu=1_000_100) for pid in range(1001, 1005) for worker in (0, 1)]
    must_fail("worker CPU does not exceed 1 ms", rows)

    rows = [line("ENTER", pid, worker, addr=ADDR + 4) for pid in range(1001, 1005) for worker in (0, 1)]
    rows += [line("EXIT", pid, worker, cpu=1_100_100, addr=ADDR + 4) for pid in range(1001, 1005) for worker in (0, 1)]
    must_fail("callback address does not resolve", rows)

    try:
        analyze_records(valid_rows(), {ADDR: SYMBOL}, True, 4, False)
    except RuntimeError:
        pass
    else:
        raise AssertionError("negative control accepted callback lacking LW/SW calls")

    try:
        analyze_records(valid_rows(), {ADDR: "different_callback"}, True, 4, True)
    except RuntimeError:
        pass
    else:
        raise AssertionError("negative control accepted missing radiation symbol")
    if args.exe:
        with tempfile.TemporaryDirectory(prefix="omp-worker-analyzer-") as tmp:
            log = Path(tmp) / "synthetic-workers.log"
            log.write_text("\n".join(valid_rows()) + "\n")
            actual = analyze_executable(args.exe, log, 4)
            assert actual["verified_all_rank_radiation_workers"]
    print("OMP_WORKER_ANALYZER_OFFLINE_TESTS_PASS: valid proof plus 10 fail-closed controls"
          + (" and current-executable symbol/disassembly check" if args.exe else ""))


if __name__ == "__main__":
    main()
