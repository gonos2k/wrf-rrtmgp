#!/usr/bin/env python3
"""Read actual NetCDFs, preserve raw captures and immutable process receipts."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import netCDF4
import numpy as np

NAMES = ('QNCCN', 'QNCLOUD', 'QNRAIN', 'QCLOUD', 'QICE', 'QRAIN', 'QSNOW', 'QGRAUP', 'QHAIL', 'CLDFRA')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runtime', type=Path, required=True)
    ap.add_argument('--repository', type=Path, required=True)
    ap.add_argument('--output', type=Path, help='fresh saved evidence directory; default is package/saved')
    args = ap.parse_args()
    root = args.repository.resolve(strict=True)
    package = root / 'validation/rrtmgp37/radiation-occurrence-runtime'
    dest = args.output or package / 'saved'
    dest.mkdir(exist_ok=False)
    sys.path.insert(0, str(root / 'WRF/test/rrtmgp'))
    from test_netcdf_zz import pin
    report = {'netcdf_readback_performed': True, 'case_comparisons': [], 'packets': {},
              'loaded_libraries': {}, 'runtime': str(args.runtime), 'physical_acceptance': False}
    def preserve(p, relative):
        q = dest / relative
        q.parent.mkdir(parents=True, exist_ok=True)
        if str(q).endswith('.gz'):
            q.write_bytes(gzip.compress(p.read_bytes(), mtime=0))
        else:
            shutil.copyfile(p, q)
    for p in args.runtime.glob('*.json'):
        preserve(p, p.name)
    for p in args.runtime.glob('command-*.stdout'):
        preserve(p, p.name + '.gz')
    for p in args.runtime.glob('command-*.stderr'):
        preserve(p, p.name + '.gz')
        init = re.findall(r'calling init:\s*(/[^\n]+)', p.read_text())
        report['loaded_libraries'][p.name] = [pin(Path(n.strip())) for n in init]
    case_names = ['off', 'on-i1-j1', 'on-i2-j1', 'on-i1-j2', 'on-i2-j2']
    off = args.runtime / 'off'
    targets = sorted(p.name for p in off.iterdir() if p.name.startswith(('wrfout', 'wrfrst')))
    if len(targets) != 2:
        raise ValueError('expected one history and one restart output')
    for name in case_names:
        case = args.runtime / name
        for n in ('launch.json', 'namelist.input', 'namelist.output') + tuple(targets):
            preserve(case / n, Path(name) / (n if n.endswith('.json') or n=='namelist.input' else n + '.gz'))
        for p in (case / 'capture').glob('*') if (case/'capture').is_dir() else []:
            preserve(p, Path(name) / 'capture' / (p.name + '.gz'))
        with netCDF4.Dataset(case / targets[0]) as nc:
            nc.set_auto_mask(False)
            times = netCDF4.chartostring(nc['Times'][:]).tolist()
            expected_times=['1999-10-22_19:00:'+str(t).zfill(2) for t in range(0,60,10)]+['1999-10-22_19:01:00','1999-10-22_19:01:10']
            if times != expected_times:
                raise ValueError('unexpected history times')
            data = np.stack([nc[n][6].astype('<f4') for n in NAMES])
            if data.shape != (10, 59, 2, 2):
                raise ValueError('unexpected history packet shape')
            packet = data.tobytes()
            (dest / name / 'history_60s.bin').write_bytes(packet)
            original=np.frombuffer((root/'validation/rrtmgp37/research-policy-contract/history_60s_after_step6.bin').read_bytes(), dtype='<f4').reshape(10,59,2,2)
            report['packets'][name] = {'sha256': sha(packet), 'size_bytes': len(packet), 'time_index': 6,
                                       'times': times, 'names': NAMES, 'shape': list(data.shape),
                                       'original_PR167_variable_changed_cells': {n:int(np.count_nonzero(data[idx].view('u4')!=original[idx].view('u4'))) for idx,n in enumerate(NAMES)},
                                       'original_PR167_packet_bytes_equal': packet == (root/'validation/rrtmgp37/research-policy-contract/history_60s_after_step6.bin').read_bytes()}
        if name == 'off':
            continue
        for n in targets:
            with netCDF4.Dataset(off / n) as a, netCDF4.Dataset(case / n) as b:
                a.set_auto_mask(False); b.set_auto_mask(False)
                if list(a.variables) != list(b.variables) or list(a.dimensions) != list(b.dimensions):
                    raise ValueError('NetCDF roster changed')
                for d in a.dimensions:
                    if len(a.dimensions[d]) != len(b.dimensions[d]) or a.dimensions[d].isunlimited() != b.dimensions[d].isunlimited():
                        raise ValueError('NetCDF dimensions changed')
                if a.ncattrs() != b.ncattrs() or any(a.getncattr(k) != b.getncattr(k) for k in a.ncattrs()):
                    raise ValueError('global attrs changed')
                for k in a.variables:
                    av,bv=a[k],b[k]
                    if av.dtype != bv.dtype or av.dimensions != bv.dimensions or av.ncattrs() != bv.ncattrs():
                        raise ValueError('variable definition changed: '+k)
                    if any(not np.array_equal(av.getncattr(t),bv.getncattr(t)) for t in av.ncattrs()):
                        raise ValueError('variable attribute changed: '+k)
                    if av[:].tobytes() != bv[:].tobytes():
                        raise ValueError('variable bytes changed: '+k)
                rec={'case': name,'file': n,'variables': len(a.variables), 'variable_bytes_equal': True,
                     'definitions_and_attributes_equal': True,'off': pin(off/n),'on': pin(case/n),
                     'whole_file_bytes_equal': (off/n).read_bytes() == (case/n).read_bytes()}
                if not rec['whole_file_bytes_equal']:
                    raise ValueError('full file changed')
                report['case_comparisons'].append(rec)
    before=json.loads((args.runtime/'identity-before.json').read_text())
    snapshot=Path(before['observer_restoration'][0]['observed']['path']).parents[1]
    corpus=json.loads((root/'validation/rrtmgp37/connected-host-number/source/tracked-WRF-corpus.json').read_text())
    rows=[];missing=[];mismatch=[]
    for entry in corpus['files']:
        path=snapshot/Path(entry['path']).relative_to('WRF')
        if not path.is_file():
            missing.append(entry['path']);continue
        observed=path.read_bytes()
        restored,count=re.subn(rb'! HOST_CONNECTED_OBSERVER_BEGIN\n.*?! HOST_CONNECTED_OBSERVER_END\n',b'',observed,flags=re.S)
        row={'path':entry['path'],'observed_sha256':sha(observed),'production_sha256':sha(restored),'observer_blocks_removed':count}
        rows.append(row)
        if row['production_sha256']!=entry['sha256']:mismatch.append(entry['path'])
    audit={'scope':'Post-run actual retained source snapshot readback against all tracked current WRF production bytes; build receipt and executable hash reused, no new build',
           'files':rows,'missing':missing,'mismatch':mismatch,'source_files':len(rows),'production_accepted':False}
    if missing or mismatch:raise ValueError('source snapshot differs from current production corpus')
    (dest/'source-audit.json.gz').write_bytes(gzip.compress((json.dumps(audit,indent=2)+'\n').encode(),mtime=0))
    report['library_hashes_observed_after_runs']=True
    report['complete_loaded_library_bytes_captured_during_each_process']=False
    report['python_readback_versions']={'numpy':np.__version__,'netCDF4':netCDF4.__version__}
    report['cloud_LUT_bounds']={}
    for name in ('rrtmgp-clouds-lw-bnd.nc','rrtmgp-clouds-sw-bnd.nc'):
        with netCDF4.Dataset(off/name) as lut:
            report['cloud_LUT_bounds'][name]={'pin':pin(off/name), 'values':{k:float(lut[k][:]) for k in ('radliq_lwr','radliq_upr','diamice_lwr','diamice_upr')}}
    (dest/'readback.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'netcdf_pairs': len(report['case_comparisons']), 'packet_matches': {k:v['original_PR167_packet_bytes_equal'] for k,v in report['packets'].items()}},indent=2))

if __name__ == '__main__':
    main()
