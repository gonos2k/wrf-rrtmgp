#!/usr/bin/env python3
"""Authenticate saved UDM entry packets and recompute conditional diagnostics."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True

PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[2]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def pin(p):
    b = p.read_bytes()
    return {"sha256": hashlib.sha256(b).hexdigest(), "size_bytes": len(b)}


def checked(root, name):
    require(isinstance(name, str) and name and not Path(name).is_absolute()
            and ".." not in Path(name).parts, "unsafe manifest path")
    p = root / name
    require(p.is_file() and not p.is_symlink()
            and p.resolve().is_relative_to(root.resolve()), "missing/escaped payload: " + name)
    return p


def authenticate(root, rows):
    names = [r['path'] for r in rows]
    require(len(names) == len(set(names)), "duplicate manifest path")
    for row in rows:
        require(set(row) == {'path', 'sha256', 'size_bytes'}, "pin schema")
        require(pin(checked(root, row['path'])) ==
                {k: row[k] for k in ('sha256', 'size_bytes')}, "changed pin: " + row['path'])
    return set(names)


def portable(value):
    # Saved absolute runtime paths differ from this checkout; identity, content
    # hashes, sizes, equations, clocks and values must still match exactly.
    if isinstance(value, dict):
        return {k: portable(v) for k, v in value.items() if k != 'path'}
    if isinstance(value, list):
        return [portable(v) for v in value]
    return value


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-root', type=Path, default=REPO)
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    root = args.source_root.resolve()
    manifest = json.loads((PACKAGE / 'manifest.json').read_text())
    require(manifest['schema'] == 'UDM_ENTRY_DENSITY_EVIDENCE_V1', 'manifest schema')
    payload = authenticate(PACKAGE, manifest['payload'])
    roster = {p.relative_to(PACKAGE).as_posix() for p in PACKAGE.rglob('*')
              if p.is_file() and p != PACKAGE / 'manifest.json' and '__pycache__' not in p.parts}
    require(roster == payload, 'closed payload roster changed')
    authenticate(root, manifest['sources'])
    parser = root / 'WRF/test/rrtmgp/test_udm_entry_density.py'
    spec = importlib.util.spec_from_file_location('_saved_entry_density', parser)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    cases = {}
    for tag in ('cold', 'warm'):
        saved = json.loads(checked(PACKAGE, tag + '-analysis.json').read_text())
        fresh = mod.inspect(PACKAGE / 'capture' / tag, PACKAGE / 'capture' / tag)
        require(portable(fresh) == portable(saved), tag + ' saved diagnostics/joins changed')
        require(fresh['packet_count'] == 6 and fresh['join_count'] == 6, tag + ' packet count')
        require([x['identity']['step'] for x in fresh['entry_packets']] == list(range(1, 7)), tag + ' step roster')
        require([x['source_time_seconds'] for x in fresh['entry_packets']] == [0, 10, 20, 30, 40, 50], tag + ' clocks')
        require(all(len(x['levels']) == 59 for x in fresh['entry_packets']), tag + ' native levels')
        cases[tag] = {'packets': 6, 'same_call_joins': 6, 'level_samples': 354}
    scm = json.loads(checked(PACKAGE, 'scm-receipt.json').read_text())
    require(scm['status'] == 'PASS_SCOPED_PASSIVITY_AND_ARCHIVE_REGRESSION' and scm['actual_forecast_invocations'] == 6
            and scm['standalone_rte_invocations'] == 0, 'saved SCM run status/counts')
    require(len(scm['arms']) == 6 and all(a['returncode'] == 0 for a in scm['arms'].values()), 'saved model RCs')
    require(all(c['status'] == 'PASS' and c['strict_variable_roster_equal']
                and c['strict_all_array_data_and_masks_equal'] for c in scm['comparisons'].values()), 'saved comparisons')
    for tag in ('cold', 'warm'):
        c = scm['comparisons'][tag + '_37_off_vs_on']
        require(c['all_metadata_equal'] and c['whole_file_byte_identical'], 'off/on byte passivity')
    build = json.loads(checked(PACKAGE, 'build-receipt.json').read_text())
    require(build['status'] == 'BUILD_PASS_SCOPED' and build['build_command_invocations'] == 1
            and build['build_invocation']['returncode'] == 0, 'saved fresh build status')
    text_count = 0
    for name in manifest['text_archives']:
        require(name in payload, 'unknown archive')
        archive = json.loads(gzip.decompress(checked(PACKAGE, name).read_bytes()))
        require(archive['schema'] == 'UDM_ENTRY_DENSITY_TEXT_ARCHIVE_V1', 'archive schema')
        names = [r['path'] for r in archive['files']]
        require(len(names) == len(set(names)), 'duplicate text artifact')
        for row in archive['files']:
            name = row['path']
            require(isinstance(name, str) and name and not Path(name).is_absolute()
                    and '..' not in Path(name).parts, 'unsafe archive path')
            b = row['content_utf8'].encode('utf-8')
            require(len(b) == row['size_bytes']
                    and hashlib.sha256(b).hexdigest() == row['sha256'], 'archive text changed')
        text_count += len(names)
    result = {'status': 'PASS_SCOPED_SAVED_PACKET_REEVALUATION', 'cases': cases,
              'payload_count': len(payload), 'source_count': len(manifest['sources']),
              'archived_text_files': text_count, 'fresh_model_build_RTE_calls': 0,
              'scope': 'saved calls/byte passivity authenticated; EOS hypotheses conditional; no physical correction or density/LUT authority claim'}
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
