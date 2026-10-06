#!/usr/bin/env python3
"""Compile/run the six input_wrf UDM sentinel guards for both storage kinds.

The fixture embeds the exact four preprocessor groups selected from
WRF/share/input_wrf.F: three restart-startup assignments and one assignment
for each failed-read field case. This is a focused kind-compatibility fixture,
not an input_wrf or WRF build.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


FIELDS = {
    "udm_cldfra": ("real", "-1."),
    "udm_cf_step": ("integer", "-1"),
    "udm_cf_top": ("integer", "-1"),
}
EXPECTED_GROUPS = [
    ("udm_cldfra", "udm_cf_step", "udm_cf_top"),
    ("udm_cldfra",), ("udm_cf_step",), ("udm_cf_top",),
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_groups(source: Path) -> tuple[bytes, list[str]]:
    raw = source.read_bytes()
    text = raw.decode("utf-8")
    lines = text.splitlines(keepends=True)
    groups = []
    i = 0
    while i < len(lines):
        if lines[i].strip() != "#ifdef USE_ALLOCATABLES":
            i += 1
            continue
        start = i
        i += 1
        while i < len(lines) and lines[i].strip() != "#endif":
            i += 1
        if i >= len(lines):
            raise ValueError("unterminated USE_ALLOCATABLES guard in input_wrf.F")
        group = "".join(lines[start:i + 1])
        if "grid%udm_" in group:
            groups.append(group)
        i += 1
    if len(groups) != 4:
        raise ValueError(f"expected four source-selected guard groups, got {len(groups)}")
    for index, (group, expected) in enumerate(zip(groups, EXPECTED_GROUPS)):
        alloc, pointer = group.split("#else", 1)
        alloc_fields = tuple(name for name in FIELDS if f"ALLOCATED(grid%{name})" in alloc)
        pointer_fields = tuple(name for name in FIELDS if f"ASSOCIATED(grid%{name})" in pointer)
        if alloc_fields != expected or pointer_fields != expected:
            raise ValueError(f"source guard group {index} fields mismatch: {alloc_fields}, {pointer_fields}")
        for name in expected:
            kind, sentinel = FIELDS[name]
            if f"grid%{name} = {sentinel}" not in alloc or f"grid%{name} = {sentinel}" not in pointer:
                raise ValueError(f"source guard group {index} changed sentinel for {name}")
    return raw, groups


def fixture_source(groups: list[str]) -> str:
    failed_cases = {
        "udm_cldfra": groups[1],
        "udm_cf_step": groups[2],
        "udm_cf_top": groups[3],
    }
    failed_body = "\n".join(
        f"    CASE ('{name}')\n{group}"
        for name, group in failed_cases.items())
    return f'''module input_wrf_udm_sentinel_fixture
  implicit none
  type :: grid_type
#ifdef USE_ALLOCATABLES
    real, allocatable :: udm_cldfra(:,:,:)
    integer, allocatable :: udm_cf_step(:,:), udm_cf_top(:,:)
#else
    real, pointer :: udm_cldfra(:,:,:) => null()
    integer, pointer :: udm_cf_step(:,:) => null(), udm_cf_top(:,:) => null()
#endif
  end type
contains
  subroutine seed_restart(grid, enabled)
    type(grid_type), intent(inout) :: grid
    logical, intent(in) :: enabled
    if (enabled) then
{groups[0]}    endif
  end subroutine

  subroutine recover_failed_read(grid, enabled, ierr, is_restart, in_use, name)
    type(grid_type), intent(inout) :: grid
    logical, intent(in) :: enabled, is_restart, in_use
    integer, intent(in) :: ierr
    character(*), intent(in) :: name
    if (enabled .and. ierr /= 0 .and. is_restart .and. in_use) then
      select case (trim(name))
{failed_body}
      end select
    endif
  end subroutine
end module

program test_input_wrf_udm_sentinels
  use input_wrf_udm_sentinel_fixture
  implicit none
  type(grid_type) :: grid, empty_grid
  integer :: ierr
  allocate(grid%udm_cldfra(2,3,2), grid%udm_cf_step(2,2), grid%udm_cf_top(2,2))
  grid%udm_cldfra=9.; grid%udm_cf_step=9; grid%udm_cf_top=9
  call seed_restart(grid,.false.)
  if (any(grid%udm_cldfra /= 9.) .or. any(grid%udm_cf_step /= 9) .or. &
      any(grid%udm_cf_top /= 9)) error stop 11
  call seed_restart(grid,.true.)
  if (any(grid%udm_cldfra /= -1.) .or. any(grid%udm_cf_step /= -1) .or. &
      any(grid%udm_cf_top /= -1)) error stop 12
  grid%udm_cldfra=8.; grid%udm_cf_step=8; grid%udm_cf_top=8
  ierr=17
  call recover_failed_read(grid,.false.,ierr,.true.,.true.,'udm_cldfra')
  if (any(grid%udm_cldfra /= 8.)) error stop 13
  call recover_failed_read(grid,.true.,ierr,.true.,.false.,'udm_cldfra')
  if (any(grid%udm_cldfra /= 8.)) error stop 14
  call recover_failed_read(grid,.true.,ierr,.true.,.true.,'udm_cldfra')
  call recover_failed_read(grid,.true.,ierr,.true.,.true.,'udm_cf_step')
  call recover_failed_read(grid,.true.,ierr,.true.,.true.,'udm_cf_top')
  if (any(grid%udm_cldfra /= -1.) .or. any(grid%udm_cf_step /= -1) .or. &
      any(grid%udm_cf_top /= -1)) error stop 15
  grid%udm_cldfra=5.; grid%udm_cf_step=5; grid%udm_cf_top=5
  call recover_failed_read(grid,.true.,0,.true.,.true.,'udm_cf_step')
  call recover_failed_read(grid,.true.,ierr,.false.,.true.,'udm_cf_top')
  call recover_failed_read(grid,.true.,ierr,.true.,.true.,'unsupported_restart_field')
  if (any(grid%udm_cldfra /= 5.) .or. any(grid%udm_cf_step /= 5) .or. &
      any(grid%udm_cf_top /= 5)) error stop 16
  call seed_restart(empty_grid,.true.)
  call recover_failed_read(empty_grid,.true.,ierr,.true.,.true.,'udm_cldfra')
  call recover_failed_read(empty_grid,.true.,ierr,.true.,.true.,'udm_cf_step')
  call recover_failed_read(empty_grid,.true.,ierr,.true.,.true.,'udm_cf_top')
  print '(A)', 'INPUT_WF_UDM_SENTINEL_KIND_FIXTURE_PASS'
end program
'''


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def run_child(argv: list[str], cwd: Path, log: Path, timeout: float = 120.0) -> dict:
    started = __import__("time").time()
    try:
        with log.open("wb") as output:
            child = subprocess.run(argv, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                                   timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        return {"argv": argv, "status": "TIMED_OUT", "returncode": None,
                "timeout_seconds": timeout, "child_reaped": True,
                "log": str(log), "error": type(exc).__name__,
                "started_epoch": started, "ended_epoch": __import__("time").time()}
    return {"argv": argv, "status": "EXITED_ZERO" if child.returncode == 0 else "EXITED_NONZERO",
            "returncode": child.returncode, "log": str(log),
            "log_sha256": sha(log.read_bytes()), "log_size_bytes": log.stat().st_size,
            "started_epoch": started, "ended_epoch": __import__("time").time()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wrf_root", type=Path)
    parser.add_argument("--compiler", default=shutil.which("gfortran") or "gfortran")
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    wrf = args.wrf_root.resolve()
    if not (wrf / "share/input_wrf.F").is_file():
        parser.error(f"not a WRF root: {wrf}")
    if args.output and args.output.exists():
        parser.error(f"refusing existing output file: {args.output}")
    source = wrf / "share/input_wrf.F"
    raw, groups = extract_groups(source)
    if args.workdir:
        work = args.workdir.resolve()
        work.mkdir(parents=True, exist_ok=True)
        cleanup = None
    else:
        cleanup = tempfile.TemporaryDirectory(prefix="input-wrf-udm-sentinels-")
        work = Path(cleanup.name)
    results = []
    try:
        for mode in ("pointer", "allocatable"):
            case = work / mode
            case.mkdir(parents=True, exist_ok=False)
            fixture = case / "test_input_wrf_udm_sentinels.F90"
            fixture.write_text(fixture_source(groups))
            exe = case / "fixture.exe"
            argv = [args.compiler, "-cpp", "-std=f2008", "-ffree-line-length-none",
                    "-O0", str(fixture), "-o", str(exe)]
            if mode == "allocatable":
                argv.insert(1, "-DUSE_ALLOCATABLES")
            compile_result = run_child(argv, case, case / "compile.log")
            record = {"mode": mode, "compile": compile_result,
                      "fixture_sha256": sha(fixture.read_bytes())}
            if compile_result["returncode"] != 0:
                results.append(record)
                receipt = make_receipt(source, raw, groups, results)
                if args.output: atomic_json(args.output.resolve(), receipt)
                raise RuntimeError(f"{mode} fixture compilation failed")
            execution = run_child([str(exe)], case, case / "run.log")
            record["execution"] = execution
            logtext = (case / "run.log").read_text(errors="replace")
            record["pass_marker_present"] = "INPUT_WF_UDM_SENTINEL_KIND_FIXTURE_PASS" in logtext
            results.append(record)
            if execution["returncode"] != 0 or not record["pass_marker_present"]:
                receipt = make_receipt(source, raw, groups, results)
                if args.output: atomic_json(args.output.resolve(), receipt)
                raise RuntimeError(f"{mode} fixture execution failed")
        receipt = make_receipt(source, raw, groups, results)
        if args.output: atomic_json(args.output.resolve(), receipt)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    finally:
        if cleanup:
            cleanup.cleanup()


def make_receipt(source: Path, raw: bytes, groups: list[str], results: list[dict]) -> dict:
    return {"schema": "UDM_INPUT_WRESTART_SENTINEL_STORAGE_FIXTURE_V1",
            "status": "PASS_POINTER_AND_ALLOCATABLE" if len(results) == 2 and all(
                r.get("execution", {}).get("returncode") == 0 and r.get("pass_marker_present")
                for r in results) else "INCOMPLETE_OR_FAILED",
            "source": {"path": "WRF/share/input_wrf.F", "sha256": sha(raw),
                       "guard_group_sha256": [sha(g.encode()) for g in groups],
                       "guard_group_count": len(groups)},
            "modes": results,
            "scope": "Actual source-selected sentinel guards compiled and run in small pointer/allocatable fixtures; this is not a full input_wrf or WRF build.",
            "execution_counts": {"fixture_compiles": sum("compile" in r for r in results),
                                 "fixture_runs": sum("execution" in r for r in results),
                                 "WRF_builds": 0, "models": 0, "RTE": 0}}


if __name__ == "__main__":
    raise SystemExit(main())
