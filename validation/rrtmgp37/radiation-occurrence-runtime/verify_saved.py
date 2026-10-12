#!/usr/bin/env python3
"""Replay captured radiation boundaries with stdlib; never run WRF or reread NetCDF."""
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import struct

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[2]
CASES = ('on-i1-j1', 'on-i2-j1', 'on-i1-j2', 'on-i2-j2')
PHASES = ('lw', 'sw')
SPECIES = (('LWP','QC','SOURCE_QC',3), ('IWP','QI','SOURCE_QI',4),
           ('RWP','QR','SOURCE_QR',5), ('SWP','QS','SOURCE_QS',6),
           ('GWP','QG','QG',7), ('HWP','QH','QH',8))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def bits(value):
    return struct.pack('<f', value)


def load_bytes(path):
    data = path.read_bytes()
    return gzip.decompress(data) if path.suffix == '.gz' else data


def trace(data, kind):
    lines = data.decode('ascii').splitlines()
    magic, header = lines[:2]
    if kind == 'raw':
        require(magic == 'RRTMGP_RAW_V1', 'raw magic')
        phase,i,j,nl = header.split()
        header = [phase,int(i),int(j),int(nl)]
    elif kind == 'input':
        require(magic in ('RRTMGP_REPLAY_V12','RRTMGP_REPLAY_V9'), 'input magic')
        h=header.split(); header=[h[0]]+[int(x) for x in h[1:]]
        require(len(header)==6,'input header')
    else:
        require(magic == 'RRTMGP_RESULT_V1', 'result magic')
        h=header.split(); header=[h[0]]+[int(x) for x in h[1:]]
        require(len(header)==3,'result header')
    pos=2; records={}
    while pos < len(lines):
        if not lines[pos].strip():
            pos+=1;continue
        fields=lines[pos].split();pos+=1
        name=fields[0];shape=tuple(int(x) for x in fields[1:])
        require(len(shape) in {'raw':(1,),'input':(2,3),'result':(3,)}[kind] and min(shape)>0,'record shape')
        require(name not in records,'duplicate record')
        count=math.prod(shape);values=[]
        while len(values)<count and pos<len(lines):
            values.extend(float(x.replace('D','E').replace('d','e')) for x in lines[pos].split());pos+=1
        require(len(values)==count and all(math.isfinite(x) for x in values),'record values')
        records[name]={'shape':shape,'values':values}
    return header,records


def read_capture(saved,case,phase):
    return {kind:trace(load_bytes(saved/case/'capture'/f'{phase}.{kind}.gz'),kind)
            for kind in ('raw','input','result')}


