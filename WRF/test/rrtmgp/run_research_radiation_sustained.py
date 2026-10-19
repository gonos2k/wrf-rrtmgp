#!/usr/bin/env python3
"""Run a preregistered sustained 00/11 discriminator using the frozen normal WRF build."""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import numpy as np
import netCDF4


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('exe', 'template', 'positive', 'plan', 'workdir', 'library_dir'):
        ap.add_argument('--' + name.replace('_', '-'), required=True, type=Path)
    ap.add_argument('--stage', choices=['hour', 'day'], default='hour')
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[2]
    h = load(root / 'test/rrtmgp/test_netcdf_zz.py', 'durable_runner')
    setup = load(root / 'test/rrtmgp/test_udm_startup_snow_scm.py', 'namelist_setup')
    plan = json.loads(a.plan.read_text())
    for p, key in ((a.exe, 'executable_sha256'), (a.positive, 'input_sha256')):
        if h.pin(p)['sha256'] != plan[key]:
            raise ValueError('frozen identity differs: ' + str(p))
    stage = next(x for x in plan['stages'] if x['name'] == a.stage)
    if a.stage == 'day':
        gate = a.workdir.parent / 'hour' / 'receipt.json'
        if not gate.exists() or json.loads(gate.read_text()).get('status') != 'COMPLETED_DISCRIMINATOR':
            raise ValueError('hour discriminator has not passed; day campaign prohibited')
    out = a.workdir.resolve()
    out.mkdir(exist_ok=False, parents=True)
    shutil.copy2(a.plan, out / 'preregistration.json')
    env = dict(os.environ, OMP_NUM_THREADS='1')
    env['LD_LIBRARY_PATH'] = str(a.library_dir.resolve()) + ':' + env.get('LD_LIBRARY_PATH', '')
    for key in list(env):
        if key.startswith(('WRF_RRTMGP_', 'WRF_UDM_', 'WRF_RESEARCH_', 'WRF_RADIATION_ENERGY')):
            env.pop(key)
    runner = h.Runner(out, 10800 if a.stage == 'day' else 900, env, 2)
    receipt = {'schema': 'SUSTAINED_RESEARCH_RUN_V1', 'stage': a.stage,
               'preregistration': h.pin(out / 'preregistration.json'),
               'executable': h.pin(a.exe), 'physical_input': h.pin(a.positive),
               'library_directory': str(a.library_dir.resolve()),
               'production_accepted': False, 'cases': [], 'status': 'PREPARED'}
    def save():
        receipt['processes'] = runner.commands
        h.write_json(out / 'receipt.json', receipt)
    start = dt.datetime.strptime(plan['fixed']['start'], '%Y-%m-%d_%H:%M:%S')
    end = start + dt.timedelta(seconds=stage['duration_seconds'])
    save()
    for cap, size in plan['policies']:
        name = f'{a.stage}_{cap}{size}'
        d = out / name
        d.mkdir()
        for p in a.template.iterdir():
            if p.is_file() and not p.name.startswith(('wrfout', 'wrfrst', 'rsl.', 'udm_')) and p.name not in ('stdout.log', 'namelist.output'):
                shutil.copy2(p, d / p.name)
        shutil.copy2(a.positive, d / 'wrfinput_d01')
        with netCDF4.Dataset(d / 'wrfinput_d01', 'r+') as nc:
            nc.setncattr('RRTMGP_CAPACITY_POLICY', np.int32(cap))
            nc.setncattr('RRTMGP_LIQUID_SIZE_POLICY', np.int32(size))
        with netCDF4.Dataset(a.positive) as x, netCDF4.Dataset(d / 'wrfinput_d01') as y:
            if any(np.asarray(x[n][:]).tobytes() != np.asarray(y[n][:]).tobytes() for n in x.variables):
                raise ValueError('physical input arrays changed')
        text = (a.template / 'namelist.input').read_text()
        settings = [(k, str(v), 'time_control') for k, v in {
            'run_days': stage['duration_seconds'] // 86400,
            'run_hours': stage['duration_seconds'] % 86400 // 3600,
            'run_minutes': 0, 'run_seconds': 0,
            'end_year': end.year, 'end_month': end.month, 'end_day': end.day,
            'end_hour': end.hour, 'end_minute': end.minute, 'end_second': end.second,
            'history_interval': 0, 'history_interval_s': stage['history_interval_seconds'],
            'restart_interval': 0, 'restart_interval_s': stage.get('checkpoint_interval_seconds', 21610)
        }.items()]
        settings += [('restart', '.false.', 'time_control'),
                     ('rrtmgp_capacity_policy', str(cap), 'physics'),
                     ('rrtmgp_liquid_size_policy', str(size), 'physics'),
                     ('radt', '0.5', 'physics')]
        for key, val, group in settings:
            text = setup.set_assignment(text, key, val, group=group)
        (d / 'namelist.input').write_text(text)
        (d / 'capture').mkdir()
        # A single late call is retained; do not export every g-point every step.
        runner.environment.update(WRF_RRTMGP_CAPTURE_DIR=str(d / 'capture'),
                                  WRF_RRTMGP_CAPTURE_CALL='61', WRF_RRTMGP_BATCH_SIZE='1')
        c = {'name': name, 'policy': [cap, size], 'namelist': h.pin(d / 'namelist.input'),
             'input': h.pin(d / 'wrfinput_d01'), 'requested_end': end.isoformat(), 'status': 'STARTED'}
        receipt['cases'].append(c)
        save()
        try:
            stdout = runner.run([a.exe.resolve()], d, name)
            log = stdout.read_text(errors='replace')
        except BaseException as e:
            log = (out / f'command-{runner.attempts:02d}.stdout').read_text(errors='replace')
            c['exception'] = repr(e)
        stderr = (out / f'command-{runner.attempts:02d}.stderr').read_text(errors='replace')
        c['stderr'] = stderr
        fatal = 'FATAL CALLED' in log
        if 'error while loading shared libraries' in stderr:
            c['status'] = 'ENVIRONMENT_ERROR_BEFORE_MODEL'
        elif fatal and any(s in log for s in ('warm-only column required', 'warm liquid/rain scope', 'cold/frozen', 'all-warm', 'requires warm', 'CF0 condensate unsupported')):
            c['status'] = 'SCOPE_REJECTED'
        elif not fatal and 'SUCCESS COMPLETE WRF' in log and not c.get('exception'):
            c['status'] = 'COMPLETED'
        else:
            c['status'] = 'NUMERICAL_OR_EXECUTION_FAILURE'
        c['stdout_tail'] = log[-5000:]
        history = sorted(d.glob('wrfout*'))
        if history:
            with netCDF4.Dataset(history[0]) as nc:
                times = netCDF4.chartostring(nc['Times'][:]).tolist()
                c['history_times'] = times
                c['finite_history'] = all(np.isfinite(np.asarray(v[:])).all() for v in nc.variables.values() if v.dtype.kind in 'fiu')
                c['ranges'] = {n: {'min': float(np.min(nc[n][:])), 'max': float(np.max(nc[n][:]))} for n in
                               ('T', 'QVAPOR', 'QCLOUD', 'QRAIN', 'QNCLOUD', 'QNRAIN', 'QNCCN', 'RE_CLOUD', 'CLDFRA', 'SWDOWN', 'COSZEN', 'RTHRATEN') if n in nc.variables}
                if c['status'] == 'COMPLETED' and (not c['finite_history'] or times[-1] != end.strftime('%Y-%m-%d_%H:%M:%S')):
                    c['status'] = 'DIAGNOSTIC_FAILURE'
        if c.get('status') == 'COMPLETED' and any(c['ranges'][n]['min'] < 0 for n in ('QVAPOR', 'QCLOUD', 'QRAIN', 'QNCLOUD', 'QNRAIN', 'QNCCN') if n in c.get('ranges', {})):
            c['status'] = 'NEGATIVE_STATE_REQUIRES_REVIEW'
        save()
        print(json.dumps({'case': name, 'status': c['status'], 'last_history': c.get('history_times', [None])[-1]}), flush=True)
    receipt['status'] = 'COMPLETED_DISCRIMINATOR' if all(c['status'] == 'COMPLETED' for c in receipt['cases']) else 'STOPPED_DISCRIMINATOR'
    save()

if __name__ == '__main__':
    main()
