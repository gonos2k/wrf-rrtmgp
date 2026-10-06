#!/usr/bin/env python3
"""Source contract and real SFCLAY USTM recurrence regression.

This test is intentionally narrow: it compiles the repository's actual
module_sf_sfclay.F under EM_CORE=1 and checks its USTM INOUT recurrence. It
also checks the exact wrapper branches that feed that routine and all four
fractional-ice QZ0 blends. The test does not run WRF or claim that an absent
optional USTM argument is supported by the full EM_CORE SFCLAY entry point.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def section(text: str, start: str, end: str) -> str:
    lo = text.lower().index(start.lower())
    hi = text.lower().index(end.lower(), lo + len(start))
    return text[lo:hi]


def compile_sfclay_probe(compiler: str, source: Path, scratch: Path) -> dict:
    probe = scratch / "sfclay_ustm_probe.f90"
    probe.write_text(PROBE_FORTRAN)
    obj = scratch / "module_sf_sfclay.o"
    exe = scratch / "sfclay_ustm_probe"
    compile_module = [compiler, "-cpp", "-DEM_CORE=1", "-ffree-form",
                      "-finit-real=snan", "-fcheck=all", "-c", str(source),
                      "-o", str(obj)]
    subprocess.run(compile_module, check=True, cwd=scratch, capture_output=True, text=True)
    link = subprocess.run([compiler, "-finit-real=snan", "-fcheck=all", str(probe),
                           str(obj), "-o", str(exe)], cwd=scratch,
                          capture_output=True, text=True)
    if link.returncode:
        raise RuntimeError(f"SFCLAY probe link failed:\n{link.stderr}")
    run = subprocess.run([str(exe)], check=True, cwd=scratch, capture_output=True, text=True)
    values = [float(x) for x in run.stdout.split()]
    if len(values) != 3 or not all(math.isfinite(v) for v in values):
        raise AssertionError(f"unexpected real SFCLAY probe output: {run.stdout!r}")
    # Same atmospheric state means the production INOUT update differs only
    # by half the initial-state difference. Third value is a repeated call.
    if abs((values[1] - values[0]) - 0.2) > 2e-6 or abs(values[2] - values[1]) > 2e-7:
        raise AssertionError(f"SFCLAY recurrence did not settle deterministically: {values}")
    return {"updated_ustm_from_0_1": values[0], "updated_ustm_from_0_5": values[1],
            "repeated_ustm_from_0_5": values[2],
            "actual_source_probe_stdout": run.stdout.strip()}


def compile_extracted_sequence_probe(compiler: str, scratch: Path, active_wrapper: str,
                                     qz_block: str, recurrence: str,
                                     blend_guard: str, ustm_blend: str,
                                     ice_guard: str, threshold: float,
                                     expect_fixed: bool = True) -> dict:
    """Execute wrapper-state statements copied verbatim from the source."""
    snap = next((m for m in re.finditer(r"IF\s*\(\s*PRESENT\(USTM\)\s*\)\s*THEN.*?ENDIF",
                                        active_wrapper, re.I | re.S)
                if re.search(r"USTM_HOLD\(its:ite,jts:jte\)\s*=\s*USTM\(its:ite,jts:jte\)",
                             m.group(0), re.I)), None)
    restore = re.search(r"USTM_SEA\(its:ite,jts:jte\)\s*=\s*USTM_HOLD\(its:ite,jts:jte\)",
                        active_wrapper, re.I)
    if expect_fixed and (not snap or not restore):
        raise AssertionError("could not extract wrapper snapshot/restore statements")
    snapshot_code = snap.group(0) if snap else "! baseline has no USTM snapshot"
    restore_code = (restore.group(0) if restore else
                    "USTM_SEA(1,1)=ieee_value(0.0,ieee_quiet_nan) ! poison for undefined baseline local")
    qz_match = re.search(r"IF\s*\(\s*myj\s*\)\s*THEN\s*\n\s*qz0\(i,j\).*?\n\s*ENDIF",
                         qz_block, re.I | re.S) if expect_fixed else None
    if expect_fixed and not qz_match:
        raise AssertionError("could not extract guarded production QZ0 blend")
    if qz_match:
        qz_code = qz_match.group(0)
    else:
        expr = re.search(r"qz0\(i,j\)\s*=.*?qz0_sea\(i,j\)\s*\)", qz_block,
                         re.I | re.S)
        if not expr:
            raise AssertionError("could not extract baseline QZ0 blend")
        qz_code = expr.group(0)
    code = EXTRACTED_FORTRAN.replace("@SNAPSHOT@", snapshot_code)
    code = code.replace("@RESTORE@", restore_code)
    code = code.replace("@BLEND_GUARD@", blend_guard)
    code = code.replace("@USTM_BLEND@", ustm_blend)
    code = code.replace("@ICE_GUARD@", ice_guard)
    code = code.replace("@XICE_THRESHOLD@", repr(threshold))
    code = code.replace("@QZ_BLEND@", qz_code)
    code = code.replace("@USTM_RECURRENCE@", recurrence)
    source = scratch / "extracted_wrapper_probe.f90"
    source.write_text(code)
    exe = scratch / "extracted_wrapper_probe"
    built = subprocess.run([compiler, "-finit-real=snan", "-fcheck=all", str(source), "-o", str(exe)],
                           cwd=scratch, capture_output=True, text=True)
    if built.returncode:
        raise RuntimeError(f"extracted wrapper probe compile failed:\n{built.stderr}")
    run = subprocess.run([str(exe)], cwd=scratch, capture_output=True, text=True)
    if run.returncode:
        raise RuntimeError(f"extracted wrapper probe failed:\n{run.stderr}")
    values = [float(x) for x in run.stdout.split()]
    if len(values) != 8:
        raise AssertionError(f"unexpected extracted probe output: {run.stdout!r}")
    if expect_fixed and not all(math.isfinite(v) for v in values):
        raise AssertionError(f"patched extracted source produced a non-finite value: {values}")
    partial, full, clear, repeat, no_optional, q0, qmid, qfull = values
    if expect_fixed:
        expected = [0.25, 0.25, 0.25, 0.325, 0.0, 0.006, 0.00795, 0.006]
        for got, want in zip(values, expected):
            if abs(got - want) > 2e-6:
                raise AssertionError(f"extracted source branch mismatch: got {values}, wanted {expected}")
    elif not (math.isnan(values[0]) and math.isnan(values[1]) and math.isfinite(values[2])
              and math.isnan(values[5])):
        raise AssertionError(f"unfixed-source control did not expose both undefined reads: {values}")
    def json_value(v: float):
        return v if math.isfinite(v) else "NaN"
    return {"control": "patched" if expect_fixed else "unfixed-source-derived-sentinel-control",
            "partial_ice": json_value(partial), "full_ice": json_value(full),
            "no_ice": json_value(clear), "optional_ustm_absent_wrapper_scratch": json_value(no_optional),
            "repeated_step": json_value(repeat), "myj_false_qz0_unchanged": json_value(q0),
            "myj_true_qz0_partial_weight": json_value(qmid), "myj_true_qz0_full_ice": json_value(qfull),
            "nan_flags": {"partial_ice": math.isnan(partial), "full_ice": math.isnan(full),
                          "myj_false_qz0": math.isnan(q0)},
            "actual_extracted_code": run.stdout.strip()}


PROBE_FORTRAN = r"""program sfclay_ustm_probe
  use module_sf_sfclay, only: sfclay1d, sfclayinit
  implicit none
  real :: ux(1), vx(1), t1(1), qv(1), p1(1), dz(1), dx(1), psfc(1)
  real :: chs(1), chs2(1), cqs2(1), cpm(1), pblh(1), rmol(1), znt(1), ust(1)
  real :: mavail(1), zol(1), mol(1), regime(1), psim(1), psih(1), fm(1), fh(1)
  real :: xland(1), hfx(1), qfx(1), tsk(1), u10(1), v10(1), th2(1), t2(1), q2(1)
  real :: flhc(1), flqc(1), qgh(1), qsfc(1), lh(1), gz(1), wspd(1), br(1)
  real :: lakemask(1), ustm(1), ck(1), cka(1), cd(1), cda(1)
  real :: a, b, again, partial, full, clear, partial_repeat
  real, parameter :: cp=1004., g=9.81, rovcp=0.286, r=287., xlv=2.5e6
  real, parameter :: svp1=0.6112, svp2=17.67, svp3=29.65, svpt0=273.15
  real, parameter :: ep1=0.608, ep2=0.622, karman=0.4, eomeg=7.292e-5, stb=5.67e-8
  real, parameter :: p1000=100000.
  integer, parameter :: one=1
  call sfclayinit(.false.)
  call run_once(0.1, a)
  call run_once(0.5, b)
  call run_once(0.5, again)
  write(*,'(3(ES24.16,1X))') a, b, again