def analyze_capture(capture,packet,i,j,phase):
    rh, rr = capture['raw']; ah, ar = capture['input']; oh, orecs = capture['result']
    require(rh == [phase.upper(),i,j,59], 'wrong raw column/layers/phase')
    backend_nl={'lw':103,'sw':60}[phase]
    require(ah[:4]==[phase.upper(),1,backend_nl,2] and ah[5]==4,'wrong adapter dimensions/policy')
    require(oh==[phase.upper(),1,backend_nl], 'wrong optical result dimensions')
    def raw(name):
        require(name in rr,'missing raw '+name)
        return rr[name]['values']
    def scalar(name,value):
        require(raw(name)==[value],'wrong '+name)
    for name,value in (('RADIATION_STEP',7.),('SOURCE_TIME_SECONDS',60.),('UDM_CF_SOURCE_STEP',6.),
                       ('MP_PHYSICS',27.),('HOST_REAL_BITS',32.)):
        scalar(name,value)
    def native(name):
        require(len(raw(name))==59,'wrong native extent '+name)
        return raw(name)
    def adapter(name):
        require(name in ar and ar[name]['shape']==(1,backend_nl),'wrong adapter extent '+name)
        return ar[name]['values']
    def result(name):
        require(name in orecs and orecs[name]['shape'][:2]==(1,backend_nl),'wrong result extent '+name)
        return orecs[name]
    def pvalue(var,k):
        return packet[var*236 + k*4 + (j-1)*2+(i-1)]
    cf=native('CF'); md=native('DRY_LAYER_MASS_KG_M2')
    require(all(0<=x<=1 for x in cf) and all(x>0 for x in md),'invalid CF/dry mass')
    require(cf==native('RAD_CF_SOURCE')==adapter('CF')[:59], 'CF provenance')
    require(all(0<=x<=1 for x in native('UDM_CF_USED')) and raw('UDM_CF_TOP')==[58.], 'UDM CF provenance extent')
    history_cf=[pvalue(9,k) for k in range(59)]
    require(all(0<=x<=1 for x in history_cf),'invalid history CF')
    require(all(bits(native('SOURCE_QNC')[k])==bits(pvalue(1,k)) for k in range(59)),'snapshot QNC mismatch')
    paths={}; closure=0.; cells=[]
    for path,qname,source,var in SPECIES:
        q=native(source)
        require(q==native(qname),'native/source hydrometeor mapping '+qname)
        require(all(bits(q[k])==bits(pvalue(var,k)) for k in range(59)),'snapshot hydrometeor mismatch '+qname)
        require(all(x>=0 for x in q),'unexpected negative source '+qname)
        require(native('NUMERIC_CLIPPED_'+qname)==[0.]*59,'unexpected numeric clipping '+qname)
        grid=native(path+'_GRID');rad=native(path+'_RADIATION');om=native(path+'_OMITTED')
        require(native('NEGATIVE_GRID_CORRECTION_'+path)==[0.]*59,'unexpected negative correction')
        for k in range(59):
            original=q[k]*(md[k]*1000.)
            require(grid[k]==f32(original),'grid path arithmetic '+path)
            if path in ('GWP','HWP'):
                require(q[k]==grid[k]==rad[k]==om[k]==0.,'unsupported positive G/H')
            else:
                expected_rad=f32(original/cf[k]) if cf[k]>0 else 0.
                expected_om=0. if cf[k]>0 else f32(original)
                require(rad[k]==expected_rad and om[k]==expected_om,'occurrence partition '+path)
                require(adapter(path)[k]==rad[k],'backend path mapping '+path)
            residual=grid[k]-cf[k]*rad[k]-om[k]
            closure=max(closure,abs(residual))
            require(abs(residual)<=2**-22*max(abs(grid[k]),1e-35),'rounded path partition '+path)
        paths[path]={'grid_sum_g_m2':math.fsum(grid), 'omitted_sum_g_m2':math.fsum(om),
                     'positive_cells':sum(x>0 for x in q),
                     'cf0_positive_cells':sum(q[k]>0 and cf[k]==0 for k in range(59))}
    for raw_name,adapter_name,source_name in (('REL','REL','SOURCE_RE_CLOUD'),('REI','REI','SOURCE_RE_ICE'),('RES','RES','SOURCE_RE_SNOW')):
        require(adapter(adapter_name)[:59]==native(raw_name), 'adapter radius mapping '+raw_name)
        # Host meter radii are converted using native REAL32 multiplication.
        require(native(raw_name)==[f32(x*f32(1e6)) for x in native(source_name)],'host radius conversion '+raw_name)
    for name,expected in (('RL_USED',[min(21.5,max(2.5,x)) for x in native('REL')]),
                          ('DI_USED',[min(180.,max(10.,2*x)) for x in native('REI')])):
        used=result(name)
        require(used['shape']==(1,backend_nl,1) and used['values'][:59]==expected,'LUT coordinate mapping '+name)
    for k in range(59):
        if native('SOURCE_QI')[k]>0 and cf[k]==0:
            def layer_max(name):
                record=result(name)
                return max(abs(record['values'][k+backend_nl*b]) for b in range(record['shape'][2]))
            optical={n:layer_max(n) for n in ('CLOUD_TAU','PRECIP_TAU','PREPARED_TAU','MASK')}
            require(all(v==0 for v in optical.values()),'CF0 omitted layer has nonzero hydrometeor optics/mask')
            cells.append({'phase':phase.upper(),'i':i,'j':j,'level1':k+1,'source_time_seconds':60,
                          'radiation_step':7,'udm_cf_source_step':6,'cf':cf[k],'history_cf':history_cf[k],'supplied_udm_cf':native('UDM_CF_USED')[k],
                          'qice_kg_kg':native('SOURCE_QI')[k], 'dry_mass_kg_m2':md[k],
                          'grid_path_g_m2':native('IWP_GRID')[k], 'incloud_path_g_m2':native('IWP_RADIATION')[k],
                          'omitted_path_g_m2':native('IWP_OMITTED')[k], 'host_radius_m':native('SOURCE_RE_ICE')[k],
                          'adapter_radius_um':native('REI')[k],'used_diameter_um':result('DI_USED')['values'][k], **optical})
    return {'phase':phase.upper(),'i':i,'j':j,'native_layers':59,'backend_layers':backend_nl,
            'history_CF_differs_from_radiation_CF_cells':sum(x!=y for x,y in zip(cf,history_cf)),
            'supplied_udm_CF_differs_from_radiation_CF_cells':sum(x!=y for x,y in zip(cf,native('UDM_CF_USED'))),
            'paths':paths,'maximum_partition_rounding_residual_g_m2':closure,'cf0_ice_cells':cells}


