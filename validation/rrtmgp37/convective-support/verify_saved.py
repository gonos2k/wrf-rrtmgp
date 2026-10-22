#!/usr/bin/env python3
"""Portable replay of existing rain fields and the terminal fixed-period record."""
from pathlib import Path
import argparse, gzip, hashlib, importlib.util, io, json, re, tarfile

P = Path(__file__).resolve().parent
R = P.parents[2]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

S = load('convective_spatial', P / 'analyze_spatial.py')
A = load('convective_runtime', P / 'analyze_run.py')
M = load('convective_summary', P / 'summarize.py')
I = load('convective_instrument', P / 'instrument.py')
V = load('retained_real_budget', P.parent / 'real-case-budget/verify_saved.py')
H = load('historical_convective_sources', P.parent / 'historical-source/binding.py')
require = A.require

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def data():
    identity = json.loads((P / 'identity.json').read_text())
    raw = (P / 'saved/evidence.tar.gz').read_bytes()
    require(sha(raw) == identity['archive']['sha256'], 'archive hash')
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(raw)), mode='r:') as tar:
        require(set(tar.getnames()) == set(identity['files']), 'unindexed archive')
        d = {name: tar.extractfile(name).read() for name in identity['files']}
    for name, pin in identity['files'].items():
        require(sha(d[name]) == pin['sha256'] and len(d[name]) == pin['bytes'], 'payload ' + name)
    root = H.HistoricalRoot(R, identity['current_sources'])
    for name, pin in identity['current_sources'].items():
        require(sha((root / name).read_bytes()) == pin['sha256'], 'historical source ' + name)
    for name, source in I.transform(root).items():
        require(d['build/' + name] == source.encode(), 'generated observer source ' + name)
        folder = 'WRF/dyn_em' if name in ['solve_em.F', 'module_em.F'] else 'WRF/phys'
        V.readonly((root / folder / name).read_text(), source)
    require(d['build/probe.f90'] == (P / 'probe.f90').read_bytes(), 'compiled observer helper')
    build = json.loads(d['build/receipt.json'])
    host = json.loads(d['host/receipt.json'])
    require(build['executable']['sha256'] == host['executable']['sha256'], 'runtime executable')
    for name, pin in build['private_sources'].items():
        require(sha(d['build/' + name]) == pin['sha256'], 'compiled private source ' + name)
    for name, pin in build['public_sources'].items():
        require(sha((root / name).read_bytes()) == pin['sha256'], 'compiled historical public source ' + name)
    require(all(c['actual_returncode'] == 0 and not c['timed_out'] for c in build['commands']), 'build failed')
    require(len(host['commands']) == 1, 'not one preregistered cold model process')
    require(host['status'] in ['SUCCESS', 'STOPPED'], 'cannot deposit a running evaluation')
    if host['status'] == 'SUCCESS':
        c = host['commands'][0]
        log = d['host/command-01.stdout'].decode(errors='replace')
        require(c['actual_returncode'] == 0 and not c['timed_out'], 'successful run receipt contradicts command')
        require('SUCCESS COMPLETE WRF' in log and 'FATAL CALLED' not in log, 'terminal success missing')
        require(host['last_model_times'][-1] == '2016-10-07_00:00:00', '24-hour terminal model time')
    require(host['plan']['sha256'] == sha(d['plan.json']) == sha((P / 'plan.json').read_bytes()), 'preregistered plan changed')
    require(host['namelist']['sha256'] == sha(d['host/host/namelist.input']), 'runtime namelist')
    require(host['trace']['sha256'] == sha(d['host/real-budget.txt']), 'runtime trace')
    prior = V.data()
    prior_receipt = json.loads(prior['host/receipt.json'])
    require(host['forcing']['sha256'] == prior_receipt['forcing']['sha256'], 'original real forcing changed')
    inventory = json.loads(prior['inventory.json'])
    require(host['initial']['sha256'] == inventory['availability'][0]['file']['sha256'], 'original initial state changed')
    require(build['base_library']['sha256'] == json.loads(prior['build/receipt.json'])['base_library']['sha256'], 'corrected public library changed')
    old = V.load('retained_corrected_restart', P.parent / 'restart-first-step/verify_saved.py').data()
    expected = old['fixed/continuous/namelist.input'].decode()
    for name, value in {'run_seconds':'86400', 'end_day':'07', 'end_hour':'0', 'end_minute':'0',
                        'end_second':'0', 'history_begin_s':'0', 'history_interval_s':'3600',
                        'restart_interval_s':'1000000'}.items():
        expected, count = re.subn(r'(?im)^(\s*' + name + r'\s*=\s*)[^,\n]+', lambda m: m[1] + value, expected)
        require(count == 1, 'declared output/duration edit ' + name)
    require(expected.encode() == d['host/host/namelist.input'], 'physics or guard configuration changed')
    actual_nml = d['host/host/namelist.output'].decode()
    require(re.search(r'(?im)^\s*SWINT_OPT\s*=\s*0\s*,', actual_nml), 'SW interpolation invalidates call-hold diagnostic')
    before = json.loads(d['coefficients-during.json'])['files']
    final_coefficients = json.loads(d['coefficients-after.json'])
    after = final_coefficients['files']
    require(set(before) == set(after), 'coefficient file set changed')
    require(all(before[n]['sha256'] == after[n]['sha256'] for n in before), 'coefficient bytes changed')
    frozen = final_coefficients['frozen_table']
    require(frozen['sha256'] == sha((P.parent / 'frozen-planck-coverage/expanded/frozen-ice-psd-moments.nc').read_bytes()), 'actual configured frozen table changed')
    nml = d['host/host/namelist.input'].decode()
    data_path = re.search(r"(?im)^\s*rrtmgp_data_path\s*=\s*'([^']+)'", nml)[1]
    frozen_path = re.search(r"(?im)^\s*rrtmgp_udm_frozen_table\s*=\s*'([^']+)'", nml)[1]
    require(frozen_path == frozen['path'], 'frozen pin is not the configured file')
    require(all(str(Path(data_path) / n) == after[n]['path'] == before[n]['path'] for n in after), 'optical pins are not configured files')
    return d

