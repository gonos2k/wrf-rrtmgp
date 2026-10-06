#!/usr/bin/env python3
"""Standard-library-only verifier for the archived QNN boundary observer evidence."""
import argparse, gzip, hashlib, json, math, pathlib, re, struct, sys

DEFAULT_ROOT=pathlib.Path(__file__).resolve().parent
ROOT=DEFAULT_ROOT

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def load(path):return json.loads(path.read_text())
def safe_payload(rel):
    p=pathlib.PurePosixPath(rel)
    if p.is_absolute() or '..' in p.parts or not p.parts:raise ValueError(f'unsafe payload path {rel!r}')
    q=ROOT.joinpath(*p.parts)
    if q.is_symlink() or not q.is_file():raise ValueError(f'missing/nonregular payload {rel}')
    return q
def f32(x):return struct.unpack('<f',struct.pack('<f',float(x)))[0]

def verify():
    manifest=load(ROOT/'manifest.json')
    if manifest.get('schema')!='QNN_BOUNDARY_EVIDENCE_ARCHIVE_V1':raise ValueError('manifest schema')
    rows=manifest.get('payloads')
    if not isinstance(rows,list) or len({r.get('path') for r in rows})!=len(rows):raise ValueError('duplicate/invalid manifest payload row')
    expected={r['path'] for r in rows}
    actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p!=ROOT/'manifest.json'}
    if actual!=expected:raise ValueError(f'closed-roster mismatch missing={sorted(expected-actual)} extra={sorted(actual-expected)}')
    for row in rows:
        p=safe_payload(row['path'])
        if p.stat().st_size!=row['size_bytes'] or digest(p)!=row['sha256']:raise ValueError(f'payload hash/size mismatch: {row["path"]}')
    origins=load(ROOT/'origins.json')
    origin_rows=origins.get('origins',[])
    origin_by={r['path']:r for r in origin_rows}
    if len(origin_by)!=len(origin_rows):raise ValueError('duplicate origin record')
    # Every archived copied/derived evidence file is explicitly joined to its origin.
    required_origins=expected-{'README.md','verify_saved.py','origins.json'}
    if set(origin_by)!=required_origins:raise ValueError('origin roster does not cover all non-authored payloads')
    for rel,o in origin_by.items():
        p=safe_payload(rel)
        if o.get('archive_sha256')!=digest(p) or o.get('archive_size_bytes')!=p.stat().st_size:raise ValueError(f'origin/archive join: {rel}')
    pins=load(ROOT/'source/source-pins.json')
    implementation=load(ROOT/'source/implementation.json')
    proof=load(ROOT/'source/source-preservation.json')
    if pins['instrumented_source_head']!='87b3f116e7e9832be14916dcb7821c5e3f09a4e9' or pins['instrumented_source_tree']!='558db787ca8d9a1bc68c4e10d9f30409d78335d8':raise ValueError('instrumented source identity')
    if len(pins['source_files'])!=2 or len(pins['frozen_original_files'])!=2:raise ValueError('expected exact two-file source pin sets')
    expected_files={'WRF/share/module_bc.F','WRF/dyn_em/solve_em.F'}
    if {x['path'].removeprefix('build/udm37-qnn-boundary-observer-source-v1/') for x in pins['source_files']}!=expected_files:raise ValueError('source file set')
    if implementation['source_pins']!=pins['source_files'] or implementation['frozen_original_pins']!=pins['frozen_original_files']:
        raise ValueError('implementation/source pin join')
    if implementation['patch']!=pins['patch'] or implementation['schema_pin']!=pins['schema'] or implementation['preservation_proof']!=pins['source_preservation_proof']:
        raise ValueError('implementation evidence pin join')
    if implementation.get('base_head')!='474c4af4928b49b4922fae30d422850b29ec1571':raise ValueError('observer patch base')
    if proof['WRF/share/module_bc.F']['new_sha256']!=next(x['sha256'] for x in pins['source_files'] if x['path'].endswith('/module_bc.F')):
        raise ValueError('module_bc preservation pin')
    if proof['WRF/dyn_em/solve_em.F']['new_sha256']!=next(x['sha256'] for x in pins['source_files'] if x['path'].endswith('/solve_em.F')):
        raise ValueError('solve_em preservation pin')
    if any(proof[k].get('original_statement_stream_after_removing_observer') is not True for k in expected_files):
        raise ValueError('source preservation statement-stream proof')
    for name in ('module_bc.F','solve_em.F'):
        gz=ROOT/'source'/f'{name}.gz';data=gzip.decompress(gz.read_bytes())
        pinned=next(x for x in pins['source_files'] if x['path'].endswith('/'+name))
        if len(data)!=pinned['size_bytes'] or hashlib.sha256(data).hexdigest()!=pinned['sha256']:
            raise ValueError(f'archived source snapshot mismatch: {name}')
    patch=ROOT/'source/observer.patch'
    if {'sha256':digest(patch),'size_bytes':patch.stat().st_size}!={k:pins['patch'][k] for k in ('sha256','size_bytes')}:
        raise ValueError('source patch pin')
    schema=load(ROOT/'schema/capture-schema.json')
    if schema.get('magic')!='UDM37QNNB1' or schema.get('host_kind')!=32 or schema.get('expected_packets')!=24 or schema.get('rows_each_packet')!=44:
        raise ValueError('capture schema constants')
    expected_columns={
      (0,1):(23,1,'Y-start',(1,45,1,25),(23,2),1),
      (1,4):(90,26,'X-end',(46,90,26,50),(89,26),2),
      (2,3):(1,74,'X-start',(1,45,51,75),(2,74),1),
      (3,2):(68,99,'Y-end',(46,90,76,99),(68,98),2),
    }
    name_rx=re.compile(r'^qnn_d(?P<d>\d+)_rank(?P<rank>\d+)_tile(?P<tile>\d+)_step(?P<step>\d+)_rk(?P<rk>\d+)_side(?P<side>\d+)\.raw$')
    packet_paths=sorted((ROOT/'capture').glob('*.raw'))
    if len(packet_paths)!=24:raise ValueError(f'packet count {len(packet_paths)}')
    keys=set();tiles={};rows_n=0;inflows=outflows=0;rhos=[];qncs=[];qnrs=[]
    for path in packet_paths:
        m=name_rx.fullmatch(path.name)
        if not m:raise ValueError(f'bad packet filename {path.name}')
        x={k:int(v) for k,v in m.groupdict().items()};rs=(x['rank'],x['side'])
        if rs not in expected_columns:raise ValueError(f'unexpected rank/side {rs}')
        i,j,label,bounds,source,tile_expected=expected_columns[rs]
        if x['d']!=1 or x['tile']!=tile_expected or x['step'] not in (1,2) or x['rk'] not in (1,2,3):raise ValueError(f'packet identity {x}')
        key=(x['d'],x['rank'],x['tile'],x['step'],x['rk'],x['side'])
        if key in keys:raise ValueError(f'duplicate packet key {key}')
        keys.add(key);tiles.setdefault(rs,set()).add(x['tile'])
        lines=path.read_text().splitlines()
        if len(lines)!=46 or lines[0]!='UDM37QNNB1':raise ValueError(f'{path.name}: magic/line count')
        h=[int(v) for v in lines[1].split()]
        if len(h)!=15:raise ValueError(f'{path.name}: header width')
        domain,step,rk,rank,tile,side,hi,hj,kts,ktf,bits,its,itf,jts,jtf=h
        if (domain,step,rk,rank,tile,side,hi,hj)!=(x['d'],x['step'],x['rk'],x['rank'],x['tile'],x['side'],i,j):raise ValueError(f'{path.name}: filename/header identity')
        if (kts,ktf,bits,its,itf,jts,jtf)!=(1,44,32,*bounds):raise ValueError(f'{path.name}: domain/header bounds')
        for idx,line in enumerate(lines[2:]):
            f=line.split()
            if len(f)!=18:raise ValueError(f'{path.name}: field count')
            ints=[int(v) for v in f[:5]];v=[float(s) for s in f[5:]]
            if not all(math.isfinite(t) for t in v):raise ValueError(f'{path.name}: nonfinite field')
            k,branch,si,sj,valid=ints
            if k!=kts+idx or branch not in (0,1) or valid!=1:raise ValueError(f'{path.name}: bad level/status')
            vel,ccn,q0,q1,nc0,nc1,nr0,nr1,al,alb,native_sum,rho,source_qnn=v
            s32=f32(f32(al)+f32(alb));r32=f32(1.0/s32)
            if not s32>0 or not math.isfinite(r32) or native_sum!=s32 or rho!=r32:raise ValueError(f'{path.name}: native REAL32 rho identity')
            side_inflow=(vel>=0 if side in (1,3) else vel<=0)
            if branch!=(1 if side_inflow else 0):raise ValueError(f'{path.name}: branch/velocity')
            if nc0!=nc1 or nr0!=nr1:raise ValueError(f'{path.name}: QNC/QNR changed')
            if branch==1:
                inflows+=1
                if (si,sj,source_qnn)!=(0,0,0.0) or q1!=ccn or ccn!=1.0e8:raise ValueError(f'{path.name}: inflow source assignment/CCN')
            else:
                outflows+=1
                if (si,sj)!=source or q1!=source_qnn:raise ValueError(f'{path.name}: outflow adjacent source assignment')
            rhos.append(rho);qncs.append(nc0);qnrs.append(nr0);rows_n+=1
    if len(keys)!=24 or rows_n!=1056 or inflows!=756 or outflows!=300 or not inflows:raise ValueError('packet/row/branch total mismatch')
    if any(len(v)!=1 for v in tiles.values()) or len(tiles)!=4:raise ValueError('rank/tile coverage')
    # Preserve and validate the original failed model-run receipt; recovery is additive.
    execution=load(ROOT/'receipts/v2-original-failed-execution.json')
    if execution.get('status')!='FAIL_PRESERVED' or execution.get('model_calls')!=2:raise ValueError('original v2 failure chronology')
    failure=execution['arms']['on'].get('error','')
    if 'outflow source/copy contract' not in failure:raise ValueError('preserved original failure is not the expected v2 parser contract failure')
    if any(execution['arms'][a].get('actual_rc')!=0 or not execution['arms'][a].get('reaped') for a in ('off','on')):raise ValueError('model completion receipt')
    stageplan=load(ROOT/'receipts/v2-stage-plan.json')
    if stageplan.get('schema')!='UDM37_QNN_BOUNDARY_OFF_ON_2MIN_STAGE_V2':raise ValueError('v2 stage-plan schema')
    if stageplan['runner']['sha256']!=execution['runner']['sha256'] or stageplan['runner']['size_bytes']!=execution['runner']['size_bytes']:
        raise ValueError('stage plan / executed runner identity')
    stagebytes=(ROOT/'receipts/v2-stage-plan.json').read_bytes()
    if {'sha256':hashlib.sha256(stagebytes).hexdigest(),'size_bytes':len(stagebytes)}!={k:execution['stage_pins']['stage-plan.json'][k] for k in ('sha256','size_bytes')}:
        raise ValueError('archived plan / original execution stage pin')
    auth=load(ROOT/'receipts/v2-root-authorization.json')
    authbytes=(ROOT/'receipts/v2-root-authorization.json').read_bytes()
    if {'sha256':hashlib.sha256(authbytes).hexdigest(),'size_bytes':len(authbytes)}!={k:execution['stage_pins']['root-authorization.json'][k] for k in ('sha256','size_bytes')}:
        raise ValueError('archived root authorization / execution pin')
    if auth.get('stage_plan_sha256')!=hashlib.sha256(stagebytes).hexdigest() or auth.get('runner_sha256')!=execution['runner']['sha256']:
        raise ValueError('root authorization does not bind staged plan and executed runner')
    recovery=load(ROOT/'receipts/saved-recovery-result.json')
    if recovery.get('status')!='PASS_SAVED_RUNTIME_CONSISTENCY_SCOPED' or recovery['capture']['packet_count']!=24 or recovery['capture']['row_count']!=1056:
        raise ValueError('saved recovery report status/count')
    if recovery['source_failure_preserved']['reason']!=failure:raise ValueError('recovery did not preserve original failure reason')
    if recovery['capture']['inflow_rows']!=inflows or recovery['capture']['outflow_rows']!=outflows:raise ValueError('recovery row summary mismatch')
    if not all(x.get('pass_exact') and x.get('whole_file_exact') for x in recovery['off_on_saved_outputs']):raise ValueError('saved output comparison receipt')
    if any(not all(v.get('arrays_exact') for v in x.get('variables',[])) or x.get('array_mismatches') or
           x.get('dimension_differences') or x.get('global_attribute_differences') or x.get('variable_attribute_differences')
           for x in recovery['off_on_saved_outputs']):raise ValueError('recovery report lacks full variable/schema/attribute equality')
    capr=recovery['capture']
    if capr['qnc_minmax']!=[min(qncs),max(qncs)] or capr['qnc_nonzero_rows']!=sum(v!=0 for v in qncs):raise ValueError('QNC context summary mismatch')
    if capr['qnr_minmax']!=[min(qnrs),max(qnrs)] or capr['qnr_nonzero_rows']!=sum(v!=0 for v in qnrs):raise ValueError('QNR context summary mismatch')
    if capr['rho_dry_minmax']!=[min(rhos),max(rhos)]:raise ValueError('rho summary mismatch')
    build_result=load(ROOT/'receipts/observer-build-result.json')
    if build_result.get('status')!='PASS_BUILD_INSTALL_SCOPED' or build_result.get('source_head')!=pins['instrumented_source_head'] or build_result.get('source_tree')!=pins['instrumented_source_tree']:
        raise ValueError('build receipt source/status')
    terminal=load(ROOT/'receipts/terminal-independent-review.json')
    prelaunch=load(ROOT/'receipts/prelaunch-independent-review.json')
    if terminal.get('status')!='PASS_SCOPED_SAVED_OFF_ON_EQUALITY_AND_BOUNDARY_RELATIONS':raise ValueError('terminal review status')
    terminal_outputs=terminal.get('OFF_ON_comparisons',[])
    if len(terminal_outputs)!=2 or any(not x.get('whole_file_exact') or not x.get('dimension_schema_exact') or
          not x.get('global_attributes_exact') or not x.get('ordered_variable_roster_exact') or
          not all(v.get('raw_bytes_exact') and v.get('attributes_exact') for v in x.get('variables',[])) for x in terminal_outputs):
        raise ValueError('terminal review does not prove full OFF/ON saved output equality')
    if prelaunch.get('status')!='PASS_SCOPED_PRELAUNCH_REVIEW':raise ValueError('prelaunch review status')
    erratum=load(ROOT/'receipts/width5-coordinate-erratum.json')
    if erratum.get('preserved') is not True or erratum.get('correct_sources')!={'0':[23,2],'1':[89,26],'2':[2,74],'3':[68,98]}:
        raise ValueError('width5/spec_zone erratum')
    return {'status':'PASS_ARCHIVE_INTEGRITY_AND_SAVED_PACKET_CHECKS','payloads':len(rows),'packets':len(packet_paths),'rows':rows_n,
      'inflows':inflows,'outflows':outflows,'rho_min':min(rhos),'rho_max':max(rhos),
      'qnc_minmax':[min(qncs),max(qncs)],'qnc_nonzero':sum(v!=0 for v in qncs),
      'qnr_minmax':[min(qnrs),max(qnrs)],'qnr_nonzero':sum(v!=0 for v in qnrs),
      'off_on_saved_files_exact':len(recovery['off_on_saved_outputs']),'model_calls_repeated':0,
      'scientific_accepted':False}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--package-dir',type=pathlib.Path,default=DEFAULT_ROOT)
    args=ap.parse_args();ROOT=args.package_dir.resolve()
    try:result=verify()
    except Exception as e:
        print(json.dumps({'status':'FAIL','error':repr(e)}));sys.exit(1)
    print(json.dumps(result,sort_keys=True))
