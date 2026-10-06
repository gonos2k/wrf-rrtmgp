#!/usr/bin/env python3
"""Source-extracted regression for the UDM warm-ice effective-radius endpoint.

This compiles only the actual native radius subroutine inside a small fixture
module. It does not build or run WRF. Example::

  python3 test_udm_warm_ice_radius.py --wrf-root WRF --workdir /tmp/radius-test \
      --output /tmp/radius-test/receipt.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
from typing import Any


WARM_REPRO_RESULT_SHA256 = "4504a8b870f643914b3551139a7a49c9085cd766f8b3adde2f51fec5727b788f"
WARM_PACKET_SHA256 = "5e8b83b867e2e0848576789e67d7e713666d9efdff94e6e7b08da462b79ae166"
WARM_ROWS = [
    {"k": 31, "T_K": 274.4627990722656, "QI_kg_kg": 4.904224942814395e-11,
     "RHO_kg_m3": 0.8843621015548706, "IWC_kg_m3": 4.337110676925153e-11},
    {"k": 32, "T_K": 273.90325927734375, "QI_kg_kg": 2.060881065801823e-8,
     "RHO_kg_m3": 0.87006676197052, "IWC_kg_m3": 1.7931041157285462e-8},
    {"k": 33, "T_K": 273.2991027832031, "QI_kg_kg": 2.3331041987262324e-8,
     "RHO_kg_m3": 0.8554592728614807, "IWC_kg_m3": 1.9958756213524104e-8},
]
QMIN = 1.0000000036274937e-15
T0C = 273.1499938964844
GUARDED = "temp = max(0., t0c - t(k))"
ORIGINAL = "temp = t0c - t(k)"
ROUTINE_RE = re.compile(
    r"(?ims)^subroutine\s+udm_mp_effective_radius\b.*?"
    r"^end\s+subroutine\s+udm_mp_effective_radius\s*$"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_routine(source: Path) -> str:
    matches = list(ROUTINE_RE.finditer(source.read_text()))
    if len(matches) != 1:
        raise RuntimeError(f"expected one effective-radius routine, found {len(matches)}")
    routine = matches[0].group(0)
    if routine.count(GUARDED) != 1:
        raise RuntimeError("expected exactly one guarded warm-ice temperature expression")
    return routine


def make_program(routine: str) -> str:
    rows = WARM_ROWS
    t_values = ",".join(f"{row['T_K']:.17e}" for row in rows)
    qi_values = ",".join(f"{row['QI_kg_kg']:.17e}" for row in rows)
    rho_values = ",".join(f"{row['RHO_kg_m3']:.17e}" for row in rows)
    return f"""module udm_radius_fixture
  implicit none
  real, parameter :: pi = 4.0*atan(1.0), pidnc=pi*1000.0/6.0
  real, parameter :: pidn0s=pi*100.0*2.0e6
  real, parameter :: recmin=2.51e-6, recmax=50.e-6
  real, parameter :: reimin=5.01e-6, reimax=125.e-6
  real, parameter :: resmin=25.e-6, resmax=999.e-6
  real, parameter :: alpha=.12, n0smax=1.e11, n0s=2.e6
contains
{routine}
end module udm_radius_fixture

program exercise_radius
  use udm_radius_fixture
  implicit none
  real :: t0c, qmin, t(1:1), qc(1:1), qi(1:1), qs(1:1), rho(1:1), nc(1:1)
  real :: rc(1:1), ri(1:1), rs(1:1)
  integer :: mode, j, ios, bits
  real :: warm_t(3), warm_qi(3), warm_rho(3)
  character(len=16) :: arg
  t0c={T0C:.17e}
  qmin={QMIN:.17e}
  warm_t=[{t_values}]
  warm_qi=[{qi_values}]
  warm_rho=[{rho_values}]
  call get_command_argument(1,arg)
  read(arg,*,iostat=ios) mode
  if (ios /= 0) stop 10
  if (mode == 1) then
    do j=1,3
      t(1)=warm_t(j); qi(1)=warm_qi(j); rho(1)=warm_rho(j)
      call one()
    enddo
    t(1)=t0c; qi(1)=warm_qi(2); rho(1)=warm_rho(2)
    call one()
  else if (mode == 2) then
    do j=1,3
      qi(1)=warm_qi(2); rho(1)=warm_rho(2)
      select case(j)
      case(1); t(1)=t0c-0.001
      case(2); t(1)=t0c-10.0
      case(3); t(1)=t0c-40.0
      end select
      call one()
    enddo
  else if (mode == 3) then
    t(1)=warm_t(1); qi(1)=warm_qi(1); rho(1)=warm_rho(1)
    call one()
  else
    stop 11
  endif