def csv_text(cells):
    stream=io.StringIO(newline='')
    writer=csv.DictWriter(stream,fieldnames=list(cells[0]),lineterminator='\n')
    writer.writeheader();writer.writerows(cells)
    return stream.getvalue()


def analyze(saved):
    packet_bytes=(saved/'off/history_60s.bin').read_bytes()
    require(len(packet_bytes)==9440,'wrong packet size')
    packet=struct.unpack('<2360f',packet_bytes)
    groups=[];cells=[]
    for case in CASES:
        i=int(case[4]);j=int(case[7])
        require((saved/case/'history_60s.bin').read_bytes()==packet_bytes,'OFF/ON state packet changed')
        for phase in PHASES:
            group=analyze_capture(read_capture(saved,case,phase),packet,i,j,phase)
            groups.append(group);cells+=group['cf0_ice_cells']
    phase_summary={}
    for phase in ('LW','SW'):
        selected=[x for x in groups if x['phase']==phase]
        require(sum(len(x['cf0_ice_cells']) for x in selected)==12,'wrong physical CF0 ice cell roster')
        phases={p:{'grid_sum_g_m2':math.fsum(x['paths'][p]['grid_sum_g_m2'] for x in selected),
                   'omitted_sum_g_m2':math.fsum(x['paths'][p]['omitted_sum_g_m2'] for x in selected),
                   'positive_cells':sum(x['paths'][p]['positive_cells'] for x in selected),
                   'cf0_positive_cells':sum(x['paths'][p]['cf0_positive_cells'] for x in selected)} for p,*_ in SPECIES}
        phases['IWP']['omitted_to_total_native_column_path_ratio']=phases['IWP']['omitted_sum_g_m2']/phases['IWP']['grid_sum_g_m2']
        phase_summary[phase]=phases
    require(phase_summary['LW']==phase_summary['SW'],'different LW/SW native path states')
    return {'schema':'UDM37_RADIATION_OCCURRENCE_RUNTIME_V1','status':'PASS_SCOPED',
            'actual_wrf_runs':10,'final_evidence_wrf_runs':5,'initial_campaign_wrf_runs':5,'captured_phase_calls':8,'physical_columns':4,'source_time_seconds':60,
            'LW_SW_counts_are_separate':True,'netcdf_readback_in_saved_CI':False,
            'source_to_builder_to_backend_mapping':'PASS','f32_partition_replay':'PASS',
            'weighted_path_is_not_optical_or_flux_loss':True,'CF0_optical_input_exclusion_verified':True,
            'physical_approval':False,'production_accepted':False,
            'PHY_OCCURRENCE':'OPEN','phase_summary':phase_summary,'captures':groups}, csv_text(cells)


