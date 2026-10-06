#!/usr/bin/env python3
"""Read selected-column RRTMG observations without loading WRF or running physics."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

SCHEMA = 'RRTMG4_SELECTED_COLUMN_EXPORT_V1'
STAGES = {'INPUT', 'CLOUD', 'GAS', 'RESULT'}
CONTEXT = {'domain': 1, 'step': 2161, 'source_seconds': 129600.0, 'i': 24, 'j': 55}


@dataclass(frozen=True)
class Field:
    name: str
    units: str
    shape: tuple[int, ...]
    values: tuple[float, ...]

    def at(self, *indices: int) -> float:
        """Zero-based indices, with the first index varying fastest."""
        if len(indices) != len(self.shape):
            raise ValueError('index rank differs from field rank')
        offset, stride = 0, 1
        for index, size in zip(indices, self.shape):
            if not 0 <= index < size:
                raise IndexError(index)
            offset += index * stride
            stride *= size
        return self.values[offset]


def read_export(path: Path, *, expected_phase: str | None = None, expected_context: dict | None = None) -> dict:
    lines = path.read_text(encoding='ascii').splitlines()
    if not lines or lines[0].strip() != SCHEMA:
        raise ValueError(f'{path}: unexpected export schema')
    cursor = 1
    metadata = {}
    for key in ('phase', 'domain', 'step', 'source_seconds', 'i', 'j'):
        if cursor >= len(lines):
            raise ValueError(f'{path}: missing metadata {key}')
        words = lines[cursor].split()
        cursor += 1
        if len(words) != 2 or words[0] != key:
            raise ValueError(f'{path}: malformed metadata {key}')
        value = words[1]
        if key == 'phase':
            value = value.upper()
            if value not in ('LW', 'SW'):
                raise ValueError(f'{path}: invalid phase {value}')
            metadata[key] = value
        else:
            parsed = float(value.replace('D', 'E').replace('d', 'e'))
            if not math.isfinite(parsed):
                raise ValueError(f'{path}: nonfinite metadata {key}')
            if key != 'source_seconds' and not parsed.is_integer():
                raise ValueError(f'{path}: noninteger metadata {key}')
            metadata[key] = parsed if key == 'source_seconds' else int(parsed)
    if expected_phase is not None and metadata['phase'] != expected_phase:
        raise ValueError(f'{path}: phase does not match requested input')
    for key, value in (CONTEXT if expected_context is None else expected_context).items():
        if metadata[key] != value:
            raise ValueError(f'{path}: context {key}={metadata[key]} differs from {value}')
    if cursor >= len(lines):
        raise ValueError(f'{path}: missing array layout declaration')
    layout = lines[cursor].strip()
    cursor += 1
    if not layout.startswith('layout ') or 'fortran' not in layout.lower():
        raise ValueError(f'{path}: unsupported array layout {layout}')

    fields, stage_order, stage = {}, [], None
    while cursor < len(lines):
        words = lines[cursor].split()
        cursor += 1
        if not words:
            continue
        if words[0] == 'stage':
            if len(words) != 2 or words[1] not in STAGES:
                raise ValueError(f'{path}: malformed stage marker')
            stage = words[1]
            if stage in stage_order:
                raise ValueError(f'{path}: repeated stage {stage}')
            stage_order.append(stage)
            continue
        if stage is None or len(words) not in (3, 4):
            raise ValueError(f'{path}: field outside stage or invalid field header')
        name, units = words[:2]
        try:
            shape = tuple(int(x) for x in words[2:])
        except ValueError as exc:
            raise ValueError(f'{path}: noninteger dimensions for {name}') from exc
        count = math.prod(shape)
        if any(n <= 0 for n in shape) or count > 1_000_000:
            raise ValueError(f'{path}: invalid field shape {name} {shape}')
        key = (stage, name)
        if key in fields:
            raise ValueError(f'{path}: duplicate field {stage}/{name}')
        values = []
        while len(values) < count:
            if cursor >= len(lines):
                raise ValueError(f'{path}: truncated field {stage}/{name}')
            tokens = lines[cursor].split()
            cursor += 1
            if not tokens:
                raise ValueError(f'{path}: blank numeric record in {stage}/{name}')
            try:
                parsed = [float(x.replace('D', 'E').replace('d', 'e')) for x in tokens]
            except ValueError as exc:
                raise ValueError(f'{path}: nonnumeric value in {stage}/{name}') from exc
            if not all(math.isfinite(x) for x in parsed):
                raise ValueError(f'{path}: nonfinite value in {stage}/{name}')
            values.extend(parsed)
            if len(values) > count:
                raise ValueError(f'{path}: excess values in {stage}/{name}')
        fields[key] = Field(name, units, shape, tuple(values))
    if not STAGES <= set(stage_order):
        raise ValueError(f'{path}: required stages are incomplete')
    if stage_order != ['INPUT', 'CLOUD', 'GAS', 'RESULT']:
        raise ValueError(f'{path}: unexpected stage order')
    if any(not any(k[0] == s for k in fields) for s in stage_order):
        raise ValueError(f'{path}: empty stage')
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'metadata': metadata, 'layout': layout, 'stage_order': stage_order, 'fields': fields}


def inventory(export: dict) -> dict:
    """Descriptors only; no spectral averaging or accuracy decision."""
    return {
        'path': export['path'], 'sha256': export['sha256'],
        'metadata': export['metadata'], 'layout': export['layout'],
        'stages': export['stage_order'],
        'fields': [
            {'stage': stage, 'name': f.name, 'units': f.units, 'shape': f.shape,
             'minimum': min(f.values), 'maximum': max(f.values),
             'zero_values': sum(x == 0 for x in f.values)}
            for (stage, _), f in export['fields'].items()
        ],
        'limits': 'This checks captured records and describes fields. It does not establish matched optics, solver accuracy, or an observational result.',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lw', type=Path, required=True)
    parser.add_argument('--sw', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'schema': 'rrtmg4-selected-export-inventory-v1',
              'LW': inventory(read_export(args.lw, expected_phase='LW')),
              'SW': inventory(read_export(args.sw, expected_phase='SW'))}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'LW_fields': len(result['LW']['fields']),
                      'SW_fields': len(result['SW']['fields'])}))


if __name__ == '__main__':
    main()
