#!/usr/bin/env python3
"""Two strict preserved-column replays with an explicitly reviewed validator update."""
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
OUT = Path(__file__).resolve().parent
ORIGINAL = OUT.parent
PLAN = ROOT/'build/udm-stratified-capture-plan-v3/plan.json'
PLAN_SHA = '4f9e642fad9b648f352805ac6f9d71363945df0388c1e0acc608b3740f374279'
VALIDATOR = ROOT/'build/udm-frozen-replay-validator-work/WRF/test/rrtmgp/test_column_replay.py'
VALIDATOR_SHA = '823120117dc9f9b47578c8626b4ef40d89ea415cc889f27aa07b1e7fd94e0671'
REVIEW_DIFF = ROOT/'build/udm-frozen-replay-validator-review-v3/review.diff'
REVIEW_DIFF_SHA = '6529b4d69d78cfa5e6c19b7b09e0c684a2e2fd4cfa667a7a837f920c4d99bd6c'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def independent_result_parser(path, canonical):
    # A separate token/count parser cross-checks the retained canonical parser.
    import numpy as np
    lines = path.read_text(encoding='ascii').splitlines()
    assert lines[0] == 'RRTMGP_RESULT_V1'
    phase, nc, nl = lines[1].split()
    assert (phase, int(nc), int(nl)) == (canonical['phase'], canonical['nc'], canonical['nl'])
    index = 2
    parsed = {}
    count = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        name, *dimensions = lines[index].split()
        index += 1
        assert name not in parsed and len(dimensions) == 3
        shape = tuple(int(d) for d in dimensions)
        assert min(shape) > 0
        needed = int(np.prod(shape))
        values = []
        while len(values) < needed:
            values.extend(float(t.replace('D', 'E').replace('d', 'e')) for t in lines[index].split())
            index += 1
        assert len(values) == needed
        array = np.asarray(values).reshape(shape, order='F')
        assert np.isfinite(array).all()
        assert np.array_equal(array, canonical['sections'][name]), name
        parsed[name] = list(shape)
        count += needed
    assert set(parsed) == set(canonical['sections'])
    return {'header': [phase, int(nc), int(nl)], 'section_shapes': parsed,
            'section_count': len(parsed), 'numeric_values_checked': count,
            'all_finite_and_equal_to_canonical_parser': True, 'sha256': sha(path)}


