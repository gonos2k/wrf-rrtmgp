#!/usr/bin/env python3
"""Prepare, but do not run, same-arm continuous 00:00-13:00 controls."""
import argparse, datetime as dt, hashlib, json, os, pathlib, re, shutil, subprocess, sys

BASE = pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
SOURCE = BASE / "build/udm37-main-runtime-io-mpi-source-v1"
BUILD = BASE / "build/udm37-main-runtime-io-mpi-build-v1"
ORIGIN = BASE / "build/udm37-registry-subgrid-matthew-48h-v1"
RUNNER = BASE / "build/udm37-main-runtime-io-integration-preparation-v1/mpi_control_once.py"
SCANNER = BASE / "build/udm37-matthew-dt60-paired-48h-v1/validate_all_numeric.py"

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

def pin(path):
    return {"path": str(path.resolve()), "sha256": sha(path),
            "size_bytes": path.stat().st_size,
            "link": os.readlink(path) if path.is_symlink() else None}

def atomic_json(path, value):
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("x") as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n"); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)

def set_scalar(text, name, value):
    pattern = re.compile(r"(?mi)^(\s*" + re.escape(name) + r"\s*=\s*)[^,\n]+")
    changed, count = pattern.subn(lambda m: m.group(1) + value, text)
    if count != 1:
        raise ValueError(f"expected one {name} assignment, got {count}")
    return changed

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage-root", type=pathlib.Path, required=True,
                    help="new destination; created only when this preparer is explicitly run")
    args = ap.parse_args()
    root = args.stage_root.resolve()
    if root.exists(): raise FileExistsError(root)

    prior = json.loads((ORIGIN / "stage-plan.json").read_text())
    prior_run = json.loads((ORIGIN / "execution.json").read_text())
    build = json.loads((BUILD / "result.json").read_text())
    if prior_run.get("status") != "PASS_PAIRED_RUNTIME_SCOPED" or prior_run.get("model_calls") != 2:
        raise ValueError("the preserved 48-hour pair is not a completed two-arm control")
    for arm in ("ra4", "ra37"):
        result = prior_run.get("results", {}).get(arm, {})
        observed = result.get("validation", {}).get("times", [])
        if result.get("actual_rc") != 0 or result.get("reaped") is not True or result.get("timed_out"):
            raise ValueError(f"preserved 48-hour {arm} parent did not finish RC0/reaped")
        if len(observed) != 49 or observed[0] != "2016-10-06_00:00:00" or observed[-1] != "2016-10-08_00:00:00":
            raise ValueError(f"preserved 48-hour {arm} parent lacks the exact 49-record horizon")
    if build.get("status") != "PASS_BUILD_INSTALL_SCOPED" or build.get("models") != 0:
        raise ValueError("fresh ZZ build/install receipt is not a scoped zero-model pass")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=SOURCE, text=True).strip()
    if head != build["source_head"] or head != "dd7eb1da3a23ca8f21bd4d5bf82f7feecf813fc5":
        raise ValueError("source head does not match the frozen ZZ build")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=SOURCE, text=True).strip():
        raise ValueError("source worktree is dirty")
    if len(prior["cases"]["ra4"]["files"]) != 104 or len(prior["cases"]["ra37"]["files"]) != 104:
        raise ValueError("expected exactly the preserved 104-file static roster per arm")
    if not RUNNER.is_file() or not SCANNER.is_file(): raise FileNotFoundError("runner/scanner")

    root.mkdir(parents=True)
    cases = {}
    for arm in ("ra4", "ra37"):
        source_case = pathlib.Path(prior["cases"][arm]["directory"])
        case = root / arm; case.mkdir()
        entries = []
        for record in prior["cases"][arm]["files"]:
            rel = record["path"]
            src, dst = source_case / rel, case / rel
            if src.is_symlink():
                resolved = src.resolve(strict=True)
                if os.readlink(src) != record["link_text"]: raise ValueError(f"origin symlink drift: {arm}/{rel}")
                if str(resolved) != record["resolved_path"] or resolved.stat().st_size != record["size_bytes"] or sha(resolved) != record["sha256"]:
                    raise ValueError(f"origin symlink target drift: {arm}/{rel}")
                dst.symlink_to(os.readlink(src))
            else:
                if not src.is_file() or src.stat().st_size != record["size_bytes"] or sha(src) != record["sha256"]:
                    raise ValueError(f"origin asset drift: {arm}/{rel}")
                shutil.copy2(src, dst)
            entries.append(rel)

        # A fresh executable is the only roster entry intentionally replaced.
        new_exe = BUILD / "install/bin/wrf"
        exe_dest = case / "wrf.exe"
        if "wrf.exe" not in entries: raise ValueError("preserved static roster has no wrf.exe")
        if exe_dest.is_symlink() or exe_dest.exists(): exe_dest.unlink()
        shutil.copy2(new_exe, exe_dest)

        nml = (case / "namelist.input").read_text()
        changes = {"run_days":"0", "run_hours":"13", "run_minutes":"0", "run_seconds":"0",
                   "start_year":"2016", "start_month":"10", "start_day":"06", "start_hour":"00",
                   "end_year":"2016", "end_month":"10", "end_day":"06", "end_hour":"13",
                   "history_interval":"60", "restart":".false.", "restart_interval":"720",
                   "io_form_restart":"2", "time_step":"60"}
        for key, value in changes.items(): nml = set_scalar(nml, key, value)
        if re.search(r"(?mi)^\s*write_hist_at_0h_rst\s*=", nml):
            nml = set_scalar(nml, "write_hist_at_0h_rst", ".false.")
        else:
            nml, count = re.subn(r"(?mi)(^\s*&time_control\s*\n)", r"\1 write_hist_at_0h_rst = .false.,\n", nml, count=1)
            if count != 1: raise ValueError("could not add write_hist_at_0h_rst to time_control")
        if not re.search(r"(?mi)^\s*multi_perturb\s*=", nml):
            # The namelist omits this optional setting; record and rely on the
            # pinned registry default (0), rather than silently adding a group.
            multi_policy = "omitted; Registry default is 0"
        else:
            vals = re.findall(r"(?mi)^\s*multi_perturb\s*=\s*([^,\n]+)", nml)
            if vals != ["0"]: raise ValueError(f"unexpected multi_perturb setting: {vals}")
            multi_policy = "explicit 0"
        (case / "namelist.input").write_text(nml)
        files = {p.name: pin(p) for p in sorted(case.iterdir())}
        expected_times = [(dt.datetime(2016,10,6)+dt.timedelta(hours=h)).strftime("%Y-%m-%d_%H:%M:%S") for h in range(14)]
        cases[arm] = {"directory": str(case), "source_case": str(source_case), "files": files,
                      "expected_restart_files": 1, "multi_perturb_policy": multi_policy,
                      "namelist_changes": changes | {"write_hist_at_0h_rst": ".false."},
                      "status": "STAGED_UNRUN"}

    stage = {"schema":"UDM_NETCDF_ZZ_CONTINUOUS_13H_STAGE_V1", "status":"STAGED_UNRUN",
             "purpose":"same-arm continuous 00:00-13:00 control producing a 12:00 restart",
             "source":{"path":str(SOURCE),"head":head,"tree":build["source_tree"],
                       "selected_files":build["selected_source_files_unchanged"] if isinstance(build.get("selected_source_files_unchanged"),dict) else {}},
             "build_result":pin(BUILD/"result.json"), "origin_stage_plan":pin(ORIGIN/"stage-plan.json"),
             "origin_execution":pin(ORIGIN/"execution.json"), "runner":pin(RUNNER), "numeric_scanner":pin(SCANNER),
             "runtime":{"MPI":4,"OMP":2,"duration_minutes":780,"history_interval_minutes":60,
                        "start":"2016-10-06_00:00:00","end":"2016-10-06_13:00:00","restart_interval_minutes":720},
             "case":{"start":"2016-10-06_00:00:00","end":"2016-10-06_13:00:00","duration_seconds":46800,
                     "history_interval_minutes":60,"expected_history_times":expected_times,"expected_restart_files":1},
             "limits":{"max_models":2,"per_arm_timeout_seconds":300,"first_failure_stops":True},
             "models_launched":0,"cases":cases,"physical_accepted":False,
             "scope":"Preparation only; no model launched. Restart seed continuity is not asserted here."}
    # Use the full source manifest from the build plan when available.
    build_plan = json.loads((BUILD/"plan.json").read_text())
    stage["source"]["selected_files"] = {str(pathlib.Path(p["path"]).relative_to(SOURCE)): p for p in build_plan["source_pins"]}
    registry_stoch = SOURCE / "WRF/Registry/registry.stoch"
    registry_text = registry_stoch.read_text()
    if not re.search(r'(?mi)^rconfig\s+integer\s+multi_perturb\s+.*?\s+0\s+-\s+"stochastic forcing option', registry_text):
        raise ValueError("pinned Registry does not declare multi_perturb default 0")
    stage["source"]["selected_files"]["WRF/Registry/registry.stoch"] = pin(registry_stoch)
    atomic_json(root/"stage-plan.json", stage)
    verify = '''#!/usr/bin/env python3
import hashlib,json,pathlib,re,sys
root=pathlib.Path(__file__).resolve().parent
p=json.loads((root/"stage-plan.json").read_text()); errors=[]
def digest(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for block in iter(lambda:f.read(1<<20),b""): h.update(block)
 return h.hexdigest()
for arm,c in p["cases"].items():
 d=pathlib.Path(c["directory"]); expected=set(c["files"]); actual={x.name for x in d.iterdir()}
 if actual!=expected: errors.append(f"{arm}: roster extra={sorted(actual-expected)} missing={sorted(expected-actual)}")
 for name,pin in c["files"].items():
  q=d/name
  if not q.is_file(): errors.append(f"{arm}/{name}: not a file"); continue
  if q.stat().st_size!=pin["size_bytes"] or digest(q)!=pin["sha256"]: errors.append(f"{arm}/{name}: pin mismatch")
 if (d/"wrf.exe").is_symlink(): errors.append(f"{arm}: wrf.exe must be staged as the new-build copy")
 n=(d/"namelist.input").read_text()
 want={"run_days":"0","run_hours":"13","run_minutes":"0","run_seconds":"0","start_year":"2016","start_month":"10","start_day":"06","start_hour":"00","end_year":"2016","end_month":"10","end_day":"06","end_hour":"13","history_interval":"60","restart":".false.","restart_interval":"720","time_step":"60","io_form_restart":"2","mp_physics":"27","use_mp_re":"1","radt":"10","cu_physics":"1","cudt":"5","numtiles":"2"}
 for k,v in want.items():
  got=re.findall(r"(?mi)^\\s*"+k+r"\\s*=\\s*([^,\\n]+)",n)
  if got!=[v]: errors.append(f"{arm}: {k}={got}, expected {[v]}")
 if re.search(r"(?mi)^\\s*multi_perturb\\s*=\\s*([^,\\n]+)",n):
  got=re.findall(r"(?mi)^\\s*multi_perturb\\s*=\\s*([^,\\n]+)",n)
  if got!=["0"]: errors.append(f"{arm}: multi_perturb={got}")
 if list(d.glob("rsl.*")) or list(d.glob("wrfout*")) or list(d.glob("wrfrst*")) or (d/"namelist.output").exists(): errors.append(f"{arm}: pre-existing model outputs")
 expected_ra="37" if arm=="ra37" else "4"
 for k,v in {"ra_lw_physics":expected_ra,"ra_sw_physics":expected_ra,"rrtmgp_udm_frozen_optics":"1" if arm=="ra37" else "0"}.items():
  got=re.findall(r"(?mi)^\\s*"+k+r"\\s*=\\s*([^,\\n]+)",n)
  if got!=[v]: errors.append(f"{arm}: {k}={got}")
print(json.dumps({"status":"FAIL" if errors else "PASS_STAGED_UNRUN","errors":errors,"files_per_arm":{a:len(c["files"]) for a,c in p["cases"].items()},"models_launched":0}))
sys.exit(bool(errors))
'''
    (root/"verify_stage.py").write_text(verify)
    os.chmod(root/"verify_stage.py", 0o755)
    atomic_json(root/"PENDING_ROOT_AUTHORIZATION.json", {"status":"PENDING_ROOT_REVIEW",
                 "plan_sha256":sha(root/"stage-plan.json"),"runner_sha256":sha(RUNNER),
                 "max_models":2,"per_arm_timeout_seconds":300,"physical_accepted":False})
    print(json.dumps({"status":"STAGED_UNRUN","models_launched":0,"files_per_arm":104,
                      "duration_minutes":780,"stage_plan_sha256":sha(root/"stage-plan.json")}))

if __name__ == "__main__": main()
