#!/usr/bin/env python3
"""Synthetic capsule schema, join, and tamper tests; no WRF/build is run."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

VERIFY = Path(__file__).resolve().parents[1] / "verify_capsule.py"


def digest(path):
    data = Path(path).read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    return path


def pin(root_name, root, rel):
    p = Path(root) / rel
    sha, size = digest(p)
    return {"root": root_name, "path": rel, "sha256": sha, "size_bytes": size}


def jsonfile(path, data):
    return write(path, json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")


class CapsuleFixture:
    def __init__(self, base):
        self.base = Path(base)
        self.cap, self.src = self.base / "capsule", self.base / "src"
        self.bld, self.inst = self.base / "bld", self.base / "inst"
        for p in (self.cap, self.src, self.bld, self.inst):
            p.mkdir(parents=True)
        write(self.src / "tracked.f90", "program dummy\nend\n")
        subprocess.run(["git", "init", "-q", str(self.src)], check=True)
        subprocess.run(["git", "-C", str(self.src), "-c", "user.name=fixture", "-c",
                        "user.email=fixture@example.invalid", "add", "tracked.f90"], check=True)
        subprocess.run(["git", "-C", str(self.src), "-c", "user.name=fixture", "-c",
                        "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
        self.head = subprocess.run(["git", "-C", str(self.src), "rev-parse", "HEAD"],
                                   check=True, text=True, capture_output=True).stdout.strip()
        self.tree = subprocess.run(["git", "-C", str(self.src), "rev-parse", "HEAD^{tree}"],
                                   check=True, text=True, capture_output=True).stdout.strip()
        srcpin = pin("source", self.src, "tracked.f90")
        self.source_manifest = {"head": self.head, "tree": self.tree, "clean": True,
            "files": [{"path": "tracked.f90", "kind": "file", "sha256": srcpin["sha256"],
                       "size_bytes": srcpin["size_bytes"]}], "symlinks": []}

        for rel, text in (("toolchain.cmake", "toolchain"),
                          ("bin/gfortran", "compiler"), ("bin/gcc", "cc"),
                          ("bin/cpp", "cpp"), ("bin/cmake", "cmake"), ("bin/make", "make"),
                          ("bin/nc-config", "netcdf-c"), ("bin/nf-config", "netcdf-f"),
                          ("lib/libfixture.so", "shared")):
            write(self.bld / rel, text)
        write(self.bld / "CMakeCache.txt", "WRF_CORE:STRING=ARW\nWRF_CASE:STRING=EM_SCM_XY\nUSE_ALLOCATABLES:BOOL=ON\n")
        for rel, text in (("bin/ideal", "ideal executable"), ("bin/wrf", "wrf executable")):
            write(self.inst / rel, text)
        self.exe_pins = {role: pin("install", self.inst, f"bin/{role}") for role in ("ideal", "wrf")}

        self.plan_specs = {}
        self.child_inputs = {}
        for role in ("ideal", "wrf"):
            case = "ideal" if role == "ideal" else "forecast"
            case_dir = self.cap / "inputs" / case
            case_names = ["force_ideal.nc", "input_soil", "input_sounding", "namelist.input",
                          "radiation_iofields.txt"] + (["wrfinput_d01"] if role == "wrf" else [])
            refs = []
            for name in case_names:
                content = ("&domains\n max_dom=1,\n/\n&physics\n mp_physics=27,\n ra_lw_physics=37,\n"
                           " ra_sw_physics=37,\n use_mp_re=1,\n cu_physics=0,\n/\n") if name == "namelist.input" else name + " bytes\n"
                write(case_dir / name, content)
                refs.append(pin("capsule", self.cap, f"inputs/{case}/{name}"))

            tables = []
            table_refs = []
            for name in ("rrtmgp-clouds-lw-bnd.nc", "rrtmgp-clouds-sw-bnd.nc",
                         "rrtmgp-gas-lw-g128.nc", "rrtmgp-gas-sw-g112.nc"):
                write(self.inst / "run" / name, name + " coefficients\n")
                item = pin("install", self.inst, f"run/{name}")
                table_refs.append(item)
                tables.append({"case_name": name, "resolved_path": str((self.inst / item["path"]).resolve()),
                               "sha256": item["sha256"], "size_bytes": item["size_bytes"]})
            executable = self.exe_pins[role]
            plan = {"kind": "ideal" if role == "ideal" else "forecast",
                    "executable": str((self.inst / executable["path"]).resolve()),
                    "sha256": executable["sha256"], "size_bytes": executable["size_bytes"],
                    "inputs": [ref["path"] for ref in refs], "table_links": tables,
                    "capture": role == "wrf"}
            plan_path = f"plans/{plan['kind']}.json"
            jsonfile(self.cap / plan_path, plan)
            plan_ref = pin("capsule", self.cap, plan_path)
            self.plan_specs[role] = (plan, plan_ref)
            self.child_inputs[role] = refs + table_refs

        # Both output namelists are retained. The forecast one is selected by its run-directory name.
        self.case_dirs = {"ideal": "shared-seed", "wrf": "candidate-case"}
        self.namelist_paths = {}
        for role in ("ideal", "wrf"):
            source = self.cap / "inputs" / ("ideal" if role == "ideal" else "forecast") / "namelist.input"
            rel = f"outputs/runtime/{self.case_dirs[role]}/namelist.output"
            write(self.cap / rel, source.read_bytes())
            self.namelist_paths[role] = rel

        build_receipts = {}
        for key, status in (("configure", "PASS_CONFIGURE"), ("build", "PASS_BUILD"), ("install", "PASS_INSTALL")):
            rel = f"receipts/{key}.json"
            jsonfile(self.bld / rel, {"status": status, "actual_child_RC": 0,
                                      "head": self.head, "tree": self.tree})
            build_receipts[key] = {"file": pin("build", self.bld, rel),
                                   "expected_status": status, "actual_rc": 0}
        self.identity = {
            "run_id": "fixture-001", "physical_status": "NOT_ACCEPTED",
            "source": {"root": "source", "head": self.head, "tree": self.tree, "clean": True},
            "build": {"receipts": build_receipts,
                "toolchain": pin("build", self.bld, "toolchain.cmake"),
                "cmake_cache": pin("build", self.bld, "CMakeCache.txt"),
                "cmake_cache_values": {"WRF_CORE": "ARW", "WRF_CASE": "EM_SCM_XY", "USE_ALLOCATABLES": "ON"},
                "tools": {name: {"binary": pin("build", self.bld, rel), "version": "fixture 1"}
                    for name, rel in (("c_compiler", "bin/gcc"), ("fortran_compiler", "bin/gfortran"),
                        ("preprocessor", "bin/cpp"), ("cmake", "bin/cmake"), ("make", "bin/make"),
                        ("netcdf_c", "bin/nc-config"), ("netcdf_fortran", "bin/nf-config"))},
                "shared_dependencies": [pin("build", self.bld, "lib/libfixture.so")],
                "executables": self.exe_pins},
            "case_policy": {"namelist": pin("capsule", self.cap, "inputs/forecast/namelist.input"),
                "domains": [{"domain_id": 1, "mp_physics": 27, "ra_lw_physics": 37,
                             "ra_sw_physics": 37, "use_mp_re": 1, "cu_physics": 0}],
                "required_inputs": self.child_inputs["wrf"]}}

        jsonfile(self.cap / "source-manifest.json", self.source_manifest)
        shutil.copyfile(self.cap / "source-manifest.json", self.cap / "source-post-manifest.json")
        self.identity["source"]["manifest_pre"] = pin("capsule", self.cap, "source-manifest.json")
        self.identity["source"]["manifest_post"] = pin("capsule", self.cap, "source-post-manifest.json")
        jsonfile(self.cap / "identity.json", self.identity)

        self.processes = {}
        children = []
        for role, pid in (("ideal", 101), ("wrf", 102)):
            plan, plan_ref = self.plan_specs[role]
            exe = self.exe_pins[role]
            case_dir = self.case_dirs[role]
            cwd = f"/fixture/run/{case_dir}"
            command = ["/usr/bin/timeout", "10s", f"/fixture/install/{exe['path']}"]
            process = {"status": "COMPLETE", "reaped": True, "timed_out": False, "returncode": 0,
                "pid": pid, "process_group": pid, "started_unix": float(pid), "ended_unix": float(pid + 1),
                "command": command, "cwd": cwd, "environment": {"OMP_NUM_THREADS": "1",
                    "capture_enabled": role == "wrf", "column_selection": "default (1,1)"},
                "executable": command[-1], "executable_sha256": exe["sha256"],
                "executable_sha256_after": exe["sha256"], "executable_size_bytes": exe["size_bytes"],
                "executable_size_bytes_after": exe["size_bytes"]}
            proc_rel = f"outputs/runtime/{case_dir}/process-result.json"
            jsonfile(self.cap / proc_rel, process)
            proc_ref = pin("capsule", self.cap, proc_rel)
            self.processes[role] = process
            children.append({"role": role, "actual_rc": 0, "status": "COMPLETE", "pid": pid,
                "started_unix": process["started_unix"], "ended_unix": process["ended_unix"],
                "argv": command, "cwd": cwd, "environment": process["environment"],
                "executable_pin": exe, "input_paths": self.child_inputs[role],
                "input_plan": plan_ref, "process_receipt": proc_ref})
        jsonfile(self.cap / "execution.json", {"run_id": "fixture-001", "children": children})

        self.history_rel = "outputs/runtime/candidate-case/wrfout_d01_2000-01-01_00:01:00"
        write(self.cap / self.history_rel, b"synthetic history bytes\n")
        self.history_ref = pin("capsule", self.cap, self.history_rel)
        capture = {scheme: {"adapter_layers": 5, "native_layers": 4,
            "fixture_level_native_and_adapter_zero_based": 2, "optical_band_count": n,
            "optical_dimension_label": "spectral bands", "cf": 1.0, "qs": 1e-4,
            "rwp_grid": 0.0, "swp_grid": 1.0, "source_re_snow_m": 1e-5,
            "startup_radius_m": 1e-4, "prepared_res_um": 100.0,
            "precip_tau_threshold": 1e-12, "precip_tau_above_threshold_count": n,
            "precip_tau_floor_source": "fixture" if scheme == "SW" else None}
            for scheme, n in (("LW", 16), ("SW", 14))}
        wrf_proc = self.processes["wrf"]
        runtime = {"status": "PASS_SCOPED_STARTUP_SNOW_RUNTIME_ONLY", "run_id": "fixture-001",
            "ideal_invocations": 1, "models_invoked": 1, "forecast_attempts": 1,
            "arms_completed": [{"arm": "candidate-case", "history_sha256": self.history_ref["sha256"],
                "process": wrf_proc, "startup_capture": capture}]}
        jsonfile(self.cap / "outputs/runtime/execution.json", runtime)
        runtime_ref = pin("capsule", self.cap, "outputs/runtime/execution.json")
        namelist_refs = [pin("capsule", self.cap, self.namelist_paths[r]) for r in ("ideal", "wrf")]
        log_rel = "outputs/runtime/candidate-case/wrf.log"
        write(self.cap / log_rel, "SUCCESS COMPLETE WRF\n")
        log_ref = pin("capsule", self.cap, log_rel)
        validation = {"run_id": "fixture-001", "source_head": self.head, "source_tree": self.tree,
            "history": self.history_ref, "selected_layer": capture, "status": "PASS_ENGINEERING_IDENTITY",
            "physical_status": "NOT_ACCEPTED", "runtime_validation_ref": runtime_ref}
        jsonfile(self.cap / "validation-report.json", validation)
        report_ref = pin("capsule", self.cap, "validation-report.json")
        jsonfile(self.cap / "outputs.json", {"run_id": "fixture-001",
            "files": [self.history_ref, *namelist_refs, log_ref, runtime_ref, report_ref],
            "runtime_validation_ref": runtime_ref, "validation_report_path": report_ref})
        self.reseal()

    def reseal(self):
        entries = []
        for p in sorted(self.cap.rglob("*")):
            if p.is_file() and p != self.cap / "manifest.json":
                sha, size = digest(p)
                entries.append({"path": p.relative_to(self.cap).as_posix(), "sha256": sha, "size_bytes": size})
        jsonfile(self.cap / "manifest.json", {"schema": "wrf-single-execution-capsule-v1",
            "run_id": "fixture-001", "files": entries})

    def verify(self, cwd=None, expected_sha=None):
        cmd = [sys.executable, "-I", "-S", str(VERIFY), str(self.cap / "manifest.json"),
               "--root", f"source={self.src}", "--root", f"build={self.bld}",
               "--root", f"install={self.inst}"]
        if expected_sha:
            cmd += ["--expected-manifest-sha256", expected_sha]
        return subprocess.run(cmd, cwd=cwd or self.base, text=True, capture_output=True)


class TestCapsule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fx = CapsuleFixture(Path(self.tmp.name) / "fixture")

    def tearDown(self):
        self.tmp.cleanup()

    def test_actual_shape_valid_from_foreign_cwd(self):
        foreign = Path(self.tmp.name) / "elsewhere"
        foreign.mkdir()
        proc = self.fx.verify(cwd=foreign)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["physical_status"], "NOT_ACCEPTED")

    def test_trusted_manifest_digest_rejects_rewritten_manifest(self):
        manifest = self.fx.cap / "manifest.json"
        trusted, _ = digest(manifest)
        data = json.loads(manifest.read_text())
        data["run_id"] = "rewritten"
        jsonfile(manifest, data)
        self.assertNotEqual(self.fx.verify(expected_sha=trusted).returncode, 0)

    def test_extra_capsule_file_rejected(self):
        write(self.fx.cap / "unlisted.bin", "extra")
        self.assertNotEqual(self.fx.verify().returncode, 0)

    def test_duplicate_manifest_path_rejected(self):
        p = self.fx.cap / "manifest.json"
        data = json.loads(p.read_text())
        data["files"].append(data["files"][0])
        jsonfile(p, data)
        self.assertNotEqual(self.fx.verify().returncode, 0)

    def test_capsule_path_traversal_rejected(self):
        p = self.fx.cap / "manifest.json"
        data = json.loads(p.read_text())
        data["files"][0]["path"] = "../escape"
        jsonfile(p, data)
        self.assertNotEqual(self.fx.verify().returncode, 0)

    def test_capsule_symlink_rejected(self):
        (self.fx.cap / "escape-link").symlink_to(self.fx.src / "tracked.f90")
        self.assertNotEqual(self.fx.verify().returncode, 0)

    def test_manifest_parent_symlink_rejected(self):
        alias = self.fx.base / "capsule-alias"
        alias.symlink_to(self.fx.cap, target_is_directory=True)
        cmd = [sys.executable, "-I", "-S", str(VERIFY), str(alias / "manifest.json"),
               "--root", f"source={self.fx.src}", "--root", f"build={self.fx.bld}",
               "--root", f"install={self.fx.inst}"]
        self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)

    def test_external_reference_symlink_rejected(self):
        target = self.fx.inst / "run/rrtmgp-gas-lw-g128.nc"
        target.unlink()
        target.symlink_to(self.fx.inst / "bin/wrf")
        self.assertNotEqual(self.fx.verify().returncode, 0)

    def test_changed_output_bytes_rejected(self):
        write(self.fx.cap / self.fx.history_rel, b"tampered\n")
        self.assertNotEqual(self.fx.verify().returncode, 0)

    def test_nonzero_child_rc_rejected(self):
        p = self.fx.cap / "execution.json"
        data = json.loads(p.read_text())
        data["children"][1]["actual_rc"] = 17
        jsonfile(p, data)
        self.fx.reseal()
        self.assertNotEqual(self.fx.verify().returncode, 0)

    def test_table_plan_join_rejects_missing_offered_table(self):
        p = self.fx.cap / "execution.json"
        data = json.loads(p.read_text())
        data["children"][1]["input_paths"].pop()
        jsonfile(p, data)
        self.fx.reseal()
        self.assertNotEqual(self.fx.verify().returncode, 0)

    def test_plan_executable_rejects_wrong_binary(self):
        p = self.fx.cap / "plans/forecast.json"
        data = json.loads(p.read_text())
        data["sha256"] = "0" * 64
        jsonfile(p, data)
        self.fx.reseal()
        self.assertNotEqual(self.fx.verify().returncode, 0)

    def test_runtime_report_history_join_rejects_stale_hash(self):
        p = self.fx.cap / "validation-report.json"
        data = json.loads(p.read_text())
        data["history"]["sha256"] = "0" * 64
        jsonfile(p, data)
        self.fx.reseal()
        self.assertNotEqual(self.fx.verify().returncode, 0)

    def test_capture_must_match_validation_report(self):
        p = self.fx.cap / "outputs/runtime/execution.json"
        data = json.loads(p.read_text())
        data["arms_completed"][0]["startup_capture"]["LW"]["qs"] = 0.0
        jsonfile(p, data)
        self.fx.reseal()
        self.assertNotEqual(self.fx.verify().returncode, 0)

    def test_physical_acceptance_escalation_rejected(self):
        p = self.fx.cap / "validation-report.json"
        data = json.loads(p.read_text())
        data["physical_status"] = "ACCEPTED"
        jsonfile(p, data)
        self.fx.reseal()
        self.assertNotEqual(self.fx.verify().returncode, 0)

    def test_tracked_source_symlink_is_pinned_as_literal_without_following(self):
        link = self.fx.src / "unused-external-link"
        link.symlink_to("../../vendor/unused-target")
        subprocess.run(["git", "-C", str(self.fx.src), "add", "unused-external-link"], check=True)
        subprocess.run(["git", "-C", str(self.fx.src), "-c", "user.name=fixture", "-c",
                        "user.email=fixture@example.invalid", "commit", "-qm", "add-link"], check=True)
        self.fx.head = subprocess.run(["git", "-C", str(self.fx.src), "rev-parse", "HEAD"],
                                      check=True, text=True, capture_output=True).stdout.strip()
        self.fx.tree = subprocess.run(["git", "-C", str(self.fx.src), "rev-parse", "HEAD^{tree}"],
                                      check=True, text=True, capture_output=True).stdout.strip()
        ls = subprocess.run(["git", "-C", str(self.fx.src), "ls-files", "-s", "--", "unused-external-link"],
                            check=True, text=True, capture_output=True).stdout.strip()
        self.fx.source_manifest["head"] = self.fx.head
        self.fx.source_manifest["tree"] = self.fx.tree
        self.fx.source_manifest["symlinks"] = [{"path": "unused-external-link",
            "target_text": os.readlink(link), "git_blob": ls.split()[1]}]
        jsonfile(self.fx.cap / "source-manifest.json", self.fx.source_manifest)
        shutil.copyfile(self.fx.cap / "source-manifest.json", self.fx.cap / "source-post-manifest.json")
        self.fx.identity["source"].update({"head": self.fx.head, "tree": self.fx.tree,
            "manifest_pre": pin("capsule", self.fx.cap, "source-manifest.json"),
            "manifest_post": pin("capsule", self.fx.cap, "source-post-manifest.json")})
        jsonfile(self.fx.cap / "identity.json", self.fx.identity)
        for key, status in (("configure", "PASS_CONFIGURE"), ("build", "PASS_BUILD"), ("install", "PASS_INSTALL")):
            rel = f"receipts/{key}.json"
            jsonfile(self.fx.bld / rel, {"status": status, "actual_child_RC": 0,
                      "head": self.fx.head, "tree": self.fx.tree})
            self.fx.identity["build"]["receipts"][key]["file"] = pin("build", self.fx.bld, rel)
        jsonfile(self.fx.cap / "identity.json", self.fx.identity)
        report_path = self.fx.cap / "validation-report.json"
        report = json.loads(report_path.read_text())
        report["source_head"], report["source_tree"] = self.fx.head, self.fx.tree
        jsonfile(report_path, report)
        out_path = self.fx.cap / "outputs.json"
        out = json.loads(out_path.read_text())
        report_ref = pin("capsule", self.fx.cap, "validation-report.json")
        out["files"][-1] = report_ref
        out["validation_report_path"] = report_ref
        jsonfile(out_path, out)
        self.fx.reseal()
        proc = self.fx.verify()
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