def main():
    assert sha(PLAN) == PLAN_SHA
    plan = json.loads(PLAN.read_text())
    assert sha(REVIEW_DIFF) == REVIEW_DIFF_SHA and sha(VALIDATOR) == VALIDATOR_SHA
    source = Path(plan['replay_validator']['path']).parents[3]
    manifest = json.loads(Path(plan['source_manifest']['path']).read_text())
    entries = {entry['path']: entry for entry in manifest['files']}
    pins = {item['path']: item['sha256'] for item in
            [plan['source_manifest'], plan['build_receipt'], plan['executable'], plan['configure'],
             plan['strict_reference'], plan['strict_reference_source'], plan['replay_validator'],
             plan['state_identity']['checkpoint']]}
    pins.update(plan['external_asset_sha256'])
    pins.update({name: item['sha256'] for name, item in plan['executor_support_scripts'].items()})
    pins.update({str(PLAN): PLAN_SHA, str(REVIEW_DIFF): REVIEW_DIFF_SHA, str(VALIDATOR): VALIDATOR_SHA,
                 str(ORIGINAL/'receipt.json'): '2bc9b28a9ac828372a8093541707383bc74d5dc117e8512f08196f1d5d9965a0',
                 str(ORIGINAL/'replay-recovery-v1/recovery-receipt.json'):
                 '7de947c5d32ddc92827e24561f2ed141f25d3f392407f775dc7ab731470d1e95'})
    assert sha(ORIGINAL/'replay-recovery-v1/recovery-receipt.json') == pins[str(ORIGINAL/'replay-recovery-v1/recovery-receipt.json')]
    old_recovery = json.loads((ORIGINAL/'replay-recovery-v1/recovery-receipt.json').read_text())
    captures = old_recovery['original_capture_sha256']
    assert set(captures) == {phase+'.'+ext for phase in ('lw', 'sw') for ext in ('input', 'raw', 'result')}
    pins.update({str(ORIGINAL/'capture'/name): digest for name, digest in captures.items()})
    imports = {'test_column_replay': {'path': str(VALIDATOR), 'sha256': VALIDATOR_SHA,
                                    'explicit_reviewed_update': True}}
    for name in ('test_cloud_scm', 'test_surface_scm', 'compare_column_replay'):
        old = source/'WRF/test/rrtmgp'/(name+'.py')
        expected = entries[str(old.relative_to(source))]['sha256']
        new = VALIDATOR.parent/(name+'.py')
        imports[name] = {'path': str(new), 'sha256': expected, 'unchanged_original_path': str(old)}
        pins[str(old)] = pins[str(new)] = expected

    def verify_pins():
        for path, digest in pins.items():
            assert sha(path) == digest, path

    verify_pins()
    assert not (OUT/'capture').exists() and not (OUT/'recovery-receipt.json').exists()
    (OUT/'capture').mkdir()
    for name, digest in captures.items():
        shutil.copy2(ORIGINAL/'capture'/name, OUT/'capture'/name)
        assert sha(OUT/'capture'/name) == digest
    preflight = {'executed_runner_sha256': sha(__file__), 'reviewed_plan_sha256': PLAN_SHA,
                 'reviewed_validator_diff_sha256': REVIEW_DIFF_SHA,
                 'explicit_validator_update': imports['test_column_replay'],
                 'unchanged_plan_validator': plan['replay_validator'],
                 'all_input_pins': pins, 'copied_capture_sha256': captures,
                 'strict_reference_calls_allowed': ['LW', 'SW'], 'no_wrf_or_variants': True}
    write(OUT/'pin-staging-preflight.json', preflight)
    rec = dict(preflight, status='STARTED_REPLAY_ONLY', phase_reports=[], reference_invocations=[])
    write(OUT/'recovery-receipt.json', rec)
    audit = None
    try:
        env = {'PATH': '/usr/bin:/bin',
               'LD_LIBRARY_PATH': str(ROOT/'build/deps/netcdf/lib')+':/usr/lib/x86_64-linux-gnu',
               'OMP_NUM_THREADS': '1', 'OMP_DYNAMIC': 'FALSE', 'OPENBLAS_NUM_THREADS': '1',
               'WRF_RRTMGP_FROZEN_TABLE': next(name for name in plan['external_asset_sha256']
                                              if name.endswith('frozen-ice-psd-moments.nc'))}
        os.environ.clear()
        os.environ.update(env)
        resource.setrlimit(resource.RLIMIT_STACK, (536870912, resource.getrlimit(resource.RLIMIT_STACK)[1]))
        rec['controlled_environment'] = env
        rec['master_stack_bytes'] = resource.getrlimit(resource.RLIMIT_STACK)
        sys.path.insert(0, str(VALIDATOR.parent))
        for name, item in imports.items():
            module = importlib.import_module(name)
            assert Path(module.__file__).resolve() == Path(item['path']).resolve()
            assert sha(module.__file__) == item['sha256']
        verify_pins()
        rec['successful_imports_before_reference_calls'] = imports
        write(OUT/'dependency-import-receipt.json', imports)
        replay = sys.modules['test_column_replay']
        compare = sys.modules['compare_column_replay']
        import numpy as np
        replay.DATA_DIR = Path(next(name for name in plan['external_asset_sha256']
                                   if name.endswith('rrtmgp-gas-lw-g128.nc'))).parent
        helper = ROOT/'build/udm-selected-real-audit/run_selected_column_audit.py'
        spec = importlib.util.spec_from_file_location('pinned_audit', helper)
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        task = ROOT/'build/udm-phase-path-statistics-real-wrf'
        audit.SOURCE_MANIFEST_REL = task.relative_to(ROOT)/'source-manifest.json'
        audit.BUILD_RECEIPT_REL = task.relative_to(ROOT)/'build-receipt.json'
        rec['source_before'] = audit.verify_build_manifest(ROOT, source, Path(plan['executable']['path']))
        original_run = replay.subprocess.run

        def bounded_reference_run(command, **kwargs):
            index = len(rec['reference_invocations'])
            assert index < 2, 'only two strict reference calls authorized'
            phase = ('LW', 'SW')[index]
            expected = [plan['strict_reference']['path'], str(replay.DATA_DIR),
                        str(OUT/'capture'/(phase.lower()+'.input')),
                        str(OUT/'capture'/(phase.lower()+'.reference.result'))]
            assert command == expected and kwargs['cwd'] == OUT, command
            verify_pins()
            rec['reference_invocations'].append({'phase': phase, 'command': command, 'cwd': str(OUT)})
            write(OUT/'recovery-receipt.json', rec)
            result = original_run(command, **kwargs)
            rec['reference_invocations'][-1]['returncode'] = result.returncode
            return result

        replay.subprocess.run = bounded_reference_run
        rec['independent_parser_proof'] = {}
        for phase, version in (('LW', 'RRTMGP_REPLAY_V8'), ('SW', 'RRTMGP_REPLAY_V9')):
            raw_phase, i, j, raw = replay.read_raw(OUT/'capture'/(phase.lower()+'.raw'))
            parsed_phase, nc, nl, _, _, _, inp = replay.read_input(OUT/'capture'/(phase.lower()+'.input'))
            assert (raw_phase, parsed_phase, i, j, nc, len(raw['DP_HPA'])) == (phase, phase, 136, 48, 1, 39)
            assert (OUT/'capture'/(phase.lower()+'.input')).read_text().splitlines()[0] == version
            assert raw['MP_PHYSICS'].item() == 27 and raw['RADIATION_STEP'].item() == 721
            assert raw['SOURCE_TIME_SECONDS'].item() == 43200.
            required = {'QC', 'QI', 'QR', 'QS', 'QG', 'QH', 'SOURCE_QC', 'SOURCE_QI',
                        'SOURCE_QR', 'SOURCE_QS', 'SOURCE_RE_CLOUD', 'SOURCE_RE_ICE',
                        'SOURCE_RE_SNOW', 'RAD_CF_SOURCE', 'DRY_LAYER_MASS_KG_M2'}
            assert required <= raw.keys()
            for species in ('QC', 'QI', 'QR', 'QS'):
                assert np.array_equal(raw[species], raw['SOURCE_'+species])
            production = compare.read_result(OUT/'capture'/(phase.lower()+'.result'))
            assert np.all((production['sections']['MASK'] == 0.) | (production['sections']['MASK'] == 1.))
            if phase == 'SW':
                assert np.array_equal(inp['MCICA_MASK'], production['sections']['MASK'])
                assert np.array_equal(inp['RAW_GAS_TAU'], production['sections']['GAS_TAU_RAW'])
            report = replay.validate_capture(OUT, phase, 27, Path(plan['strict_reference']['path']))
            assert report['reference_comparison']['passed']
            rec['phase_reports'].append(report)
            write(OUT/('strict-'+phase.lower()+'.json'), report)
            reference = compare.read_result(OUT/'capture'/(phase.lower()+'.reference.result'))
            assert np.array_equal(production['sections']['MASK'], reference['sections']['MASK'])
            rec['independent_parser_proof'][phase] = {
                'version': version, 'site': [i, j], 'native_layers': 39, 'adapter_layers': nl,
                'step': 721, 'source_time_seconds': 43200., 'raw_source_species_exact': ['QC', 'QI', 'QR', 'QS'],
                'mask_binary_and_exact_to_reference': True, 'sw_recorded_input_mask_and_raw_gas_tau_exact': phase == 'SW',
                'production': independent_result_parser(OUT/'capture'/(phase.lower()+'.result'), production),
                'reference': independent_result_parser(OUT/'capture'/(phase.lower()+'.reference.result'), reference)}
            write(OUT/'independent-parser-proof.json', rec['independent_parser_proof'])
            write(OUT/'recovery-receipt.json', rec)
        assert len(rec['reference_invocations']) == 2
        rec['status'] = 'STRICT_LW_SW_REPLAY_RECOVERY_PASS'
    except Exception as exc:
        rec.update(status='RECOVERY_FAIL_PRESERVED', error=repr(exc))
    finally:
        if audit is not None:
            # Restore subprocess before the source checker, even on a replay failure.
            if 'original_run' in locals():
                replay.subprocess.run = original_run
            try:
                rec['source_after'] = audit.verify_build_manifest(ROOT, source, Path(plan['executable']['path']))
                assert rec['source_after'] == rec['source_before']
            except Exception as exc:
                rec.update(status='RECOVERY_FAIL_PRESERVED', source_postflight_error=repr(exc))
        try:
            verify_pins()
            for name, digest in captures.items():
                assert sha(OUT/'capture'/name) == digest
            rec['all_pins_original_failures_and_copied_captures_unchanged'] = True
        except Exception as exc:
            rec.update(status='RECOVERY_FAIL_PRESERVED', pin_postflight_error=repr(exc))
        rec['output_hashes'] = {str(path.relative_to(OUT)): sha(path) for path in sorted(OUT.rglob('*'))
                                if path.is_file() and path.name != 'recovery-receipt.json'}
        write(OUT/'recovery-receipt.json', rec)
    print(rec['status'])
    assert rec['status'] == 'STRICT_LW_SW_REPLAY_RECOVERY_PASS'


if __name__ == '__main__':
    main()
