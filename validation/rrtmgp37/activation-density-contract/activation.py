#!/usr/bin/env python3
"""Portable, source-extracted native UDM CCN activation contract fixture.

This script compiles and executes only the extracted local Fortran block when an
operator invokes it. It never builds WRF or calls RRTMGP. Run with:
  python3 activation.py --source-root PATH --output-dir NEW_PATH [--fc gfortran]
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, pathlib, re, shlex, struct, subprocess, sys

SOURCE_REL = pathlib.Path("WRF/phys/module_mp_udm.F")
EXPECTED_SOURCE_SHA256 = "9b7b878b263f6b0111edba4cfb1c6c30e53b3f7534035cda2c0411a573b81c2c"
EXPECTED_BLOCK_SHA256 = "c26d239d86b964e84e47834a9ce65e4642930f1ac0d67ac9936ca0be823115e2"
EXPECTED_SOURCE_LINES = (2508, 2520)
EXPECTED_PARAMETERS = {
    "satmax": 0.0048,
    "actk": 0.6,
    "actr": 1.5e-6,
    "ccnmin": 50.0e6,
    "ncmin": 1.0e-3,
    "dtcldcr": 180.0,
}
DENSITIES = (0.5, 1.0, 1.5)
DT_SECONDS = 60.0
DEFAULT_REAL_EPS = 2.0 ** -23
OPERATION_EPS_FACTOR = 16.0


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def f32(value: float) -> float:
    return struct.unpack("=f", struct.pack("=f", float(value)))[0]


def ulp32(value: float) -> float:
    """Spacing to the next default-REAL value; state values here are nonnegative."""
    x = f32(value)
    if not math.isfinite(x) or x < 0.0:
        raise ValueError("ULP helper requires a finite nonnegative default-REAL state")
    bits = struct.unpack("=I", struct.pack("=f", x))[0]
    if bits >= 0x7f7fffff:
        raise ValueError("ULP helper reached largest finite default-REAL")
    return float(struct.unpack("=f", struct.pack("=I", bits + 1))[0]) - float(x)


def write_json(path: pathlib.Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def extract_contract(source_path: pathlib.Path):
    raw = source_path.read_bytes()
    src_sha = digest(raw)
    if src_sha != EXPECTED_SOURCE_SHA256:
        raise ValueError(f"source SHA mismatch: {src_sha}")
    lines = raw.decode("utf-8").splitlines()
    matches = [i for i, line in enumerate(lines) if "if(rh_mul(k)>1.) then" in line]
    if len(matches) != 1:
        raise ValueError(f"expected one activation conditional, got {len(matches)}")
    first = matches[0]
    last = next((i for i in range(first, len(lines)) if lines[i].strip() == "endif"), None)
    if last is None or last - first + 1 != 13:
        raise ValueError("activation IF block did not match the pinned 13-line source block")
    if (first + 1, last + 1) != EXPECTED_SOURCE_LINES:
        raise ValueError(f"source line range changed: {(first+1,last+1)}")
    block = "\n".join(lines[first:last + 1]) + "\n"
    block_sha = digest(block.encode())
    if block_sha != EXPECTED_BLOCK_SHA256:
        raise ValueError(f"activation block SHA mismatch: {block_sha}")
    parameters = {}
    for name, expected in EXPECTED_PARAMETERS.items():
        found = re.findall(rf"^\s*{re.escape(name)}\s*=\s*([0-9]+(?:\.[0-9]*)?(?:[eEdD][+-]?[0-9]+)?)\s*[,/&]", raw.decode(), re.M)
        if len(found) != 1:
            # ccnmin and ncmin declarations terminate without continuation punctuation.
            found = re.findall(rf"^\s*{re.escape(name)}\s*=\s*([0-9]+(?:\.[0-9]*)?(?:[eEdD][+-]?[0-9]+)?)\s*(?:[,/&]|!|$)", raw.decode(), re.M)
        if len(found) != 1:
            raise ValueError(f"could not uniquely locate source parameter {name}: {len(found)} matches")
        literal = found[0].replace("D", "E").replace("d", "e")
        value = float(literal)
        if value != expected:
            raise ValueError(f"source parameter {name} changed: {literal} != {expected}")
        parameters[name] = {"literal": found[0], "value": value}
    init_text = "\n".join(lines[862:889])
    if "ncr(k,i,1) = min(max(ncr1(i,k,1),ccnmin),ccnmax)" not in init_text or "ncr(k,i,2) = max(ncr1(i,k,2),0.0)" not in init_text:
        raise ValueError("source initialization clamp contract changed")
    if "loops = max(ceiling(delt/dtcldcr),1)" not in "\n".join(lines[914:923]):
        raise ValueError("source substep selection contract changed")
    return raw, block, parameters


def make_fortran(block: str, p: dict) -> str:
    # The activation IF source block is inserted without edits; only its test shell is new.
    return f"""program activation_fixture
  implicit none
  integer :: case_id, density_id, k, ktop, kts, i
  real :: q(1,1), qci(1,1,1), ncr(1,1,2), den(1,1)
  real :: rh_mul(1), ncact(1), pcact(1), t(1,1), xlv(1,1), cpm(1,1)
  real :: temp, dtcld, rdtcld, pi
  real, parameter :: satmax={p['satmax']['literal']}, actk={p['actk']['literal']}, actr={p['actr']['literal']}
  real, parameter :: denr=1000., ccnmin={p['ccnmin']['literal']}, ncmin={p['ncmin']['literal']}
  real :: q0, qc0, nccn0, nc0, t0
  real, parameter :: densities(3) = (/0.5, 1.0, 1.5/)
  if (storage_size(temp) /= 32) error stop 'default REAL must be 32 bits'
  pi = 4.*atan(1.)
  dtcld = {DT_SECONDS}
  rdtcld = 1./dtcld
  ktop = 1
  kts = 1
  i = 1
  do density_id=1,3
    do case_id=1,4
      den(1,1) = densities(density_id)
      qci(1,1,1) = 1.e-4
      ncr(1,1,1) = 100.e6
      ncr(1,1,2) = 1.e6
      q(1,1) = 1.e-3
      rh_mul(1) = 1.0005
      if (case_id == 1) rh_mul(1) = 1.0
      if (case_id == 3) q(1,1) = 1.e-9
      if (case_id == 4) then
        ! Branch-isolation fixture; ordinary source initialization clamps nccn to ccnmin.
        rh_mul(1) = 1.00000011920928955078125
        ncr(1,1,1) = 0.01
        ncr(1,1,2) = 0.
      endif
      t(1,1) = 273.
      xlv(1,1) = 2.5e6
      cpm(1,1) = 1004.
      ncact(1) = 0.
      pcact(1) = 0.
      q0=q(1,1); qc0=qci(1,1,1)
      nccn0=ncr(1,1,1); nc0=ncr(1,1,2); t0=t(1,1)
      do k=ktop,kts,-1
{block}      enddo
      write(*,'(2(I0,1X),17(ES24.16E3,1X))') density_id, case_id, &
        real(densities(density_id)), rh_mul(1), q0, qc0, nccn0, nc0, &
        den(1,1), q(1,1), qci(1,1,1), ncr(1,1,1), ncr(1,1,2), &
        t0, t(1,1), ncact(1), pcact(1), ncact(1)*dtcld, pcact(1)*dtcld
    enddo
  enddo
