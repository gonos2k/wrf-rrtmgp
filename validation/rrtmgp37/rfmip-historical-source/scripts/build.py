#!/usr/bin/env python3
"""Build isolated historical libraries and diagnostic driver; do not run it."""
from pathlib import Path
import hashlib, json, os, re, subprocess, time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def pin(p):
    p = Path(p); data = p.read_bytes()
    return {'path':str(p.resolve()),'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}

def closure(executable, env):
    text = subprocess.check_output(['/usr/bin/ldd',str(executable)],env=env,text=True)
    if 'not found' in text:
        raise ValueError('Missing runtime library: '+text)
    result = {}
    for line in text.splitlines():
        m = re.match(r'\s*(\S+)\s+=>\s+(/\S+)',line)
        if m:
            result[m.group(1)] = pin(Path(m.group(2)).resolve())
        else:
            m = re.match(r'\s*(/\S+)\s+\(',line)
            if m:
                result[m.group(1)] = pin(Path(m.group(1)).resolve())
    return result

def main():
    output = HERE / 'build-receipt.json'
    if output.exists():
        raise FileExistsError('No implicit build repeat')
    plan = json.loads((HERE/'plan.json').read_text())
    for rec in [*plan['source_files'],*plan['pins'].values()]:
        got = pin(rec['path'])
        if (got['sha256'],got['size']) != (rec['sha256'],rec['bytes']):
            raise ValueError('Frozen plan input changed: '+rec['path'])
    compiler = pin('/usr/bin/gfortran')
    if compiler['sha256'] != '7e292e9d5da17a37bb1c17a06afb6463db786c70827fd6893ed31a86715b03c3':
        raise ValueError('Compiler differs from completed v5')
    env = dict(os.environ)
    baseline = json.loads((ROOT/'build/udm37-rfmip-residual-next-diagnostic-v5/baseline-runtime-closure-v4.json').read_text())
    env.update(baseline['controlled_env'])
    for key in ['RTE_KERNELS','MAKEFLAGS','MFLAGS']:
        env.pop(key,None)
    src = HERE/'source'; libs = src/'build'; ex = src/'examples/rfmip-clear-sky'
    obj = HERE/'objects'; obj.mkdir(exist_ok=False)
    flags = ['-O0','-ffree-line-length-none']
    include = ['-I'+plan['build']['NetCDF_include'],'-I'+str(libs),'-I'+str(obj)]
    commands = [(['/usr/bin/make','-C',str(libs),'FC=/usr/bin/gfortran',
                  'FCFLAGS='+' '.join(flags),'FCINCLUDE=-I'+plan['build']['NetCDF_include']],libs)]
    for name,file in [('mo_simple_netcdf',src/'examples/mo_simple_netcdf.F90'),
                      ('mo_rfmip_io',ex/'mo_rfmip_io.F90'),
                      ('mo_load_coefficients',src/'examples/mo_load_coefficients.F90'),
                      ('rrtmgp_rfmip_sw_diag',HERE/'rrtmgp_rfmip_sw_diag.F90')]:
        commands.append((['/usr/bin/gfortran',*flags,*include,'-c',str(file),'-o',str(obj/(name+'.o'))],obj))
    executable = HERE/'rrtmgp_rfmip_sw_diag'
    commands.append((['/usr/bin/gfortran',*flags,'-o',str(executable),
        *[str(obj/(name+'.o')) for name in ['rrtmgp_rfmip_sw_diag','mo_simple_netcdf','mo_rfmip_io','mo_load_coefficients']],
        '-L'+str(libs),'-L'+plan['build']['NetCDF_libraries'],'-lrrtmgp','-lrte','-lnetcdff','-lnetcdf'],obj))
    receipt = {'status':'BUILDING_NO_SOLVER','plan_sha256':pin(HERE/'plan.json')['sha256'],
               'compiler':compiler,'controlled_environment':baseline['controlled_env'],
               'commands':[],'solver_invocations':0,'WRF_or_REAL_invocations':0}
    try:
        for index,(cmd,cwd) in enumerate(commands):
            log=HERE/f'build-{index:02}.log'; started=time.time()
            with log.open('x') as stream:
                result=subprocess.run(cmd,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=300)
            receipt['commands'].append({'argv':cmd,'cwd':str(cwd),'returncode':result.returncode,'elapsed_s':time.time()-started,'log':pin(log)})
            if result.returncode:
                raise RuntimeError(f'Build command {index} failed; inspect {log.name}')
        actual=closure(executable,env)
        expected=baseline['resolved_libraries']
        if actual != expected:
            receipt['runtime_closure_actual']=actual
            receipt['runtime_closure_expected']=expected
            raise ValueError('Runtime closure differs from retained current-source arm')
        receipt.update(status='PASS_BUILD_NO_SOLVER',executable=pin(executable),
                       runtime_closure=actual,runtime_closure_exact_to_v5=True,
                       archives=[pin(libs/'librte.a'),pin(libs/'librrtmgp.a')])
    except Exception as exc:
        receipt.update(status='BUILD_FAILED_NO_SOLVER',error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        output.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':receipt['status'],'compiler_commands':len(commands),'executable':receipt['executable'],'runtime_libraries':len(actual)},sort_keys=True))

if __name__=='__main__':main()
