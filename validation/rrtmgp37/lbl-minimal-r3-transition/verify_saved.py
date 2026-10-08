#!/usr/bin/env python3
"""Replay included target observations. No compiler, solver or raw OD read."""
from pathlib import Path
import collections,gzip,hashlib,json,math,re,struct
BASE=Path(__file__).resolve().parent
TARGET=618.6144711111115
TAGS={'INIT','INIT_STATE','CN_PRE','CN_POST','CN_WRITE','RSYM_GATE','XSECT_GATE','XINT_CALL','XINT_WRITE','PANEL_PRE','SHIFT_PRE','GRID_SHIFT','SHIFT_POST','CARRY','CLEAR'}

def require(ok,message):
    if not ok:raise ValueError(message)

def bits(x):return struct.pack('<d',x)

def analyze(text):
    rows=[]
    for line in text.splitlines():
        a=line.split();require(len(a)>=14 and a[0] in TAGS,'record grammar')
        i=list(map(int,a[1:12]));v=list(map(float,a[12:]));require(len(v)==i[-1]+2,'record width')
        require(all(math.isfinite(x) for x in v),'nonfinite trace')
        rows.append({'tag':a[0],'sequence':i[0],'layer':i[1],'panel':i[2],'target_index':i[3],'MAX3':i[4],'destination':i[5],'source_index':i[6],'line_slot':i[7],'phase':i[8],'flags':i[9],'VFT':v[0],'DVR3':v[1],'values':v[2:]})
    require(rows and [r['sequence'] for r in rows]==list(range(1,len(rows)+1)),'sequence coverage')
    require(all(r['layer']==21 and r['MAX3']==283 for r in rows),'owner and extent')
    require(rows[0]['tag']=='INIT' and rows[0]['values']==[0.,1.,1.,0.],'native initial gates')
    require(all(r['flags']==0 for r in rows if r['tag']=='RSYM_GATE'),'unsupported RSYM')
    chosen=[r for r in rows if r['target_index']>0]
    require(all(1<=r['target_index']<=r['MAX3'] and abs(r['VFT']+(r['target_index']-1)*r['DVR3']-TARGET)<1e-7 for r in chosen),'physical frequency or extent')
    mutations=[r for r in chosen if r['tag'] in ('CN_WRITE','XINT_WRITE','CARRY','CLEAR')]
    require(mutations and mutations[0]['tag']=='CLEAR','missing defined initialization')
    last=None;origin=None;first=None;prefix_count=0;replays=0;unknown_prefix=False
    for r in mutations:
        v=r['values'];before,after=v[:2]
        require(r['destination']==r['target_index'],'destination identity')
        if r['tag']=='CLEAR':
            require(before==after==0. and r['source_index']==0,'clear must define zero')
            require(r['target_index']>r['MAX3']-151+1,'tail clear extent')
            last=after;origin=r
        else:
            require(last is not None and bits(before)==bits(last),'mutation before/after chain')
            if r['tag']=='CN_WRITE':
                require(r['phase'] in (1,2),'CN phase')
                term=v[2]*v[3]
                if r['phase']==2:term=term*v[4]
                require(bits(before+term)==bits(after),'CN source-order arithmetic')
                replays+=1
            elif r['tag']=='CARRY':
                require(before==after and r['source_index']-r['destination']==150,'physical carry')
            else:
                require(bits(before+v[2]*v[3])==bits(after),'XINT computed contribution')
                if first is None:unknown_prefix=True
            last=after
        if first is None:
            prefix_count+=1
            if before>=0>after:first=r
    require(first is not None,'first negative missing')
    state=None
    for r in chosen:
        if r['tag']=='CLEAR':state=r['values'][1]
        elif r['tag'] in ('CN_WRITE','XINT_WRITE','CARRY'):
            require(state is not None and bits(state)==bits(r['values'][0]),'mutation state continuity')
            state=r['values'][1]
        elif r['tag'] in ('CN_PRE','CN_POST','PANEL_PRE','SHIFT_PRE','SHIFT_POST','INIT_STATE'):
            require(state is not None and bits(state)==bits(r['values'][0]),'unobserved target mutation')
    matches=[r for r in chosen if r['tag']=='PANEL_PRE' and r['target_index']==20 and r['values'][0]==-1.686827144352549e-5]
    require(matches,'historical coordinate/value not joined')
    return {'rows':len(rows),'tag_counts':dict(collections.Counter(r['tag'] for r in rows)),'selected_rows':len(chosen),'selected_mutations':len(mutations),'all_CN_selected_mutations_bitwise_replayed':replays,'initialized_target':origin,'first_negative':first,'prefix_mutations_to_first_negative':prefix_count,'unsupported_XINT_source_write_before_first_negative':unknown_prefix,'historical_R3_20_state_matches':matches[:1],'target_index_path':sorted(set(r['target_index'] for r in chosen)),'selected_accumulator_prefix_closed':not unknown_prefix}

