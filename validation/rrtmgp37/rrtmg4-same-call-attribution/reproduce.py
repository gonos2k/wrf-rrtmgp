#!/usr/bin/env python3
"""Portable read-only verifier for selected same-call RRTMG4/RRTMGP evidence.

Uses only the Python standard library plus the bundled PR74 read_export.py.
It does not run WRF, RRTMGP, a solver, or a compiler.
"""
from __future__ import annotations
import argparse, csv, gzip, hashlib, importlib.util, json, math, struct, sys, tempfile
from pathlib import Path

PKG=Path(__file__).resolve().parent
MANIFEST=PKG/'artifact-manifest.json'
EXPORT_INDEX=json.loads((PKG/'external-pins/pr74-export-index.json').read_text())
EXPECTED_PHASES=('LW','SW')
ARMS=('OLD_OFF','NEW_OFF','NEW_ON')
POINT={'domain':1,'step':2161,'source_seconds':129600.0,'i':24,'j':55}


def sha_bytes(b:bytes)->str: return hashlib.sha256(b).hexdigest()
def sha_file(p:Path)->str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()
def f64bits(x:float)->bytes:return struct.pack('>d',float(x))
def f32bits(x:float)->bytes:return struct.pack('>f',float(x))
def f32(x:float)->float:return struct.unpack('>f',f32bits(x))[0]


def load_read_export():
    p=PKG/'parser/read_export.py'
    spec=importlib.util.spec_from_file_location('bundled_read_export',p)
    if spec is None or spec.loader is None:raise RuntimeError('cannot import bundled read_export.py')
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    return mod


def read_trace(path:Path, kind:str):
    lines=path.read_text(encoding='ascii').splitlines()
    expected={'raw':'RRTMGP_RAW_V1','result':'RRTMGP_RESULT_V1'}.get(kind)
    if len(lines)<2 or (kind=='input' and lines[0].strip() not in ('RRTMGP_REPLAY_V10','RRTMGP_REPLAY_V11')) or (kind!='input' and lines[0].strip()!=expected):raise ValueError(f'{path}: invalid {kind} magic')
    h=lines[1].split()
    if kind=='input':
        if len(h)!=6:raise ValueError(f'{path}: bad V10/V11 header')
        meta={'phase':h[0].upper(),'ncol':int(h[1]),'nlay':int(h[2]),'overlap':int(h[3]),'seed':int(h[4]),'iceflag':int(h[5])}; pos=2; scalar=False
    elif kind=='raw':
        if len(h)!=4:raise ValueError(f'{path}: bad raw header')
        meta={'phase':h[0].upper(),'i':int(h[1]),'j':int(h[2]),'native_nlay':int(h[3])}; pos=2; scalar=True
    else:
        if len(h)!=3:raise ValueError(f'{path}: bad result header')
        meta={'phase':h[0].upper(),'ncol':int(h[1]),'nlay':int(h[2])}; pos=2; scalar=False
    if meta['phase'] not in EXPECTED_PHASES:raise ValueError(f'{path}: bad phase')
    records={}
    while pos<len(lines):
        if not lines[pos].strip():pos+=1;continue
        head=lines[pos].split();pos+=1
        try:
            name=head[0].upper(); dims=tuple(int(x) for x in head[1:])
        except Exception as exc:raise ValueError(f'{path}: malformed record at line {pos}') from exc
        if name in records or not dims or any(x<1 for x in dims):raise ValueError(f'{path}: duplicate/invalid record {name}')
        count=dims[0] if scalar else math.prod(dims)
        vals=[]
        while len(vals)<count and pos<len(lines):
            try: row=[float(x.replace('D','E').replace('d','e')) for x in lines[pos].split()]
            except ValueError as exc:raise ValueError(f'{path}: invalid float at line {pos+1}') from exc
            pos+=1
            if not all(math.isfinite(x) for x in row):raise ValueError(f'{path}: nonfinite {name}')
            vals.extend(row)
            if len(vals)>count:raise ValueError(f'{path}: too many values for {name}')
        if len(vals)!=count:raise ValueError(f'{path}: truncated {name}')
        records[name]={'shape':dims,'values':vals}
    return meta,records


