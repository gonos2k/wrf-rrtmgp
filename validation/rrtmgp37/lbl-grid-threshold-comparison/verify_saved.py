"""Saved executed comparison replay; no fresh LBLRTM build or full raw reopening."""
from pathlib import Path
import gzip,hashlib,importlib.util,json,math,struct
BASE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('grid_core',BASE/'verify_core.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
def loadj(n):return json.loads((BASE/n).read_text())
def raw(n):return gzip.decompress((BASE/n).read_bytes())
def validate_passivity(x):
    c.require(x['production_accepted'] is False and x['root_read_all_45_OD_files'] and x['saved_CI_reopens_full_OD'] is False,'readback scope')
    c.require(x['science_identical'] and x['whole_file_status']=='FAIL_PRESERVED_TIMESTAMP_DIFFERENCES','science passivity and whole-byte FAIL')
    c.require(len(x['files'])==45 and sum(r['records']-1 for r in x['files'])==x['science_records']==57007,'all45 totals')
    for r in x['files']:
        c.require(r['science_identical'] and len(r['science_sha256'])==64,'actual science comparison')
        c.require(all(1336<=j<1352 for v in r['header_difference_offsets0'].values() for j in v),'non-timestamp header difference')
def replay():
    meta=loadj('TAPE3-readback.json');c.require(meta['actual_root_readback'] and meta['full_file_roster_repeated'] is False,'excerpt scope')
    blocks={str(n):raw(f'TAPE3/{n}.bin.gz') for n in meta['data_records']}
    for p in meta['payloads']:
        b=raw(f"TAPE3/{p['record']}.bin.gz");c.require(len(b)==p['bytes'] and hashlib.sha256(b).hexdigest()==p['sha256'],'actual TAPE3 excerpt pin')
    arms={};samples={};coordinates={};samplemeta=loadj('samples.json')
    for a in c.ARMS:
        trace=raw(f'traces/{a}.layer.gz').decode();minimum=raw(f'traces/{a}.min.gz').decode()
        for r in c.parse(trace):
            if r['tag']=='ENTRY':
                lo,hi,n,words=struct.unpack('<ddii',raw(f"TAPE3/{r['record']-1}.bin.gz"))
                c.require(words==9750 and 1<=r['slot']<=n<=250 and lo<=r['v'][0]<=hi,'actual block extent')
        arms[a]=c.analyze_arm(trace,minimum,blocks,a)
        c.require(len(samplemeta[a])==81,'physical sample roster')
        samples[a]=[];coordinates[a]=[]
        for j,r in enumerate(samplemeta[a]):
            c.same(r['nu'],c.TARGET+(j-40)*c.H,'shared physical coordinate')
            header=raw(f"OD/{a}.{r['panel']}.header.gz")
            lo,hi,dv,n,pad=struct.unpack('<dddii',header)
            c.same(dv,arms[a]['actual_DV'],'actual OD and line-use DV join')
            coordinates[a].append(lo+round((r['nu']-lo)/dv)*dv)
            samples[a].append(c.sample_od(header,raw(f"OD/{a}.{r['panel']}.payload.gz"),r['nu']))
    diag={'computed_from_actual_saved_panel_headers':True,'arms':{a:{'target_actual_coordinate':v[40],
      'max_abs_planned_coordinate_residual':max(abs(t-r['nu']) for t,r in zip(v,samplemeta[a]))} for a,v in coordinates.items()},
      'target_coordinate_bit_identical_across_arms':len({struct.pack('<d',v[40]) for v in coordinates.values()})==1,
      'maximum_cross_arm_coordinate_mismatch':max(abs(v[j]-coordinates['h'][j]) for v in coordinates.values() for j in range(81))}
    c.require(diag==loadj('coordinate-diagnostic.json') and diag['target_coordinate_bit_identical_across_arms'],'actual coordinate diagnostic')
    computed=c.result(arms,samples)
    c.require(computed==loadj('result.json'),'computed result and physical promotion')
    c.require({a:v['contributors'] for a,v in arms.items()}==loadj('contributions.json'),'per actual origin contribution inventory')
    return computed

def main():
    manifest=loadj('manifest.json');actual={str(p.relative_to(BASE)) for p in BASE.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
    c.require(manifest['production_accepted'] is False and {r['path'] for r in manifest['files']}==actual,'sealed exact roster')
    for r in manifest['files']:
        b=(BASE/r['path']).read_bytes();c.require(len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'],'sealed bytes')
    prep=loadj('preparation.json');b=raw('source/oprop.observer.f90.gz')
    c.require(hashlib.sha256(b).hexdigest()==prep['source_sha256'],'executed source hash')
    for r in reversed(prep['observer_only_changes']):
        c.require(b.count(r['after'].encode())==1,'exact observer adaptation inverse');b=b.replace(r['after'].encode(),r['before'].encode(),1)
    parent=gzip.decompress((BASE.parent/'lbl-layer-line-use/source/oprop.observer.f90.gz').read_bytes())
    c.require(b==parent and hashlib.sha256(b).hexdigest()==prep['parent_sha256'],'inverse restores PR164 bytes')
    identity=loadj('execution-identity.json');c.require(identity['source_sha256']==prep['source_sha256'] and identity['production_accepted'] is False,'execution identity')
    obj=loadj('object-comparison.json');c.require(obj=={'changed_objects':['oprop.o'],'other_objects':20,'all_other_objects_identical':True},'only observer object changed')
    old=raw('inputs/original.TAPE5.gz');plan=loadj('plan.json');c.require(plan['production_accepted'] is False and len(plan['arms'])==6,'six final arms')
    controls={r['name']:r for r in plan['arms']};controls['probe']={'SAMPLE':4.,'DPTMIN_input':-1.,'observer':False,'IOD':2}
    held=None;exe=None
    for a,r in controls.items():
        tape=raw(f'inputs/{a}.TAPE5.gz');before=old.decode().splitlines(keepends=True);after=tape.decode().splitlines(keepends=True)
        c.require(len(before)==len(after),'same45 layer state')
        for i,(x,y) in enumerate(zip(before,after)):
            mask=list(y)
            for line,l,u in ((1,64,65),(2,20,30),(2,60,70)):
                if i==line:mask[l:u]=x[l:u]
            c.require(''.join(mask)==x,'only three official control spans changed')
        c.require(after[1][64]=='2' and float(after[2][20:30])==r['SAMPLE'] and float(after[2][60:70])==r['DPTMIN_input'],'actual IOD/SAMPLE/DPTMIN inputs')
        inp=loadj(f'runtime/case-{a}-inputs.json');c.require(len(inp['files'])==38,'held38 input files')
        c.require(inp['original_TAPE5_sha256']==hashlib.sha256(old).hexdigest(),'original45 layer input pin')
        c.require(next(v['sha256'] for v in inp['files'] if v['path']=='TAPE5')==hashlib.sha256(tape).hexdigest(),'actual executed TAPE5')
        others=[v for v in inp['files'] if v['path']!='TAPE5']
        c.require(held is None or others==held,'same other37 inputs');held=others
        c.require(next(v['sha256'] for v in others if v['path']=='TAPE3')==loadj('TAPE3-readback.json')['raw_file_sha256'],'executed original TAPE3')
        receipt=loadj(f'runtime/solver-{a}-result.json')
        c.require(receipt['returncode']==0 and receipt['process_exit']=='REAPED' and receipt['observer_environment']==str(int(r['observer'])),'actual exited process and OFF/ON')
        if a!='probe':
            c.require(exe is None or exe==receipt['command'],'same final executable');exe=receipt['command']
    build=loadj('build-result.json');c.require(build['returncode']==0 and build['process_exit']=='REAPED','build completed')
    c.require(raw('inputs/h-off.TAPE5.gz')==raw('inputs/h.TAPE5.gz')==raw('inputs/probe.TAPE5.gz'),'passivity same actual input')
    validate_passivity(loadj('passivity.json'))
    result=replay()
    print(json.dumps({'status':result['status'],'target_cm1':result['target_cm1'],'OD':{a:r['target_OD'] for a,r in result['arms'].items()},'science_records':57007,'physical_reference_accepted':False}))
if __name__=='__main__':main()
