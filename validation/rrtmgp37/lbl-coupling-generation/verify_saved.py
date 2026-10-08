#!/usr/bin/env python3
"""Validate included excerpts and selected coefficient generation, not physics."""
from pathlib import Path
import gzip,hashlib,json,re,subprocess,sys,importlib.util
BASE=Path(__file__).resolve().parent
PARENT=BASE.parent/'lbl-minimal-r3-transition'
spec=importlib.util.spec_from_file_location('coeff_core',BASE/'verify_core.py');core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
require=core.require

def validate_comparison(d):
    files=d['files']
    require(len(files)==45 and {r['path'] for r in files}=={f'ODdeflt_{n:03d}' for n in range(1,46)},'comparison exact files')
    require(d['all_scientific_records_equal'] is True and all(r['scientific_records_equal'] is True and r['whole_file_equal'] is False for r in files),'scientific/whole-file scope')
    require(sum(r['records']-1 for r in files)==d['scientific_records']==53279,'scientific record count')
    require(d['whole_file_status']=='FAIL_PRESERVED_TIMESTAMP_DIFFERENCES' and d['physical_reference_accepted'] is False and d['raw_OD_reopened_by_saved_CI'] is False,'comparison acceptance scope')
    require(all(set(r['header_difference_offsets0'])=={'OFF','PR160'} and all(offsets and all(1336<=n<1352 for n in offsets) for offsets in r['header_difference_offsets0'].values()) for r in files),'date/time exception')
    raw=gzip.decompress((PARENT/'trace.txt.gz').read_bytes());expected=hashlib.sha256(raw).hexdigest();m=d['minimal_trace']
    require(m['byte_identical'] is True and m['bytes']==len(raw) and m['new_sha256']==m['PR160_sha256']==expected,'parent trace identity')

def main():
    manifest=json.loads((BASE/'manifest.json').read_text())
    actual={str(p.relative_to(BASE)) for p in BASE.rglob('*') if p.is_file() and p!=BASE/'manifest.json' and '__pycache__' not in p.parts}
    require(len(manifest['files'])==len(actual) and {r['path'] for r in manifest['files']}==actual,'manifest roster')
    require(manifest['production_accepted'] is False,'manifest acceptance')
    for r in manifest['files']:
        p=BASE/r['path'];require(p.stat().st_size==r['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'],'package bytes '+r['path'])
    subprocess.run([sys.executable,'-I','-S',str(PARENT/'verify_saved.py')],check=True)
    parent_source=gzip.decompress((PARENT/'source/oprop.observer.f90.gz').read_bytes()).decode()
    source=gzip.decompress((BASE/'source/oprop.observer.f90.gz').read_bytes()).decode()
    restored=re.sub(r'! UDM37_COEFF_BEGIN\n.*?! UDM37_COEFF_END\n','',source,flags=re.S).replace(' USE udm37_min_r3\n USE udm37_line_coeff\n',' USE udm37_min_r3\n')
    require(restored==parent_source,'native source restoration')
    readback=json.loads((BASE/'line-readback.json').read_text())
    excerpts={r['kind']:r for r in readback['excerpts']}
    require(len(excerpts)==len(readback['excerpts'])==3 and set(excerpts)=={'file_header','line_block_header','line_data'},'excerpt roster')
    data={}
    for kind,r in excerpts.items():
        data[kind]=gzip.decompress((BASE/r['included_gzip']).read_bytes())
        require(len(data[kind])==r['bytes'] and hashlib.sha256(data[kind]).hexdigest()==r['payload_sha256'],'excerpt identity')
    require([excerpts[k]['number'] for k in ('file_header','line_block_header','line_data')]==[1,520,521] and readback['block_data_record']==521 and readback['block_header_record']==520 and readback['block_ordinal']==260,'physical record naming')
    require(readback['physical_reference_accepted'] is False and readback['upstream_HITRAN_or_AER_database_record_authenticated'] is False,'input authority scope')
    parent=json.loads((PARENT/'result.json').read_text())
    trace=gzip.decompress((BASE/'coeff-trace.txt.gz').read_bytes()).decode()
    result=core.analyze(trace,data['file_header'],data['line_block_header'],data['line_data'],parent['first_negative'])
    require(json.loads((BASE/'result.json').read_text())==result,'saved result replay')
    validate_comparison(json.loads((BASE/'scientific-record-comparison.json').read_text()))
    print(json.dumps({'status':result['status'],'selected_line':result['line_identity'],'exact_binary64_checks':len(result['bitwise_checks']),'libm_checks':len(result['transcendental_checks']),'full_TAPE3_reopened':False,'full_OD_reopened':False,'physical_reference_accepted':False,'production_accepted':False}))

if __name__=='__main__':main()
