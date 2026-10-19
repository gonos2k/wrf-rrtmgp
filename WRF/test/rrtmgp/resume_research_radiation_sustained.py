#!/usr/bin/env python3
"""Resume the declared 21610 s checkpoint, preserving physical/radiation choices.

The explicit output-timer settings retain a 300 s history cadence when WRF's
stock restore would repeat the remaining 290 s delay. No state field is edited.
"""
import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import shutil


def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('exe','campaign','plan','library-dir','workdir'):
        ap.add_argument('--'+name,required=True,type=Path)
    a=ap.parse_args();root=Path(__file__).resolve().parents[2]
    h=load(root/'test/rrtmgp/test_netcdf_zz.py','restart_runner')
    setup=load(root/'test/rrtmgp/test_udm_startup_snow_scm.py','restart_namelist')
    plan=json.loads(a.plan.read_text())
    if h.pin(a.exe)['sha256']!=plan['executable_sha256']:
        raise ValueError('frozen executable differs')
    case=a.campaign/'day/day_11'
    start=dt.datetime.strptime(plan['fixed']['start'],'%Y-%m-%d_%H:%M:%S')
    stage=next(x for x in plan['stages'] if x['name']=='day')
    restart=start+dt.timedelta(seconds=stage['checkpoint_interval_seconds'])
    end=start+dt.timedelta(seconds=stage['duration_seconds'])
    cp=case/('wrfrst_d01_'+restart.strftime('%Y-%m-%d_%H:%M:%S'))
    out=a.workdir.resolve();out.mkdir(parents=True,exist_ok=False)
    d=out/'resumed_11';d.mkdir()
    for p in case.iterdir():
        if p.is_file() and not p.name.startswith(('wrfout','wrfrst','rsl.','udm_')) and p.name not in ('stdout.log','namelist.output'):
            shutil.copy2(p,d/p.name)
    shutil.copy2(cp,d/cp.name)
    text=(case/'namelist.input').read_text()
    seconds=int((end-restart).total_seconds())
    settings={'run_days':seconds//86400,'run_hours':seconds%86400//3600,
              'run_minutes':seconds%3600//60,'run_seconds':seconds%60,
              'restart':'.true.','write_hist_at_0h_rst':'.true.','restart_interval_s':0,
              'override_restart_timers':'.true.',
              'history_begin_s':(-stage['checkpoint_interval_seconds'])%stage['history_interval_seconds']}
    for prefix,clock in [('start',restart),('end',end)]:
        for part in ('year','month','day','hour','minute','second'):
            settings[prefix+'_'+part]=getattr(clock,part)
    for key,val in settings.items():
        text=setup.set_assignment(text,key,str(val),group='time_control')
    (d/'namelist.input').write_text(text);(d/'capture').mkdir()
    env=dict(os.environ,OMP_NUM_THREADS='1')
    env['LD_LIBRARY_PATH']=str(a.library_dir.resolve())+':'+env.get('LD_LIBRARY_PATH','')
    for key in list(env):
        if key.startswith(('WRF_RRTMGP_','WRF_UDM_','WRF_RESEARCH_','WRF_RADIATION_ENERGY')):
            env.pop(key)
    env.update(WRF_RRTMGP_CAPTURE_DIR=str(d/'capture'),WRF_RRTMGP_CAPTURE_CALL='1',WRF_RRTMGP_BATCH_SIZE='1')
    runner=h.Runner(out,10800,env,1)
    receipt={'schema':'SUSTAINED_RESTART_V1','checkpoint':h.pin(cp),
             'executable':h.pin(a.exe),'preregistration':h.pin(a.plan),
             'status':'PREPARED','production_accepted':False}
    h.write_json(out/'receipt.json',receipt)
    try:
        log=runner.run([a.exe.resolve()],d,'resumed_11').read_text()
        receipt['status']='COMPLETED' if 'SUCCESS COMPLETE WRF' in log and 'FATAL CALLED' not in log else 'MODEL_REJECTED'
    finally:
        receipt['processes']=runner.commands;h.write_json(out/'receipt.json',receipt)
    print(receipt['status'])

if __name__=='__main__':main()