end program activation_fixture
"""


def parse_rows(text: str):
    rows=[]
    for line in text.splitlines():
        cols=line.split()
        if len(cols)!=19:
            raise ValueError(f"expected 19 output fields, got {len(cols)}")
        vals=[float(x.replace('D','E').replace('d','e')) for x in cols[2:]]
        if not all(math.isfinite(v) for v in vals): raise ValueError("nonfinite output field")
        if any(f32(v) != v for v in vals): raise ValueError("output is not default REAL")
        rows.append({"density_id":int(cols[0]),"case_id":int(cols[1]),"values":vals})
    expected=[(d,c) for d in range(1,4) for c in range(1,5)]
    actual=[(r["density_id"],r["case_id"]) for r in rows]
    if actual != expected:
        raise ValueError(f"case roster/order mismatch: {actual}")
    return rows


def assess(rows, p):
    checks=[]
    satmax=p["satmax"]["value"]; actk=p["actk"]["value"]; actr=p["actr"]["value"]
    ccnmin=p["ccnmin"]["value"]; ncmin=p["ncmin"]["value"]
    # denr=1000 kg m-3, xlv=2.5e6 J kg-1, cpm=1004 J kg-1 K-1 are declared test inputs.
    denr=1000.; xlv=2.5e6; cpm=1004.; dt=DT_SECONDS
    m_emb=4.0*math.pi*denr*math.exp(math.log(actr)*3.0)/3.0
    eps=OPERATION_EPS_FACTOR*DEFAULT_REAL_EPS
    for row in rows:
        rho,rh,q0,qc0,nccn0,nc0,rho_echo,q1,qc1,nccn1,nc1,t0,t1,ncrate,pcrate,native_dn,native_dm=row["values"]
        if rho != f32(DENSITIES[row["density_id"]-1]) or rho_echo != rho:
            raise ValueError("density output does not match the requested/default-REAL density")
        case_id=row['case_id']
        expected_initial=(1. if case_id==1 else (1.00000011920928955078125 if case_id==4 else 1.0005),
                          1.e-9 if case_id==3 else 1.e-3, 1.e-4,
                          .01 if case_id==4 else 100.e6,
                          0. if case_id==4 else 1.e6, 273.)
        if (rh,q0,qc0,nccn0,nc0,t0) != tuple(f32(v) for v in expected_initial):
            raise ValueError('fixture initial state echoes changed')
        if row["case_id"]==1:
            if any(v!=0.0 for v in (q1-q0,qc1-qc0,nccn1-nccn0,nc1-nc0,t1-t0,ncrate,pcrate,native_dn,native_dm)):
                raise ValueError("saturation-inactive case changed state")
            checks.append({"case":"saturation_inactive","density_kg_m3":rho,"exact_zero_changes":True})
            continue
        supersat=(rh-1.0)/satmax
        temp_ideal=min(1.0,math.exp(math.log(supersat)*actk))
        dn_ideal=max(0.0,(nccn0+nc0)*temp_ideal-nc0)
        rate_ideal=dn_ideal/dt
        rate_bound=0.5*ulp32(rate_ideal)+eps*abs(rate_ideal)
        if abs(ncrate-rate_ideal)>rate_bound:
            raise ValueError(f"ncact rate outside derived REAL bound: {ncrate} vs {rate_ideal} +/- {rate_bound}")
        dn_process=native_dn
        dn_source_operation=f32(ncrate*f32(dt))
        if native_dn != dn_source_operation:
            raise ValueError('emitted native ncact*dt disagrees with rounded recorded rate')
        dn_process_bound=0.5*ulp32(dn_source_operation)+eps*abs(dn_process)
        if abs(dn_process-dn_ideal)>dn_process_bound+rate_bound*dt:
            raise ValueError("native ncact*dt process increment disagrees with independent binary64 oracle")
        pc_unbounded=m_emb*rate_ideal/rho
        available_rate=max(q0,0.0)/dt
        pc_ideal=min(pc_unbounded,available_rate)
        pc_bound=0.5*ulp32(pc_ideal)+eps*abs(pc_ideal)
        if abs(pcrate-pc_ideal)>pc_bound:
            raise ValueError(f"pcact rate outside derived REAL bound: {pcrate} vs {pc_ideal} +/- {pc_bound}")
        # Independently evaluate the native process increment from the recorded rate
        # and compare it to the binary64 source-equation rate*dt.
        process_increment=native_dm
        if native_dm != f32(pcrate*f32(dt)):
            raise ValueError('emitted native pcact*dt disagrees with rounded recorded rate')
        oracle_increment=pc_ideal*dt
        process_bound=0.5*ulp32(f32(pcrate*f32(dt)))+eps*abs(oracle_increment)+pc_bound*dt
        if abs(process_increment-oracle_increment)>process_bound:
            raise ValueError("pcact*dt native process increment differs from binary64 source-equation oracle")
        expected_nc=max(nc0+dn_ideal,ncmin)
        expected_ccn=max(nccn0-dn_ideal,ccnmin)
        if abs(nc1-expected_nc)>0.5*ulp32(nc1)+eps*abs(dn_ideal):
            raise ValueError('cloud-number poststate exceeds rounding bound')
        if abs(nccn1-expected_ccn)>0.5*ulp32(nccn1)+eps*abs(dn_ideal):
            raise ValueError('CCN poststate exceeds rounding bound')
        if row["case_id"]==2:
            if not pcrate < 0.5*available_rate:
                raise ValueError("uncapped case is not clearly below q/dt water cap")
            case_name="active_uncapped_number_floor_inactive"
            if nccn0 < ccnmin or nc0 <= p["ncmin"]["value"]:
                raise ValueError("uncapped case initial number state violates stated inactive-floor conditions")
            volume_residual=abs((qc1-qc0)-m_emb*dn_process/rho)
            mass_specific_residual=abs((qc1-qc0)-m_emb*dn_process)
        elif row["case_id"]==3:
            case_name="active_water_cap"
            if not math.isclose(pcrate,available_rate,rel_tol=eps,abs_tol=1e-24) or not pc_unbounded>available_rate:
                raise ValueError("water-cap branch is not demonstrated")
            volume_residual=abs((qc1-qc0)-m_emb*dn_process/rho)
            mass_specific_residual=abs((qc1-qc0)-m_emb*dn_process)
        else:
            case_name="active_number_min_branch"
            if f32(nc1) != f32(ncmin) or f32(nccn1) != f32(ccnmin):
                raise ValueError("ncmin/ccnmin floor branch was not demonstrated")
            if abs((nc1-nc0)-dn_process)<1.e-4:
                raise ValueError("number-floor effect was not separated from raw activation increment")
            expected_cloud_number=max(nc0+dn_ideal,ncmin)
            expected_ccn=max(nccn0-dn_ideal,ccnmin)
            if abs(nc1-expected_cloud_number)>0.5*ulp32(nc1)+eps*abs(dn_ideal):
                raise ValueError("cloud-number poststate outside derived floor/REAL bound")
            if abs(nccn1-expected_ccn)>0.5*ulp32(nccn1)+eps*abs(dn_ideal):
                raise ValueError("CCN poststate outside derived floor/REAL bound")
            volume_residual=abs((qc1-qc0)-m_emb*dn_process/rho)
            mass_specific_residual=abs((qc1-qc0)-m_emb*dn_process)
        # Expected poststates use the independent binary64 process increment;
        # bounds are half an ULP at the actual stored poststate plus 16 REAL eps.
        qc_expected=qc0+oracle_increment
        qv_expected=max(q0-oracle_increment,0.0)
        qc_bound=0.5*ulp32(qc1)+eps*abs(oracle_increment)
        qv_bound=0.5*ulp32(q1)+eps*abs(oracle_increment)
        if abs(qc1-qc_expected)>qc_bound:
            raise ValueError(f"qc poststate outside derived default-REAL bound in {case_name}")
        if abs(q1-qv_expected)>qv_bound:
            raise ValueError(f"qv poststate outside derived default-REAL bound in {case_name}")
        t_increment=oracle_increment*xlv/cpm
        t_expected=t0+t_increment
        t_bound=0.5*ulp32(t1)+eps*abs(t_increment)
        if abs(t1-t_expected)>t_bound:
            raise ValueError(f"temperature poststate outside derived default-REAL bound in {case_name}")
        checks.append({"case":case_name,"density_kg_m3":rho,
            "activation_delta_N_binary64_oracle":dn_ideal,"activation_delta_N_native_rate_times_dt":dn_process,
            "native_water_process_increment_pcact_times_dt":process_increment,
            "binary64_water_process_increment_oracle":oracle_increment,
            "process_increment_abs_error":abs(process_increment-oracle_increment),
            "qc_delta_from_rounded_states":qc1-qc0,"qv_delta_from_rounded_states":q1-q0,
            "volume_interpretation_residual_from_rounded_states_kgkg":volume_residual,
            "mass_specific_interpretation_residual_from_rounded_states_kgkg":mass_specific_residual,
            "qc_poststate_bound":qc_bound,"qv_poststate_bound":qv_bound,
            "temperature_increment_from_source":t1-t0,"temperature_rounding_bound":t_bound,
            "water_cap_active":row["case_id"]==3,"number_floor_branch_isolation_only":row["case_id"]==4})
    return checks


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root",required=True,type=pathlib.Path,help="root of the pinned PR104 source worktree")
    parser.add_argument("--output-dir",required=True,type=pathlib.Path,help="new output directory; existing paths are refused")
    parser.add_argument("--fc",default="gfortran",help="Fortran compiler command (default: gfortran)")
    args=parser.parse_args()
    out=args.output_dir.expanduser().resolve()
    if out.exists(): parser.error(f"output directory already exists: {out}")
    source_root=args.source_root.expanduser().resolve()
    src=source_root/SOURCE_REL
    try:
        out.mkdir(parents=True,exist_ok=False)
        _,block,params=extract_contract(src)
        source_sha=digest(src.read_bytes())
        block_path=out/"activation-block.exact.f90.inc"
        block_path.write_text(block)
        source=make_fortran(block,params)
        source_path=out/"activation_fixture.f90"
        source_path.write_text(source)
        if block not in source:
            raise RuntimeError("generated fixture did not embed exact extracted activation block")
        compiler=shlex.split(args.fc)
        if not compiler: raise RuntimeError("empty compiler command")
        version=subprocess.run(compiler+["--version"],capture_output=True,text=True,timeout=30)
        write_json(out/"compiler-version.receipt.json",{"argv":compiler+["--version"],"returncode":version.returncode,"stdout":version.stdout,"stderr":version.stderr})
        if version.returncode: raise RuntimeError("compiler version probe failed")
        runs=[]
        for opt in ("O0","O2"):
            exe=out/f"activation_{opt}.exe"
            clog=out/f"compile_{opt}.log"
            compile_argv=compiler+[f"-{opt}","-std=f2008","-ffp-contract=off","-Wall","-Wextra","-o",str(exe),str(source_path)]
            with clog.open("wb") as stream: cp=subprocess.run(compile_argv,stdout=stream,stderr=subprocess.STDOUT)
            write_json(out/f"compile_{opt}.receipt.json",{"argv":compile_argv,"returncode":cp.returncode,"stdout_sha256":digest(clog.read_bytes())})
            if cp.returncode: raise RuntimeError(f"{opt} compile failed; durable receipt written")
            rlog=out/f"run_{opt}.stdout"
            with rlog.open("wb") as stream: rp=subprocess.run([str(exe)],stdout=stream,stderr=subprocess.STDOUT,timeout=30)
            write_json(out/f"run_{opt}.receipt.json",{"argv":[str(exe)],"returncode":rp.returncode,"stdout_sha256":digest(rlog.read_bytes()),"executable_sha256":digest(exe.read_bytes())})
            if rp.returncode: raise RuntimeError(f"{opt} fixture executable failed; durable receipt written")
            rows=parse_rows(rlog.read_text())
            checks=assess(rows,params)
            runs.append({"optimization":opt,"compiler":compiler,"compile_returncode":cp.returncode,"run_returncode":rp.returncode,
                "generated_source_sha256":digest(source_path.read_bytes()),"executable_sha256":digest(exe.read_bytes()),
                "stdout_sha256":digest(rlog.read_bytes()),"rows":rows,"checks":checks})
        for a,b in zip(runs[0]["rows"],runs[1]["rows"]):
            if (a["density_id"],a["case_id"])!=(b["density_id"],b["case_id"]): raise RuntimeError("O0/O2 roster mismatch")
            for x,y in zip(a["values"],b["values"]):
                if not math.isclose(x,y,rel_tol=2.0*OPERATION_EPS_FACTOR*DEFAULT_REAL_EPS,abs_tol=1e-12):
                    raise RuntimeError("O0/O2 default-REAL output mismatch")
        result={"status":"PASS_SOURCE_EXTRACTED_LOCAL_ACTIVATION_CONTRACT_FIXTURE",
            "source":{"relative_path":SOURCE_REL.as_posix(),"sha256":source_sha,"activation_lines":list(EXPECTED_SOURCE_LINES),"activation_block_sha256":EXPECTED_BLOCK_SHA256,"parameters":params},
            "fixture":{"generated_fortran_sha256":digest(source_path.read_bytes()),"compiler_version":version.stdout.splitlines()[0],"default_real_bits":32,"dtcld_seconds":DT_SECONDS,
                "density_values_kg_m3":[f32(x) for x in DENSITIES],"case_roster":[[d,c] for d in range(1,4) for c in range(1,5)],"optimized_runs":runs},
            "independent_oracle":{"arithmetic":"binary64 source-equation evaluation, followed by explicit default-REAL poststate comparison","default_real_eps":DEFAULT_REAL_EPS,
                "operation_eps_factor":OPERATION_EPS_FACTOR,"state_bound":"half ULP at the actual stored poststate plus 16 default-REAL epsilons times the expected increment",
                "embryo_mass_kg":"4*pi*denr*exp(log(actr)*3)/3 in binary64; denr=1000 kg m-3 is an explicit fixture input",
                "other_explicit_fixture_inputs":{"dtcld_s":DT_SECONDS,"xlv_J_kg":2.5e6,"cpm_J_kg_K":1004.0}},
            "execution_counts":{"compile_invocations":2,"compile_returncode_zero":2,"fixture_executable_invocations":2,"fixture_executable_returncode_zero":2,"cases_per_optimization":12},
            "scope_limit":"Conditional local source-process closure only. It does not establish transported QNC units, producer-consumer coupling correctness, radiation impact, or physical accuracy.",
            "model_calls":0,"WRF_calls":0,"RTE_calls":0}
        write_json(out/"result.json",result)
        print(json.dumps({"status":result["status"],"output_dir":str(out),"case_count_per_optimization":12,"source_sha256":source_sha,"block_sha256":EXPECTED_BLOCK_SHA256},sort_keys=True))
    except Exception as exc:
        write_json(out/"failure.json",{"status":"FIXTURE_FAILED","error":repr(exc),"source_root":str(source_root),"source_sha256":digest(src.read_bytes()) if src.is_file() else None})
        raise

if __name__=="__main__": main()