def check_history(history, run):
    states = history['states']
    require(history['records'] == len(states), 'history record inventory')
    require(len({s['time'] for s in states}) == len(states), 'duplicate history time')
    for s in states:
        require(set(s['water_species_kg_m2']) == set(['QVAPOR', 'QCLOUD', 'QRAIN', 'QICE', 'QSNOW', 'QGRAUP', 'QHAIL']), 'history water species omission')
        require(len(history['array_inventory'][s['time']]) == 225, 'history array omission')
    require(not history['forecast_skill_approved'], 'no observations for forecast approval')
    overlap = history['original_overlap']
    require(len(overlap) == 1 and overlap[0]['time'] == '2016-10-06_06:00:00', 'original trajectory overlap missing')
    require(overlap[0]['compared_arrays'] == 225 and overlap[0]['all_byte_equal'] and not overlap[0]['differences'], 'observer changed original trajectory')
    if run['target_period_completed']:
        from datetime import datetime, timedelta
        expected = [(datetime(2016, 10, 6) + timedelta(hours=h)).strftime('%Y-%m-%d_%H:%M:%S') for h in range(25)]
        require([s['time'] for s in states] == expected, '24-hour hourly history coverage')

def evaluate(d):
    prior = json.loads((P.parent / 'real-case-budget/result.json').read_text())
    meta = json.loads(d['rain-spatial.json'])
    history = json.loads(d['history.json'])
    require(meta['source_file']['sha256'] == history['original_corrected_history']['sha256'], 'spatial source detached from original history')
    old = json.loads(V.load('original_history_binding', P.parent / 'restart-first-step/verify_saved.py').data()['analysis.json'])
    require(meta['source_file']['sha256'] == old['fixed_restart']['left_file']['sha256'], 'spatial source is not original corrected continuous history')
    for overlap in history['original_overlap']:
        t = overlap['time']
        for name, pin in old['fixed_restart']['inventory'][t].items():
            require(history['array_inventory'][t][name]['sha256'] == pin['left_sha256'], 'original overlap array ' + name)
    # The saved precipitation bytes are exact arrays from that original NetCDF.
    for t in meta['times']:
        if t not in old['fixed_restart']['inventory']:
            continue  # 05:59 is bound by the original whole-file pin; old per-array inventory starts 06:00.
        for name in meta['fields']:
            require(meta['field_sha256'][t][name] == old['fixed_restart']['inventory'][t][name]['left_sha256'], 'precipitation field detached from original history')
    spatial = S.analyze(d['rain-spatial.bin'], meta, prior)
    run = A.analyze(d['host/real-budget.txt'].decode(), json.loads(d['host/receipt.json']))
    check_history(history, run)
    result = M.summarize(spatial, run, history)
    require(all(not result[k] for k in ['water_conservation_approved', 'whole_energy_approved', 'frozen_accuracy_approved', 'forecast_skill_approved']), 'scientific status promotion')
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    result = evaluate(data())
    if args.write:
        (P / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    else:
        require(result == json.loads((P / 'result.json').read_text()), 'result detached from saved inputs')
    print(json.dumps({k: result[k] for k in ['status', 'target_period_completed', 'completed_seconds', 'model_steps', 'history_records']}))
    identity = json.loads((P / 'identity.json').read_text())
    matches = all(sha((R / name).read_bytes()) == pin['sha256'] for name, pin in identity['current_sources'].items())
    print('current_runtime_source_matches=' + str(matches).lower() + ' source_scope=' + ('current' if matches else 'historical_PR192_snapshot') + ' new_model_runs=0 water_conservation_approved=false whole_energy_approved=false')

if __name__ == '__main__':
    main()
