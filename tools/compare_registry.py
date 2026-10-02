#!/usr/bin/env python3
"""Compare Registry diagnostics with the exact pre-registration input.

Reuse the same compiled original generator and flags. Do not edit the working
WRF source. Reconstruction is accepted only when its Git blob is the recorded
upstream blob, so this does not guess the original Registry contents.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Callable


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def warning_counts(text: str) -> Counter:
    return Counter(line.strip() for line in text.splitlines()
                   if re.match(r'^(?:REGISTRY )?WARNING:', line.strip()))


def compare_registry(root: Path, out: Path, log: Path, execute: Callable) -> dict:
    registered_log = log.read_text()
    before = warning_counts(registered_log)
    receipt = json.loads((root / 'config/registration37.json').read_text())
    common_name = 'Registry/Registry.EM_COMMON'
    registered = (out / common_name).read_bytes()
    if git_blob(registered) != receipt['patched_blobs'][common_name]:
        raise ValueError('REGISTERED_INPUT_CHANGED_BEFORE_BASELINE')
    text = registered.decode('utf-8')
    data_path_pattern = (
        r'(?im)^[ \t]*rconfig[ \t]+character[ \t]+'
        r'rrtmgp_data_path\b[^\r\n]*(?:\r?\n|$)')
    data_path_lines = re.findall(data_path_pattern, text)
    expected_data_path_lines = 1 if receipt.get('backend') == 'CPU_LINKED' else 0
    if len(data_path_lines) != expected_data_path_lines:
        raise ValueError('RRTMGP_DATA_PATH_RCONFIG_COUNT_MISMATCH')
    if data_path_lines:
        text = re.sub(data_path_pattern, '', text, count=1)
    roughness_pattern = (
        r'(?im)^[ \t]*rconfig[ \t]+integer[ \t]+'
        r'rrtmgp_ice_roughness\b[^\r\n]*(?:\r?\n|$)')
    roughness_lines = re.findall(roughness_pattern, text)
    expected_roughness = int('rrtmgp_ice_roughness' in receipt.get('global_rconfig', []))
    if len(roughness_lines) != expected_roughness:
        raise ValueError('RRTMGP_ICE_ROUGHNESS_RCONFIG_COUNT_MISMATCH')
    if roughness_lines:
        text = re.sub(roughness_pattern, '', text, count=1)
    registered_without_data_path = text.encode('utf-8')
    suffix = b'\n\ninclude registry.rrtmgp37\n'
    if not registered_without_data_path.endswith(suffix):
        raise ValueError('REGISTRY37_SUFFIX_MISMATCH')
    prefix = registered_without_data_path[:-len(suffix)]
    candidates = [prefix + b'\n' * n for n in range(9)]
    valid = [data for data in candidates
             if git_blob(data) == receipt['original_blobs'][common_name]]
    if len(valid) != 1:
        raise ValueError('CANNOT_RECONSTRUCT_VERIFIED_ORIGINAL_REGISTRY')
    baseline = out / 'baseline'
    baseline.mkdir()
    shutil.copytree(out / 'Registry', baseline / 'Registry', symlinks=True)
    (baseline / common_name).write_bytes(valid[0])
    (baseline / 'Registry/registry.rrtmgp37').unlink()
    (baseline / 'inc').mkdir()
    (baseline / 'frame').mkdir()
    offset = len(log.read_text())
    execute([out / 'tools/registry', '-DEM_CORE=1', '-DNMM_CORE=0',
             '-DDA_CORE=0', '-DWRF_CHEM=0', '-DNEW_BDYS',
             baseline / 'Registry/Registry.EM'], baseline, log)
    baseline_log = log.read_text()[offset:]
    if 'REGISTRY ERROR' in baseline_log:
        raise ValueError('BASELINE_REGISTRY_ERROR')
    state = baseline / 'frame/module_state_description.F'
    if not state.is_file() or not state.stat().st_size:
        raise ValueError('BASELINE_STATE_MODULE_NOT_GENERATED')
    if re.search(r'\brrtmgp_(?:lw|sw)scheme\s*=', state.read_text(), re.I):
        raise ValueError('OPTION37_LEAKED_INTO_BASELINE')
    original = warning_counts(baseline_log)
    introduced = before - original
    removed = original - before
    result = {
        'scope': 'SAME_ORIGINAL_GENERATOR_AND_SERIAL_FLAGS; NOT A MODEL BUILD',
        'original_common_git_blob': git_blob(valid[0]),
        'registered_warning_count': sum(before.values()),
        'baseline_warning_count': sum(original.values()),
        'introduced_warnings': dict(introduced),
        'removed_warnings': dict(removed),
        'warnings_identical': before == original,
    }
    (out / 'registry-warning-comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    with log.open('a') as stream:
        stream.write('\nREGISTRY_BASELINE_COMPARISON=' + json.dumps(result, sort_keys=True) + '\n')
    if introduced or removed:
        raise ValueError('REGISTRY_DIAGNOSTICS_DIFFER_FROM_UPSTREAM_BASELINE')
    return result
