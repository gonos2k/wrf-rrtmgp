#!/usr/bin/env python3
"""Verify sealed full-host records with stdlib only; no native/model execution."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent


def require(value,message):
    if not value:
        raise ValueError(message)


def verify():
    m=json.loads((ROOT/'manifest.json').read_text())
    roster={r['path'] for r in m['payloads']}
    actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p!=ROOT/'manifest.json'}
    require(actual==roster and len(roster)==len(m['payloads']),'payload roster mismatch')
    for r in m['payloads']:
        p=ROOT/r['path']
        require(not p.is_symlink() and p.resolve().is_relative_to(ROOT),'unsafe payload')
        data=p.read_bytes()
        require(len(data)==r['size_bytes'] and hashlib.sha256(data).hexdigest()==r['sha256'],'payload mismatch '+r['path'])
    require(m['production_accepted'] is False and m['physical_remaining']==7,'physical approval changed')
    spec=importlib.util.spec_from_file_location('saved_connected',ROOT/'scripts/verify_records.py')
    checker=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    r=json.loads((ROOT/'runtime/receipt.json').read_text())
    require(r['status']=='PASS' and r['production_accepted'] is False and r['physical_units_approved'] is False,'runtime status/scope mismatch')
    require(len(r['commands'])==7 and all(p['status']=='TERMINAL' and p['actual_returncode']==0 for p in r['commands']),'actual final model processes mismatch')
    b=json.loads((ROOT/'build/build-receipt.json').read_text())
    require(b['status']=='PASS_SCOPED_CONNECTED_HOST_BUILD_AND_RUNTIME' and len(b['commands'])==5,'fresh build scope mismatch')
    require(all(p['status']=='TERMINAL' and p['actual_returncode']==0 for p in b['commands']),'fresh build actual RC mismatch')
    require(b['executables']==r['executables'],'runtime binaries differ from fresh build')
    mapping=json.loads((ROOT/'runtime/file-mapping.json').read_text())
    by_original={v['original_path']:v for v in mapping}
    require(len(by_original)==len(mapping),'duplicate mapped payload')
    for row in mapping:
        data=gzip.decompress((ROOT/row['archive_path']).read_bytes())
        require(len(data)==row['size_bytes'] and hashlib.sha256(data).hexdigest()==row['uncompressed_sha256'],'uncompressed runtime payload mismatch')
    for arm in r['arms'].values():
        for key in ('input','history','log'):
            if key in arm:
                data=arm[key];mapped=by_original[data['path']]
                require(mapped['uncompressed_sha256']==data['sha256'] and mapped['size_bytes']==data['size_bytes'],'receipt payload linkage mismatch')
    source=json.loads((ROOT/'source/observer-source-pins.json').read_text())
    require(len(source)==5,'observer source roster mismatch')
    for rel,pins in source.items():
        original=gzip.decompress((ROOT/'source/production'/(rel+'.gz')).read_bytes())
        observed=gzip.decompress((ROOT/'source/observed'/(rel+'.gz')).read_bytes())
        stripped=re.sub(rb'! HOST_CONNECTED_OBSERVER_BEGIN\n.*?! HOST_CONNECTED_OBSERVER_END\n',b'',observed,flags=re.S)
        require(stripped==original and pins['byte_exact_reverse'] is True,'observer reversal mismatch')
        require(hashlib.sha256(original).hexdigest()==pins['production_sha256'] and
                hashlib.sha256(observed).hexdigest()==pins['snapshot_sha256'],'observer source binding mismatch')
    rows=0
    for name,command,restart in (('nonuniform-on',3,False),('empty-qnn-on',4,False),('warm-cloud-on',6,False),('restart-on',7,True)):
        raw=gzip.decompress((ROOT/f'runtime/command-{command:02}.stdout.gz').read_bytes()).decode()
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'records.txt';path.write_text(raw)
            records=checker.parse(path)
        derived=checker.verify_join(records,restart=restart)
        stored=r['arms'][name]['joined_checks']
        require(all(stored[k]==v for k,v in derived.items()),'rederived join checks differ '+name)
        require(stored['exact_stage_step_slot_layer_roster'] and stored['input_return_transport_consumer_join_bitwise'],'host joins absent')
        positive=sum(k[0]=='HELPER_IN' and v[1][1]>0 and v[1][3]>0 for k,v in records.items())
        if not restart:
            require(positive==stored['positive_QNC_QC_helper_rows'],'positive helper roster differs')
        if name=='warm-cloud-on':
            require(positive>0,'no actual positive mass/number helper input')
            rejected=[]
            for label,stage in (('missing-consumer','UDM_ENTRY'),('wrong-consumer-number','UDM_ENTRY'),
                                ('missing-RK-stage','RK_POST'),('wrong-old-buffer','RK_PRE'),('missing-helper-output','HELPER_OUT')):
                altered=dict(records)
                key=next(k for k in altered if k[0]==stage and (label!='wrong-old-buffer' or k[2]==2))
                if label.startswith('missing'):
                    altered.pop(key)
                else:
                    bits,values=altered[key];values=list(values);bits=list(bits)
                    field=1 if label=='wrong-old-buffer' else 0
                    values[field]=checker.f32(values[field]+100000.)
                    bits[field]=struct.unpack('!I',struct.pack('!f',values[field]))[0]
                    altered[key]=(tuple(bits),tuple(values))
                try:
                    checker.verify_join(altered)
                except ValueError:
                    rejected.append(label)
                else:
                    raise ValueError('negative record passed '+label)
            require(len(rejected)==5,'negative control roster mismatch')
        rows+=derived['RK_update_pairs']
    require(all(p['history_arrays_bitwise']==211 and p['history_file_bytes_equal'] for p in r['observer_passivity'].values()),'observer history passivity mismatch')
    return {'status':'PASS_SCOPED_SAVED_CONNECTED_HOST','payloads':len(roster),
            'rederived_actual_RK_update_pairs':rows,'negative_controls_rejected':5,
            'new_compiler_model_or_NetCDF_reader_runs':0,'physical_acceptance':False}


if __name__=='__main__':
    try:
        print(json.dumps(verify()))
    except (ValueError,KeyError,OSError,StopIteration) as error:
        print(json.dumps({'status':'FAIL_SAVED_CONNECTED_HOST','error':str(error)}))
        sys.exit(1)
