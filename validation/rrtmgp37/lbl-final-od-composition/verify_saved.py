#!/usr/bin/env python3
"""Check included raw OD excerpt and actual trace; no solver rerun or physical approval."""
from pathlib import Path
import gzip,hashlib,json,re,subprocess,sys,importlib.util
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('final_core',BASE/'verify_core.py');core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
require=core.require

def main():
    manifest=json.loads((BASE/'manifest.json').read_text())
    roster={str(p.relative_to(BASE)) for p in BASE.rglob('*') if p.is_file() and p!=BASE/'manifest.json' and '__pycache__' not in p.parts}
    require(len(manifest['files'])==len(roster) and {x['path'] for x in manifest['files']}==roster,'manifest exact roster')
    require(manifest['production_accepted'] is False,'manifest acceptance')
    for r in manifest['files']:
        p=BASE/r['path'];require(p.stat().st_size==r['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'],'package bytes '+r['path'])
    parent=BASE.parent/'lbl-coupling-generation'
    subprocess.run([sys.executable,'-I','-S',str(parent/'verify_saved.py')],check=True)
    source=gzip.decompress((BASE/'source/oprop.observer.f90.gz').read_bytes()).decode()
    original=gzip.decompress((parent/'source/oprop.observer.f90.gz').read_bytes()).decode()
    require(re.sub(r'! UDM37_FINAL_BEGIN\n.*?! UDM37_FINAL_END\n','',source,flags=re.S)==original,'exact parent source restoration')
    readback=json.loads((BASE/'OD-readback.json').read_text());require(readback['record_count']==390 and readback['selected_panel_ordinal']==14,'OD origin metadata')
    require(readback['all_markers_checked'] is True and readback['physical_reference_accepted'] is False,'OD readback scope')
    require([r['physical_record_1based'] for r in readback['excerpts']]==[1,28,29],'excerpt physical record roster')
    values={}
    for r in readback['excerpts']:
        raw=gzip.decompress((BASE/r['path']).read_bytes());require(len(raw)==r['bytes'] and hashlib.sha256(raw).hexdigest()==r['sha256'],'OD excerpt bytes');values[r['path']]=raw
    require(set(values)=={'excerpts/file_header.bin.gz','excerpts/panel14_header.bin.gz','excerpts/panel14_OD.bin.gz'},'excerpt path roster')
    result=core.analyze(gzip.decompress((BASE/'trace.txt.gz').read_bytes()).decode(),values['excerpts/panel14_header.bin.gz'],values['excerpts/panel14_OD.bin.gz'])
    require(result==json.loads((BASE/'result.json').read_text()),'result replay')
    comparison=json.loads((BASE/'scientific-record-comparison.json').read_text());files=comparison['files']
    require(len(files)==45 and {r['path'] for r in files}=={f'ODdeflt_{i:03d}' for i in range(1,46)},'comparison exact file roster')
    require(sum(r['records']-1 for r in files)==comparison['scientific_records']==53279,'science count')
    require(comparison['all_scientific_records_equal'] is True and all(r['scientific_records_equal'] is True and r['whole_file_equal'] is False for r in files),'comparison scope')
    require(comparison['whole_file_status']=='FAIL_PRESERVED_TIMESTAMP_DIFFERENCES' and comparison['raw_OD_reopened_by_saved_CI'] is False and comparison['physical_reference_accepted'] is False,'full OD scope')
    require(all(set(r['header_difference_offsets0'])=={'OFF','PR161'} and all(xs and all(1336<=x<1352 for x in xs) for xs in r['header_difference_offsets0'].values()) for r in files),'header exceptions')
    require(len(comparison['parent_traces'])==2 and {r['path'] for r in comparison['parent_traces']}=={'UDM37_MIN_R3','UDM37_LINE_COEFF'},'parent trace roster')
    for r in comparison['parent_traces']:
        p=(BASE.parent/'lbl-minimal-r3-transition/trace.txt.gz') if r['path']=='UDM37_MIN_R3' else parent/'coeff-trace.txt.gz'
        raw=gzip.decompress(p.read_bytes());require(r['byte_identical'] is True and r['bytes']==len(raw) and r['sha256']==r['parent_sha256']==hashlib.sha256(raw).hexdigest(),'parent trace bytes')
    print(json.dumps({'status':result['status'],'exact_checks':result['exact_arithmetic_and_value_checks'],'selected_OD':result['selected']['OD'],'raw_selected_OD_excerpt_replayed':True,'full_45_OD_files_reopened':False,'solver_rerun':False,'physical_reference_accepted':False,'production_accepted':False}))
if __name__=='__main__':main()
