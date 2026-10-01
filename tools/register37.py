#!/usr/bin/env python3
"""Register option 37 in vendored official WRF; keep execution fail-closed."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WRF = ROOT / 'WRF'
ORIGINAL = {
 'Registry/Registry.EM_COMMON': 'd0065b60635e6e7b8046523e5048d4b9014a1a7a',
 'phys/module_physics_init.F': '9e604a4f37ec2871035a93491fa07f7bfe873c1b',
 'phys/module_radiation_driver.F': '00cfd82f25ef3e1586b9c5c41a8a71d1c6e6e496',
}
MARKER = '! RRTMGP37_OFFICIAL_REGISTRATION_ONLY'

def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()

def guard(lw, sw):
    return f'''{MARKER}
   ! The backend is not yet connected to the WRF host. Never use silent fallback.
   IF (({lw} == 37) .NEQV. ({sw} == 37)) THEN
      CALL wrf_error_fatal('RRTMGP37_PAIR_REQUIRED: select both LW and SW option 37')
      RETURN
   END IF
   IF ({lw} == 37 .OR. {sw} == 37) THEN
      CALL wrf_error_fatal('RRTMGP37_BACKEND_NOT_LINKED: no radiation fallback')
      RETURN
   END IF
! END_RRTMGP37_OFFICIAL_REGISTRATION_ONLY

'''

def main():
    receipt = ROOT / 'config/registration37.json'
    if receipt.exists():
        previous = json.loads(receipt.read_text())
        for name, sha in previous['patched_blobs'].items():
            if blob((WRF / name).read_bytes()) != sha:
                raise ValueError('MODIFIED_REGISTERED_SOURCE: ' + name)
        print('REGISTRATION37_ALREADY_APPLIED_AND_VERIFIED')
        return
    originals = {}
    for name, expected in ORIGINAL.items():
        data = (WRF / name).read_bytes()
        if blob(data) != expected:
            raise ValueError('ORIGINAL_BLOB_MISMATCH: ' + name)
        originals[name] = data.decode('utf-8')
    fragment_name = 'Registry/registry.rrtmgp37'
    if (WRF / fragment_name).exists():
        raise ValueError('REGISTRY_FRAGMENT_ALREADY_EXISTS')
    common = originals['Registry/Registry.EM_COMMON']
    records = list(re.finditer(r'^\s*package\s+(\w+)\s+ra_(lw|sw)_physics\s*==\s*(\d+)\s+(-)\s+([^\r\n]+)$', common, re.M | re.I))
    if any(int(m[3]) == 37 for m in records):
        raise ValueError('RADIATION37_ALREADY_REGISTERED')
    lines = ['# RRTMGP registration only; WRF runtime remains guarded.', '# Allocation requirements mirror RRTMG; not a statement of cloud/aerosol support.']
    for band in ('lw', 'sw'):
        matches = [m for m in records if m[2].lower() == band and int(m[3]) == 4]
        if len(matches) != 1 or matches[0][1].lower() != f'rrtmg_{band}scheme':
            raise ValueError('UNIQUE_RRTMG_BASE_REQUIRED')
        lines.append(f'package rrtmgp_{band}scheme ra_{band}_physics==37 - {matches[0][5]}')
    rad = originals['phys/module_radiation_driver.F']
    rad_anchor = '   logical, save :: feedback_restart, direct_sw_feedback\n\n'
    if rad.count(rad_anchor) != 1:
        raise ValueError('RADIATION_ANCHOR_CHANGED')
    rad = rad.replace(rad_anchor, rad_anchor + guard('lw_physics', 'sw_physics'), 1)
    init = originals['phys/module_physics_init.F']
    start = re.search(r'^\s*SUBROUTINE\s+ra_init\s*\(', init, re.M | re.I)
    if start is None:
        raise ValueError('RA_INIT_MISSING')
    end = re.search(r'^\s*END\s+SUBROUTINE\s+ra_init\b', init[start.start():], re.M | re.I)
    if end is None:
        raise ValueError('RA_INIT_END_MISSING')
    lo, hi = start.start(), start.start() + end.end()
    body = init[lo:hi]
    anchor = '   INTEGER :: i, j, k, itf, jtf, ktf\n!---------------------------------------------------------------------\n\n'
    if body.count(anchor) != 1:
        raise ValueError('INITIALIZATION_ANCHOR_CHANGED')
    body = body.replace(anchor, anchor + guard('config_flags%ra_lw_physics', 'config_flags%ra_sw_physics'), 1)
    init = init[:lo] + body + init[hi:]
    # Prepare every transformation before the first write.
    changed = {
       'Registry/Registry.EM_COMMON': common.rstrip('\n') + '\n\ninclude registry.rrtmgp37\n',
       fragment_name: '\n'.join(lines) + '\n',
       'phys/module_radiation_driver.F': rad,
       'phys/module_physics_init.F': init,
    }
    patched = {}
    for name, text in changed.items():
        data = text.encode('utf-8')
        (WRF / name).write_bytes(data)
        patched[name] = blob(data)
    receipt.parent.mkdir(exist_ok=True)
    receipt.write_text(json.dumps({'upstream_commit': '06d4240ae989cc3e50af412bb472df3d9048783c', 'original_blobs': ORIGINAL, 'patched_blobs': patched, 'backend': 'NOT_LINKED', 'wrf_forecast_validated': False}, indent=2) + '\n')
    print('REGISTERED37_WITH_INITIALIZATION_AND_RADIATION_GUARDS')

if __name__ == '__main__':
    main()
