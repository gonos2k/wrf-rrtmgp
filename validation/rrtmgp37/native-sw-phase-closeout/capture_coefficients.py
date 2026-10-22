#!/usr/bin/env python3
"""Pin actual configured data files, labeling observation time honestly."""
from pathlib import Path
import argparse, hashlib, json, re, time

P = Path(__file__).resolve().parent
B = P.parents[2].parent
H = B / 'udm37-native-sw-day-v2'
O = B / 'udm37-native-sw-analysis-v1'
O.mkdir(exist_ok=True)
parser = argparse.ArgumentParser()
parser.add_argument('--stage', choices=['during', 'after'], default='after')
args = parser.parse_args()
if args.stage == 'after':
    assert json.loads((H / 'receipt.json').read_text())['status'] in ['SUCCESS', 'STOPPED']
nml = (H / 'host/namelist.input').read_text()

def configured(name):
    return Path(re.search(r'(?im)^\s*' + name + r"\s*=\s*'([^']+)'", nml)[1])

def pin(path):
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'bytes': path.stat().st_size, 'mtime_ns': path.stat().st_mtime_ns}

names = ['rrtmgp-gas-lw-g128.nc', 'rrtmgp-gas-sw-g112.nc',
         'rrtmgp-clouds-lw-bnd.nc', 'rrtmgp-clouds-sw-bnd.nc']
result = {'observed_at_epoch': time.time(), 'stage': args.stage,
          'files': {n: pin(configured('rrtmgp_data_path') / n) for n in names},
          'frozen_table': pin(configured('rrtmgp_udm_frozen_table'))}
target = O / ('coefficients-' + args.stage + '.json')
with target.open('x') as f:
    json.dump(result, f, indent=2)
    f.write('\n')
print('ACTUAL_COEFFICIENT_FILES_PINNED', args.stage)
