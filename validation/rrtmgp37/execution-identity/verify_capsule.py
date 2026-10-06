#!/usr/bin/env python3
"""Verify a closed, byte-pinned single-execution identity capsule."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


class GateError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise GateError(message)


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise GateError(f"cannot parse JSON {path}: {exc}") from exc


def sha_file(path):
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def safe_rel(text):
    require(isinstance(text, str) and text, "empty/non-string relative path")
    p = Path(text)
    require(not p.is_absolute() and ".." not in p.parts and "" not in p.parts,
            f"unsafe relative path: {text!r}")
    require(p.as_posix() == text and text not in (".", "manifest.json"),
            f"noncanonical or reserved path: {text!r}")
    return p


def no_symlink_components(root, rel, allow_internal_symlinks=False):
    cur = root
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            require(allow_internal_symlinks, f"symlink path component rejected: {cur}")
            target = cur.resolve(strict=True)
            require(target.is_relative_to(root.resolve(strict=True)), f"symlink escapes root: {cur}")
    resolved_root = root.resolve(strict=True)
    resolved = cur.resolve(strict=True)
    require(resolved == resolved_root or resolved.is_relative_to(resolved_root),
            f"path escapes root: {rel}")
    return cur


def pin_matches(path, item):
    require(path.is_file(), f"referenced file missing/not regular: {path}")
    digest, size = sha_file(path)
    require(digest == item.get("sha256"), f"SHA-256 mismatch: {path}")
    require(size == item.get("size_bytes"), f"size mismatch: {path}")
    return path


def ref_key(ref):
    """Compare byte identities while ignoring descriptive table-link labels."""
    return (ref.get("root"), ref.get("path"), ref.get("sha256"), ref.get("size_bytes"))


def reject_symlink_components(path):
    path = Path(os.path.abspath(path))
    for component in reversed((path, *path.parents)):
        require(not component.is_symlink(), f"symlink path component rejected: {component}")


def capsule_inventory(root, manifest):
    files = manifest.get("files")
    require(isinstance(files, list), "manifest.files must be a list")
    expected = {}
    for item in files:
        require(isinstance(item, dict), "manifest file entry must be an object")
        rel = safe_rel(item.get("path"))
        key = rel.as_posix()
        require(key not in expected, f"duplicate manifest path: {key}")
        require(isinstance(item.get("sha256"), str) and len(item["sha256"]) == 64,
                f"invalid SHA-256 for {key}")
        require(type(item.get("size_bytes")) is int and item["size_bytes"] >= 0,
                f"invalid size for {key}")
        expected[key] = item

    actual = set()
    for path in root.rglob("*"):
        if path == root / "manifest.json":
            continue
        require(not path.is_symlink(), f"capsule contains symlink: {path.relative_to(root)}")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    require(actual == set(expected),
            f"capsule roster mismatch: missing={sorted(set(expected)-actual)} extra={sorted(actual-set(expected))}")
    for rel, item in expected.items():
        pin_matches(no_symlink_components(root, Path(rel)), item)
    return expected


def parse_roots(values):
    roots = {}
    for value in values:
        require("=" in value, "--root must be NAME=PATH")
        name, path = value.split("=", 1)
        require(name and name not in roots and Path(name).name == name,
                f"invalid/duplicate root name: {name!r}")
        resolved = Path(path).resolve(strict=True)
        require(resolved.is_dir(), f"root is not a directory: {path}")
        roots[name] = resolved
    return roots


def resolve_ref(ref, capsule, roots, roster):
    require(isinstance(ref, dict), "byte reference must be an object")
    root_name = ref.get("root")
    rel = safe_rel(ref.get("path"))
    require(root_name in ("capsule", *roots.keys()), f"unknown reference root: {root_name!r}")
    if root_name == "capsule":
        key = rel.as_posix()
        require(key in roster, f"capsule reference is not in closed roster: {key}")
        item = roster[key]
        require(item["sha256"] == ref.get("sha256") and item["size_bytes"] == ref.get("size_bytes"),
                f"capsule reference pin disagrees with manifest: {key}")
        root = capsule
    else:
        root = roots[root_name]
    path = no_symlink_components(root, rel)
    pin_matches(path, ref)
    return path


def check_source(identity, capsule, roots, roster):
    source = identity.get("source")
    require(isinstance(source, dict) and source.get("clean") is True,
            "source must explicitly attest a clean worktree")
    require(source.get("head") and source.get("tree"), "source head/tree missing")
    pre_ref = source.get("manifest_pre")
    post_ref = source.get("manifest_post")
    pre_path = resolve_ref(pre_ref, capsule, roots, roster)
    post_path = resolve_ref(post_ref, capsule, roots, roster)
    pre_sm = load_json(pre_path)
    post_sm = load_json(post_path)
    require(pre_sm == post_sm, "source pre/post manifest contents differ")
    sm = pre_sm
    require(sm.get("head") == source["head"] and sm.get("tree") == source["tree"],
            "source manifest head/tree do not join identity")
    require(sm.get("clean") is True, "source manifest is not clean")
    entries = sm.get("files")
    require(isinstance(entries, list) and entries, "source manifest has no tracked file roster")
    seen = set()
    source_root_name = source.get("root")
    require(source_root_name in roots, "source.root must name an explicit external root")
    source_root = roots[source_root_name]
    try:
        head = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD"],
                              check=True, capture_output=True, text=True, timeout=60).stdout.strip()
        tree = subprocess.run(["git", "-C", str(source_root), "rev-parse", "HEAD^{tree}"],
                              check=True, capture_output=True, text=True, timeout=60).stdout.strip()
        status = subprocess.run(["git", "-C", str(source_root), "status", "--porcelain=v1",
                                 "--untracked-files=all"], check=True, capture_output=True, text=True,
                                timeout=60).stdout
        tracked_raw = subprocess.run(["git", "-C", str(source_root), "ls-files", "-s", "-z"],
                                     check=True, capture_output=True, timeout=60).stdout
    except Exception as exc:
        raise GateError(f"cannot authenticate source Git tree: {exc}") from exc
    require(head == source["head"] and tree == source["tree"], "source Git HEAD/tree mismatch")
    require(status == "", "source Git worktree is not clean")
    git_records = {}
    for raw in tracked_raw.split(b"\0"):
        if not raw:
            continue
        meta, rawpath = raw.split(b"\t", 1)
        mode, blob, _stage = meta.decode("ascii").split()
        git_records[rawpath.decode("utf-8", errors="surrogateescape")] = {"mode": mode, "blob": blob}
    tracked = set(git_records)
    symlinks = sm.get("symlinks", [])
    require(isinstance(symlinks, list), "source symlinks must be a list")
    declared = {safe_rel(entry.get("path")).as_posix() for entry in entries if isinstance(entry, dict)}
    link_paths = {safe_rel(entry.get("path")).as_posix() for entry in symlinks if isinstance(entry, dict)}
    require(not declared.intersection(link_paths) and declared | link_paths == tracked,
            "source manifest files/symlinks do not exactly match git ls-files roster")
    for entry in entries:
        require(isinstance(entry, dict), "bad source file record")
        rel = safe_rel(entry.get("path"))
        key = rel.as_posix()
        require(key not in seen, f"duplicate source path: {key}")
        seen.add(key)
        is_git_link = git_records.get(key, {}).get("mode") == "120000"
        parent_rel = Path(*rel.parts[:-1]) if len(rel.parts) > 1 else Path(".")
        if str(parent_rel) != ".":
            no_symlink_components(source_root, parent_rel, allow_internal_symlinks=True)
        p = source_root / rel
        if is_git_link:
            require(p.is_symlink(), f"tracked source symlink missing: {key}")
            # Git tracks a symlink's literal target bytes. Do not follow a source-tree
            # link: unused external/dangling vendor links are identity data, not inputs.
            target_text = os.readlink(p)
            require(entry.get("kind") == "symlink" and
                    entry.get("target_text", entry.get("target")) == target_text,
                    f"source symlink target mismatch: {key}")
            require(entry.get("git_blob") == git_records[key]["blob"], f"source symlink blob mismatch: {key}")
        else:
            require(not p.is_symlink(), f"source regular file is an unexpected symlink: {key}")
            require(entry.get("kind", "file") == "file", f"source kind mismatch: {key}")
            require(p.resolve(strict=True).is_relative_to(source_root.resolve(strict=True)),
                    f"source file escapes root: {key}")
            pin_matches(p, entry)
    require(seen == declared, "source regular-file manifest roster mismatch")
    symlink_seen = set()
    for entry in symlinks:
        require(isinstance(entry, dict), "bad source symlink record")
        rel = safe_rel(entry.get("path"))
        key = rel.as_posix()
        require(key not in symlink_seen and git_records.get(key, {}).get("mode") == "120000",
                f"invalid/duplicate source symlink record: {key}")
        symlink_seen.add(key)
        path = source_root / rel
        require(path.is_symlink(), f"tracked source symlink missing: {key}")
        require(os.readlink(path) == entry.get("target_text"), f"source symlink literal mismatch: {key}")
        require(git_records[key]["blob"] == entry.get("git_blob"), f"source symlink blob mismatch: {key}")


def parse_namelist_policy(text):
    def group_text(group):
        match = re.search(r"(?ims)^\s*&" + re.escape(group) + r"\b(.*?)^\s*/", text)
        require(match is not None, f"namelist group &{group} missing")
        return match.group(1)
    def assignment(group_body, key):
        matches = re.findall(r"(?im)^\s*" + re.escape(key) + r"\s*=\s*([^,\n/]+)", group_body)
        require(len(matches) == 1, f"namelist key {key} must occur exactly once")
        return matches[0].strip().strip("'").strip('"').lower()
    domains = group_text("domains")
    require(int(assignment(domains, "max_dom")) == 1, "namelist max_dom is not 1")
    physics = group_text("physics")
    return {key: assignment(physics, key) for key in
            ("mp_physics", "ra_lw_physics", "ra_sw_physics", "use_mp_re", "cu_physics")}


def process_record(receipt_ref, capsule, roots, roster):
    require(isinstance(receipt_ref, dict), "process_receipt missing")
    ref = receipt_ref.get("ref", receipt_ref)
    doc = load_json(resolve_ref(ref, capsule, roots, roster))
    if "children" not in doc:
        require("index" not in receipt_ref, "process receipt index supplied for scalar record")
        return doc
    index = receipt_ref.get("index")
    require(type(index) is int and 0 <= index < len(doc["children"]), "process receipt child index invalid")
    return doc["children"][index]


def check_build(identity, capsule, roots, roster):
    build = identity.get("build")
    require(isinstance(build, dict), "build identity missing")
    receipts = build.get("receipts")
    require(isinstance(receipts, dict) and {"configure", "build", "install"} <= set(receipts),
            "configure/build/install receipts required")
    for name in ("configure", "build", "install"):
        entry = receipts[name]
        receipt_path = resolve_ref(entry.get("file"), capsule, roots, roster)
        rec = load_json(receipt_path)
        require(rec.get("status") == entry.get("expected_status"), f"{name} receipt status mismatch")
        require(rec.get("actual_child_RC") == 0, f"{name} child did not exit zero")
        require(entry.get("actual_rc") == 0, f"{name} summary child RC is not zero")
        require(rec.get("head") == identity["source"]["head"] and
                rec.get("tree") == identity["source"]["tree"],
                f"{name} receipt source identity mismatch")
    require(build.get("toolchain") is not None, "toolchain byte pin missing")
    resolve_ref(build["toolchain"], capsule, roots, roster)
    require(build.get("cmake_cache") is not None, "CMakeCache byte pin missing")
    resolve_ref(build["cmake_cache"], capsule, roots, roster)
    tools = build.get("tools")
    require(isinstance(tools, dict) and {"c_compiler", "fortran_compiler", "preprocessor", "cmake", "make", "netcdf_c", "netcdf_fortran"} <= set(tools),
            "actual compiler/preprocessor/build/NetCDF tool pins required")
    for tool in tools.values():
        resolve_ref(tool.get("binary"), capsule, roots, roster)
        require(tool.get("version"), "tool version string missing")
    dependencies = build.get("shared_dependencies")
    require(isinstance(dependencies, list) and dependencies, "resolved shared dependency pins required")
    for dep in dependencies:
        resolve_ref(dep, capsule, roots, roster)
    expected_cache = build.get("cmake_cache_values")
    require(isinstance(expected_cache, dict) and expected_cache, "selected CMakeCache values must be pinned")
    cache_path = resolve_ref(build["cmake_cache"], capsule, roots, roster)
    cache_text = cache_path.read_text(encoding="utf-8", errors="replace")
    parsed = {}
    for line in cache_text.splitlines():
        if line and not line.startswith("//") and not line.startswith("#") and ":" in line and "=" in line:
            left, value = line.split("=", 1)
            key, _kind = left.split(":", 1)
            parsed[key] = value
    require(all(parsed.get(key) == value for key, value in expected_cache.items()),
            "CMakeCache selected values mismatch")
    executables = build.get("executables")
    require(isinstance(executables, dict) and {"ideal", "wrf"} <= set(executables),
            "ideal and wrf executable pins required")
    for role in ("ideal", "wrf"):
        resolve_ref(executables[role], capsule, roots, roster)

    policy = identity.get("case_policy")
    require(isinstance(policy, dict), "case_policy missing")
    namelist_pin = policy.get("namelist")
    resolve_ref(namelist_pin, capsule, roots, roster)
    expected_domains = policy.get("domains")
    require(isinstance(expected_domains, list) and len(expected_domains) == 1,
            "single-domain case requires one explicit expected domain policy")
    require(all(isinstance(d, dict) and d.get("domain_id") == 1 and
                {"mp_physics", "ra_lw_physics", "ra_sw_physics", "use_mp_re"} <= set(d)
                for d in expected_domains), "domain policy is missing explicit physics flags")
    require(policy.get("domain_count", len(expected_domains)) == 1,
            "single-domain policy must declare exactly one domain")
    namelist_text = resolve_ref(namelist_pin, capsule, roots, roster).read_text(encoding="utf-8", errors="replace")
    observed = parse_namelist_policy(namelist_text)
    expected = {key: str(value).lower() for key, value in expected_domains[0].items() if key != "domain_id"}
    require(observed == expected, f"namelist physics policy mismatch: expected {expected}, observed {observed}")
    identity["_checked_namelist_pin"] = namelist_pin
    identity["_checked_expected_domains"] = expected_domains
    required_inputs = policy.get("required_inputs")
    require(isinstance(required_inputs, list) and required_inputs,
            "case_policy.required_inputs must be a nonempty list")
    for ref in required_inputs:
        resolve_ref(ref, capsule, roots, roster)
    identity["_checked_required_inputs"] = required_inputs


def check_execution(execution, identity, capsule, roots, roster):
    require(execution.get("run_id") == identity.get("run_id"), "execution run_id mismatch")
    children = execution.get("children")
    require(isinstance(children, list) and len(children) == 2, "expected exactly ideal and WRF child records")
    roles = [c.get("role") for c in children]
    require(roles == ["ideal", "wrf"], "child order/roles must be ideal then wrf")
    wrf_offered = next(c for c in children if c["role"] == "wrf").get("input_paths")
    require(isinstance(wrf_offered, list) and
            sorted(ref_key(r) for r in wrf_offered) ==
            sorted(ref_key(r) for r in identity.get("case_policy", {}).get("required_inputs", [])),
            "case_policy.required_inputs must exactly equal all inputs offered to WRF")
    for child in children:
        require(child.get("actual_rc") == 0 and child.get("status") == "COMPLETE",
                f"child did not complete with actual RC 0: {child.get('role')}")
        exeref = child.get("executable_pin")
        resolve_ref(exeref, capsule, roots, roster)
        expected = identity["build"]["executables"][child["role"]]
        require(exeref == expected, f"{child['role']} executable pin differs from build identity")
        plan_path = resolve_ref(child.get("input_plan"), capsule, roots, roster)
        plan = load_json(plan_path)
        expected_kind = "ideal" if child["role"] == "ideal" else "forecast"
        require(plan.get("kind") == expected_kind, f"{child['role']} input plan kind mismatch")
        plan_executable = plan.get("executable")
        install_root = roots.get("install")
        require(install_root is not None and isinstance(plan_executable, str),
                "input plan needs an absolute executable path and install root")
        plan_exe_path = Path(plan_executable).resolve(strict=True)
        require(plan_exe_path.is_relative_to(install_root), "input plan executable escapes install root")
        require(plan_exe_path == no_symlink_components(install_root,
                    Path(plan_exe_path.relative_to(install_root).as_posix())),
                "input plan executable path is not the installed executable")
        require(plan.get("sha256") == exeref.get("sha256") and plan.get("size_bytes") == exeref.get("size_bytes"),
                f"{child['role']} executable hash/size differs from its input plan")
        plan_inputs = plan.get("inputs")
        child_inputs = child.get("input_paths")
        require(isinstance(plan_inputs, list) and isinstance(child_inputs, list),
                f"{child['role']} input path roster missing")
        capsule_inputs = [r for r in child_inputs if r.get("root") == "capsule"]
        require([Path(r["path"]).as_posix() for r in capsule_inputs] == plan_inputs,
                f"{child['role']} capsule input paths differ from frozen plan")
        for input_ref in child_inputs:
            resolve_ref(input_ref, capsule, roots, roster)
        table_links = plan.get("table_links")
        require(isinstance(table_links, list), f"{child['role']} table_links must be a list")
        case_names = set()
        expected_table_refs = []
        for table in table_links:
            require(isinstance(table, dict) and table.get("case_name") and
                    table["case_name"] not in case_names, f"{child['role']} duplicate/invalid table link")
            case_names.add(table["case_name"])
            resolved = Path(table.get("resolved_path", "")).resolve(strict=True)
            require(resolved.is_relative_to(install_root), f"{child['role']} table link escapes install root")
            rel_table = resolved.relative_to(install_root).as_posix()
            table_ref = {"root":"install", "path":rel_table, "sha256":table.get("sha256"),
                         "size_bytes":table.get("size_bytes")}
            resolve_ref(table_ref, capsule, roots, roster)
            expected_table_refs.append(table_ref)
        if child["role"] == "wrf":
            table_names = {table["case_name"] for table in table_links}
            expected_tables = {"rrtmgp-clouds-lw-bnd.nc", "rrtmgp-clouds-sw-bnd.nc",
                               "rrtmgp-gas-lw-g128.nc", "rrtmgp-gas-sw-g112.nc"}
            require(expected_tables <= table_names, "WRF input plan omits a pinned RRTMGP table link")
            require(plan.get("capture") is True, "WRF forecast plan must explicitly enable capture")
            require(all(ref in child_inputs for ref in identity["_checked_required_inputs"]),
                    "WRF input plan omits a case-policy input")
        else:
            require(plan.get("capture") is False, "ideal plan must explicitly disable capture")
        external_input_refs = [r for r in child_inputs if r.get("root") == "install"]
        require(sorted(ref_key(r) for r in external_input_refs) ==
                sorted(ref_key(r) for r in expected_table_refs),
                f"{child['role']} offered installed-table inputs differ from plan table_links")
        process = process_record(child.get("process_receipt"), capsule, roots, roster)
        require(process.get("status") == "COMPLETE" and process.get("reaped") is True,
                f"{child['role']} process receipt is not reaped")
        require(process.get("timed_out") is False, f"{child['role']} process timed out")
        process_rc = process.get("returncode", process.get("actual_rc"))
        require(process_rc == child["actual_rc"] == 0,
                f"{child['role']} process RC does not join")
        process_argv = process.get("command", process.get("argv"))
        child_argv = child.get("command", child.get("argv"))
        require(process.get("pid") == child.get("pid") and process.get("started_unix") == child.get("started_unix") and
                process.get("ended_unix") == child.get("ended_unix") and process_argv == child_argv and
                process.get("cwd") == child.get("cwd"), f"{child['role']} process metadata does not join")
        require(isinstance(process.get("environment"), dict) and process["environment"],
                f"{child['role']} process environment not recorded")
        require(process.get("environment") == child.get("environment") and
                process.get("process_group", process.get("pid")) == child.get("process_group", child.get("pid")) and
                ("timed_out" not in child or process.get("timed_out") == child.get("timed_out")),
                f"{child['role']} environment/group/timeout summary mismatch")
        require(process.get("executable_sha256") == exeref.get("sha256") and
                process.get("executable_sha256_after") == exeref.get("sha256"),
                f"{child['role']} executable hashes differ across process")
        require(process.get("executable_size_bytes") == exeref.get("size_bytes") and
                process.get("executable_size_bytes_after") == exeref.get("size_bytes"),
                f"{child['role']} executable sizes differ across process")
        require(child.get("pid", 0) > 0 and child.get("ended_unix", 0) >= child.get("started_unix", 0),
                f"{child['role']} PID/time invalid")
        inputs = child.get("input_paths")
        require(isinstance(inputs, list) and inputs, f"{child['role']} input pins missing")
        for ref in inputs:
            resolve_ref(ref, capsule, roots, roster)
        if child["role"] == "wrf":
            require(identity["_checked_namelist_pin"] in inputs,
                    "WRF child inputs do not include the case-policy namelist")
            require(all(ref in inputs for ref in identity["_checked_required_inputs"]),
                    "WRF child inputs omit pinned runtime table/input files")


def check_outputs(outputs, identity, capsule, roots, roster):
    require(outputs.get("run_id") == identity.get("run_id"), "outputs run_id mismatch")
    entries = outputs.get("files")
    require(isinstance(entries, list) and entries, "output file roster missing")
    seen = set()
    for ref in entries:
        key = (ref.get("root"), ref.get("path"))
        require(key not in seen, f"duplicate output path: {key}")
        seen.add(key)
        resolve_ref(ref, capsule, roots, roster)
    runtime_ref = outputs.get("runtime_validation_ref")
    runtime_path = resolve_ref(runtime_ref, capsule, roots, roster)
    runtime = load_json(runtime_path)
    require(runtime.get("status") == "PASS_SCOPED_STARTUP_SNOW_RUNTIME_ONLY" and
            runtime.get("ideal_invocations") == 1 and runtime.get("models_invoked") == 1 and
            runtime.get("forecast_attempts") == 1, "startup-snow runtime validation scope mismatch")
    require(len(runtime.get("arms_completed", [])) == 1, "expected one completed runtime arm")
    arm = runtime["arms_completed"][0]
    execution_path = resolve_ref({"root":"capsule", **roster["execution.json"]}, capsule, roots, roster)
    wrf_child = next(c for c in load_json(execution_path)["children"] if c["role"] == "wrf")
    proc = process_record(wrf_child["process_receipt"], capsule, roots, roster)
    runtime_proc = arm.get("process", {})
    require(runtime_proc.get("returncode") == 0 and runtime_proc.get("pid") == proc.get("pid") and
            runtime_proc.get("executable_sha256") == proc.get("executable_sha256"),
            "runtime report WRF invocation does not join child receipt")
    require(runtime_proc.get("started_unix") == proc.get("started_unix") and
            runtime_proc.get("ended_unix") == proc.get("ended_unix") and
            runtime_proc.get("cwd") == proc.get("cwd") and
            runtime_proc.get("command", runtime_proc.get("argv")) == proc.get("command", proc.get("argv")) and
            runtime_proc.get("environment") == proc.get("environment") and
            runtime_proc.get("executable_sha256_after") == proc.get("executable_sha256_after") and
            runtime_proc.get("reaped") is True and runtime_proc.get("timed_out") is False,
            "runtime arm process record differs from observed child process")
    report_ref = outputs.get("validation_report_path")
    report_path = resolve_ref(report_ref, capsule, roots, roster)
    report = load_json(report_path)
    require(report.get("run_id") == identity.get("run_id"), "validation report run_id mismatch")
    require(report.get("source_head") == identity["source"]["head"] and
            report.get("source_tree") == identity["source"]["tree"],
            "validation report source identity mismatch")
    require(report.get("status") == "PASS_ENGINEERING_IDENTITY", "validation report is not a pass")
    require(report.get("physical_status") == "NOT_ACCEPTED", "physical status must remain NOT_ACCEPTED")
    require(report.get("runtime_validation_ref") == runtime_ref, "validation report runtime reference mismatch")
    require(report_ref in entries, "validation report must appear in output roster")
    selection_report = report.get("selected_layer")
    require(isinstance(selection_report, dict) and set(selection_report) == {"LW", "SW"},
            "validation report must contain exactly LW/SW selected-layer records")
    selection = {}
    for scheme in ("LW", "SW"):
        capture = arm.get("startup_capture", {}).get(scheme)
        selected = selection_report[scheme]
        require(isinstance(capture, dict) and capture == selected,
                f"{scheme} runtime capture differs from validation report")
        level = selected.get("fixture_level_native_and_adapter_zero_based")
        require(type(level) is int, f"{scheme} selected layer is not an integer")
        if "level_native_zero_based" in selection:
            require(level == selection["level_native_zero_based"], "LW/SW selected levels differ")
        selection["level_native_zero_based"] = level
    column_text = runtime_proc.get("environment", {}).get("column_selection", "")
    column_match = re.search(r"\((\d+)\s*,\s*(\d+)\)", column_text)
    require(column_match is not None, "runtime process has no parseable column selection")
    selection["i"], selection["j"] = int(column_match.group(1)), int(column_match.group(2))
    history_matches = [r for r in entries if r.get("sha256") == arm.get("history_sha256")]
    require(len(history_matches) == 1,
            "runtime report history hash does not join output file")
    namelist_outputs = [r for r in entries if r.get("path", "").endswith("namelist.output") and
                        Path(r["path"]).parent.name == Path(proc.get("cwd", "")).name]
    require(len(namelist_outputs) == 1, "expected one forecast namelist.output matching WRF child cwd")
    output_policy = parse_namelist_policy(resolve_ref(namelist_outputs[0], capsule, roots, roster).read_text(
        encoding="utf-8", errors="replace"))
    expected_policy = {key: str(value).lower() for key, value in
                       identity["_checked_expected_domains"][0].items() if key != "domain_id"}
    require(output_policy == expected_policy, "namelist.output policy differs from expected case policy")
    history_ref = report.get("history")
    require(isinstance(history_ref, dict) and history_ref in entries,
            "validation report history must be an exact output reference")
    require(history_ref.get("sha256") == arm.get("history_sha256"),
            "validation report history hash mismatch")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--expected-manifest-sha256", help="trusted out-of-band digest for manifest.json")
    args = parser.parse_args(argv)
    try:
        manifest_input = Path(os.path.abspath(args.manifest))
        require(manifest_input.name == "manifest.json", "manifest must be named manifest.json")
        reject_symlink_components(manifest_input)
        manifest_path = manifest_input.resolve(strict=True)
        if args.expected_manifest_sha256:
            digest, _size = sha_file(manifest_path)
            require(digest == args.expected_manifest_sha256.lower(), "manifest trust-anchor SHA-256 mismatch")
        capsule = manifest_path.parent.resolve(strict=True)
        manifest = load_json(manifest_path)
        require(manifest.get("schema") == "wrf-single-execution-capsule-v1", "unsupported manifest schema")
        require(manifest.get("run_id"), "manifest run_id missing")
        roots = parse_roots(args.root)
        roster = capsule_inventory(capsule, manifest)
        for name in ("identity.json", "execution.json", "outputs.json"):
            require(name in roster, f"required capsule record absent: {name}")
        identity = load_json(resolve_ref({"root":"capsule", **roster["identity.json"]}, capsule, roots, roster))
        execution = load_json(resolve_ref({"root":"capsule", **roster["execution.json"]}, capsule, roots, roster))
        outputs = load_json(resolve_ref({"root":"capsule", **roster["outputs.json"]}, capsule, roots, roster))
        require(identity.get("run_id") == manifest["run_id"], "identity run_id mismatch")
        require(identity.get("physical_status") == "NOT_ACCEPTED", "identity physical status must be NOT_ACCEPTED")
        check_source(identity, capsule, roots, roster)
        check_build(identity, capsule, roots, roster)
        check_execution(execution, identity, capsule, roots, roster)
        check_outputs(outputs, identity, capsule, roots, roster)
        print(json.dumps({"status":"PASS_ENGINEERING_IDENTITY", "physical_status":"NOT_ACCEPTED",
                          "run_id":manifest["run_id"], "capsule_files":len(roster),
                          "external_roots":sorted(roots)}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status":"FAIL_IDENTITY", "error":str(exc)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
