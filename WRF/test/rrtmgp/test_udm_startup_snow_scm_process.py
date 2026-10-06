#!/usr/bin/env python3
"""Failure-injection tests for the SCM runner's child/receipt lifecycle.

Only short Python dummy processes are launched. No WRF executable or model is
used; run_once itself is imported from the production SCM harness.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("startup_scm", HERE / "test_udm_startup_snow_scm.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load production startup SCM runner")
startup_scm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(startup_scm)


def dummy_executable(directory: Path, body: str) -> Path:
    path = directory / "dummy-model.py"
    path.write_text(f"#!{sys.executable}\n" + body)
    path.chmod(0o755)
    return path


class RunOnceLifecycle(unittest.TestCase):
    def setUp(self) -> None:
        # The repository test volume is executable; /tmp may be mounted noexec.
        self.temp = tempfile.TemporaryDirectory(dir=HERE)
        self.root = Path(self.temp.name)
        self.case = self.root / "case"
        self.case.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_starting_record_failure_never_spawns(self):
        exe = dummy_executable(self.root, "raise SystemExit(0)\n")
        with patch.object(startup_scm, "atomic_json", side_effect=OSError("STARTING storage failed")), \
             patch.object(startup_scm.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(OSError, "STARTING storage failed"):
                startup_scm.run_once(exe, self.case, "dummy.log", False, "fixture")
        popen.assert_not_called()
        self.assertFalse((self.case / "dummy.log").exists())

    def test_running_and_terminal_record_failures_still_reap_child(self):
        exe = dummy_executable(self.root, "import time\ntime.sleep(30)\n")
        real_popen = subprocess.Popen
        children = []

        def capture_popen(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            return child

        real_atomic = startup_scm.atomic_json
        stages = []

        def fail_persistently_after_starting(path, record):
            stages.append(record.get("status"))
            if record.get("status") != "STARTING":
                raise OSError(f"persistent storage failure at {record.get('status')}")
            return real_atomic(path, record)

        with patch.object(startup_scm, "atomic_json", side_effect=fail_persistently_after_starting), \
             patch.object(startup_scm.subprocess, "Popen", side_effect=capture_popen), \
             patch.object(startup_scm, "TIMEOUT_SECONDS", 60):
            with self.assertRaisesRegex(OSError, "persistent storage failure at RUNNING") as caught:
                startup_scm.run_once(exe, self.case, "dummy.log", False, "fixture")

        self.assertEqual(len(children), 1)
        child = children[0]
        self.assertIsNotNone(child.returncode)
        note = " ".join(getattr(caught.exception, "__notes__", []))
        self.assertIn("child_returncode=", note)
        self.assertEqual(stages[0], "STARTING")
        self.assertEqual(stages[1], "RUNNING")
        self.assertTrue(any(str(s).endswith("CHILD_REAPED") for s in stages[2:]))
        # The durable STARTING snapshot is truthful: later storage was broken,
        # so no fabricated terminal receipt is claimed.
        saved = json.loads((self.case / "process-result.json").read_text())
        self.assertEqual(saved["status"], "STARTING")

    def test_normal_dummy_records_real_exit_status(self):
        exe = dummy_executable(self.root, "print('dummy completed')\nraise SystemExit(7)\n")
        with patch.object(startup_scm, "TIMEOUT_SECONDS", 10):
            record = startup_scm.run_once(exe, self.case, "dummy.log", False, "fixture")
        self.assertEqual(record["status"], "COMPLETE")
        self.assertEqual(record["returncode"], 7)
        self.assertTrue(record["reaped"])
        saved = json.loads((self.case / "process-result.json").read_text())
        self.assertEqual(saved["returncode"], 7)

    def test_interrupted_wait_reaps_process_group_descendant(self):
        pidfile = self.root / "descendant.pid"
        exe = dummy_executable(
            self.root,
            "import subprocess,sys,time\n"
            "child=subprocess.Popen([sys.executable,'-c',"
            "'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)'])\n"
            f"open({str(pidfile)!r},'w').write(str(child.pid))\n"
            "raise SystemExit(0)\n",
        )
        real_popen = subprocess.Popen
        proxies = []

        class InterruptFirstWait:
            def __init__(self, child):
                self.child = child
                self.pid = child.pid
                self.did_interrupt = False

            def poll(self):
                return self.child.poll()

            def wait(self, *args, **kwargs):
                if not self.did_interrupt:
                    deadline = time.monotonic() + 3
                    while self.child.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.did_interrupt = True
                    raise KeyboardInterrupt("injected wait interruption")
                return self.child.wait(*args, **kwargs)

        def capture_popen(*args, **kwargs):
            proxy = InterruptFirstWait(real_popen(*args, **kwargs))
            proxies.append(proxy)
            return proxy

        with patch.object(startup_scm.subprocess, "Popen", side_effect=capture_popen), \
             patch.object(startup_scm, "TIMEOUT_SECONDS", 60), \
             patch.object(startup_scm, "CHILD_CLEANUP_GRACE_SECONDS", 0.2):
            with self.assertRaisesRegex(KeyboardInterrupt, "injected wait interruption"):
                startup_scm.run_once(exe, self.case, "dummy.log", False, "fixture")

        self.assertEqual(len(proxies), 1)
        child = proxies[0].child
        self.assertIsNotNone(child.returncode)
        receipt = json.loads((self.case / "process-result.json").read_text())
        self.assertEqual(receipt["status"], "INTERRUPTED_CHILD_REAPED")
        self.assertEqual(receipt["returncode"], child.returncode)
        self.assertTrue(receipt["reaped"])
        descendant = int(pidfile.read_text())
        deadline = time.monotonic() + 3
        while Path(f"/proc/{descendant}/stat").exists() and time.monotonic() < deadline:
            stat = Path(f"/proc/{descendant}/stat").read_text().split()
            if len(stat) > 2 and stat[2] == "Z":
                break
            time.sleep(0.02)
        if Path(f"/proc/{descendant}/stat").exists():
            self.assertEqual(Path(f"/proc/{descendant}/stat").read_text().split()[2], "Z")


if __name__ == "__main__":
    unittest.main()
