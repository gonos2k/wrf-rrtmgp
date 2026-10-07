#!/usr/bin/env python3
"""Run the unchanged historical verifier on disposable exact package copies."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
PACKAGES = ('rfmip-fixed-rte', 'rfmip-historical-rte')


def pins(root):
    result = {}
    for name in PACKAGES:
        for path in sorted((root / 'validation/rrtmgp37' / name).rglob('*')):
            if path.is_symlink():
                raise ValueError('evidence symlink is unsupported')
            if path.is_file():
                data = path.read_bytes()
                result[path.relative_to(root).as_posix()] = {
                    'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data)}
    harness = root / 'WRF/test/rrtmgp/rrtmgp_rfmip_sw_fixed_rte.F90'
    data = harness.read_bytes()
    result[harness.relative_to(root).as_posix()] = {
        'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data)}
    return result


def main():
    before = pins(ROOT)
    with tempfile.TemporaryDirectory(prefix='udm37-historical-evidence-') as temporary:
        isolated = Path(temporary)
        for name in PACKAGES:
            shutil.copytree(ROOT / 'validation/rrtmgp37' / name,
                            isolated / 'validation/rrtmgp37' / name)
        harness = isolated / 'WRF/test/rrtmgp/rrtmgp_rfmip_sw_fixed_rte.F90'
        harness.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / harness.relative_to(isolated), harness)
        if pins(isolated) != before:
            raise ValueError('temporary evidence copy differs from original bytes')
        def interrupted(signum, frame):
            raise KeyboardInterrupt(f'interrupted by signal {signum}')

        previous = {sig: signal.signal(sig, interrupted)
                    for sig in (signal.SIGTERM, signal.SIGINT)}
        child = None
        try:
            child = subprocess.Popen(
                [sys.executable, '-I', '-S', str(isolated / 'validation/rrtmgp37/rfmip-historical-rte/verify_saved.py')],
                cwd=isolated, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, start_new_session=True)
            stdout, stderr = child.communicate(timeout=120)
        except BaseException:
            if child is not None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.communicate(timeout=10)
            raise
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        if child.returncode != 0:
            raise RuntimeError(f'isolated historical verifier RC={child.returncode}: {stderr[-2000:]}')
        if pins(isolated) != before:
            raise ValueError('recomputed disposable evidence differs from original bytes')
        if pins(ROOT) != before:
            raise ValueError('original evidence changed during isolated verification')
        report = json.loads(stdout)
        if report.get('scientific_execution') is not False:
            raise ValueError('saved-only verifier scope changed')
        print(json.dumps({'status': 'PASS_SAVED_HISTORICAL_ISOLATED',
                          'original_pinned_files': len(before),
                          'original_bytes_unchanged': True,
                          'disposable_bytes_reproduced': True,
                          'child_returncode': child.returncode,
                          'child_reaped': True,
                          'saved_verifier_report': report,
                          'new_model_or_solver_calls': 0,
                          'physical_accepted': False}, sort_keys=True))


if __name__ == '__main__':
    main()
