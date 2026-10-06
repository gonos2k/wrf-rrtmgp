#!/usr/bin/env python3
"""Exercise consumer harness journal-failure cleanup and actual timeout."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('consumers', Path(__file__).with_name('test_cmake_installed_consumers.py'))
consumers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(consumers)


class ProcessLifecycle(unittest.TestCase):
    def test_running_journal_failure_reaps_mocked_child(self):
        # Mocked launch only: a storage failure is injected after Popen returns.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = {'stages': []}
            child = unittest.mock.Mock()
            child.pid = 123456789
            child.poll.side_effect = [None, 0]
            child.wait.return_value = 0
            original_atomic = consumers.atomic
            calls = 0
            def failing_atomic(path, value):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError('injected RUNNING journal failure')
                return original_atomic(path, value)
            with patch.object(consumers, 'atomic', side_effect=failing_atomic), \
                 patch.object(consumers.subprocess, 'Popen', return_value=child), \
                 patch.object(consumers.os, 'killpg') as kill:
                with self.assertRaisesRegex(OSError, 'injected RUNNING'):
                    consumers.stage(state, root/'receipt.json', 'mocked-journal-failure',
                                    ['never-launched'], root, {}, root/'child.log', 1)
            kill.assert_called_once_with(child.pid, consumers.signal.SIGTERM)
            child.wait.assert_called_once_with(timeout=consumers.TERM_GRACE)
            self.assertEqual(state['status'], 'FAIL_PRESERVED')
            self.assertEqual(state['stages'][0]['status'], 'INTERRUPTED_CHILD_REAPED')
            self.assertEqual(state['stages'][0]['returncode'], 0)

    def test_timeout_kills_and_records_real_child_returncode(self):
        # One Python child, no compiler, WRF or RTE process. Ignore TERM to
        # exercise bounded escalation to KILL without using model executables.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = {'stages': []}
            code = 'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(20)'
            with patch.object(consumers, 'TERM_GRACE', 0.2):
                with self.assertRaisesRegex(RuntimeError, 'failed with actual child RC'):
                    consumers.stage(state, root/'receipt.json', 'real-python-timeout',
                                    [sys.executable, '-c', code], root, os.environ.copy(),
                                    root/'child.log', 0.5)
            record = state['stages'][0]
            self.assertTrue(record['timed_out'])
            self.assertTrue(record['reaped'])
            self.assertEqual(record['returncode'], -consumers.signal.SIGKILL)
            self.assertEqual(record['status'], 'COMMAND_FAILED')
            self.assertEqual(state['status'], 'FAIL_PRESERVED')


if __name__ == '__main__':
    unittest.main()
