#!/usr/bin/env python3
"""Prepare or, only with an external root authorization, run one pinned OD case."""
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
RUN_DIR = HERE / "runs" / "od-v1"
TIMEOUT_SECONDS = 7200
STOCK_EXE_SHA256 = "a5c363c87a44b686e8bff1cf0e60fcfb7b0e167c8ec74d0201b6cc6b2b41473b"
TAPE5_SHA256 = "a676bc7761e09ab42f212c3cca80ebfd1be27604cd332cc966205d1280ae62dd"
TAPE3_SHA256 = "4b8c696c40ed1b80c03ee3b697422f37d95c832bcf3f7cdd3106930bb84da459"
FSCDXS_SHA256 = "1a5cebba2d3787c2e48c9cc0f2e4d1593720e4655b6ae4e7e4bc1a31c4b426f6"


def digest(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            h.update(block)
    return h.hexdigest(), size


def canonical_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def durable_json(path: Path, obj: Any) -> str:
    data = canonical_bytes(obj)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    return hashlib.sha256(data).hexdigest()


def load_plan() -> dict[str, Any]:
    plan = json.loads(PLAN_PATH.read_text())
    if plan.get("schema") != "UDM_LBLRTM_OD_SINGLE_RUN_PLAN_V1":
        raise RuntimeError("unexpected plan schema")
    if plan["executable"]["sha256"] != STOCK_EXE_SHA256:
        raise RuntimeError("plan does not pin the authorized stock executable")
    if plan["deck"]["sha256"] != TAPE5_SHA256 or plan["tape3"]["sha256"] != TAPE3_SHA256:
        raise RuntimeError("deck or TAPE3 pin differs from frozen expected identity")
    if plan["fscdxs"]["sha256"] != FSCDXS_SHA256:
        raise RuntimeError("FSCDXS pin differs from frozen expected identity")
    if plan["controls"].get("ICNTNM") != 1:
        raise RuntimeError("this runner is restricted to the frozen ICNTNM=1 NOCPL deck")
    return plan


def resolve_pin(entry: dict[str, Any]) -> Path:
    path = Path(entry["path"])
    if not path.is_absolute():
        path = ROOT / path
    path = path.resolve(strict=True)
    got_sha, got_size = digest(path)
    if got_sha != entry["sha256"] or got_size != entry["size_bytes"]:
        raise RuntimeError(f"pinned asset changed: {entry['path']}")
    return path


def verify_all(plan: dict[str, Any]) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    for key in ("executable", "deck", "tape3", "fscdxs", "mt_ckd_data"):
        resolved[key] = resolve_pin(plan[key])
    for lib in plan["runtime_libraries"]:
        resolved["lib:" + lib["soname"]] = resolve_pin(lib)
    for item in plan["components"]:
        resolved["component:" + item["relative_path"]] = resolve_pin(item)
    for receipt in plan["provenance_files"]:
        resolved["provenance:" + receipt["path"]] = resolve_pin(receipt)
    return resolved


def inventory_inputs(run_dir: Path, plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    staged = [("TAPE5", plan["deck"]), ("TAPE3", plan["tape3"]), ("FSCDXS", plan["fscdxs"]), (plan["mt_ckd_data"]["runtime_basename"], plan["mt_ckd_data"])]
    for rel, expected in staged:
        p = run_dir / rel
        if rel == "TAPE5":
            if p.is_symlink():
                raise RuntimeError("TAPE5 must be an isolated regular copy")
            got_sha, got_size = digest(p)
            if got_sha != expected["sha256"] or got_size != expected["size_bytes"]:
                raise RuntimeError(f"staged input mismatch: {rel}")
            rows.append({"path": rel, "kind": "copied_input", "sha256": got_sha, "size_bytes": got_size})
        else:
            if not p.is_symlink() or p.resolve(strict=True) != resolve_pin(expected):
                raise RuntimeError(f"wrong staged symlink: {rel}")
            got_sha, got_size = digest(p)
            rows.append({"path": rel, "kind": "symlink_input", "resolved_path": str(p.resolve()), "sha256": got_sha, "size_bytes": got_size})
    for item in plan["components"]:
        p = run_dir / item["relative_path"]
        if not p.is_symlink() or p.resolve(strict=True) != resolve_pin(item):
            raise RuntimeError(f"wrong component symlink: {item['relative_path']}")
        got_sha, got_size = digest(p)
        rows.append({"path": item["relative_path"], "kind": "symlink_input", "resolved_path": str(p.resolve()), "sha256": got_sha, "size_bytes": got_size})
    return rows


def prepare(plan: dict[str, Any]) -> None:
    if RUN_DIR.exists():
        raise RuntimeError(f"refusing to overwrite existing case directory: {RUN_DIR}")
    resolved = verify_all(plan)
    RUN_DIR.parent.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(mode=0o700)
    shutil_copyfile = __import__("shutil").copyfile
    shutil_copyfile(resolved["deck"], RUN_DIR / "TAPE5")
    os.symlink(resolved["tape3"], RUN_DIR / "TAPE3")
    os.symlink(resolved["fscdxs"], RUN_DIR / "FSCDXS")
    (RUN_DIR / "xs").mkdir()
    for item in plan["components"]:
        target = resolve_pin(item)
        destination = RUN_DIR / item["relative_path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, destination)
    os.symlink(resolved["mt_ckd_data"], RUN_DIR / plan["mt_ckd_data"]["runtime_basename"])
    rows = inventory_inputs(RUN_DIR, plan)
    exe_sha, exe_size = digest(resolved["executable"])
    prepared = {
        "schema": "UDM_LBLRTM_OD_PREPARED_CASE_V1",
        "status": "READY_NOT_RUN",
        "plan_sha256": digest(PLAN_PATH)[0],
        "runner_sha256": digest(Path(__file__))[0],
        "case_path": str(RUN_DIR),
        "executable": {"path": str(resolved["executable"]), "sha256": exe_sha, "size_bytes": exe_size},
        "inputs": rows,
        "input_count": len(rows),
        "control_scope": plan["controls"],
        "launch_authorization": "not supplied; no executable invoked",
    }
    durable_json(RUN_DIR / "prepared.json", prepared)


def validate_authorization(path: Path, plan: dict[str, Any], prepared: dict[str, Any]) -> None:
    auth = json.loads(path.read_text())
    wanted = {
        "schema": "UDM_LBLRTM_SINGLE_RUN_AUTH_V1",
        "authorized": True,
        "plan_sha256": digest(PLAN_PATH)[0],
        "runner_sha256": digest(Path(__file__))[0],
        "prepared_sha256": digest(RUN_DIR / "prepared.json")[0],
    }
    for key, value in wanted.items():
        if auth.get(key) != value:
            raise RuntimeError(f"authorization does not match {key}")
    if auth.get("scope") != "one stock GNU-double LBLRTM OD-only run; ICNTNM=1; NOCPL line-coupling diagnostic":
        raise RuntimeError("authorization scope mismatch")


def output_inventory(run_dir: Path) -> list[dict[str, Any]]:
    excluded = {"TAPE5", "TAPE3", "FSCDXS", "absco-ref_wv-mt-ckd.nc", "prepared.json", "launch.json", "execution.json", "execution-details.json", "postflight.json", "stdout.log", "stderr.log", "authorization.json"}
    rows = []
    for p in sorted(run_dir.rglob("*")):
        if p.is_symlink() or p.is_dir():
            continue
        rel = p.relative_to(run_dir).as_posix()
        if rel in excluded:
            continue
        h, size = digest(p)
        rows.append({"path": rel, "sha256": h, "size_bytes": size})
    return rows


def run_once(plan: dict[str, Any], authorization: Path) -> int:
    if not RUN_DIR.is_dir():
        raise RuntimeError("run --prepare first")
    prepared_path = RUN_DIR / "prepared.json"
    if not prepared_path.is_file():
        raise RuntimeError("prepared receipt is missing")
    prepared = json.loads(prepared_path.read_text())
    validate_authorization(authorization, plan, prepared)
    if any((RUN_DIR / name).exists() for name in ("launch.json", "execution.json", "execution-details.json", "postflight.json")):
        raise RuntimeError("this one-use case already has a launch/execution receipt")
    if authorization.resolve().is_relative_to(RUN_DIR.resolve()):
        raise RuntimeError("authorization must be supplied externally, not from inside the case directory")
    resolved = verify_all(plan)
    current_inputs = inventory_inputs(RUN_DIR, plan)
    if current_inputs != prepared["inputs"]:
        raise RuntimeError("staged inputs differ from prepared receipt")
    # New case directory means no stale output can be mistaken for this run.
    existing = output_inventory(RUN_DIR)
    if existing:
        raise RuntimeError("unexpected files exist before launch; refusing to run")
    auth_copy = RUN_DIR / "authorization.json"
    auth_copy.write_bytes(authorization.read_bytes())
    home_before = os.environ.get("HOME")
    if home_before is None:
        raise RuntimeError("HOME is not set; refusing to launch")
    env = {
        "HOME": home_before,
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "LD_LIBRARY_PATH": plan["ld_library_path"],
    }
    command = [str(resolved["executable"])]
    start = time.time()
    proc = None
    launch = {
        "schema": "UDM_LBLRTM_LAUNCH_IDENTITY_V1",
        "command": command,
        "cwd": str(RUN_DIR),
        "started_epoch": start,
        "pid": None,
        "timeout_seconds": TIMEOUT_SECONDS,
        "environment_controls": {"HOME_unchanged": True, "HOME_was_set": True, "PATH": env["PATH"], "LANG": env["LANG"], "LC_ALL": env["LC_ALL"], "LD_LIBRARY_PATH": env["LD_LIBRARY_PATH"]},
        "executable_sha256": digest(resolved["executable"])[0],
        "authorization_sha256": digest(auth_copy)[0],
    }
    try:
        with (RUN_DIR / "stdout.log").open("xb") as stdout, (RUN_DIR / "stderr.log").open("xb") as stderr:
            proc = subprocess.Popen(command, cwd=RUN_DIR, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, start_new_session=True)
            launch["pid"] = proc.pid
            durable_json(RUN_DIR / "launch.json", launch)
            timed_out = False
            try:
                actual_rc = proc.wait(timeout=TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    actual_rc = proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    actual_rc = proc.wait(timeout=10)
        # Crucial ordering: persist actual child RC before hashing logs or inspecting outputs.
        execution = {
            "schema": "UDM_LBLRTM_CHILD_EXECUTION_V1",
            "status": "TIMED_OUT" if timed_out else ("CHILD_RC0" if actual_rc == 0 else "CHILD_NONZERO_RC"),
            "pid": proc.pid,
            "command": command,
            "cwd": str(RUN_DIR),
            "started_epoch": start,
            "ended_epoch": time.time(),
            "timeout_seconds": TIMEOUT_SECONDS,
            "timed_out": timed_out,
            "actual_child_returncode": actual_rc,
            "home_unchanged": os.environ.get("HOME") == home_before,
        }
        durable_json(RUN_DIR / "execution.json", execution)
        details = {
            "schema": "UDM_LBLRTM_EXECUTION_DETAILS_V1",
            "execution_sha256": digest(RUN_DIR / "execution.json")[0],
            "launch_receipt_sha256": digest(RUN_DIR / "launch.json")[0],
            "authorization_sha256": digest(auth_copy)[0],
            "executable_sha256": digest(resolved["executable"])[0],
            "prepared_sha256": digest(prepared_path)[0],
            "stdout": _filepin(RUN_DIR / "stdout.log"),
            "stderr": _filepin(RUN_DIR / "stderr.log"),
        }
        durable_json(RUN_DIR / "execution-details.json", details)
    except BaseException as exc:
        actual_rc = None
        if proc is not None:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=10)
                except Exception:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except Exception:
                        pass
                    proc.wait()
            actual_rc = proc.returncode
        failure = {
            "schema": "UDM_LBLRTM_CHILD_EXECUTION_V1",
            "status": "RUNNER_EXCEPTION_AFTER_LAUNCH" if proc is not None else "LAUNCH_FAILED",
            "pid": proc.pid if proc is not None else None,
            "actual_child_returncode": actual_rc,
            "exception": repr(exc),
            "started_epoch": start,
            "ended_epoch": time.time(),
            "home_unchanged": os.environ.get("HOME") == home_before,
        }
        if not (RUN_DIR / "execution.json").exists():
            durable_json(RUN_DIR / "execution.json", failure)
        raise
    artifacts = output_inventory(RUN_DIR)
    post = {
        "schema": "UDM_LBLRTM_OD_POSTFLIGHT_V1",
        "status": ("OUTPUTS_INVENTORIED_CHILD_RC0" if actual_rc == 0 and not execution["timed_out"] else "OUTPUTS_INVENTORIED_CHILD_FAILURE"),
        "execution_sha256": digest(RUN_DIR / "execution.json")[0],
        "actual_child_returncode": actual_rc,
        "output_file_count": len(artifacts),
        "outputs": artifacts,
        "scope": "stock LBLRTM OD-only; ICNTNM=1; not a complete gas-point absorption or radiance result",
    }
    durable_json(RUN_DIR / "postflight.json", post)
    return actual_rc


def _filepin(path: Path) -> dict[str, Any]:
    h, size = digest(path)
    return {"path": path.name, "sha256": h, "size_bytes": size}


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true", help="verify and stage inputs only; no LBLRTM launch")
    mode.add_argument("--launch", action="store_true", help="requires a matching external root authorization JSON")
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args()
    try:
        plan = load_plan()
        if args.prepare:
            prepare(plan)
            print(json.dumps({"status": "READY_NOT_RUN", "prepared": str(RUN_DIR / "prepared.json"), "input_count": len(json.loads((RUN_DIR / "prepared.json").read_text())["inputs"])}))
            return 0
        if args.authorization is None:
            raise RuntimeError("--launch requires --authorization from root review")
        return run_once(plan, args.authorization.resolve(strict=True))
    except Exception as exc:
        print(f"runner error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