contains
  subroutine one()
    qc=0.; qs=0.; nc=0.; rc=0.; ri=0.; rs=0.
    call udm_mp_effective_radius(t,qc,qi,qs,rho,qmin,t0c,nc,rc,ri,rs,1,1,1,1)
    bits=transfer(ri(1),bits)
    write(*,'(I0,1X,ES24.16E3)') bits,ri(1)
  end subroutine one
end program exercise_radius
"""


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=False)


def compile_fixture(compiler: str, work: Path, label: str, routine: str,
                    optimization: str, *, trap: bool) -> dict[str, Any]:
    source = work / f"{label}.f90"
    executable = work / label
    source.write_text(make_program(routine))
    command = [compiler, optimization, "-g", "-fbacktrace", "-ffree-form",
               "-ffree-line-length-none", "-fcheck=all"]
    if trap:
        command.append("-ffpe-trap=invalid")
    command.extend([str(source), "-o", str(executable)])
    result = run(command, work)
    record = {"command": command, "returncode": result.returncode,
              "stdout": result.stdout, "stderr": result.stderr,
              "source_sha256": sha256(source), "executable": str(executable)}
    if result.returncode:
        raise RuntimeError(f"compile failed for {label}: {result.stderr}")
    return record


def execute(executable: Path, mode: int, cwd: Path) -> dict[str, Any]:
    command = [str(executable), str(mode)]
    result = run(command, cwd)
    return {"command": command, "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr}


def check_output(result: dict[str, Any], expected_count: int) -> list[tuple[int, float]]:
    if result["returncode"] != 0:
        raise RuntimeError(f"fixture execution failed: {result}")
    parsed = []
    for line in result["stdout"].splitlines():
        fields = line.split()
        if len(fields) != 2:
            raise RuntimeError(f"unexpected fixture output line: {line!r}")
        parsed.append((int(fields[0]), float(fields[1])))
    if len(parsed) != expected_count or not all(math.isfinite(r) for _, r in parsed):
        raise RuntimeError(f"invalid output row count/finiteness: {parsed}")
    return parsed


def run_suite(wrf: Path, work: Path, compiler: str) -> dict[str, Any]:
    source = wrf / "phys/module_mp_udm.F"
    if not source.is_file():
        raise RuntimeError(f"not a WRF root: {wrf}")
    actual_routine = extract_routine(source)
    old_routine = actual_routine.replace(GUARDED, ORIGINAL, 1)
    if old_routine.replace(ORIGINAL, GUARDED, 1) != actual_routine:
        raise RuntimeError("old control differs from the source only at the endpoint expression")

    builds: dict[str, Any] = {}
    executions: dict[str, Any] = {}
    for opt in ("-O0", "-O2"):
        key = opt[1:]
        builds[f"patched_{key}"] = compile_fixture(compiler, work, f"patched_{key}", actual_routine,
                                                    opt, trap=True)
        builds[f"old_{key}"] = compile_fixture(compiler, work, f"old_{key}", old_routine,
                                                 opt, trap=False)
        executions[f"patched_warm_{key}"] = execute(Path(builds[f"patched_{key}"]["executable"]), 1, work)
        executions[f"patched_cold_{key}"] = execute(Path(builds[f"patched_{key}"]["executable"]), 2, work)
        executions[f"old_cold_{key}"] = execute(Path(builds[f"old_{key}"]["executable"]), 2, work)
        warm = check_output(executions[f"patched_warm_{key}"], 4)
        if not all(5.01e-6 <= radius <= 125.e-6 for _, radius in warm):
            raise RuntimeError(f"patched {opt} warm endpoint outside clamp: {warm}")
        if len({bits for bits, _ in warm}) != 1 or any(abs(r - 103.4832e-6) > 2e-11 for _, r in warm):
            raise RuntimeError(f"patched {opt} warm endpoint differs from finite T0C value: {warm}")
        cold_new = check_output(executions[f"patched_cold_{key}"], 3)
        cold_old = check_output(executions[f"old_cold_{key}"], 3)
        if [bits for bits, _ in cold_new] != [bits for bits, _ in cold_old]:
            raise RuntimeError(f"cold output bits changed at {opt}: new={cold_new}, old={cold_old}")

    builds["old_trapped_O0"] = compile_fixture(compiler, work, "old_trapped_O0", old_routine,
                                                "-O0", trap=True)
    executions["old_trapped_warm"] = execute(
        Path(builds["old_trapped_O0"]["executable"]), 3, work)
    trap = executions["old_trapped_warm"]
    if trap["returncode"] != -signal.SIGFPE:
        raise RuntimeError(f"old warm control did not terminate with SIGFPE: {trap}")
    if not re.search(r"udm_mp_effective_radius", trap["stderr"], re.IGNORECASE):
        raise RuntimeError(f"SIGFPE backtrace did not identify effective-radius routine: {trap}")
    frame = re.search(r"old_trapped_O0\.f90:(\d+)", trap["stderr"])
    if not frame:
        raise RuntimeError(f"SIGFPE backtrace did not include the scratch source line: {trap}")
    trap_line = int(frame.group(1))
    generated_lines = make_program(old_routine).splitlines()
    if (trap_line < 1 or trap_line > len(generated_lines)
            or "sqrt(temp)" not in generated_lines[trap_line - 1]):
        raise RuntimeError(f"SIGFPE did not originate on the unguarded sqrt(temp) expression: {trap}")

    return {
        "status": "PASS",
        "scope": "Standalone source-extracted native radius routine only; no WRF build or model.",
        "source": {"path": str(source), "sha256": sha256(source),
                   "routine_sha256": hashlib.sha256(actual_routine.encode()).hexdigest()},
        "fixture": {"originating_reproduction_result_sha256": WARM_REPRO_RESULT_SHA256,
                    "warm_packet_sha256": WARM_PACKET_SHA256, "qmin": QMIN,
                    "t0c_k": T0C, "warm_rows": WARM_ROWS,
                    "fixture_test_sha256": sha256(Path(__file__).resolve())},
        "compiler": compiler,
        "builds": builds,
        "executions": executions,
        "checks": {
            "patched_O0_O2_invalid_trap_warm_endpoint": "finite; matches T=T0C at 103.4832 um",
            "cold_guard_effect": "bitwise identical at O0 and O2",
            "unguarded_warm_negative_control": "SIGFPE on sqrt(temp) source line in udm_mp_effective_radius",
        },
        "counts": {"standalone_compiles": len(builds), "standalone_runs": len(executions),
                   "wrf_builds": 0, "wrf_models": 0},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wrf-root", type=Path, default=Path(__file__).resolve().parents[2],
                        help="WRF source root (default: inferred from this test file)")
    parser.add_argument("--workdir", type=Path, help="retain isolated fixture sources and executables")
    parser.add_argument("--output", type=Path, help="write JSON receipt; refuses to overwrite")
    parser.add_argument("--compiler", default=shutil.which("gfortran") or "gfortran")
    args = parser.parse_args()
    wrf = args.wrf_root.resolve()
    if args.output and args.output.exists():
        parser.error(f"refusing to overwrite existing receipt: {args.output}")
    cleanup = None
    if args.workdir:
        work = args.workdir.resolve()
        work.mkdir(parents=True, exist_ok=True)
    else:
        cleanup = tempfile.TemporaryDirectory(prefix="udm-warm-ice-radius-")
        work = Path(cleanup.name)
    started = time.time()
    try:
        receipt = run_suite(wrf, work, args.compiler)
        receipt["elapsed_seconds"] = time.time() - started
        receipt["workdir"] = str(work) if args.workdir else None
        print(json.dumps(receipt, indent=2, sort_keys=True))
        if args.output:
            output = args.output.resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x") as stream:
                json.dump(receipt, stream, indent=2, sort_keys=True)
                stream.write("\n")
        return 0
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc),
                          "wrf_root": str(wrf), "workdir": str(work)}, indent=2))
        return 1
    finally:
        if cleanup is not None:
            cleanup.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
