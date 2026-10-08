"""Saved excerpt/trace replay. Does not run solver or reopen full OD/TAPE3."""
from pathlib import Path
import gzip,hashlib,importlib.util,json,re,struct
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('layer_core',BASE/'verify_core.py')
core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
def load():
    trace=gzip.decompress((BASE/'layer-use.trace.gz').read_bytes()).decode()
    parent=BASE.parent/'lbl-minimal-r3-transition'
    old=gzip.decompress((parent/'trace.txt.gz').read_bytes()).decode()
    meta=json.loads((BASE/'TAPE3-readback.json').read_text())
    blocks={str(n):gzip.decompress((BASE/'excerpts'/f'{n}.bin.gz').read_bytes()) for n in meta['data_records']}
    return trace,old,blocks
def validate_receipts(comp,receipts):
    core.require(comp['production_accepted'] is False and comp['physical_reference_accepted'] is False,'physical promotion')
    core.require(comp['raw_OD_reopened_by_root'] is True and comp['raw_OD_reopened_by_saved_CI'] is False,'readback scope')
    core.require(comp['scientific_records']==53279 and comp['all_scientific_records_equal'] is True,'science passivity')
    core.require(comp['whole_file_status']=='FAIL_PRESERVED_TIMESTAMP_DIFFERENCES','whole-byte FAIL preserved')
    core.require(len(comp['files'])==45 and sum(r['records']-1 for r in comp['files'])==53279,'per-file totals')
    for r in comp['files']:
        core.require(r['scientific_records_equal'] is True,'per-file science flag')
        for offsets in r['header_difference_offsets0'].values():core.require(all(1336<=i<1352 for i in offsets),'non-timestamp header change')
    for r in receipts:core.require(r['returncode']==0 and r['process_exit']=='REAPED','actual final process result')
    core.require([r.get('observer_environment') for r in receipts[1:]]==['0','1'],'OFF/ON execution environment')
def main():
    manifest=json.loads((BASE/'manifest.json').read_text())
    actual={str(p.relative_to(BASE)) for p in BASE.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
    core.require(manifest['production_accepted'] is False and {x['path'] for x in manifest['files']}==actual and len(manifest['files'])==len(actual),'sealed package roster')
    for r in manifest['files']:
        v=(BASE/r['path']).read_bytes();core.require(len(v)==r['bytes'] and hashlib.sha256(v).hexdigest()==r['sha256'],'sealed bytes')
    parent=BASE.parent/'lbl-final-od-composition'
    new=gzip.decompress((BASE/'source/oprop.observer.f90.gz').read_bytes())
    old=gzip.decompress((parent/'source/oprop.observer.f90.gz').read_bytes())
    core.require(re.sub(rb'! UDM37_USE_BEGIN\n.*?! UDM37_USE_END\n',b'',new,flags=re.S)==old,'observer removal restores parent bytes')
    prep=json.loads((BASE/'preparation.json').read_text())
    core.require(hashlib.sha256(new).hexdigest()==prep['new_source_sha256'] and hashlib.sha256(old).hexdigest()==prep['parent_sha256'],'source pins')
    trace,old_trace,blocks=load()
    meta=json.loads((BASE/'TAPE3-readback.json').read_text())
    core.require(meta['root_actual_readback'] and meta['physical_reference_accepted'] is False and len(meta['data_records'])==58,'actual excerpt scope')
    header=gzip.decompress((BASE/'excerpts/1.bin.gz').read_bytes());core.require(len(header)==1664 and header[55:56]!=b'^','header layout')
    for r in meta['payloads']:
        v=gzip.decompress((BASE/'excerpts'/f"{r['record']}.bin.gz").read_bytes());core.require(len(v)==r['bytes'] and hashlib.sha256(v).hexdigest()==r['sha256'],'payload pins')
    for r in core.parse(trace):
        if r['tag']=='ENTRY':
            h=gzip.decompress((BASE/'excerpts'/f"{r['record']-1}.bin.gz").read_bytes());lo,hi,nrec,nwds=struct.unpack('<ddii',h)
            core.require(1<=r['slot']<=nrec<=250 and nwds==9750 and lo<=r['v'][0]<=hi,'actual block extent')
    result=core.analyze(trace,old_trace,blocks);core.require(result==json.loads((BASE/'result.json').read_text()),'declared scoped result')
    core.require(core.inventory_csv(trace)==gzip.decompress((BASE/'line-use.csv.gz').read_bytes()),'reviewable inventory generated from actual trace')
    comp=json.loads((BASE/'scientific-record-comparison.json').read_text())
    receipts=[json.loads((BASE/'runtime'/n).read_text()) for n in ('build-v3-result.json','solver-v3-off-result.json','solver-v3-on-result.json')]
    validate_receipts(comp,receipts)
    objects=json.loads((BASE/'build-object-check-v3.json').read_text())
    core.require(objects['changed_objects']==['oprop.o'] and objects['all_other_objects_identical'] is True and objects['other_objects']==20,'only observer object changed')
    identity=json.loads((BASE/'execution-identity-v3.json').read_text())
    core.require(identity['source_sha256']==prep['new_source_sha256'] and identity['production_accepted'] is False,'executed source identity')
    inputs=[json.loads((BASE/'runtime'/f'inputs-v3-{arm}.json').read_text()) for arm in ('off','on')]
    core.require(inputs[0]==inputs[1] and inputs[0]['inputs_count']==38 and inputs[0]['TAPE5_modified'] is False,'same held OFF/ON inputs')
    tape=next(r for r in inputs[0]['files'] if r['path']=='TAPE3')
    core.require(tape['sha256']==meta['raw_sha256'] and tape['bytes']==122157832,'executed and root-read TAPE3 identity')
    for r in comp['parent_traces']:
        core.require(r['byte_identical'] and r['sha256']==r['parent_sha256'],'root parent trace comparison')
        if r['path']=='UDM37_MIN_R3':core.require(hashlib.sha256(old_trace.encode()).hexdigest()==r['sha256'],'parent MIN trace pin')
    spec=importlib.util.spec_from_file_location('final_core',parent/'verify_core.py');final=importlib.util.module_from_spec(spec);spec.loader.exec_module(final)
    result_od=final.analyze(gzip.decompress((BASE/'final-od.trace.gz').read_bytes()).decode(),
        gzip.decompress((BASE/'excerpts/panel14_header.bin.gz').read_bytes()),gzip.decompress((BASE/'excerpts/panel14_OD.bin.gz').read_bytes()))
    core.require(result_od==json.loads((parent/'result.json').read_text()),'new actual OD excerpt and final trace match parent scientific result')
    print(json.dumps({'status':result['status'],'LNC_entries':result['LNC_entries'],'R3_target_write_count':result['R3_target_write_count'],'R3_contributors':result['R3_target_contributing_lines'],'science_records':53279,'selected_OD':result_od['selected']['OD'],'physical_reference_accepted':False}))
if __name__=='__main__':main()