contains
  subroutine run_once(start_ustm, result)
    real, intent(in) :: start_ustm
    real, intent(out) :: result
    ux=3.; vx=1.; t1=280.; qv=0.005; p1=90000.; dz=20.; dx=10000.; psfc=100000.
    chs=0.01; chs2=0.01; cqs2=0.01; cpm=1004.; pblh=500.; rmol=0.01
    znt=0.1; ust=0.2; mavail=1.; zol=0.01; mol=0.01; regime=0.
    psim=0.; psih=0.; fm=0.; fh=0.; xland=2.; hfx=0.; qfx=0.; tsk=280.
    u10=0.; v10=0.; th2=280.; t2=280.; q2=0.005; flhc=0.; flqc=0.
    qgh=0.; qsfc=0.005; lh=0.; gz=0.; wspd=3.; br=0.; lakemask=0.
    ustm=start_ustm; ck=0.; cka=0.; cd=0.; cda=0.
    call sfclay1d(j=1,ux=ux,vx=vx,t1d=t1,qv1d=qv,p1d=p1,dz8w1d=dz, &
      cp=cp,g=g,rovcp=rovcp,r=r,xlv=xlv,psfcpa=psfc,chs=chs,chs2=chs2, &
      cqs2=cqs2,cpm=cpm,pblh=pblh,rmol=rmol,znt=znt,ust=ust,mavail=mavail, &
      zol=zol,mol=mol,regime=regime,psim=psim,psih=psih,fm=fm,fh=fh, &
      xland=xland,hfx=hfx,qfx=qfx,tsk=tsk,u10=u10,v10=v10,th2=th2,t2=t2, &
      q2=q2,flhc=flhc,flqc=flqc,qgh=qgh,qsfc=qsfc,lh=lh,gz1oz0=gz, &
      wspd=wspd,br=br,isfflx=1,dx=dx,svp1=svp1,svp2=svp2,svp3=svp3, &
      svpt0=svpt0,ep1=ep1,ep2=ep2,karman=karman,eomeg=eomeg,stbolt=stb, &
      p1000mb=p1000,lakemask=lakemask,ids=1,ide=1,jds=1,jde=1,kds=1,kde=1, &
      ims=1,ime=1,jms=1,jme=1,kms=1,kme=1,its=1,ite=1,jts=1,jte=1, &
      kts=1,kte=1,isftcflx=1,iz0tlnd=1,scm_force_flux=0,ustm=ustm, &
      ck=ck,cka=cka,cd=cd,cda=cda)
    result=ustm(1)
  end subroutine run_once
