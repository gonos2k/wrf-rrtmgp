from pathlib import Path
import hashlib, importlib.util, json, os

BASE=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
ROOT=BASE/'build/udm37-followup-evidence-integration-pr-work'
OUT=BASE/'build/udm37-followup-evidence-integration-tests-v1'
HELPER=BASE/'build/udm37-main-runtime-io-integration-pr-work/WRF/test/rrtmgp/test_netcdf_zz.py'
SPEC=importlib.util.spec_from_file_location('bounded_runner', HELPER)
MODULE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PYTHON='/usr/bin/python3.12'
PACKAGES=['rfmip-fixed-rte','rfmip-historical-rte','qnn-boundary-rk-observer','positive-nc-stage','positive-nc-activation','fractional-cf-population']
paths=[p for name in PACKAGES for p in (ROOT/'validation/rrtmgp37'/name).rglob('*') if p.is_file()]
paths += [ROOT/'WRF/test/rrtmgp/rrtmgp_rfmip_sw_fixed_rte.F90']
paths += [ROOT/'.github/workflows'/name for name in ['validate-rfmip-fixed-rte.yml','validate-rfmip-historical-rte.yml','validate-qnn-boundary-observer.yml','validate-positive-nc-stage-evidence.yml','validate-positive-nc-activation.yml','validate-fractional-cf-population.yml']]
paths += [HELPER]
paths += [ROOT/'validation/rrtmgp37/followup-evidence-integration/verify_historical_isolated.py']
pins=[MODULE.pin(p) for p in sorted(set(paths))]
if OUT.exists(): raise RuntimeError('one-use output exists; no retry')
OUT.mkdir()
steps=[(name,[PYTHON,'-I','-S',str(ROOT/'validation/rrtmgp37'/name/'verify_saved.py')]) for name in PACKAGES]
steps[1][1][-1]=str(ROOT/'validation/rrtmgp37/followup-evidence-integration/verify_historical_isolated.py')
steps[-1][1].extend(['--output',str(OUT/'fractional-cf-validation.json')])
steps.append(('fractional-cf-controls',[PYTHON,'-I','-S',str(ROOT/'validation/rrtmgp37/fractional-cf-population/scripts/test_validate_cf_population.py')]))
env=dict(os.environ)
env['PYTHONDONTWRITEBYTECODE']='1'
plan={'schema':'UDM37_FOLLOWUP_EVIDENCE_SAVED_TEST_PLAN_V1','base_main':'a91d0d855da3e24094c2e6c7ba1088b56bc8c461','commands':steps,'input_pins':pins,'python':MODULE.pin(PYTHON),'runner':MODULE.pin(__file__),'timeout_per_step_seconds':180,'wrf_model_invocations':0,'compiler_invocations':0,'new_rte_or_lblrtm_calls':0,'physical_acceptance':False,'scope':'Closed historical package integrity and saved arithmetic; no fresh producer/runtime/scientific acceptance'}
MODULE.write_json(OUT/'plan.json',plan)
runner=MODULE.Runner(OUT,180,env,len(steps))
try:
    for kind,argv in steps:
        runner.run(argv,ROOT,kind)
        terminal=runner.commands[-1]
        try:
            os.killpg(terminal['pid'],0)
        except ProcessLookupError:
            terminal['process_group_absent_after_wait']=True
            terminal['reaped']=True
            MODULE.write_json(OUT/f'command-{len(runner.commands):02d}.json',terminal)
        else:
            os.killpg(terminal['pid'],9)
            raise RuntimeError('unexpected descendants remain after saved verifier wait; group terminated')
        print(kind+': RC0',flush=True)
    after=[MODULE.pin(q['path']) for q in pins]
    if after != pins: raise RuntimeError('package/source bytes changed during saved verification')
    MODULE.write_json(OUT/'result.json',{'schema':plan['schema'],'status':'PASS_SCOPED_SAVED_EVIDENCE_INTEGRATION','commands':runner.commands,'input_pins':pins,'wrf_model_invocations':0,'compiler_invocations':0,'new_rte_or_lblrtm_calls':0,'physical_acceptance':False,'all_pinned_bytes_unchanged':True,'limitations':['Full external NetCDF/executables are represented by historical receipts, not re-opened here.','Strict RFMIP FAIL and Nc/PSD authority gaps remain unchanged.']})
except BaseException as error:
    MODULE.write_json(OUT/'result.json',{'status':'FAIL_PRESERVED','error':repr(error),'commands':runner.commands,'input_pins':pins,'physical_acceptance':False})
    raise
