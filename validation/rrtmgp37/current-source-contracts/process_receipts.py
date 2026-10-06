#!/usr/bin/env python3
"""Durably record terminal outcomes for subprocess.run calls.

Each invocation writes an fsynced STARTED row before launch and an fsynced
terminal row immediately after completion, before callers inspect output.
Journal I/O failures propagate; persistence cannot be guaranteed if that
storage fails. In particular, a failed STARTED write prevents child launch.
TimeoutExpired is terminal because subprocess.run kills and waits for the
child before raising it; no numeric return code exists for that case.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(row, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short append while writing process receipt")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


class DurableProcessRunner:
    """A narrow subprocess.run proxy that journals start and terminal status."""

    def __init__(self, ledger: Path, default_timeout_seconds: float | None = None):
        self.ledger = Path(ledger)
        self.default_timeout_seconds = default_timeout_seconds
        self.counter = 0

    def run(self, *args, **kwargs):
        if self.default_timeout_seconds is not None:
            kwargs.setdefault("timeout", self.default_timeout_seconds)
        self.counter += 1
        attempt = f"{time.time_ns()}-{os.getpid()}-{self.counter}"
        argv = args[0] if args else kwargs.get("args")
        if isinstance(argv, (str, bytes, os.PathLike)):
            rendered_argv = os.fsdecode(argv)
        elif argv is None:
            rendered_argv = None
        else:
            rendered_argv = [os.fsdecode(x) if isinstance(x, (bytes, os.PathLike)) else str(x)
                             for x in argv]
        cwd = kwargs.get("cwd")
        timeout = kwargs.get("timeout")
        started = time.time()
        common = {"attempt_id": attempt, "argv": rendered_argv,
                  "cwd": os.fspath(cwd) if cwd is not None else None,
                  "timeout_seconds": timeout, "started_epoch": started}
        _append(self.ledger, {**common, "event": "STARTED"})
        try:
            completed = subprocess.run(*args, **kwargs)
        except subprocess.TimeoutExpired as exc:
            _append(self.ledger, {**common, "event": "TIMED_OUT",
                                  "returncode": None, "child_reaped": True,
                                  "exception": type(exc).__name__,
                                  "ended_epoch": time.time()})
            raise
        except subprocess.CalledProcessError as exc:
            _append(self.ledger, {**common, "event": "EXITED_NONZERO",
                                  "returncode": exc.returncode,
                                  "ended_epoch": time.time()})
            raise
        except OSError as exc:
            _append(self.ledger, {**common, "event": "OS_ERROR_PHASE_UNCONFIRMED",
                                  "returncode": None,
                                  "child_start_state": "UNKNOWN",
                                  "exception": type(exc).__name__,
                                  "message": str(exc), "ended_epoch": time.time()})
            raise
        except BaseException as exc:
            _append(self.ledger, {**common, "event": "ABORTED",
                                  "returncode": getattr(exc, "returncode", None),
                                  "exception": type(exc).__name__,
                                  "ended_epoch": time.time()})
            raise
        event = "EXITED_ZERO" if completed.returncode == 0 else "EXITED_NONZERO"
        _append(self.ledger, {**common, "event": event,
                              "returncode": completed.returncode,
                              "ended_epoch": time.time()})
        return completed
