#!/usr/bin/env python3
"""Actual serial WRF integration: two default-OFF radiation research choices."""
import argparse, importlib.util, json, os, shutil
from pathlib import Path
import netCDF4
import numpy as np

def load(p,name):
    spec=importlib.util.spec_from_file_location(name,p)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def require(ok,msg):
    if not ok: raise ValueError(msg)

def main():
    ap=argparse.ArgumentParser()
    for n in ['exe','template','positive','historical','workdir']: ap.add_argument('--'+n,required=True,type=Path)
    a=ap.parse_args(); root=Path(__file__).resolve().parents[2]; b=a.workdir.resolve(); b.mkdir(exist_ok=False)
    h=load(root/'test/rrtmgp/test_netcdf_zz.py','runner')
    setup=load(root/'test/rrtmgp/test_udm_startup_snow_scm.py','setup')
    env=dict(os.environ,OMP_NUM_THREADS='1')
    for k in list(env):
        if k.startswith(('WRF_RRTMGP_','WRF_UDM_','WRF_RESEARCH_','WRF_RADIATION_ENERGY')): env.pop(k)
    runner=h.Runner(b,180,env,16)
    receipt={'schema':'RESEARCH_RADIATION_INTEGRATION_V1','executable':h.pin(a.exe),
             'physical_input':h.pin(a.positive),'processes':[],'production_accepted':False}
    def save(): receipt['processes']=runner.commands; h.write_json(b/'receipt.json',receipt)
    def case(name,cap=0,size=0,radt='0',restart=False,tag=True,io=False,physical=None):
        physical=physical or a.positive
        d=b/name; d.mkdir()
        for p in a.template.iterdir():
            if p.is_file() and not p.name.startswith(('wrfout','wrfrst','rsl.','udm_')) and p.name not in ('stdout.log','namelist.output'): shutil.copy2(p,d/p.name)
        shutil.copy2(physical,d/'wrfinput_d01')
        text=(a.template/'namelist.input').read_text()
        settings=[('rrtmgp_capacity_policy',str(cap),'physics'),('rrtmgp_liquid_size_policy',str(size),'physics'),
                  ('radt',radt,'physics'),('run_minutes','0' if restart else '1','time_control'),
                  ('run_seconds','40' if restart else '0','time_control'),('end_minute','1','time_control'),
                  ('end_second','0','time_control'),('restart_interval','0','time_control'),
                  ('restart_interval_s','0' if restart else ('20' if io else '0'),'time_control'),
                  ('restart','.true.' if restart else '.false.','time_control')]
        if restart: settings += [('start_second','20','time_control'),('write_hist_at_0h_rst','.true.','time_control')]
        if io:
            settings += [('iofields_filename',"'research_iofields.txt'",'time_control')]
            (d/'research_iofields.txt').write_text((a.template/'radiation_iofields.txt').read_text()+'+:h:0:RTHRATLWC,RTHRATSWC,STEPRA\n')
        for k,v,g in settings: text=setup.set_assignment(text,k,v,group=g)
        (d/'namelist.input').write_text(text)
        if tag:
            with netCDF4.Dataset(d/'wrfinput_d01','r+') as nc:
                nc.setncattr('RRTMGP_CAPACITY_POLICY',np.int32(cap)); nc.setncattr('RRTMGP_LIQUID_SIZE_POLICY',np.int32(size))
        with netCDF4.Dataset(physical) as x,netCDF4.Dataset(d/'wrfinput_d01') as y:
            require(all(np.asarray(x[n][:]).tobytes()==np.asarray(y[n][:]).tobytes() for n in x.variables),'physical input changed')
        (d/'capture').mkdir()
        return d
    def run(d,capture='2',reject=None):
        runner.environment.update(WRF_RRTMGP_CAPTURE_DIR=str(d/'capture'),WRF_RRTMGP_CAPTURE_CALL=capture,WRF_RRTMGP_BATCH_SIZE='1')
        p=runner.run([a.exe.resolve()],d,d.name); text=p.read_text(errors='replace'); save()
        if reject:
            require(reject in text and 'SUCCESS COMPLETE WRF' not in text,'refusal not observed: '+d.name)
            require(not list(d.glob('wrfout*')),'refusal after history creation')
        else: require('SUCCESS COMPLETE WRF' in text and 'FATAL CALLED' not in text,'WRF failed: '+d.name)
    def compare(x,y,terminal=False):
        with netCDF4.Dataset(next(x.glob('wrfout*'))) as p,netCDF4.Dataset(next(y.glob('wrfout*'))) as q:
            names=[n for n in p.variables if 'Time' in p[n].dimensions]
            for n in names:
                u=np.asarray(p[n][-1] if terminal else p[n][:]); v=np.asarray(q[n][-1] if terminal else q[n][:])
                require(u.tobytes()==v.tobytes(),'arrays differ: '+x.name+'/'+y.name+'/'+n)
            return len(names)
    try:
        for cap,size in [(0,0),(0,1),(1,0),(1,1)]:
            d=case(f'cloud_{cap}{size}',cap,size); run(d)
        receipt['historical_arrays_equal']={n:compare(a.historical/old,b/n) for n,old in [('cloud_00','cloud_native'),('cloud_01','cloud_gamma8')]}
        d=case('capacity_previous',1,0,physical=a.template/'wrfinput_d01'); run(d,'1')
        receipt['capacity_prior_arrays_equal']=compare(a.historical/'capacity',d)
        d=case('defaults_previous',physical=a.template/'wrfinput_d01',tag=False)
        text=(d/'namelist.input').read_text()
        text='\n'.join(line for line in text.splitlines() if not any(k in line for k in ('rrtmgp_capacity_policy','rrtmgp_liquid_size_policy')))+'\n'
        (d/'namelist.input').write_text(text); run(d,'1')
        receipt['omitted_defaults_prior_arrays_equal']=compare(a.historical/'legacy',d)
        held=case('held_11',1,1,'0.5',io=True); run(held)
        cp=held/'wrfrst_d01_1999-10-22_19:00:20'; require(cp.exists(),'between-call checkpoint missing')
        resumed=case('resumed_11',1,1,'0.5',restart=True,io=True); shutil.copy2(cp,resumed/cp.name); run(resumed,'1')
        receipt['terminal_arrays_equal']=compare(held,resumed,True)
        receipt['checkpoint_time_seconds']=20; receipt['radiation_interval_seconds']=30
        for name,cap,size in [('mismatch_capacity',0,1),('mismatch_size',1,0)]:
            d=case(name,cap,size,'0.5',restart=True); shutil.copy2(cp,d/cp.name); run(d,'1','RRTMGP research policy differs')
        d=case('missing_tag',1,1,tag=False); run(d,'1','RRTMGP research policy differs')
        d=case('bad_tag',1,1)
        with netCDF4.Dataset(d/'wrfinput_d01','r+') as nc: nc.setncattr('RRTMGP_CAPACITY_POLICY','bad')
        run(d,'1','Malformed RRTMGP research metadata')
        d=case('unsupported_theta',1,1)
        (d/'namelist.input').write_text(setup.set_assignment((d/'namelist.input').read_text(),'use_theta_m','0',group='dynamics'))
        run(d,'1','RRTMGP research policies require')
        d=case('audit_11',1,1); (d/'audit').mkdir()
        runner.environment.update(WRF_RRTMGP_AUDIT_DIR=str(d/'audit'),WRF_RRTMGP_AUDIT_SEEDS='2')
        run(d,'2')
        receipt['audit_passivity_arrays_equal']=compare(b/'cloud_11',d)
        require((d/'audit/same_state.csv').is_file(),'paired diagnostic missing')
        receipt['status']='PASS_SCOPED_INTEGRATED_RESEARCH'; save(); print(json.dumps(receipt,indent=2))
    except BaseException as e: receipt.update(status='FAIL_PRESERVED',error=repr(e)); save(); raise
if __name__=='__main__': main()