def expect_manifest():
    m=json.loads(MANIFEST.read_text())
    listed={x['path'] for x in m['files']}
    actual={p.relative_to(PKG).as_posix() for p in PKG.rglob('*') if p.is_file() and p!=MANIFEST}
    if listed!=actual:
        raise ValueError(f'package roster mismatch: missing={sorted(listed-actual)} extra={sorted(actual-listed)}')
    checks=[]
    for x in m['files']:
        p=PKG/x['path']; data=p.read_bytes()
        if len(data)!=x['size_bytes'] or sha_bytes(data)!=x['sha256']:
            raise ValueError(f'artifact hash/size mismatch: {x["path"]}')
        checks.append({'path':x['path'],'size_bytes':len(data),'sha256':x['sha256'],'ok':True})
    return m,checks


def main(output:Path):
    if PKG in output.resolve().parents:raise ValueError('output must be outside the immutable evidence package')
    manifest,artifact_checks=expect_manifest()
    read_export=load_read_export()
    exports={}; export_meta=[]
    byname={x['filename']:x for x in EXPORT_INDEX['files']}
    with tempfile.TemporaryDirectory(prefix='rrtmg4-samecall-') as td:
        for phase in EXPECTED_PHASES:
            filename=f'rrtmg4_d01_i24_j55_step2161_{phase.lower()}.txt'
            name=filename+'.gz'; rel=f'exports/{name}'; entry=byname[filename]
            gz=(PKG/rel).read_bytes()
            if sha_bytes(gz)!=entry['gzip_sha256'] or len(gz)!=entry['gzip_size_bytes']:
                raise ValueError(f'{name}: deterministic gzip pin mismatch')
            plain=gzip.decompress(gz)
            if sha_bytes(plain)!=entry['sha256'] or len(plain)!=entry['size_bytes']:
                raise ValueError(f'{name}: uncompressed export pin mismatch')
            tmp=Path(td)/filename;tmp.write_bytes(plain)
            exp=read_export.read_export(tmp,expected_phase=phase)
            if exp['metadata']!={**POINT,'phase':phase}:
                raise ValueError(f'{name}: export point/time metadata mismatch')
            exports[phase]=exp
            export_meta.append({'file':rel,'gzip_sha256':sha_bytes(gz),'uncompressed_sha256':sha_bytes(plain),'fields':len(exp['fields']),'metadata':exp['metadata'],'ok':True})
    traces={}
    for arm in ARMS:
        traces[arm]={}
        for phase in EXPECTED_PHASES:
            stem=phase.lower()+'_000001'; base=PKG/f'traces/{arm}/{stem}'
            im,irec=read_trace(base.with_suffix('.input'),'input')
            rm,rrec=read_trace(base.with_suffix('.raw'),'raw')
            om,orec=read_trace(base.with_suffix('.result'),'result')
            if im['phase']!=phase or rm['phase']!=phase or om['phase']!=phase:
                raise ValueError(f'{arm}/{phase}: phase mismatch')
            if rm['i']!=24 or rm['j']!=55 or im['ncol']!=1 or om['ncol']!=1:
                raise ValueError(f'{arm}/{phase}: selected-column identity mismatch')
            if im['nlay']!=om['nlay'] or im['nlay']!=(57 if phase=='LW' else 45):
                raise ValueError(f'{arm}/{phase}: layer dimensions differ from pinned capture')
            if rm['native_nlay']!=44:raise ValueError(f'{arm}/{phase}: expected native44 extent')
            traces[arm][phase]={'input_meta':im,'raw_meta':rm,'result_meta':om,'input':irec,'raw':rrec,'result':orec,
              'files':{ext:{'path':f'traces/{arm}/{stem}.{ext}','sha256':sha_file(base.with_suffix('.'+ext)),'size_bytes':base.with_suffix('.'+ext).stat().st_size} for ext in ('input','raw','result')}}
    # All six GP trace records are retained and described. Cross-arm diffs are
    # descriptive because OLD_OFF/NEW_OFF/NEW_ON intentionally differ by source/policy.
    cross_arm={}
    for phase in EXPECTED_PHASES:
        cross_arm[phase]={}
        for category in ('input','raw','result'):
            ref=traces['NEW_OFF'][phase][category]
            for other in ('OLD_OFF','NEW_ON'):
                target=traces[other][phase][category]
                common=sorted(set(ref)&set(target)); changed=[]
                for key in common:
                    a,b=ref[key]['values'],target[key]['values']
                    if ref[key]['shape']!=target[key]['shape'] or len(a)!=len(b) or any(f64bits(x)!=f64bits(y) for x,y in zip(a,b)):
                        changed.append(key)
                cross_arm[phase][category+':NEW_OFF-vs-'+other]={'common_record_count':len(common),'different_record_names':changed,'comparison_scope':'descriptive; run/source/policy are not asserted identical'}
    # Same-call input mapping and output check for NEW_ON against PR74 legacy export.
    same_call={}
    for phase in EXPECTED_PHASES:
        t=traces['NEW_ON'][phase]; exp=exports[phase]; f=exp['fields']; inp=t['input']; res=t['result']
        maps={'PLAY':'PLAY','PLEV':'PLEV','TLAY':'TLAY','H2O_VMR':'H2O','CO2_VMR':'CO2','O3_VMR':'O3','CH4_VMR':'CH4','N2O_VMR':'N2O','O2_VMR':'O2'}
        if phase=='LW':maps.update({'TLEV':'TLEV','TSFC':'TSFC','SURFACE_EMISSIVITY':'EMIS','CFC11_VMR':'VMR_CFC11','CFC12_VMR':'VMR_CFC12','CFC22_VMR':'VMR_CFC22','CCl4_VMR':'VMR_CCL4'})
        else:maps.update({'COSZEN':'MU0','ALBEDO_VIS_DIRECT':'AVDIR','ALBEDO_VIS_DIFFUSE':'AVDIF','ALBEDO_NIR_DIRECT':'ANDIR','ALBEDO_NIR_DIFFUSE':'ANDIF'})
        input_checks={}
        for export_name,gp_name in maps.items():
            key=('INPUT',export_name)
            if key not in f or gp_name not in inp:raise ValueError(f'{phase}: required selected input join missing: {export_name}={gp_name}')
            a=list(f[key].values); b=inp[gp_name]['values']
            input_checks[f'{export_name}={gp_name}']={'shape_export':list(f[key].shape),'shape_trace':list(inp[gp_name]['shape']),
              'ieee_binary64_equal':len(a)==len(b) and all(f64bits(x)==f64bits(y) for x,y in zip(a,b)),
              'count':min(len(a),len(b)),'max_abs_difference':max((abs(x-y) for x,y in zip(a,b)),default=0.0)}
        coldry=next((n for n in ('COLDry','COLDRY') if ('INPUT',n) in f),None)
        if coldry is None:raise ValueError(f'{phase}: exported legacy dry column absent')
        legacy=list(f['INPUT',coldry].values); gp=res['GAS_COL_DRY']['values']; native=t['raw']['DP_HPA']['values'].__len__()
        if len(legacy)!=len(gp) or len(legacy)!=len(gp) or native!=44:raise ValueError(f'{phase}: dry-column dimensions inconsistent')
        native_rel=[(g-l)/l for l,g in zip(legacy[:native],gp[:native])]
        extension_rel=[(gp[k]-legacy[k])/legacy[k] for k in range(native,len(legacy))]
        dry={'legacy_field':coldry,'units':f['INPUT',coldry].units,'legacy_layers':len(legacy),'native_layers':native,'extension_layers':len(legacy)-native,
          'native_gas_col_dry_vs_legacy_export':{'mean_abs_relative_difference_normalized_by_legacy':sum(abs(x) for x in native_rel)/len(native_rel),
            'mean_abs_relative_difference_normalized_by_native':sum(abs((g-l)/g) for l,g in zip(legacy[:native],gp[:native]))/native,
            'max_abs_relative_difference_normalized_by_legacy':max(map(abs,native_rel)),
            'max_abs_relative_difference_normalized_by_native':max(abs((g-l)/g) for l,g in zip(legacy[:native],gp[:native])),
            'max_layer_zero_based':max(range(native),key=lambda k:abs(native_rel[k]))},
          'extension_gas_col_dry_vs_legacy_export':{'max_abs_relative_difference_normalized_by_legacy':max(map(abs,extension_rel),default=0.0),
            'by_layer':[{'layer_zero_based':k,'legacy':legacy[k],'gp':gp[k],'relative_gp_minus_legacy':(gp[k]-legacy[k])/legacy[k]} for k in range(native,len(legacy))]}}
        fluxmap={'SURFACE_DOWN':('DOWN_FLUX','DN',0),'TOA_UP':('UP_FLUX','UP',-1)}
        output_checks=[]
        for row in csv.DictReader((PKG/'csv/NEW_ON-same_state.csv').open(newline='')):
            if row['phase'].strip().upper()!=phase or row['domain'].strip()!='1' or row['step'].strip()!='2161' or row['i'].strip()!='24' or row['j'].strip()!='55':continue
            metric=row['metric'].strip()
            if metric not in ('SURFACE_DOWN','TOA_UP','HEAT_1','HEAT_31','HEAT_44'):continue
            if metric in fluxmap:
                legacy_name,gp_name,idx=fluxmap[metric]; lval=f['RESULT',legacy_name].values[idx]; gvals=res[gp_name]['values']; gval=gvals[idx]
            else:
                k=int(metric.split('_')[1])-1
                lval=f['RESULT','HEATING'].values[k]; gval=res['HR']['values'][k]
            v4=float(row['value4']);v37=float(row['value37'])
            output_checks.append({'metric':metric,'sample_count':int(row['sample_count']),
              'csv4_ieee_binary32_equal_export':f32bits(v4)==f32bits(lval),'csv37_ieee_binary32_equal_trace':f32bits(v37)==f32bits(gval),
              'csv4_minus_export':v4-lval,'csv37_minus_trace':v37-gval})
        same_call[phase]={'legacy_input_vs_GP_input':input_checks,'legacy_COLDry_vs_GP_native_mass':dry,
          'CSV_vs_same_call_result':output_checks,'csv_check_count':len(output_checks)}
    unequal=[f'{phase}:{name}' for phase, data in same_call.items() for name, item in data['legacy_input_vs_GP_input'].items() if not item['ieee_binary64_equal']]
    if unequal:raise ValueError('selected legacy/GP input joins differ in IEEE binary64: '+', '.join(unequal))
    result={'schema':'portable-same-call-optical-attribution-verification-v1','status':'PASS_PACKAGE_HASH_AND_READ_ONLY_REPLAY_CHECKS',
      'dependencies':'Python standard library only; bundled parser/read_export.py included and imported dynamically.',
      'manifest_sha256':sha_file(MANIFEST),'artifact_hash_checks':artifact_checks,
      'exports':export_meta,'six_gp_trace_calls':[
        {'arm':arm,'phase':phase,'input_header':traces[arm][phase]['input_meta'],'raw_header':traces[arm][phase]['raw_meta'],'result_header':traces[arm][phase]['result_meta'],'files':traces[arm][phase]['files']}
        for arm in ARMS for phase in EXPECTED_PHASES],
      'cross_arm_descriptive_differences':cross_arm,'same_call_new_on_vs_legacy_export':same_call,
      'scope_limits':['The three arms are separate executions and are not interpreted as a purely isolated solver experiment.',
        'The CSV summarizes 128 observer seeds, while the selected GP trace is one captured seed/call; do not conflate the summary mean with the specific trace realization.',
        'Masks, cloud paths/radius conventions and spectral grids differ between legacy RRTMG and RRTMGP; same thermodynamic/gas-state matching does not make cloud optics or g-points one-to-one.',
        'No independent observational accuracy ranking or forecast skill claim is made.']}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as f:json.dump(result,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
    print(json.dumps({'status':result['status'],'output':str(output),'artifact_count':len(artifact_checks),'trace_call_count':len(result['six_gp_trace_calls']),'export_count':len(export_meta)}))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();main(args.output)
