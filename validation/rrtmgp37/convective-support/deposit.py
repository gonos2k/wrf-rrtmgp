#!/usr/bin/env python3
"""Freeze terminal evidence only; never synthesize missing model observations."""
from pathlib import Path
import gzip, hashlib, io, json, tarfile

P = Path(__file__).resolve().parent
R = P.parents[2]
B = R.parent
O = B / 'udm37-convective-support-analysis-v1'
H = B / 'udm37-convective-support-host-v1'
assert json.loads((H / 'receipt.json').read_text())['status'] in ['SUCCESS', 'STOPPED']
payload = {}

def put(name, path):
    payload[name] = path.read_bytes()

def pin(path):
    raw = path.read_bytes()
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}

for name in ['rain-spatial.bin', 'rain-spatial.json', 'history.json',
             'coefficients-during.json', 'coefficients-after.json']:
    put(name, O / name)
put('plan.json', P / 'plan.json')
for directory, key in [('udm37-convective-support-build-v2', 'build'),
                       ('udm37-convective-support-host-v1', 'host')]:
    directory = B / directory
    put(key + '/receipt.json', directory / 'receipt.json')
    for pattern in ['command-*.*', '*.F', 'probe.f90', '*/namelist.input',
                    '*/namelist.output', '*/radiation_iofields.txt']:
        for path in sorted(directory.glob(pattern)):
            put(key + '/' + str(path.relative_to(directory)), path)
put('host/real-budget.txt', H / 'host/real-budget.txt')
# v1 was compiled but never executed. Keep its actual command history separate.
for pattern in ['receipt.json', 'command-*.*']:
    for path in sorted((B / 'udm37-convective-support-build-v1').glob(pattern)):
        put('development/unused-build-v1/' + path.name, path)

buffer = io.BytesIO()
files = {}
with tarfile.open(fileobj=buffer, mode='w') as tar:
    for name, raw in sorted(payload.items()):
        info = tarfile.TarInfo(name)
        info.size = len(raw)
        info.mtime = 0
        tar.addfile(info, io.BytesIO(raw))
        files[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
(P / 'saved').mkdir(exist_ok=True)
archive = P / 'saved/evidence.tar.gz'
archive.write_bytes(gzip.compress(buffer.getvalue(), mtime=0))
names = list(json.loads((P.parent / 'real-case-budget/identity.json').read_text())['current_sources'])
names += ['WRF/phys/module_cumulus_driver.F', 'WRF/phys/module_cu_kfeta.F',
          'WRF/Registry/Registry.EM_COMMON', 'validation/rrtmgp37/real-case-budget/identity.json',
          'validation/rrtmgp37/real-case-budget/result.json']
names += [str(path.relative_to(R)) for path in P.glob('*.py') if path.name != 'deposit.py']
names += [str((P / name).relative_to(R)) for name in ['probe.f90', 'plan.json']]
identity = {
    'base_commit': 'e513d6144e4208d136cba68b5db7e3f9d1e6584c',
    'base_tree': 'a22a6555ca6b99c68dc7ae2cecf62d42f5661940',
    'current_sources': {name: pin(R / name) for name in sorted(set(names))},
    'files': files, 'archive': pin(archive),
    'large_history_scope': 'Decoded locally, with per-array hashes and a whole-file pin. Saved CI checks the inventory and reduced operands; it does not read the large NetCDF again.',
    'qualified_model_processes': 1, 'unused_build_model_processes': 0,
    'production_changes': False, 'scientific_approval': False,
}
(P / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
print('CONVECTIVE_SUPPORT_DEPOSITED', len(files), archive.stat().st_size)