end program sfclay_ustm_probe
"""


EXTRACTED_FORTRAN = r"""program extracted_wrapper_probe
  use, intrinsic :: ieee_arithmetic
  implicit none
  real :: partial, full, clear, repeat, no_optional, q0, qmid, qfull, wrapper_ustm(1,1)
  real :: XICE(1,1), XICE_THRESHOLD
  integer :: i,j
  i=1;j=1;XICE_THRESHOLD=@XICE_THRESHOLD@
  call wrapper_case(0.35,0.1,partial,wrapper_ustm)
  call wrapper_case(1.0,0.1,full,wrapper_ustm)
  call wrapper_case(0.0,0.1,clear,wrapper_ustm)
  call wrapper_case(0.35,partial,repeat,wrapper_ustm)
  call wrapper_case(1.0,0.1,no_optional)
  call qz_case(.false.,0.35,q0)
  call qz_case(.true.,0.35,qmid)
  call qz_case(.true.,1.0,qfull)
  write(*,'(8(ES24.16,1X))') partial,full,clear,repeat,no_optional,q0,qmid,qfull
contains
  subroutine wrapper_case(xfraction,initial,result,USTM)
    real,intent(in)::xfraction,initial
    real,intent(out)::result
    real,optional,intent(inout)::USTM(:,:)
    real::USTM_HOLD(1,1),USTM_SEA(1,1)
    integer::ims,ime,jms,jme,its,ite,jts,jte
    ims=1;ime=1;jms=1;jme=1;its=1;ite=1;jts=1;jte=1
    if (present(USTM)) USTM(1,1)=initial
    @SNAPSHOT@
    if (present(USTM)) call surface_update(USTM(1,1))
    @RESTORE@
    call surface_update(USTM_SEA(1,1))
    XICE(1,1)=xfraction
    if (present(USTM)) then
      @BLEND_GUARD@
        @USTM_BLEND@
      endif
      result=USTM(1,1)
    else
      result=0.0
    endif
  end subroutine wrapper_case
  subroutine surface_update(value)
    real,intent(inout)::value
    real::WSPDI(1),PSIX,USTM(1)
    real,parameter::KARMAN=0.4
    integer::I
    I=1;WSPDI(1)=3.0;PSIX=3.0;USTM(1)=value
    @USTM_RECURRENCE@
    value=USTM(1)
  end subroutine surface_update
  subroutine qz_case(myj,xfraction,result)
    logical,intent(in)::myj
    real,intent(in)::xfraction
    real,intent(out)::result
    real::qz0(1,1),qz0_sea(1,1),XICE(1,1)
    real::qnan
    integer::i,j
    i=1;j=1;XICE(1,1)=xfraction;qz0(1,1)=0.006
    qnan=ieee_value(0.0,ieee_quiet_nan)
    if (myj) then
      qz0_sea(1,1)=0.009
    else
      qz0_sea(1,1)=qnan
    endif
    @ICE_GUARD@
      @QZ_BLEND@
    endif
    result=qz0(1,1)
  end subroutine qz_case
