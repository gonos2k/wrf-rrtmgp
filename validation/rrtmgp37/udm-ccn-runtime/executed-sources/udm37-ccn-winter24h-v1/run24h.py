#!/usr/bin/env python3
"""New CCN-fixed 24h MPI4/OMP2 case; immutable helpers, explicit model GO."""
import argparse, hashlib, importlib.util, json, re
from pathlib import Path
from netCDF4 import Dataset
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HELPER = ROOT / 'build/udm37-ccn-current-runtime-v1/runtime.py'
HELPER_SHA = '9d48cb124387a77363f7888b54e2dc876b94b497e293f32a157a37b0d1efd0aa'
INTEGRITY = HELPER.parent / 'runtime_integrity.py'
INTEGRITY_SHA = 'a53ee3df414bd4a792baefbce38c82b4df8d7e29aeb0f2bbccb06fe456e4d4b8'
for path, expected in ((HELPER, HELPER_SHA), (INTEGRITY, INTEGRITY_SHA)):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('immutable new runtime helper changed: ' + str(path))
sp = importlib.util.spec_from_file_location('frozen_ccn_runtime24', HELPER)
h = importlib.util.module_from_spec(sp)
sp.loader.exec_module(h)
m = h.m
CASE = HERE / 'case'
STAGE = HERE / 'stage.json'

def nml(text):
    if re.search(r'(?im)^\s*numtiles\s*=', text):
        raise ValueError('unexpected parent numtiles')
    text, count = re.subn(r'(?im)^(\s*max_dom\s*=\s*1\s*,?\s*)$',
                         lambda x: x[0] + '\n numtiles = 2,', text)
    if count != 1:
        raise ValueError('not the accepted single-domain parent')
    return text

def prepare(go):
    m.collision(CASE); m.collision(STAGE)
    identity = h.integrity.verify_build()
    parent, oldstage, args = h.parent_data('ra37')
    source = Path(oldstage['case']['case_path'])
    original = source / 'namelist.input'
    text = nml(original.read_text())
    if not go:
        return {'status': 'READY_NOT_STAGED', 'model_invocations': 0}
    CASE.mkdir()
    for name in oldstage['case']['link_names']:
        target = h.FRESH if name == 'wrf.exe' else (source / name).resolve(strict=True)
        (CASE / name).symlink_to(target)
    (CASE / 'namelist.input').write_text(text)
    e = dict(oldstage['case'])
    e.update(case_path=str(CASE), threads=2)
    e['snapshot'] = m.snapshot_case(e)
    r = {'status': 'STAGED_NOT_RUN', 'model_invocations': 0, 'runner': m.pin(Path(__file__)),
         'helper': m.pin(HELPER), 'integrity': m.pin(INTEGRITY), 'build': identity,
         'parent': m.pin(h.base.PARENT), 'original_namelist': m.pin(original), 'case': e}
    m.write_json(STAGE, r)
    invariants(m.digest(STAGE))
    return {'status': 'STAGED_NOT_RUN', 'stage': m.pin(STAGE)}

def invariants(stage_sha):
    m.require_hash(STAGE, stage_sha)
    r = json.loads(STAGE.read_text())
    if r['status'] != 'STAGED_NOT_RUN' or r['model_invocations'] != 0:
        raise ValueError('invalid immutable stage')
    for key in ('runner', 'helper', 'integrity', 'parent', 'original_namelist'):
        m.check_pin(r[key])
    if r['runner'] != m.pin(Path(__file__)) or h.integrity.verify_build() != r['build']:
        raise ValueError('runner/build changed')
    parent, oldstage, args = h.parent_data('ra37')
    e = r['case']
    if m.snapshot_case(e) != e['snapshot']:
        raise ValueError('case input bindings changed')
    if (CASE / 'namelist.input').read_text() != nml(Path(r['original_namelist']['path']).read_text()):
        raise ValueError('run configuration changed')
    return r, args, parent