def verify_comparison(comparison):
    require(comparison['whole_file_bitwise_status']=='FAIL_PRESERVED_TIMESTAMP_DIFFERENCES','comparison whole-file scope')
    files=comparison['files']
    require(len(files)==45 and {r['path'] for r in files}=={f'ODdeflt_{i:03d}' for i in range(1,46)},'OD receipt roster')
    require(comparison['all_45_files_scientific_records_equal'] is True and comparison['physical_reference_accepted'] is False,'OD receipt scope')
    require(all(r['all_scientific_records_equal'] is True and r['whole_file_equal'] is False and r['records']>1 for r in files),'individual OD receipt scope')
    require(sum(r['records']-1 for r in files)==comparison['scientific_records_total']==53279,'OD scientific record total')
    require(comparison['header_exception']['byte_offset0']==1336 and comparison['header_exception']['length']==16,'FILHDR exception scope')
    require(all({h['arm'] for h in r['header_differences']}=={'OFF','PRIOR'} and all(h['byte_offsets0'] and all(1336<=x<1352 for x in h['byte_offsets0']) for h in r['header_differences']) for r in files),'timestamp differences scope')

def main():
    manifest=json.loads((BASE/'manifest.json').read_text())
    actual={str(p.relative_to(BASE)) for p in BASE.rglob('*') if p.is_file() and p != BASE/'manifest.json' and '__pycache__' not in p.parts}
    expected={r['path'] for r in manifest['files']}
    require(actual==expected and len(expected)==len(manifest['files']),'package roster')
    require(manifest['production_accepted'] is False,'physical acceptance promotion')
    for r in manifest['files']:
        p=BASE/r['path'];require(p.is_file() and p.stat().st_size==r['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'],'package bytes '+r['path'])
    stock=gzip.decompress((BASE/'source/oprop.stock.f90.gz').read_bytes()).decode()
    observer=gzip.decompress((BASE/'source/oprop.observer.f90.gz').read_bytes()).decode()
    restored=re.sub(r'! UDM37_MIN_BEGIN\n.*?! UDM37_MIN_END\n','',observer,flags=re.S).replace('CALL UDM37_MIN_XINT ','CALL XINT ')
    require(restored==stock+'\n','original source restoration')
    raw=gzip.decompress((BASE/'trace.txt.gz').read_bytes());computed=analyze(raw.decode())
    result=json.loads((BASE/'result.json').read_text())
    require(result['trace']['sha256']==hashlib.sha256(raw).hexdigest() and result['trace']['bytes']==len(raw),'trace identity')
    for k,v in computed.items():
        if k!='rows':require(result[k]==v,'result field '+k)
    require(result['trace']['rows']==computed['rows'],'result count')
    require(result['production_accepted'] is False and result['full_LBLRTM_reference_accepted'] is False and result['all_operand_generation_ancestry_complete'] is False and result['negative_OD_status']=='FAIL_PRESERVED','reference scope promotion')
    comparison=json.loads((BASE/'scientific-record-comparison.json').read_text())
    verify_comparison(comparison)
    print(json.dumps({'status':'PASS_SCOPED_SAVED_TARGET_PREFIX','CN_replays':computed['all_CN_selected_mutations_bitwise_replayed'],'target_indices':computed['target_index_path'],'selected_prefix_closed':computed['selected_accumulator_prefix_closed'],'complete_operand_ancestry':False,'full_OD_files_reopened':False,'physical_reference_accepted':False,'production_accepted':False}))

if __name__=='__main__':main()
