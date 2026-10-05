#!/usr/bin/env python3
"""Exercise the opt-in source tap in the actual legacy RRTMG LW solver.

This is a small standalone column fixture, not a reference-accuracy test.  It
extracts the production modules and initialization expressions verbatim from
module_ra_rrtmg_lw.F and the writer module from module_ra_rrtmgp_audit.F.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

EXPORT_PREFIX = "WRF_RRTMGP_RRTMG4_EXPORT_"
SOURCE_FLAG = "WRF_RRTMGP_RRTMG4_EXPORT_LW_SOURCE"


def module_block(text: str, name: str) -> str:
    match = re.search(
        rf"(?ims)^\s*module\s+{re.escape(name)}\s*$.*?^\s*end\s+module\s+{re.escape(name)}\s*$",
        text,
    )
    if not match:
        raise AssertionError(f"Could not extract production module {name}")
    return match.group(0)


def assignment_block(text: str, name: str) -> str:
    lines = text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if re.match(rf"\s*{re.escape(name)}\s*\(:\)\s*=", line, re.I)),
        None,
    )
    if start is None:
        raise AssertionError(f"Could not find source assignment for {name}")
    out = [lines[start]]
    while "/)" not in out[-1]:
        start += 1
        if start >= len(lines):
            raise AssertionError(f"Unterminated source assignment for {name}")
        out.append(lines[start])
    return "\n".join(out)


def source_fixture(source: str, audit: str) -> str:
    blocks = [
        module_block(source, name)
        for name in ("parkind", "parrrtm", "rrlw_con", "rrlw_tbl", "rrlw_vsn", "rrlw_wvn", "rrtmg_lw_rtrnmc")
    ]
    marker = "MODULE module_rrtmg4_optics_export\n"
    if marker not in audit:
        raise AssertionError("Actual exporter module marker missing")
    exporter = marker + audit.split(marker, 1)[1].split("END MODULE module_rrtmg4_optics_export", 1)[0]
    exporter += "END MODULE module_rrtmg4_optics_export\n"

    # These assignments are copied from the real initialization routines.
    lwdat = source.split("subroutine lwdatinit(cpdair)", 1)[1].split("end subroutine lwdatinit", 1)[0]
    cmbdat = source.split("subroutine lwcmbdat", 1)[1].split("end subroutine lwcmbdat", 1)[0]
    spectral_init = "\n".join(
        [assignment_block(lwdat, "delwave"), assignment_block(cmbdat, "ngc"),
         assignment_block(cmbdat, "ngs"), assignment_block(cmbdat, "ngb")]
    )
    table_init = source.split("tau_tbl(0) = 0.0_rb", 1)[1].split("      enddo", 1)[0]
    table_init = "      tau_tbl(0) = 0.0_rb" + table_init + "      enddo\n"

    return "\n".join(blocks[:6]) + "\n" + exporter + "\n" + blocks[6] + "\n" + DRIVER.replace(
        "!SOURCE_SPECTRAL_INIT!", spectral_init
    ).replace("!SOURCE_TABLE_INIT!", table_init)


DRIVER = r'''program source_export_fixture
  use parkind, only: rb=>kind_rb
  use parrrtm, only: nbndlw,ngptlw
  use rrlw_con, only: fluxfac,heatfac,grav,secdy,pi
  use rrlw_tbl, only: ntbl,tau_tbl,exp_tbl,tfn_tbl,bpade,pade,tblint
  use rrlw_wvn, only: ngc,ngs,ngb,delwave
  use rrlw_vsn, only: hvrrtc,hnamrtc
  use rrtmg_lw_rtrnmc, only: rtrnmc
  use module_rrtmg4_optics_export
  implicit none
  integer, parameter :: nl=3
  integer :: g,b,l,itr,ios
  real(kind=rb) :: tfn,expeps,cpdair
  real(kind=rb) :: pz(0:nl),semiss(nbndlw),cldfmc(ngptlw,nl),taucmc(ngptlw,nl)
  real(kind=rb) :: planklay(nl,nbndlw),planklev(0:nl,nbndlw),plankbnd(nbndlw)
  real(kind=rb) :: fracs(nl,ngptlw),taut(nl,ngptlw)
  real(kind=rb) :: up0(0:nl),dn0(0:nl),net0(0:nl),hr0(0:nl)
  real(kind=rb) :: cup0(0:nl),cdn0(0:nl),cnet0(0:nl),chr0(0:nl)
  real(kind=rb) :: up1(0:nl),dn1(0:nl),net1(0:nl),hr1(0:nl)
  real(kind=rb) :: cup1(0:nl),cdn1(0:nl),cnet1(0:nl),chr1(0:nl)
  integer(kind=kind(1.0)) :: bits0(8*(nl+1)),bits1(8*(nl+1))
  character(1024) :: output_path
  integer :: output_unit

  ! Exact production spectral interval mapping and widths.
!SOURCE_SPECTRAL_INIT!
  ! Exact production RRTMG lookup-table initialization, with its source values.
  expeps=1.e-20_rb
!SOURCE_TABLE_INIT!
  ! Same conversion expressions as lwdatinit(cpdair), with its documented
  ! dry-air heat capacity supplied as the fixture input.
  grav=9.8066_rb
  secdy=8.6400e4_rb
  pi=2._rb*asin(1._rb)
  fluxfac=pi*2.e4_rb
  cpdair=1004.64_rb
  heatfac=grav*secdy/(cpdair*1.e2_rb)
  hvrrtc='test fixture'; hnamrtc='source tap fixture'

  pz=[1000._rb,700._rb,350._rb,100._rb]
  do b=1,nbndlw
    semiss(b)=0.72_rb+0.015_rb*real(mod(b,16),rb)
    plankbnd(b)=0.31_rb+0.009_rb*real(b,rb)
    do l=1,nl
      planklay(l,b)=0.18_rb+0.012_rb*real(l,rb)+0.004_rb*real(b,rb)
    enddo
    do l=0,nl
      planklev(l,b)=0.14_rb+0.017_rb*real(l,rb)+0.003_rb*real(b,rb)
    enddo
  enddo
  do g=1,ngptlw
    do l=1,nl
      fracs(l,g)=1._rb/real(count(ngb==ngb(g)),rb)
      taut(l,g)=0.004_rb+0.00017_rb*real(g,rb)+0.006_rb*real(l,rb)
      cldfmc(g,l)=0._rb
      taucmc(g,l)=0._rb
    enddo
  enddo
  ! A deterministic cloudy sample exercises the independent all-sky and
  ! clear-sky recurrences as well as layer emission and surface reflection.
  do g=1,ngptlw,11
    cldfmc(g,2)=1._rb
    taucmc(g,2)=0.11_rb+0.002_rb*real(g,rb)
  enddo

  call rtrnmc(nl,1,nbndlw,0,pz,semiss,nbndlw,cldfmc,taucmc, &
       planklay,planklev,plankbnd,1.2_rb,fracs,taut, &
       up0,dn0,net0,hr0,cup0,cdn0,cnet0,chr0)

  call rrtmg4_export_begin('lw',1,2161,129600._rb,24,55)
  if (.not.rrtmg4_export_active()) stop 21
  call rrtmg4_export_stage('INPUT')
  call rrtmg4_export_real1('FIXTURE_LEVEL_PRESSURE','hPa',pz)
  call rrtmg4_export_stage('CLOUD')
  call rrtmg4_export_real2('FIXTURE_CLOUD_FRACTION','1',transpose(cldfmc))
  call rrtmg4_export_stage('GAS')
  call rtrnmc(nl,1,nbndlw,0,pz,semiss,nbndlw,cldfmc,taucmc, &
       planklay,planklev,plankbnd,1.2_rb,fracs,taut, &
       up1,dn1,net1,hr1,cup1,cdn1,cnet1,chr1, &
       source_export=rrtmg4_export_lw_source_active())
  call rrtmg4_export_stage('RESULT')
  call rrtmg4_export_real1('FIXTURE_TOTAL_UP','W_m-2',up1)
  call rrtmg4_export_real1('FIXTURE_TOTAL_DOWN','W_m-2',dn1)
  call rrtmg4_export_real1('FIXTURE_CLEAR_UP','W_m-2',cup1)
  call rrtmg4_export_real1('FIXTURE_CLEAR_DOWN','W_m-2',cdn1)
  call rrtmg4_export_real1('FIXTURE_HEATING','K_day-1',hr1)
  call rrtmg4_export_real1('FIXTURE_CLEAR_HEATING','K_day-1',chr1)
  call rrtmg4_export_end()

  bits0=transfer([up0,dn0,net0,hr0,cup0,cdn0,cnet0,chr0],bits0)
  bits1=transfer([up1,dn1,net1,hr1,cup1,cdn1,cnet1,chr1],bits1)
  if(any(bits0/=bits1)) stop 22
  call get_environment_variable('RRTMG4_FIXTURE_NUMERICS',output_path,status=ios)
  if(ios/=0.or.len_trim(output_path)==0) stop 23
  open(newunit=output_unit,file=trim(output_path),status='replace',access='stream',form='unformatted')
  write(output_unit) up1,dn1,net1,hr1,cup1,cdn1,cnet1,chr1
  close(output_unit)
end program source_export_fixture

subroutine wrf_error_fatal(message)
  character(*),intent(in) :: message
  write(*,'(A)') trim(message)
  stop 17
end subroutine wrf_error_fatal
'''


def read_capture(path: Path) -> tuple[dict[str, tuple[str, tuple[int, ...], list[float]]], list[str], dict[str, str]]:
    lines = path.read_text().splitlines()
    if not lines or lines[0] != "RRTMG4_SELECTED_COLUMN_EXPORT_V1":
        raise AssertionError("unexpected exporter header")
    stages: list[str] = []
    field_stages: dict[str, str] = {}
    fields: dict[str, tuple[str, tuple[int, ...], list[float]]] = {}
    current_stage = ""
    i = 1
    while i < len(lines):
        row = lines[i].split()
        i += 1
        if not row:
            continue
        if row[0] == "stage":
            stages.append(row[1])
            current_stage = row[1]
            continue
        if row[0] in {"phase", "domain", "step", "source_seconds", "i", "j", "layout"}:
            continue
        if len(row) < 3:
            continue
        name, units = row[0], row[1]
        dims = tuple(int(x) for x in row[2:])
        if name in fields:
            raise AssertionError(f"duplicate exported field {name}")
        field_stages[name] = current_stage
        if i >= len(lines):
            raise AssertionError(f"missing values for {name}")
        vals = [float(x) for x in lines[i].split()]
        i += 1
        expected = 1
        for d in dims:
            expected *= d
        if len(vals) != expected:
            raise AssertionError(f"{name}: expected {expected} values, got {len(vals)}")
        fields[name] = (units, dims, vals)
    return fields, stages, field_stages


def check_reconstruction(fields: dict[str, tuple[str, tuple[int, ...], list[float]]],
                         output_path: Path) -> None:
    import numpy as np

    def field(name: str):
        units, dims, values = fields[name]
        return units, np.asarray(values, dtype=np.float64).reshape(dims, order="F")

    delwave = field("RTE_DELWAVE")[1].astype(np.float32)
    fluxfac = np.float32(field("RTE_FLUXFAC")[1][0])
    for raw_name, out_name in (("RTE_BAND_UP_NATIVE", "FIXTURE_TOTAL_UP"),
                               ("RTE_BAND_DN_NATIVE", "FIXTURE_TOTAL_DOWN"),
                               ("RTE_BAND_UP_CLEAR_NATIVE", "FIXTURE_CLEAR_UP"),
                               ("RTE_BAND_DN_CLEAR_NATIVE", "FIXTURE_CLEAR_DOWN")):
        raw = field(raw_name)[1].astype(np.float32)
        target = field(out_name)[1].astype(np.float32)
        rebuilt = np.zeros(raw.shape[1], dtype=np.float32)
        for band in range(raw.shape[0]):
            rebuilt = np.float32(rebuilt + np.float32(raw[band, :] * delwave[band]))
        rebuilt = np.float32(rebuilt * fluxfac)
        scale = np.maximum(np.abs(target), np.float32(1.0))
        if np.any(np.abs(rebuilt-target) > np.float32(4e-6)*scale):
            raise AssertionError(f"{raw_name} does not reconstruct broadband output")

    expected = {
        "RTE_PLANCK_LAYER_NATIVE": ("native_planck", (16, 3)),
        "RTE_PLANCK_LEVEL_NATIVE": ("native_planck", (16, 4)),
        "RTE_PLANCK_SURFACE_NATIVE": ("native_planck", (16,)),
        "RTE_PLANCK_FRACTIONS": ("1", (140, 3)),
        "RTE_SECDIFF": ("1", (16,)),
        "RTE_DELWAVE": ("cm-1", (16,)),
        "RTE_BAND_START_END_IOUT": ("1", (3,)),
        "RTE_TABLE_BOUNDS": ("1", (2,)),
        "RTE_TAU_TABLE": ("1", (10001,)),
        "RTE_EXP_TABLE": ("1", (10001,)),
        "RTE_TFN_TABLE": ("1", (10001,)),
        "RTE_BAND_UP_NATIVE": ("native_flux", (16, 4)),
        "RTE_BAND_DN_NATIVE": ("native_flux", (16, 4)),
        "RTE_BAND_UP_CLEAR_NATIVE": ("native_flux", (16, 4)),
        "RTE_BAND_DN_CLEAR_NATIVE": ("native_flux", (16, 4)),
    }
    for name, (units, dims) in expected.items():
        got_units, got_dims, vals = fields[name]
        if (got_units, got_dims) != (units, dims):
            raise AssertionError(f"{name}: {(got_units, got_dims)} != {(units, dims)}")
        if not all(map(__import__("math").isfinite, vals)):
            raise AssertionError(f"nonfinite values in {name}")
    if fields["RTE_TABLE_BOUNDS"][2] != [0.0, 10000.0]:
        raise AssertionError("lookup table bounds were not retained")
    tau_table = np.asarray(fields["RTE_TAU_TABLE"][2], dtype=np.float64)
    exp_table = np.asarray(fields["RTE_EXP_TABLE"][2], dtype=np.float64)
    tfn_table = np.asarray(fields["RTE_TFN_TABLE"][2], dtype=np.float64)
    if tau_table[0] != 0.0 or tau_table[-1] != 1.0e10 or exp_table[0] != 1.0:
        raise AssertionError(f"production lookup table endpoint values were not captured: "
                             f"tau={tau_table[[0,-1]]}, exp={exp_table[[0,-1]]}")
    if exp_table[-1] != float(np.float32(1.0e-20)) or tfn_table[0] != 0.0 or tfn_table[-1] != 1.0:
        raise AssertionError("production lookup table endpoint values were not captured")
    delwave = np.asarray(fields["RTE_DELWAVE"][2])
    if delwave[0] != 340.0 or delwave[-1] != 650.0:
        raise AssertionError("production band widths are not aligned with the capture")
    if fields["RTE_WTDIFF"][2] != [0.5] or \
       fields["RTE_REC_6"][2] != [float(np.float32(0.166667))]:
        raise AssertionError("source recurrence constants do not match the actual invocation")
    fractions = np.asarray(fields["RTE_PLANCK_FRACTIONS"][2]).reshape((140, 3), order="F")
    gpoint_band = np.repeat(np.arange(1, 17), np.diff([0] + [10,22,38,52,68,76,88,96,108,114,122,130,134,136,138,140]).tolist())
    for band in range(1, 17):
        if not np.allclose(fractions[gpoint_band == band, :].sum(axis=0), 1.0, rtol=0, atol=2e-7):
            raise AssertionError(f"Planck fractions do not normalize within band {band}")
    if not any(abs(x) > 0 for x in fields["RTE_BAND_UP_NATIVE"][2]):
        raise AssertionError("empty band source data")
    if fields["FIXTURE_TOTAL_UP"][2] == fields["FIXTURE_CLEAR_UP"][2]:
        raise AssertionError("cloudy and clear fixture streams did not separate")
    pz = np.asarray(fields["FIXTURE_LEVEL_PRESSURE"][2], dtype=np.float32)
    net = np.asarray(fields["FIXTURE_TOTAL_UP"][2], dtype=np.float32) - np.asarray(
        fields["FIXTURE_TOTAL_DOWN"][2], dtype=np.float32)
    clear_net = np.asarray(fields["FIXTURE_CLEAR_UP"][2], dtype=np.float32) - np.asarray(
        fields["FIXTURE_CLEAR_DOWN"][2], dtype=np.float32)
    heatfac = np.float32(fields["RTE_HEATFAC"][2][0])
    for flux, heating_name in ((net, "FIXTURE_HEATING"),
                               (clear_net, "FIXTURE_CLEAR_HEATING")):
        expected_hr = np.asarray([
            np.float32(heatfac * np.float32(flux[k] - flux[k + 1]) /
                       np.float32(pz[k] - pz[k + 1])) for k in range(3)
        ] + [0.0], dtype=np.float32)
        actual_hr = np.asarray(fields[heating_name][2], dtype=np.float32)
        if not np.allclose(actual_hr, expected_hr, rtol=3e-6, atol=1e-7):
            raise AssertionError("heating does not follow the production flux/pressure relation")
    if output_path.stat().st_size == 0:
        raise AssertionError("empty numerical output receipt")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fc", default="gfortran")
    ap.add_argument("--work-dir", type=Path, default=Path("build/udm37-legacy-lw-source-export-fixture-v1"))
    args = ap.parse_args()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    compiler = shutil.which(args.fc)
    if compiler is None:
        raise SystemExit(f"Fortran compiler unavailable: {args.fc}")
    repo = Path(__file__).resolve().parents[2]
    source_path = repo / "phys/module_ra_rrtmg_lw.F"
    audit_path = repo / "phys/module_ra_rrtmgp_audit.F"
    source = source_path.read_text()
    audit = audit_path.read_text()
    fixture = source_fixture(source, audit)
    result = {"status": "RUNNING", "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
              "audit_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
              "compiler": compiler, "forecast_calls": 0, "radiation_module": "extracted production rtrnmc"}
    version = subprocess.run([compiler, "--version"], text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, check=True).stdout.splitlines()[0]
    result["compiler_version"] = version
    with tempfile.TemporaryDirectory(prefix="legacy-lw-source-export-", dir=work) as td:
        root = Path(td)
        (root / "fixture.F90").write_text(fixture)
        exe = root / "fixture.exe"
        compile_argv = [compiler, "-cpp", "-O0", "-fcheck=all", "-ffree-line-length-none",
                        "fixture.F90", "-o", str(exe)]
        result["compile_argv"] = compile_argv
        result["fixture_source_sha256"] = hashlib.sha256((root / "fixture.F90").read_bytes()).hexdigest()
        build = subprocess.run(compile_argv, cwd=root, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        result["compile_rc"] = build.returncode
        result["compile_output"] = build.stdout
        if build.returncode:
            result["status"] = "BUILD_FAIL"
            (work / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
            raise SystemExit("standalone fixture compile failed; see receipt.json")
        result["executable_sha256"] = hashlib.sha256(exe.read_bytes()).hexdigest()
        runs = []
        clean = {k: v for k, v in os.environ.items() if not k.startswith("WRF_RRTMGP_RRTMG4_EXPORT_")}
        for name, source_flag in (("disabled", None), ("enabled", "1")):
            out = root / name
            out.mkdir()
            numerical = root / f"{name}.bin"
            env = dict(clean)
            env[EXPORT_PREFIX + "DIR"] = str(out)
            if source_flag is not None:
                env[SOURCE_FLAG] = source_flag
            env["RRTMG4_FIXTURE_NUMERICS"] = str(numerical)
            proc = subprocess.run([str(exe)], cwd=root, env=env, text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            runs.append({"name": name, "returncode": proc.returncode, "stdout": proc.stdout,
                         "numerical_sha256": hashlib.sha256(numerical.read_bytes()).hexdigest()
                         if numerical.exists() else None})
            if proc.returncode:
                result.update(status="FIXTURE_FAIL", runs=runs)
                (work / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
                raise SystemExit(f"fixture run {name} failed")
        if runs[0]["numerical_sha256"] != runs[1]["numerical_sha256"]:
            raise AssertionError("observer opt-in changed serialized numerical outputs")
        disabled_files = list((root / "disabled").glob("*.txt"))
        enabled_files = list((root / "enabled").glob("*.txt"))
        if len(disabled_files) != 1 or len(enabled_files) != 1:
            raise AssertionError("expected one exporter file per run")
        disabled_text, enabled_text = disabled_files[0].read_text(), enabled_files[0].read_text()
        if "RTE_BAND_UP_NATIVE" in disabled_text:
            raise AssertionError("source fields appeared when source observation was disabled")
        fields, stages, field_stages = read_capture(enabled_files[0])
        if stages != ["INPUT", "CLOUD", "GAS", "RESULT"]:
            raise AssertionError(f"stage sequence mismatch: {stages}")
        if "RTE_BAND_UP_NATIVE" not in enabled_text or "FIXTURE_TOTAL_UP" not in enabled_text:
            raise AssertionError("source or result records absent from enabled capture")
        if field_stages.get("FIXTURE_LEVEL_PRESSURE") != "INPUT" or \
           field_stages.get("FIXTURE_CLOUD_FRACTION") != "CLOUD" or \
           field_stages.get("RTE_BAND_UP_NATIVE") != "GAS" or \
           field_stages.get("FIXTURE_TOTAL_UP") != "RESULT":
            raise AssertionError("fields were not emitted within the expected export stage")
        check_reconstruction(fields, root / "enabled.bin")
        result.update(status="PASS", runs=runs, stages=stages, enabled_capture_sha256=
                      hashlib.sha256(enabled_files[0].read_bytes()).hexdigest(),
                      disabled_capture_sha256=hashlib.sha256(disabled_files[0].read_bytes()).hexdigest(),
                      enabled_field_count=len(fields), source_record_stage="GAS",
                      field_stage_counts={s: sum(v == s for v in field_stages.values())
                                          for s in stages},
                      meaning="synthetic standalone recurrence invariant; not a line-by-line optical truth reference")
    (work / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
