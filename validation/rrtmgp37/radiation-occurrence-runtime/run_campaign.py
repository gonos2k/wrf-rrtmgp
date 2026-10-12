#!/usr/bin/env python3
"""Five short serial SCM runs using the retained, source-bound executable.
No compile, ideal, policy change, or independent physics approval.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--seed', type=Path, required=True)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--library-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    sys.path.insert(0, str(root / 'WRF/test/rrtmgp'))
    from test_netcdf_zz import Runner, pin, write_json
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    corpus_path = root / 'validation/rrtmgp37/connected-host-number/source/tracked-WRF-corpus.json'
    corpus = json.loads(corpus_path.read_text())
    for row in corpus['files']:
        current = pin(root / row['path'])
        if any(current[k] != row[k] for k in ('sha256', 'size_bytes')):
            raise ValueError('current production corpus changed: ' + row['path'])
    observer_files = ['phys/module_ra_rrtmgp_trace.F', 'phys/module_microphysics_driver.F',
                      'phys/module_mp_udm.F', 'dyn_em/start_em.F', 'dyn_em/solve_em.F']
    observer_checks = []
    for relative in observer_files:
        original = (args.snapshot / relative).read_bytes()
        restored, count = re.subn(rb'! HOST_CONNECTED_OBSERVER_BEGIN\n.*?! HOST_CONNECTED_OBSERVER_END\n', b'', original, flags=re.S)
        if count < 1 or restored != (root / 'WRF' / relative).read_bytes():
            raise ValueError('observer restoration failed: ' + relative)
        observer_checks.append({'path': 'WRF/' + relative, 'blocks_removed': count,
                                'observed': pin(args.snapshot / relative),
                                'production': pin(root / 'WRF' / relative)})
    exe = args.executable.resolve(strict=True)
    expected = '7990e7ddc8160016761f87e4e21fc0744be5fdfdba862d8f9e732a245c63e1cd'
    if pin(exe)['sha256'] != expected:
        raise ValueError('retained executable changed')
    # Preserve existing inputs; never copy old outputs into fresh runtimes.
    inputs = [p for p in sorted(args.seed.iterdir()) if p.is_file() and
              not p.name.startswith(('wrfout', 'wrfrst', 'rsl.', 'namelist.output', 'udm-', 'command-'))]
    namelist = (args.seed / 'namelist.input').read_text()
    changed = namelist
    for name in ('run_seconds', 'end_second'):
        changed, count = re.subn(r'(?m)^(\s*' + name + r'\s*=\s*)0(\s*,)', r'\g<1>10\2', changed)
        if count != 1:
            raise ValueError('unexpected retained namelist: ' + name)
    changed, count = re.subn(r'(?m)^(\s*history_interval_s\s*=\s*)60(\s*,)', r'\g<1>10\2', changed)
    if count != 1:
        raise ValueError('unexpected history cadence')
    environment = os.environ.copy()
    removed = []
    for name in list(environment):
        if name.startswith(('WRF_RRTMGP_', 'WRF_UDM_')) or name in ('LD_PRELOAD', 'LD_DEBUG_OUTPUT'):
            removed.append(name)
            del environment[name]
    environment['LD_LIBRARY_PATH'] = str(args.library_directory.resolve(strict=True))
    environment['LD_DEBUG'] = 'libs'
    environment['OMP_NUM_THREADS'] = '1'
    identity = {'executable': pin(exe), 'current_source_corpus': pin(corpus_path),
                'production_files_checked': len(corpus['files']), 'observer_restoration': observer_checks,
                'inputs': {p.name: pin(p) for p in inputs},
                'runtime_library_files_before': [pin(p) for p in sorted(args.library_directory.glob('*.so*')) if p.is_file()],
                'removed_environment_keys': sorted(removed),
                'environment': {k: environment[k] for k in ('LD_LIBRARY_PATH', 'LD_DEBUG', 'OMP_NUM_THREADS')},
                'LD_DEBUG_is_actual_loader_output': True, 'compile_count': 0, 'ideal_count': 0,
                'source_commit': 'c1ebe4a5e95a20398921d377bcf44ddb14703698',
                'source_tree': '8b14585deaaae87ab0fafa38a9eac8608dfb69b2',
                'namelist_changes': {'run_seconds': [0, 10], 'end_second': [0, 10], 'history_interval_s': [60, 10]},
                'duration_seconds': 70, 'dt_seconds': 10, 'selected_capture_call': 7,
                'research_profile_exact_namelist_match_claimed': False, 'physical_acceptance': False}
    write_json(out / 'identity-before.json', identity)
    runner = Runner(out, 60, environment, 5)
    cases = [('off', None)] + [(f'on-i{i}-j{j}', (i, j)) for j in (1, 2) for i in (1, 2)]
    for name, column in cases:
        case = out / name
        case.mkdir()
        for source in inputs:
            shutil.copyfile(source, case / source.name)
        (case / 'namelist.input').write_text(changed)
        if column:
            capture = case / 'capture'
            capture.mkdir()
            environment.update(WRF_RRTMGP_CAPTURE_DIR=str(capture),
                               WRF_RRTMGP_COLUMN_I=str(column[0]), WRF_RRTMGP_COLUMN_J=str(column[1]),
                               WRF_RRTMGP_CAPTURE_CALL='7')
        write_json(case / 'launch.json', {'name': name, 'column': column, 'inputs': {p.name: pin(case / p.name) for p in inputs},
                                        'environment': {k: v for k, v in environment.items() if k.startswith(('WRF_', 'LD_', 'OMP_'))}})
        runner.run([str(exe)], case, name)
        print(name, 'RC0', flush=True)
    identity_after = {'executable': pin(exe), 'runtime_library_files_after': [pin(p) for p in sorted(args.library_directory.glob('*.so*')) if p.is_file()]}
    if identity_after['executable'] != identity['executable'] or identity_after['runtime_library_files_after'] != identity['runtime_library_files_before']:
        raise ValueError('executable or library files changed during campaign')
    write_json(out / 'identity-after.json', identity_after)
    write_json(out / 'execution.json', {'status': 'TERMINAL', 'wrf_processes': runner.confirmed_children,
                                      'commands': runner.commands, 'compile_count': 0,
                                      'ideal_count': 0, 'physical_acceptance': False})

if __name__ == '__main__':
    main()