def verify(package=PACKAGE):
    manifest=json.loads((package/'manifest.json').read_text())
    require(manifest['physical_approval'] is False and manifest['production_accepted'] is False,'false physical approval')
    for name,entry in manifest['files'].items():
        p=package/name
        require(not Path(name).is_absolute() and '..' not in Path(name).parts,'unsafe evidence path')
        require(p.is_file() and not p.is_symlink(),'missing/unsafe saved file '+name)
        require(p.stat().st_size==entry['size_bytes'] and sha(p.read_bytes())==entry['sha256'],'evidence bytes changed '+name)
    source=json.loads((package/'saved/identity-before.json').read_text())
    corpus=json.loads((ROOT/'validation/rrtmgp37/connected-host-number/source/tracked-WRF-corpus.json').read_text())
    require(source['production_files_checked']==len(corpus['files'])==5910,'source corpus count')
    for row in corpus['files']:
        require(sha((ROOT/row['path']).read_bytes())==row['sha256'],'current production source changed '+row['path'])
    audit=json.loads(load_bytes(package/'saved/source-audit.json.gz'))
    require(audit['source_files']==5910 and not audit['missing'] and not audit['mismatch'],'retained source snapshot mismatch')
    require({x['path']:x['production_sha256'] for x in audit['files']}=={x['path']:x['sha256'] for x in corpus['files']},'source audit roster mismatch')
    after=json.loads((package/'saved/identity-after.json').read_text())
    require(after['executable']==source['executable'] and after['runtime_library_files_after']==source['runtime_library_files_before'],'identity before/after mismatch')
    execution=json.loads((package/'saved/execution.json').read_text())
    require(execution['wrf_processes']==len(execution['commands'])==5 and execution['compile_count']==0,'wrong run count')
    for index,cmd in enumerate(execution['commands'],1):
        require(cmd['status']=='TERMINAL' and cmd['actual_returncode']==0 and not cmd['timed_out'],'incomplete/failed WRF process')
        require(cmd==json.loads((package/f'saved/command-{index:02d}.json').read_text()),'process journal mismatch')
        require(b'SUCCESS COMPLETE WRF' in load_bytes(package/f'saved/command-{index:02d}.stdout.gz'),'missing WRF success')
    readback=json.loads((package/'saved/readback.json').read_text())
    require(readback['netcdf_readback_performed'] and len(readback['case_comparisons'])==8,'missing actual readback')
    bounds={'radliq_lwr':2.5,'radliq_upr':21.5,'diamice_lwr':10.,'diamice_upr':180.}
    for row in readback['cloud_LUT_bounds'].values():
        require(row['values']==bounds,'cloud LUT coordinate bounds changed')
    first_loader=None
    for key,libs in readback['loaded_libraries'].items():
        text=load_bytes(package/'saved'/(key+'.gz')).decode()
        import re
        initialized=re.findall(r'calling init:\s*(/[^\n]+)',text)
        require(len(initialized)==len(libs) and len(libs)>2,'actual loader record mismatch')
        fingerprint=[(x['path'],x['sha256'],x['size_bytes']) for x in libs]
        if first_loader is None: first_loader=fingerprint
        require(first_loader==fingerprint,'runtime loader/library roster differs between cases')
    for row in readback['case_comparisons']:
        off=load_bytes(package/'saved/off'/(row['file']+'.gz'))
        on=load_bytes(package/'saved'/row['case']/(row['file']+'.gz'))
        require(off==on and sha(off)==row['off']['sha256']==row['on']['sha256'],'OFF/ON full NetCDF bytes changed')
        require(row['whole_file_bytes_equal'] and row['variable_bytes_equal'] and row['definitions_and_attributes_equal'],'readback flag inconsistency')
    for name in ('off',)+CASES:
        launch=json.loads((package/'saved'/name/'launch.json').read_text())
        for input_name,pin in source['inputs'].items():
            if input_name!='namelist.input':
                require(launch['inputs'][input_name]['sha256']==pin['sha256'],'runtime input changed '+input_name)
        require((package/'saved'/name/'namelist.input').read_bytes()==(package/'saved/off/namelist.input').read_bytes(),'runtime namelist changed between cases')
    require(readback['packets']['off']['times'][-1]=='1999-10-22_19:01:10' and len(readback['packets']['off']['times'])==8,'no post-capture history')
    preliminary=json.loads((package/'initial-campaign/execution.json').read_text())
    require(preliminary['wrf_processes']==5 and len(preliminary['commands'])==5 and all(c['actual_returncode']==0 and c['status']=='TERMINAL' for c in preliminary['commands']),'initial campaign run count')
    result,table=analyze(package/'saved')
    require(result==json.loads((package/'result.json').read_text()),'derived result changed')
    require(table==(package/'cf0-ice-call-cells.csv').read_text(),'derived call table changed')
    require((package/'closure-conditions.json').read_bytes()==(ROOT/'validation/rrtmgp37/research-policy-contract/closure-conditions.json').read_bytes(),'fixed seven conditions changed')
    return result

if __name__=='__main__':
    result=verify()
    print(json.dumps({k:result[k] for k in ('status','actual_wrf_runs','captured_phase_calls','production_accepted','PHY_OCCURRENCE')},indent=2))
