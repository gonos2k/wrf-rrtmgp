#!/usr/bin/env python3
"""Saved-only exact validation for the fixed-optics RTE replay streams."""
from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path

NPROF = 20
NLEV = 61
RECORD = struct.Struct('=ii')
FLOAT = struct.Struct('=d')


def read_stream(path: Path, expected_keys: list[tuple[int, int]]) -> list[bytes]:
    raw = path.read_bytes()
    record_bytes = RECORD.size + 2 * NLEV * FLOAT.size
    if len(raw) != len(expected_keys) * record_bytes:
        raise ValueError(f'{path}: exact byte-size/schema mismatch')
    rows = []
    seen = set()
    for i in range(len(expected_keys)):
        start = i * record_bytes
        row = raw[start:start + record_bytes]
        e, s = RECORD.unpack_from(row)
        key = (e, s)
        if key != expected_keys[i]:
            raise ValueError(f'{path}: key/order mismatch at record {i+1}: {key}')
        if key in seen:
            raise ValueError(f'{path}: duplicate key {key}')
        seen.add(key)
        for (value,) in struct.iter_unpack('=d', row[RECORD.size:]):
            if not math.isfinite(value):
                raise ValueError(f'{path}: nonfinite flux at record {i+1}')
        rows.append(row)
    if len(rows) != NPROF:
        raise ValueError('unexpected profile count')
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profiles', type=Path, required=True)
    ap.add_argument('--current-solver', type=Path, required=True)
    ap.add_argument('--current-written', type=Path, required=True)
    ap.add_argument('--historical-solver', type=Path, required=True)
    ap.add_argument('--historical-written', type=Path, required=True)
    ap.add_argument('--current-solver-reference', type=Path, required=True)
    ap.add_argument('--current-written-reference', type=Path, required=True)
    ap.add_argument('--historical-solver-reference', type=Path, required=True)
    ap.add_argument('--historical-written-reference', type=Path, required=True)
    a = ap.parse_args()

    keys = [tuple(map(int, line.split())) for line in a.profiles.read_text().splitlines() if line.strip()]
    if len(keys) != NPROF or len(set(keys)) != NPROF or keys != sorted(keys):
        raise ValueError('selector is not the exact sorted unique twenty-key roster')
    pairs = {
        'current_solver': (a.current_solver, a.current_solver_reference, True),
        'current_written': (a.current_written, a.current_written_reference, True),
        # The historical saved solver used a different RTE source revision.
        # Retain its differences descriptively; do not make them a fixed-current-RTE gate.
        'historical_solver': (a.historical_solver, a.historical_solver_reference, False),
        'historical_written': (a.historical_written, a.historical_written_reference, False),
    }
    counts = {}
    for name, (actual_path, reference_path, exact_gate) in pairs.items():
        actual = read_stream(actual_path, keys)
        reference = read_stream(reference_path, keys)
        differing = [i + 1 for i, (x, y) in enumerate(zip(actual, reference)) if x != y]
        counts[name] = {'profiles': len(actual), 'byte_identical_records': len(actual) - len(differing),
                        'different_record_ordinals': differing,
                        'exact_gate': exact_gate}
        if differing and exact_gate:
            raise ValueError(f'{name}: exact saved solver/written capture reproduction failed: {differing}')
    print(json.dumps({'status': 'PASS_CURRENT_OPTICS_BASELINE_REPLAY_GATE', 'comparisons': counts,
                      'strict_published_gate_changed': False, 'physical_accuracy_claim': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
