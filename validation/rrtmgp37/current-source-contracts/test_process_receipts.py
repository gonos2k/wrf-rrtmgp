#!/usr/bin/env python3
"""Exercise durable child exit, timeout, and launch-failure receipts only."""
from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

_HELPER_PATH = Path(__file__).with_name("process_receipts.py")
_SPEC = importlib.util.spec_from_file_location("test_process_receipts_helper", _HELPER_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("could not load process receipt helper")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
DurableProcessRunner = _MODULE.DurableProcessRunner


class DurableProcessReceiptTests(unittest.TestCase):
    def test_zero_exit_preserves_output_and_terminal_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "process.jsonl"
            runner = DurableProcessRunner(ledger)
            child = runner.run([sys.executable, "-c", "print('ready')"],
                               capture_output=True, text=True, check=True)
            self.assertEqual(child.returncode, 0)
            self.assertEqual(child.stdout, "ready\n")
            rows = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual([row["event"] for row in rows], ["STARTED", "EXITED_ZERO"])
            self.assertEqual(rows[-1]["returncode"], 0)

    def test_nonzero_exit_is_durable_before_return(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "process.jsonl"
            runner = DurableProcessRunner(ledger)
            child = runner.run([sys.executable, "-c", "raise SystemExit(7)"])
            self.assertEqual(child.returncode, 7)
            rows = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual([row["event"] for row in rows], ["STARTED", "EXITED_NONZERO"])
            self.assertEqual(rows[-1]["returncode"], 7)
            self.assertEqual(rows[0]["attempt_id"], rows[-1]["attempt_id"])

    def test_check_true_nonzero_exception_keeps_actual_returncode(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "process.jsonl"
            runner = DurableProcessRunner(ledger)
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                runner.run([sys.executable, "-c", "raise SystemExit(9)"], check=True)
            self.assertEqual(caught.exception.returncode, 9)
            rows = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual([row["event"] for row in rows], ["STARTED", "EXITED_NONZERO"])
            self.assertEqual(rows[-1]["returncode"], 9)

    def test_timeout_is_terminal_and_child_is_reaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "process.jsonl"
            runner = DurableProcessRunner(ledger)
            with self.assertRaises(subprocess.TimeoutExpired):
                runner.run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.05)
            rows = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual([row["event"] for row in rows], ["STARTED", "TIMED_OUT"])
            self.assertIsNone(rows[-1]["returncode"])
            self.assertTrue(rows[-1]["child_reaped"])

    def test_configured_default_timeout_is_applied_and_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "process.jsonl"
            runner = DurableProcessRunner(ledger, default_timeout_seconds=0.05)
            with self.assertRaises(subprocess.TimeoutExpired):
                runner.run([sys.executable, "-c", "import time; time.sleep(5)"])
            rows = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual(rows[-1]["event"], "TIMED_OUT")
            self.assertEqual(rows[0]["timeout_seconds"], 0.05)

    def test_launch_failure_is_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "process.jsonl"
            runner = DurableProcessRunner(ledger)
            with self.assertRaises(FileNotFoundError):
                runner.run([str(Path(tmp) / "missing-child")])
            rows = [json.loads(line) for line in ledger.read_text().splitlines()]
            self.assertEqual([row["event"] for row in rows], ["STARTED", "LAUNCH_FAILED"])
            self.assertIsNone(rows[-1]["returncode"])


if __name__ == "__main__":
    unittest.main()
