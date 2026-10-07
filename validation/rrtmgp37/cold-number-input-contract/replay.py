#!/usr/bin/env python3
"""Reapply saved executed checker to archived NetCDF/logs; not independent arithmetic."""
import gzip
import ast
import collections
import hashlib
import shutil
import struct
import types
import netCDF4
import numpy as np
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
# Compile the unchanged recorded function bodies; skip model/staging imports.
source=(ROOT/'scripts/test_udm_connected_host.py').read_text()
names={'parse','verify_join','verify_input_numbers','verify_input_negative_controls'}
module=ast.parse(source)
module.body=[node for node in module.body if isinstance(node,ast.FunctionDef) and node.name in names]
if len(module.body)!=len(names):raise ValueError('saved function roster missing')
def pin(path):
    data=path.read_bytes()
    return {'path':str(path.resolve()),'size_bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
namespace=dict(globals(),pin=pin)
exec(compile(module,'saved executed checker functions','exec'),namespace)
c=types.SimpleNamespace(**{name:namespace[name] for name in names})
r=json.loads((ROOT/'runtime/receipt.json').read_text())
with tempfile.TemporaryDirectory() as temp:
    temp=Path(temp)
    for arm in ('nonuniform-on','empty-qnn-on','warm-cloud-on','restart-on'):
        data=temp/arm;data.mkdir()
        for key in ('input','log'):
            (data/key).write_bytes(gzip.decompress((ROOT/f'runtime/{arm}/{key}.gz').read_bytes()))
        events=c.parse(data/'log');restart=arm=='restart-on'
        checks=c.verify_join(events,restart=restart)
        checks.update(c.verify_input_numbers(events,data/'input',empty_qnn=arm=='empty-qnn-on',restart=restart))
        stored=r['arms'][arm]['joined_checks']
        if any(stored[k]!=v for k,v in checks.items()):raise ValueError('saved checks differ')
        if arm=='nonuniform-on':
            rejected=c.verify_input_negative_controls(events,data/'input',data/'negative')
            if rejected!=r['input_contract_negative_controls']:raise ValueError('saved negative controls differ')
print('PASS_SCOPED_SAVED_CHECKER_REPLAY; no new model runs')