def outputs(parent):
    hs = sorted(CASE.glob('wrfout_d01_*')); cs = sorted(CASE.glob('wrfrst_d01_*'))
    if [p.name for p in hs] != ['wrfout_d01_' + m.TIMES[0]] or [p.name for p in cs] != ['wrfrst_d01_' + t for t in m.RESTART_TIMES]:
        raise ValueError('unexpected output file/clock set')
    history = m.validate_dataset(hs[0], m.TIMES, 37)
    history['default_fill_check'] = h.base.default_fills(hs[0])
    checkpoints = []
    for p, t in zip(cs, m.RESTART_TIMES):
        c = m.validate_dataset(p, [t], 37)
        c['surface'] = m.checkpoint_diagnostics(p)
        c['default_fill_check'] = h.base.default_fills(p)
        with Dataset(p) as ds:
            ds.set_auto_maskandscale(False)
            c['cu_positive_cells'] = {v: int(np.count_nonzero(ds[v][:] > 0)) for v in ('QC_CU', 'QI_CU')}
        checkpoints.append(c)
    with Dataset(hs[0]) as ds:
        icloud_cu = int(ds.getncattr('ICLOUD_CU'))
    same_old = h.base.compare_file(hs[0], Path(parent['outputs']['history']['file']['path']))
    good = history['passed'] and history['variable_count'] == 225 and history['numeric_variable_count'] == 224 and history['default_fill_check']['passed'] and icloud_cu == 2
    good = good and all(c['passed'] and c['variable_count'] == 664 and c['numeric_variable_count'] == 663 and c['default_fill_check']['passed'] and c['surface']['passed'] for c in checkpoints)
    return {'passed': bool(good), 'history': history, 'checkpoints': checkpoints, 'icloud_cu': icloud_cu,
            'old_one_tile_history_comparison': same_old,
            'scope': 'New-source 24h finite-output validation; old trajectory comparison is reported separately.'}

def run(stage_sha, execute):
    out = HERE / 'execution.json'; m.collision(out)
    r, args, parent = invariants(stage_sha)
    m.unused_case(r['case'])
    if not execute:
        return {'status': 'READY_NOT_RUN', 'actual_model_invocations': 0}
    result = {'status': 'RUNNING', 'stage': m.pin(STAGE), 'runner': m.pin(Path(__file__)),
              'actual_model_invocations': 0, 'before_pins_valid': True}
    m.write_json(out, result)
    original = m._original.clean_run_env
    def env(*a):
        v, cleared = original(*a)
        extra = [k for k in v if k.startswith(('WRF_UDM_', 'WRF_OMP_', 'GOMP_', 'KMP_'))]
        for k in extra: v.pop(k)
        v.update(OMP_NUM_THREADS='2', OMP_DYNAMIC='FALSE', OMP_MAX_ACTIVE_LEVELS='1', OMP_NESTED='FALSE', OMP_PROC_BIND='FALSE', OPENBLAS_NUM_THREADS='1')
        result['runtime_env'] = {k: x for k, x in v.items() if k.startswith(('OMP_', 'WRF_')) or k in ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'MPICH_INTERFACE_HOSTNAME', 'OPENBLAS_NUM_THREADS')}
        return v, sorted(set(cleared + extra))
    try:
        m._original.clean_run_env = env
        def launched(pid):
            result.update(actual_model_invocations=1, process_group_pid=pid); m.write_json(out, result)
        result['model'] = m.run_one(r['case'], args, on_launch=launched)
        result['outputs'] = outputs(parent)
        result['status'] = 'PASS_SCOPED_24H_NEW_CCN_SOURCE' if result['model']['model_completed'] and result['outputs']['passed'] else 'FAIL_PRESERVED'
    except Exception as exc:
        result.update(status='FAIL_PRESERVED', error=repr(exc))
    finally:
        m._original.clean_run_env = original
        try: invariants(stage_sha); result['after_pins_valid'] = True
        except Exception as exc: result.update(status='FAIL_PRESERVED', after_pins_valid=False, pin_error=repr(exc))
        m.write_json(out, result)
    return result

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=('prepare', 'run')); p.add_argument('--prepare-go', action='store_true'); p.add_argument('--execute', action='store_true'); p.add_argument('--stage-sha'); a = p.parse_args()
    result = prepare(a.prepare_go) if a.mode == 'prepare' else run(a.stage_sha, a.execute)
    print(json.dumps({'status': result['status'], 'actual_model_invocations': result.get('actual_model_invocations', 0), 'stage': result.get('stage')}))
    raise SystemExit(0 if result['status'].startswith(('READY', 'STAGED', 'PASS')) else 1)
