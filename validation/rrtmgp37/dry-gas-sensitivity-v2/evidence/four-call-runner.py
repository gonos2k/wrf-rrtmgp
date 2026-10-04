#!/usr/bin/env python3
"""One-use dry-mass sensitivity replay. --check performs no solver calls."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, os, re, subprocess, sys, time
from pathlib import Path
import numpy as np

ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
HERE=ROOT/'build/dgcf-runtime-v2'
PLAN=HERE/'plan.json'
PREFLIGHT=HERE/'preflight.json'
RUN=HERE/'run-v1'
EXE=ROOT/'build/dgcf-build-v3/cmake-build/reference_column'
DATA=ROOT/'build/udm-cu-optics-design-work/WRF/run'
TABLE=ROOT/'build/udm37-frozen-planck-coverage-v1/runs/frozen-planck-150-330-step5-plus233-v1/frozen-ice-psd-moments.nc'
CAP=ROOT/'build/udm37-rrtmg4-export-runtime-v1/NEW_ON'
LW_IN=CAP/'trace/lw_000001.input'; SW_IN=CAP/'trace/sw_000001.input'
LW_OUT=CAP/'export/rrtmg4_d01_i24_j55_step2161_lw.txt'; SW_OUT=CAP/'export/rrtmg4_d01_i24_j55_step2161_sw.txt'
DEP=ROOT/'build/udm37-dry-gas-sensitivity-design-v3/build-dependencies.json'
BUILD_RECEIPT=ROOT/'build/dgcf-build-v3/build-receipt.json'
BUILD_READBACK=ROOT/'build/dgcf-build-v3/postbuild-readback.json'
LIBPATH=str(ROOT/'build/deps/netcdf/lib')+':/usr/lib/x86_64-linux-gnu'
ENV={'PATH':'/usr/bin:/bin','LD_LIBRARY_PATH':LIBPATH,'NETCDF':str(ROOT/'build/deps/netcdf'),
     'WRF_RRTMGP_FROZEN_TABLE':str(TABLE),'OPENBLAS_NUM_THREADS':'1'}
TIMEOUT_SECONDS=300
READER=ROOT/'build/udm37-current-rrtmg4-optics-export-work/validation/rrtmgp37/rrtmg4-optics-export/read_export.py'
COMPARE=ROOT/'build/udm37-cf0-precip-audit-pr-work/WRF/test/rrtmgp/compare_column_replay.py'
READER_SHA='08519a5945e337d11cd2cb9b599c435aa76d13dfd21ec266ad291721e4cc5817'
COMPARE_SHA='6099a3819268d3ee17bbcbaf0610c03822c09247da6ac5bdfdef66c9190533a7'
AVOGADRO=6.02214076e23


def sha_bytes(b:bytes)->str: return hashlib.sha256(b).hexdigest()
def pin(path:Path)->dict:
    if not path.is_file(): raise RuntimeError(f'missing pinned file: {path}')
    b=path.read_bytes();return {'path':str(path.resolve()),'sha256':sha_bytes(b),'size_bytes':len(b)}
def atomic(path:Path,obj:dict)->None:
    tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,path);fd=os.open(path.parent,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
def import_reader():
    reader=READER
    if pin(reader)['sha256']!=READER_SHA: raise RuntimeError('export reader source pin changed')
    spec=importlib.util.spec_from_file_location('pinned_rrtmg4_export_reader',reader)
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod);return mod

def section(lines,name):
    matches=[i for i,line in enumerate(lines) if line.split() and line.split()[0]==name]
    if len(matches)!=1: raise ValueError(f'{name}: expected exactly one section, got {len(matches)}')
    i=matches[0]; hdr=lines[i].split()
    if len(hdr)<3: raise ValueError(f'{name}: malformed section header')
    dims=tuple(map(int,hdr[1:])); count=math.prod(dims); vals=[]; records=[]; j=i+1
    while len(vals)<count:
        if j>=len(lines): raise ValueError(f'{name}: truncated')
        rec=lines[j]; tokens=rec.split()
        if len(tokens)!=1: raise ValueError(f'{name}: expected one scalar per source line')
        v=float(tokens[0].replace('D','E').replace('d','e'))
        if not math.isfinite(v): raise ValueError(f'{name}: nonfinite')
        vals.append(v);records.append(j);j+=1
    if len(vals)!=count: raise ValueError(f'{name}: excess values')
    return i,dims,vals,records

def parse_sha_from_input(path:Path):
    lines=path.read_text(encoding='ascii').splitlines()
    _,dims,vals,_=section(lines,'FROZEN_TABLE_SHA256_BYTES')
    if dims!=(64,1) or any(v!=int(v) or int(v)<0 or int(v)>127 for v in vals): raise ValueError('invalid frozen table digest record')
    digest=''.join(chr(int(v)) for v in vals)
    if re.fullmatch(r'[0-9a-f]{64}',digest) is None: raise ValueError('invalid frozen digest ASCII')
    return digest

def make_cf_input(source:Path, export_path:Path, field_name:str, staged:Path, reader):
    exp=reader.read_export(export_path,expected_phase='LW' if field_name=='COLDry' else 'SW')
    field=exp['fields'].get(('INPUT',field_name))
    if field is None or field.units!='molecule_cm-2': raise ValueError(f'{field_name}: missing actual legacy INPUT export or units')
    expected_levels=57 if field_name=='COLDry' else 45
    if field.shape!=(expected_levels,): raise ValueError(f'{field_name}: unexpected shape {field.shape}')
    lines=source.read_text(encoding='ascii').splitlines()
    raw_lines=source.read_text(encoding='ascii').splitlines(keepends=True)
    _,mass_dims,mass_old,mass_rows=section(lines,'NATIVE_DRY_LAYER_MASS_KG_M2')
    if mass_dims!=(1,44) or len(field.values)<44: raise ValueError('native mass/legacy column shapes differ')
    _,mdry_dims,mdry_vals,_=section(lines,'MOL_WEIGHT_DRY')
    if mdry_dims!=(1,1) or not (mdry_vals[0]>0): raise ValueError('captured dry molar mass malformed')
    mdry=mdry_vals[0]
    mass_new=[float(field.values[k])*mdry*10000.0/AVOGADRO for k in range(44)]
    if any(not math.isfinite(v) or v<=0 for v in mass_new): raise ValueError('counterfactual native dry mass invalid')
    original_tokens=[]; new_tokens=[]
    for row,val in zip(mass_rows,mass_new):
        line=raw_lines[row]
        m=re.fullmatch(r'(\s*)([^\s]+)(\s*\r?\n?)',line)
        if not m: raise ValueError('native mass row cannot be losslessly rewritten')
        original_tokens.append(m.group(2)); new_tokens.append(format(val,'.16E'))
        raw_lines[row]=m.group(1)+new_tokens[-1]+m.group(3)
    staged.write_text(''.join(raw_lines),encoding='ascii',newline='')
    # Byte-diff must be exactly the 44 value tokens, with all other content preserved.
    srcbytes=source.read_bytes(); dstbytes=staged.read_bytes()
    roundtrip=bytearray(srcbytes)
    original_lines=srcbytes.decode('ascii').splitlines(keepends=True)
    for row,val in zip(mass_rows,new_tokens):
        m=re.fullmatch(r'(\s*)([^\s]+)(\s*\r?\n?)',original_lines[row])
        original_lines[row]=m.group(1)+val+m.group(3)
    if ''.join(original_lines).encode('ascii')!=dstbytes: raise ValueError('sidecar contains edits outside native dry-mass scalar tokens')
    # Verify all unchanged parsed records and native mass transformation.
    newlines=dstbytes.decode('ascii').splitlines()
    _,_,mass_check,_=section(newlines,'NATIVE_DRY_LAYER_MASS_KG_M2')
    if mass_check!=[float(x) for x in new_tokens]: raise ValueError('written native mass parse mismatch')
    return {'source':pin(source),'staged':pin(staged),'legacy_export':pin(export_path),'field':field_name,
            'legacy_units':field.units,'legacy_levels':len(field.values),'native_levels_replaced':44,
            'mdry_kg_mol_captured':mdry,'avogadro_mol_inv':AVOGADRO,
            'native_mass_before_minmax':[min(mass_old),max(mass_old)],
            'native_mass_after_minmax':[min(mass_new),max(mass_new)],
            'staged_diff_contract':'only 44 NATIVE_DRY_LAYER_MASS_KG_M2 value tokens changed',
            'frozen_table_sidecar_sha256':parse_sha_from_input(source)}

def normalized_ldd(exe:Path):
    cp=subprocess.run(['/usr/bin/ldd',str(exe)],env=ENV,text=True,capture_output=True,check=True)
    libs=[]
    for line in cp.stdout.splitlines():
        if '=>' not in line: continue
        loc=line.split('=>',1)[1].strip().split()[0]
        if loc.startswith('/'):
            p=Path(loc).resolve();libs.append(pin(p))
    return sorted({x['path']:x for x in libs}.values(),key=lambda x:x['path']),sha_bytes(cp.stdout.encode())

def verify_pins():
    plan=json.loads(PLAN.read_text())
    dep=json.loads(DEP.read_text()); build=json.loads(BUILD_RECEIPT.read_text()); readback=json.loads(BUILD_READBACK.read_text())
    runner_path=HERE/'run_four_calls.py'
    scratch_driver=ROOT/'build/dgcf-src-v1/WRF/test/rrtmgp/reference_column.f90'
    if pin(READER)['sha256']!=READER_SHA or pin(COMPARE)['sha256']!=COMPARE_SHA: raise RuntimeError('pinned parser source changed')
    if pin(scratch_driver)['sha256']!='dcd6756345b38f5aaa03e4b2b6e879edd886786e2e41aacfc71c0c15e16ff4d9': raise RuntimeError('scratch driver changed')
    if build.get('status')!='BUILD_PASS' or build.get('build_returncode')!=0 or build.get('solver_invocations') or build.get('model_invocations'):
        raise RuntimeError('scratch build receipt not an accepted compile-only BUILD_PASS')
    if readback.get('status')!='PASS': raise RuntimeError('scratch build independent postreadback not PASS')
    if pin(EXE)['sha256']!='6e271346cfa7115d3e5c2c170a5881065ed7a1739d716cad4ed894187977aeb2': raise RuntimeError('scratch executable pin changed')
    if pin(TABLE)['sha256']!='ebeafb9746164d5414a45eab4061c5c855f0f91e92be77003b3829722514fe6a': raise RuntimeError('captured expanded table pin changed')
    if not DATA.is_dir(): raise RuntimeError('coefficient data dir missing')
    # Bind all original data/dependency/build inputs and current capture files.
    for rec in dep['data_assets']:
        p=Path(rec['path'])
        if rec.get('kind')=='symlink':
            if not p.is_symlink() or os.readlink(p)!=rec['target']: raise RuntimeError(f'data symlink drift {p}')
        elif pin(p)['sha256']!=rec['sha256']: raise RuntimeError(f'data file drift {p}')
    for rec in dep['normalized_runtime_libraries']:
        if pin(Path(rec['path']))['sha256']!=rec['sha256']: raise RuntimeError(f'library drift {rec["path"]}')
    for rec in dep['source_pins']:
        if pin(Path(rec['path']))['sha256']!=rec['sha256']: raise RuntimeError(f'source drift {rec["path"]}')
    for name in ('frozen_table_resolved_target','captured_runtime_frozen_table'):
        rec=dep[name]
        if pin(Path(rec['path']))['sha256']!=rec['sha256']: raise RuntimeError(f'table drift {name}')
    libs,_ldd_stdout_hash_provenance_only=normalized_ldd(EXE)
    if libs!=readback['runtime_libraries']['normalized_libraries']: raise RuntimeError('scratch runtime library closure changed')
    capture={}
    for p in (LW_IN,SW_IN,LW_OUT,SW_OUT,CAP/'trace/lw_000001.raw',CAP/'trace/lw_000001.result',CAP/'trace/sw_000001.raw',CAP/'trace/sw_000001.result'):
        capture[p.name]=pin(p)
    for path,phase in ((LW_IN,'LW'),(SW_IN,'SW')):
        if parse_sha_from_input(path)!=hashlib.sha256(TABLE.read_bytes()).hexdigest(): raise RuntimeError(f'{phase} capture table digest differs from runtime table')
    for key,record in capture.items():
        expected=plan['capture_pins'][key]
        if record['sha256']!=expected['sha256'] or record['size_bytes']!=expected['size_bytes']:
            raise RuntimeError(f'capture pin changed: {key}')
    if pin(DEP)['sha256']!=plan['reviewed_build']['dependencies']['sha256']: raise RuntimeError('dependency manifest changed')
    if pin(runner_path)['sha256']!=plan['runner']['sha256']: raise RuntimeError('runner source pin changed')
    if pin(READER)['sha256']!=plan['parsers']['export_reader']['sha256'] or pin(COMPARE)['sha256']!=plan['parsers']['result_reader']['sha256']: raise RuntimeError('parser source pins changed')
    if pin(BUILD_RECEIPT)['sha256']!=plan['reviewed_build']['build_receipt']['sha256']: raise RuntimeError('build receipt changed')
    if pin(BUILD_READBACK)['sha256']!=plan['reviewed_build']['build_readback']['sha256']: raise RuntimeError('build readback changed')
    return {'runner':pin(runner_path),'plan':pin(PLAN),'export_reader':pin(READER),'result_reader':pin(COMPARE),'executable':pin(EXE),'scratch_driver':pin(scratch_driver),'data_assets_manifest_sha256':hashlib.sha256(DEP.read_bytes()).hexdigest(),
            'build_receipt':pin(BUILD_RECEIPT),'build_postreadback':pin(BUILD_READBACK),
            'frozen_table':pin(TABLE),'normalized_runtime_libraries':libs,
            'capture_inputs_and_results':capture}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--check',action='store_true',help='verify pins and inputs only; no solver calls')
    ap.add_argument('--execute',action='store_true',help='run four calls only with reviewed root authorization')
    ap.add_argument('--authorization',type=Path)
    args=ap.parse_args()
    if args.check==args.execute: ap.error('select exactly one of --check or --execute')
    reader=import_reader()
    result={'schema':'udm37-dry-gas-four-call-runner-v1','status':'PREFLIGHT_RUNNING','calls_started':0,'standalone_reference_invocations':0,'wrf_model_invocations':0,'started_unix':time.time()}
    if args.check:
        if PREFLIGHT.exists() or PREFLIGHT.is_symlink(): ap.error(f'preflight receipt exists: {PREFLIGHT}')
        if RUN.exists() or RUN.is_symlink(): ap.error(f'run root collision: {RUN}')
        if (HERE/'preflight-inputs.tmp').exists(): ap.error('staged preflight input directory collision')
        try:
            pins=verify_pins()
            tmp=HERE/'preflight-inputs.tmp'; tmp.mkdir(exist_ok=False)
            transformations={
              'legacy_dry_lw':make_cf_input(LW_IN,LW_OUT,'COLDry',tmp/'counterfactual_lw.input',reader),
              'legacy_dry_sw':make_cf_input(SW_IN,SW_OUT,'COLDRY',tmp/'counterfactual_sw.input',reader)}
            result.update({'status':'READY_NO_CALLS','pins':pins,'counterfactual_inputs':transformations,'output_root_reserved':str(RUN),'output_paths':[str(RUN/'outputs/baseline_lw.result'),str(RUN/'outputs/baseline_sw.result'),str(RUN/'outputs/legacy_dry_lw.result'),str(RUN/'outputs/legacy_dry_sw.result')],'planned_timeout_seconds_per_call':TIMEOUT_SECONDS,'planned_calls':4})
            result['runner']=pin(HERE/'run_four_calls.py');result['plan']=pin(PLAN)
            atomic(PREFLIGHT,result)
        except Exception as e:
            result.update({'status':'PREFLIGHT_FAIL_NO_CALLS','error':repr(e)});atomic(PREFLIGHT,result);raise
        print(json.dumps({'status':result['status'],'preflight':str(PREFLIGHT),'model_invocations':0},sort_keys=True));return 0
    # Execution is fail-closed and requires a separate authorization tied to this plan and binary.
    if args.authorization is None or not args.authorization.is_file(): ap.error('--execute requires a reviewed authorization JSON')
    auth=json.loads(args.authorization.read_text())
    planhash=sha_bytes(PLAN.read_bytes())
    if auth.get('schema')!='udm37-dry-gas-cf0-four-call-authorization-v1' or auth.get('approved') is not True or auth.get('plan_sha256')!=planhash or auth.get('reference_executable_sha256')!=pin(EXE)['sha256']:
        ap.error('authorization does not match this frozen plan/executable')
    if not PREFLIGHT.is_file(): ap.error('must have a passing --check preflight')
    pre=json.loads(PREFLIGHT.read_text())
    if pre.get('status')!='READY_NO_CALLS' or pre['pins']!=verify_pins(): ap.error('preflight no longer matches immutable inputs')
    if RUN.exists() or RUN.is_symlink(): ap.error('run root collision; no overwrite')
    lock=HERE/'execute.lock'
    fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    os.write(fd,json.dumps({'pid':os.getpid(),'plan_sha256':planhash}).encode());os.fsync(fd);os.close(fd)
    RUN.mkdir();(RUN/'inputs').mkdir();(RUN/'outputs').mkdir();(RUN/'logs').mkdir()
    state={'schema':'udm37-dry-gas-four-call-execution-v1','status':'RUNNING','authorization':pin(args.authorization),'preflight':pin(PREFLIGHT),'plan_sha256':planhash,'calls':[],'calls_started':0,'standalone_reference_invocations':0,'wrf_model_invocations':0,'started_unix':time.time()}
    recpath=RUN/'execution.json';atomic(recpath,state)
    try:
        # Copy byte-identical baseline inputs and the two already validated counterfactual inputs.
        staged={
          'baseline_lw':(LW_IN,RUN/'inputs/baseline_lw.input'),
          'baseline_sw':(SW_IN,RUN/'inputs/baseline_sw.input'),
        }
        expected_input_pins={}
        for name,(src,dst) in staged.items():
            dst.write_bytes(src.read_bytes())
            expected_source=(pre['pins']['capture_inputs_and_results']['lw_000001.input'] if name=='baseline_lw' else pre['pins']['capture_inputs_and_results']['sw_000001.input'])
            if pin(dst)['sha256']!=expected_source['sha256'] or pin(dst)['size_bytes']!=expected_source['size_bytes']: raise RuntimeError(f'{name} baseline input copy differs')
            expected_input_pins[name]=pin(dst)
        preinput=HERE/'preflight-inputs.tmp'
        for name in ('legacy_dry_lw','legacy_dry_sw'):
            src=preinput/f'counterfactual_{"lw" if name.endswith("lw") else "sw"}.input'
            staged_meta=pre['counterfactual_inputs'][name]['staged']
            if pin(src)['sha256']!=staged_meta['sha256'] or pin(src)['size_bytes']!=staged_meta['size_bytes']: raise RuntimeError(f'{name} staged preflight input changed')
            dst=RUN/f'inputs/{name}.input';dst.write_bytes(src.read_bytes())
            if pin(dst)['sha256']!=staged_meta['sha256'] or pin(dst)['size_bytes']!=staged_meta['size_bytes']: raise RuntimeError(f'{name} copied input changed')
            expected_input_pins[name]=pin(dst);staged[name]=(src,dst)
        call_specs=[('baseline_lw','LW',RUN/'inputs/baseline_lw.input',False),('baseline_sw','SW',RUN/'inputs/baseline_sw.input',False),('legacy_dry_lw','LW',RUN/'inputs/legacy_dry_lw.input',False),('legacy_dry_sw','SW',RUN/'inputs/legacy_dry_sw.input',True)]
        exe_pin=pin(EXE); dep_before=verify_pins()
        for name,phase,inputp,is_cf_sw in call_specs:
            if pin(EXE)!=exe_pin or verify_pins()!=dep_before: raise RuntimeError('immutable pin drift before call '+name)
            if pin(inputp)!=expected_input_pins[name]: raise RuntimeError('call input changed before launch '+name)
            if name.startswith('legacy_dry_'):
                key=name
                if pin(inputp)['sha256']!=pre['counterfactual_inputs'][key]['staged']['sha256'] or pin(inputp)['size_bytes']!=pre['counterfactual_inputs'][key]['staged']['size_bytes']:
                    raise RuntimeError('counterfactual staged input no longer matches approved preflight '+name)
            output=RUN/f'outputs/{name}.result';log=RUN/f'logs/{name}.log'
            if output.exists() or output.is_symlink() or log.exists() or log.is_symlink(): raise RuntimeError('per-call output collision '+name)
            cmd=[str(EXE),str(DATA),str(inputp),str(output)]
            if is_cf_sw: cmd += ['','','','ALLOW_CHANGED_V11_GAS_TAU']
            entry={'id':name,'phase':phase,'argv':cmd,'input':pin(inputp),'output_path':str(output),'log_path':str(log),'start_unix':time.time(),'status':'STARTING'}
            state['calls'].append(entry);atomic(recpath,state)
            with log.open('xb') as f:
                p=subprocess.Popen(cmd,cwd=RUN,env=ENV,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
                entry['pid']=p.pid;entry['status']='RUNNING';state['calls_started']+=1;state['standalone_reference_invocations']+=1;atomic(recpath,state)
                try: rc=p.wait(timeout=TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    entry['status']='TIMEOUT_TERMINATING';os.killpg(p.pid,15)
                    try: rc=p.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(p.pid,9);rc=p.wait()
                    entry['returncode']=rc;entry['end_unix']=time.time();entry['status']='TIMEOUT_TERMINATED';atomic(recpath,state)
                    raise RuntimeError(f'{name} exceeded timeout; final child return code {rc}')
            entry['returncode']=rc;entry['end_unix']=time.time();entry['status']='RETURNED';atomic(recpath,state)
            entry['log']=pin(log);entry['output_exists']=output.is_file()
            if pin(inputp)!=expected_input_pins[name]: raise RuntimeError('call input changed during replay '+name)
            if name.startswith('legacy_dry_') and (pin(inputp)['sha256']!=pre['counterfactual_inputs'][name]['staged']['sha256'] or pin(inputp)['size_bytes']!=pre['counterfactual_inputs'][name]['staged']['size_bytes']): raise RuntimeError('counterfactual input drifted during call '+name)
            if rc!=0 or not output.is_file(): entry['status']='CALL_FAILED';atomic(recpath,state);raise RuntimeError(f'{name} returned {rc} or output missing')
            entry['output']=pin(output)
            # Parser validates complete output sections are finite before next child starts.
            spec=importlib.util.spec_from_file_location('pinned_result_reader',COMPARE);mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
            parsed=mod.read_result(output)
            if parsed['phase']!=phase or parsed['nc']!=1: raise RuntimeError(f'{name} result header mismatch')
            entry['output_section_count']=len(parsed['sections']);entry['output_sections']={k:{'shape':list(v.shape),'finite':bool(np.isfinite(v).all())} for k,v in parsed['sections'].items()}
            if any(not x['finite'] for x in entry['output_sections'].values()): raise RuntimeError(f'{name} nonfinite output')
            if pin(EXE)!=exe_pin or verify_pins()!=dep_before: raise RuntimeError('immutable pin drift after call '+name)
            entry['status']='VALIDATED';atomic(recpath,state)
        # Full-array comparison by phase; differences are recorded, never judged by tolerance.
        parsed={}
        mod=mod
        for name,_,_,_ in call_specs: parsed[name]=mod.read_result(RUN/f'outputs/{name}.result')
        comparisons={}
        for phase,base,cf in [('LW','baseline_lw','legacy_dry_lw'),('SW','baseline_sw','legacy_dry_sw')]:
            a,b=parsed[base],parsed[cf]
            if (a['phase'],a['nc'],a['nl'],set(a['sections']))!=(b['phase'],b['nc'],b['nl'],set(b['sections'])): raise RuntimeError(f'{phase} result roster/shape mismatch')
            detail={}
            for key in sorted(a['sections']):
                x,y=a['sections'][key],b['sections'][key]
                if x.shape!=y.shape: raise RuntimeError(f'{phase}/{key} shape mismatch')
                delta=y-x
                detail[key]={'shape':list(x.shape),'exact_equal':bool(np.array_equal(x,y)),'changed_values':int(np.count_nonzero(delta)),'max_abs_difference':float(np.max(np.abs(delta))) if delta.size else 0.0,'mean_signed_difference':float(np.mean(delta)) if delta.size else 0.0}
            comparisons[phase]=detail
        state['comparisons']=comparisons;state['postflight_pins']=verify_pins();state['status']='ALL_FOUR_VALIDATED_DESCRIPTIVE';state['ended_unix']=time.time();atomic(recpath,state)
    except Exception as exc:
        state['status']='FAILED_PRESERVED';state['error']=repr(exc);state['ended_unix']=time.time();atomic(recpath,state);raise
    finally:
        # Keep lock as a consumed guard; never remove or overwrite it.
        pass
    print(json.dumps({'status':state['status'],'calls_started':state['calls_started'],'receipt':str(recpath)},sort_keys=True));return 0
if __name__=='__main__': raise SystemExit(main())
