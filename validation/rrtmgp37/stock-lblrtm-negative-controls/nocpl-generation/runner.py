#!/usr/bin/env python3
"""Prepare or externally authorize one NOCPL LNFL generation; never auto-runs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PLAN_PATH = HERE / "plan.json"
RUN_DIR = HERE / "run-v2"
TIMEOUT_SECONDS = 3600


def file_sha(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    n = 0
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
            n += len(block)
    return h.hexdigest(), n


def durable_json(path: Path, value: Any) -> str:
    payload = (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        dfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    return hashlib.sha256(payload).hexdigest()


def resolve_pin(rec: dict[str, Any]) -> Path:
    p = Path(rec["path"])
    if not p.is_absolute():
        p = ROOT / p
    p = p.resolve(strict=True)
    got_sha, got_size = file_sha(p)
    if got_sha != rec["sha256"] or got_size != rec["size_bytes"]:
        raise RuntimeError(f"pinned file changed: {rec['path']}")
    return p


def plan_and_pins() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    plan = json.loads(PLAN_PATH.read_text())
    if plan.get("schema") != "udm37-lblrtm-nocpl-line-generation-plan-v2" or plan.get("status") != "PREPARED_NOT_EXECUTED":
        raise RuntimeError("plan status/schema is not the frozen prepared contract")
    if plan["spectral_request"].get("record3_holind") != "NOCPL":
        raise RuntimeError("plan is not the one-control NOCPL case")
    if plan["spectral_request"]["molecule_numbers_selected"] != [1, 2, 3, 4, 6, 7, 22]:
        raise RuntimeError("selected gas flags differ from v6")
    pins = plan["verified_inputs"]
    if not pins or not all(resolve_pin(r) for r in pins):
        raise RuntimeError("preflight pin verification failed")
    return plan, pins


def tape5_bytes(plan: dict[str, Any]) -> bytes:
    req = plan["spectral_request"]["tape5_records"]
    records = [req["record1"], req["record2"], req["record3"]]
    if [len(s) for s in records] != [72, 20, 91]:
        raise RuntimeError("TAPE5 record widths do not match frozen LNFL formats")
    if records[2][0:47] != plan["parent_record3_species_flags"] or records[2][47:51] != "    " or records[2][51:56] != "NOCPL" or records[2][56:] != " " * 35:
        raise RuntimeError("Record 3 does not contain precisely the expected NOCPL field and unchanged flags")
    return ("\n".join(records) + "\n").encode("ascii")


def verify_staged(plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for rel in ("TAPE5", "TAPE1"):
        p = RUN_DIR / rel
        if rel == "TAPE5":
            if p.is_symlink():
                raise RuntimeError("staged TAPE5 must be a regular private copy")
            got, size = file_sha(p)
            expected = hashlib.sha256(tape5_bytes(plan)).hexdigest()
            if got != expected:
                raise RuntimeError("staged NOCPL TAPE5 differs from frozen record contract")
            rows.append({"path": rel, "sha256": got, "size_bytes": size, "kind": "copied_input"})
        else:
            target = resolve_pin(plan["source_stage"]["line_file"])
            if not p.is_symlink() or p.resolve(strict=True) != target:
                raise RuntimeError("TAPE1 does not resolve to the pinned publisher line file")
            got, size = file_sha(p)
            rows.append({"path": rel, "resolved_path": str(p.resolve()), "sha256": got, "size_bytes": size, "kind": "symlink_input"})
    return rows


def prepare(plan: dict[str, Any], pins: list[dict[str, Any]]) -> None:
    if RUN_DIR.exists():
        raise RuntimeError(f"refusing to overwrite or reuse {RUN_DIR}")
    RUN_DIR.mkdir(parents=True, exist_ok=False, mode=0o700)
    (RUN_DIR / "TAPE5").write_bytes(tape5_bytes(plan))
    line = resolve_pin(plan["source_stage"]["line_file"])
    (RUN_DIR / "TAPE1").symlink_to(line)
    staged = verify_staged(plan)
    prepared = {
        "schema": "UDM_LBLRTM_NOCPL_PREPARED_V2",
        "status": "READY_NOT_RUN",
        "plan_sha256": file_sha(PLAN_PATH)[0],
        "runner_sha256": file_sha(Path(__file__))[0],
        "case_dir": str(RUN_DIR),
        "staged_inputs": staged,
        "verified_source_asset_count": len(pins),
        "NOCPL_record_change": plan["input_control_diff"],
        "runtime_invocations": 0,
    }
    durable_json(RUN_DIR / "prepared.json", prepared)


def validate_authorization(path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    auth = json.loads(path.read_text())
    prepared = RUN_DIR / "prepared.json"
    expected = {
        "schema": "UDM_LBLRTM_NOCPL_ONE_RUN_AUTH_V2",
        "authorized": True,
        "max_invocations": 1,
        "plan_sha256": file_sha(PLAN_PATH)[0],
        "runner_sha256": file_sha(Path(__file__))[0],
        "prepared_sha256": file_sha(prepared)[0],
        "output_dir": str(RUN_DIR.relative_to(ROOT)),
        "control": "Record 3 HOLIND1=NOCPL only; all other fields byte-identical to LNFL v6 request",
    }
    if any(auth.get(k) != v for k, v in expected.items()):
        raise RuntimeError("external authorization does not exactly bind this one-run NOCPL plan")
    if path.resolve().is_relative_to(RUN_DIR.resolve()):
        raise RuntimeError("authorization must be external to run directory")
    return auth


def output_files() -> list[dict[str, Any]]:
    excluded = {"TAPE5", "TAPE1", "prepared.json", "authorization.json", "launch.json", "execution.json", "completion.json", "postflight.json", "stdout.log", "stderr.log"}
    rows = []
    for p in sorted(RUN_DIR.rglob("*")):
        if p.is_symlink() or p.is_dir():
            continue
        rel = p.relative_to(RUN_DIR).as_posix()
        if rel in excluded:
            continue
        h, n = file_sha(p)
        rows.append({"path": rel, "sha256": h, "size_bytes": n})
    return rows


def launch(plan: dict[str, Any], pins: list[dict[str, Any]], auth_path: Path) -> int:
    if not RUN_DIR.is_dir() or not (RUN_DIR / "prepared.json").is_file():
        raise RuntimeError("prepared case missing; run --prepare first")
    if any((RUN_DIR / n).exists() for n in ("launch.json", "execution.json", "postflight.json")):
        raise RuntimeError("one-use case already has a launch/execution receipt")
    validate_authorization(auth_path, plan)
    before = verify_staged(plan)
    if before != json.loads((RUN_DIR / "prepared.json").read_text())["staged_inputs"]:
        raise RuntimeError("staged inputs changed after prepare")
    # Revalidate all source/build/data pins immediately before process creation.
    for p in pins:
        resolve_pin(p)
    auth_copy = RUN_DIR / "authorization.json"
    auth_copy.write_bytes(auth_path.read_bytes())
    home = os.environ.get("HOME")
    if home is None:
        raise RuntimeError("HOME is unset; refusing launch")
    env = {"HOME": home, "PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
    exe = resolve_pin(plan["lnfl_build"]["binary"])
    command = [str(exe), "TAPE1"]
    started = time.time()
    proc = None
    rc = None
    timed_out = False
    with (RUN_DIR / "stdout.log").open("xb") as so, (RUN_DIR / "stderr.log").open("xb") as se:
        try:
            proc = subprocess.Popen(command, cwd=RUN_DIR, env=env, stdin=subprocess.DEVNULL, stdout=so, stderr=se, start_new_session=True)
            durable_json(RUN_DIR / "launch.json", {"schema":"UDM_LBLRTM_NOCPL_LAUNCH_V2","pid":proc.pid,"command":command,"cwd":str(RUN_DIR),"started_epoch":started,"timeout_seconds":TIMEOUT_SECONDS,"HOME_unchanged":True,"plan_sha256":file_sha(PLAN_PATH)[0],"runner_sha256":file_sha(Path(__file__))[0],"authorization_sha256":file_sha(auth_copy)[0]})
            try:
                rc = proc.wait(timeout=TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                timed_out = True
                try: os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                try: rc = proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try: os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    rc = proc.wait()
            # Durably persist actual child RC immediately after wait and before file inspection.
            terminal = {"schema":"UDM_LBLRTM_NOCPL_CHILD_RC_V2","pid":proc.pid,"actual_child_returncode":rc,"timed_out":timed_out,"started_epoch":started,"ended_epoch":time.time(),"home_unchanged":os.environ.get("HOME")==home}
            durable_json(RUN_DIR / "execution.json", terminal)
        except BaseException as exc:
            if proc is not None and proc.poll() is None:
                try: os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                try: rc = proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try: os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    rc = proc.wait()
            if proc is not None and not (RUN_DIR / "execution.json").exists():
                durable_json(RUN_DIR / "execution.json", {"schema":"UDM_LBLRTM_NOCPL_CHILD_RC_V2","pid":proc.pid,"actual_child_returncode":proc.returncode,"runner_exception":repr(exc),"started_epoch":started,"ended_epoch":time.time()})
            raise
    # Post-exit checks begin only after the durable child return-code receipt exists.
    # Recheck the private staged inputs immediately after durable RC and before output inspection.
    prepared_inputs = json.loads((RUN_DIR / "prepared.json").read_text())["staged_inputs"]
    staged_after = None
    staged_check_error = None
    try:
        staged_after = verify_staged(plan)
    except Exception as exc:
        staged_check_error = repr(exc)
    staged_unchanged = staged_after == before == prepared_inputs
    post = {"schema":"UDM_LBLRTM_NOCPL_POSTFLIGHT_V2","execution_sha256":file_sha(RUN_DIR/'execution.json')[0],"actual_child_returncode":rc,"timed_out":timed_out,"stdout":{"sha256":file_sha(RUN_DIR/'stdout.log')[0],"size_bytes":(RUN_DIR/'stdout.log').stat().st_size},"stderr":{"sha256":file_sha(RUN_DIR/'stderr.log')[0],"size_bytes":(RUN_DIR/'stderr.log').stat().st_size},"staged_inputs_unchanged":staged_unchanged,"staged_inputs_after":staged_after,"staged_input_check_error":staged_check_error}
    post["input_pins_unchanged"] = all(resolve_pin(x) for x in pins)
    post["outputs"] = output_files()
    required = ["TAPE3", "TAPE6"]
    post["required_outputs_present_nonempty"] = all((RUN_DIR/x).is_file() and (RUN_DIR/x).stat().st_size > 0 for x in required)
    post["status"] = "NOCPL_TAPE3_GENERATED" if rc == 0 and not timed_out and post["required_outputs_present_nonempty"] and post["input_pins_unchanged"] and post["staged_inputs_unchanged"] else "NOCPL_LNFL_FAILED_OR_POSTFLIGHT_INCOMPLETE"
    durable_json(RUN_DIR / "postflight.json", post)
    return 0 if post["status"] == "NOCPL_TAPE3_GENERATED" else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true", help="verify/stage only; never invokes LNFL")
    mode.add_argument("--launch", action="store_true", help="one LNFL invocation; requires external root authorization")
    ap.add_argument("--authorization", type=Path)
    args = ap.parse_args()
    plan, pins = plan_and_pins()
    if args.prepare:
        prepare(plan, pins)
        print(json.dumps({"status":"READY_NOT_RUN","run_dir":str(RUN_DIR),"verified_input_count":len(pins)}))
        return 0
    if args.authorization is None:
        raise RuntimeError("--launch requires an external root authorization file")
    return launch(plan, pins, args.authorization.resolve(strict=True))


if __name__ == "__main__":
    raise SystemExit(main())