end program extracted_wrapper_probe
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    ap.add_argument("--compiler", default="gfortran")
    ap.add_argument("--output-root", type=Path)
    args = ap.parse_args()
    repo = args.repo.resolve()
    surf = repo / "WRF/phys/module_surface_driver.F"
    sfclay = repo / "WRF/phys/module_sf_sfclay.F"
    sfclayrev = repo / "WRF/phys/module_sf_sfclayrev.F"
    text = surf.read_text()
    active = section(text, "SUBROUTINE sfclay_seaice_wrapper(", "END SUBROUTINE sfclay_seaice_wrapper")
    rev = section(text, "SUBROUTINE sfclayrev_seaice_wrapper(", "END SUBROUTINE sfclayrev_seaice_wrapper")

    blend_lines = re.findall(r"qz0\(i,j\)\s*=\s*\(\s*qz0\(i,j\).*?qz0_sea\(i,j\)", text, re.I | re.S)
    guarded_blends = re.findall(r"IF\s*\(\s*myj\s*\)\s*THEN\s*\n\s*qz0\(i,j\)\s*=.*?qz0_sea\(i,j\).*?\n\s*ENDIF", text, re.I | re.S)
    if len(blend_lines) != 4 or len(guarded_blends) != 4:
        raise AssertionError(f"expected four guarded QZ0 blends, found {len(blend_lines)} / {len(guarded_blends)}")
    for name, sub, call in (("SFCLAY", active, "call sfclay("),
                            ("SFCLAYREV", rev, "call sfclayrev(")):
        openpos = sub.lower().index("! open-water call")
        callpos = sub.lower().index(call, openpos)
        pre = sub[:callpos]
        if not re.search(r"ustm_hold\(its:ite,jts:jte\)\s*=\s*ustm\(its:ite,jts:jte\)", pre, re.I):
            raise AssertionError(f"{name} does not snapshot incoming optional USTM")
        if not re.search(r"ustm_sea\(its:ite,jts:jte\)\s*=\s*ustm_hold\(its:ite,jts:jte\)", pre, re.I):
            raise AssertionError(f"{name} open-water USTM is not initialized from the snapshot")
        if not re.search(r"ELSE\s*\n\s*USTM_HOLD\(its:ite,jts:jte\)\s*=\s*0\.0", pre, re.I):
            raise AssertionError(f"{name} does not initialize unused optional-absent scratch")
    # Verify the actual implementations read the INOUT value before writing it.
    sftext = sfclay.read_text()
    revtext = sfclayrev.read_text()
    if not re.search(r"USTM\(I\)\s*=\s*0\.5\s*\*\s*USTM\(I\).*?WSPDI\(I\)\s*/\s*PSIX", sftext, re.I):
        raise AssertionError("real SFCLAY USTM recurrence changed; review test assumptions")
    if not re.search(r"USTM_HV\s*\(\s*i\s*\)\s*=\s*USTM\s*\(\s*i\s*,\s*j\s*\).*?USTM\s*\(\s*i\s*,\s*j\s*\)\s*=\s*USTM_HV", revtext, re.I | re.S):
        raise AssertionError("real SFCLAYREV USTM read/write sequence changed; review test assumptions")
    recurrence = re.search(r"^\s*USTM\s*\(I\)\s*=.*WSPDI\(I\)\s*/\s*PSIX\s*$", sftext, re.I | re.M)
    if not recurrence:
        raise AssertionError("could not extract the actual SFCLAY USTM update")
    blend_guard_match = re.search(r"^\s*IF\s*\(\s*\(\s*XICE\(I,J\)\s*\.GE\.\s*XICE_THRESHOLD.*?THEN\s*$",
                                  active, re.I | re.M)
    ustm_blend_match = re.search(r"IF\s*\(\s*PRESENT\s*\(\s*USTM\s*\)\s*\)\s*THEN\s*"
                                 r"USTM\(i,j\)\s*=.*?ENDIF", active, re.I | re.S)
    if not blend_guard_match or not ustm_blend_match:
        raise AssertionError("could not extract wrapper sea-ice guard and USTM weighted blend")
    qz_ifpos = re.search(r"IF\s*\(\s*myj\s*\)\s*THEN\s*\n\s*qz0\(i,j\)", text, re.I)
    ice_candidates = list(re.finditer(r"^\s*IF\s*\(\s*\(\s*XICE\(I,J\).*?XICE\(i,j\).*?\.LE\.\s*1\.0.*?THEN\s*$",
                                      text, re.I | re.M))
    qz_ice_guard = next((m for m in reversed(ice_candidates) if qz_ifpos and m.start() < qz_ifpos.start()), None)
    if not qz_ice_guard:
        raise AssertionError("could not extract outer production fractional-ice QZ0 guard")
    threshold_match = re.search(r"ELSE\s+IF\s*\(\s*fractional_seaice\s*==\s*1\s*\)\s*THEN\s*"
                                r"xice_threshold\s*=\s*([0-9.]+)", text, re.I)
    if not threshold_match:
        raise AssertionError("could not extract fractional_seaice=1 threshold")
    threshold = float(threshold_match.group(1))

    local_tmp = repo / "build"
    local_tmp.mkdir(exist_ok=True)
    # A deterministic pre-fix negative control is derived from this exact
    # source: remove only the snapshot/restore and MYJ guard just added above.
    baseline_active = active
    snapshot_pattern = (r"IF\s*\(\s*PRESENT\(USTM\)\s*\)\s*THEN\s*"
                        r"USTM_HOLD\(its:ite,jts:jte\)\s*=\s*USTM\(its:ite,jts:jte\)\s*"
                        r"ELSE\s*USTM_HOLD\(its:ite,jts:jte\)\s*=\s*0\.0\s*ENDIF")
    baseline_active = re.sub(snapshot_pattern, "", baseline_active, count=1, flags=re.I)
    baseline_active = re.sub(r"USTM_SEA\(its:ite,jts:jte\)\s*=\s*USTM_HOLD\(its:ite,jts:jte\)",
                             "", baseline_active, count=1, flags=re.I)
    baseline_qz = re.sub(r"^\s*IF\s*\(\s*myj\s*\)\s*THEN\s*|\s*ENDIF\s*$", "",
                         guarded_blends[0], flags=re.I | re.M)
    with tempfile.TemporaryDirectory(prefix="fractional-seaice-", dir=local_tmp) as temp:
        scratch = Path(temp)
        probe = compile_sfclay_probe(args.compiler, sfclay, scratch)
        extracted = compile_extracted_sequence_probe(args.compiler, scratch, active, text,
                                                      recurrence.group(0).strip(),
                                                      blend_guard_match.group(0).strip(),
                                                      ustm_blend_match.group(0).strip(),
                                                      qz_ice_guard.group(0).strip(), threshold)
        original_control = compile_extracted_sequence_probe(args.compiler, scratch,
                                                             baseline_active, baseline_qz,
                                                             recurrence.group(0).strip(),
                                                             blend_guard_match.group(0).strip(),
                                                             ustm_blend_match.group(0).strip(),
                                                             qz_ice_guard.group(0).strip(),
                                                             threshold,
                                                             expect_fixed=False)
    result = {
        "status": "PASS",
        "scope": "four MYJ-only QZ0 blends guarded; both wrappers initialize open-water USTM input; actual SFCLAY1D INOUT recurrence compiled and exercised",
        "optional_ustm_absence": "wrapper scratch is deterministic, but full EM_CORE SFCLAY optional-absent entry is not claimed supported because the entry forwards USTM(ims,j) unguarded",
        "sfclayrev_scope": "same INOUT scratch defect guarded in wrapper; only SFCLAY1 is evidenced as active in the winter run",
        "source_sha256": {str(p.relative_to(repo)): digest(p) for p in (surf, sfclay, sfclayrev)},
        "qz0_blend_sites": len(guarded_blends),
        "sfclay_probe": probe,
        "source_extracted_wrapper_probe": extracted,
        "unfixed_source_negative_control": original_control,
    }
    outroot = args.output_root.resolve() if args.output_root else None
    if outroot:
        outroot.mkdir(parents=True, exist_ok=True)
        (outroot / "source-test-receipt.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
