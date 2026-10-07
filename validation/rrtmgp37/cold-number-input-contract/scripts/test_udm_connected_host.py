#!/usr/bin/env python3
"""Run an already-built, reversibly observed full WRF SCM host trajectory.

Manufactured ideal input, serial REAL32, one periodic domain, 10-second dt.
No unit/population conversion, physical approval, or lateral-boundary claim.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct

import netCDF4
import numpy as np

from test_netcdf_zz import Runner, write_json, pin
from test_udm_startup_snow_scm import prepare_case, make_namelist, set_assignment


def parse(path):
    events = {}
    for line in path.read_text(errors='replace').splitlines():
        if not line.startswith('HOST_JOIN_V1 '):
            continue
        tokens = line.split()
        if len(tokens) != 14:
            raise ValueError(f'malformed observer row: {line[:120]}')
        key = (tokens[1], *map(int, tokens[2:6]))
        if key in events:
            raise ValueError(f'duplicate event identity: {key}')
        bits = tuple(int(x, 16) for x in tokens[6:])
        vals = tuple(struct.unpack('!f', struct.pack('!I', x))[0] for x in bits)
        if not np.isfinite(vals).all():
            raise ValueError(f'nonfinite {key}')
        events[key] = (bits, vals)
    if not events:
        raise ValueError('no actual full-host observer rows')
    return events


def verify_join(events, restart=False):
    counts = collections.Counter(k[0] for k in events)
    required = {'START_PRE','START_POST','RK_PRE','RK_POST','UDM_ENTRY','UDM_RETURN','HELPER_IN','HELPER_OUT'}
    if not required <= counts.keys():
        raise ValueError(f'missing actual stages: {required-counts.keys()}')
    pre = {k[4]: v for k,v in events.items() if k[0]=='START_PRE'}
    post = {k[4]: v for k,v in events.items() if k[0]=='START_POST'}
    if pre.keys()!=post.keys():
        raise ValueError('startup level roster mismatch')
    if set(pre) != set(range(1,60)):
        raise ValueError('expected actual 59-layer input roster')
    steps=sorted({k[1] for k in events if k[0]=='UDM_ENTRY'})
    if steps != list(range(7,13) if restart else range(1,7)):
        raise ValueError(f'expected six consecutive actual model steps: {steps}')
    slot_nn,slot_nc=map(int,next(iter(pre.values()))[1][6:8])
    if slot_nn==slot_nc or slot_nn<=0 or slot_nc<=0:
        raise ValueError('invalid actual Registry QNN/QNC slot mapping')
    levels=range(1,60)
    expected={(stage,steps[0]-1,0,0,k) for stage in ('START_PRE','START_POST') for k in levels}
    expected|={(stage,step,rk,slot,k) for stage in ('RK_PRE','RK_POST') for step in steps
               for rk in (1,2,3) for slot in (slot_nn,slot_nc) for k in levels}
    expected|={(stage,step,0,0,k) for stage in ('UDM_ENTRY','UDM_RETURN','HELPER_IN','HELPER_OUT')
               for step in steps for k in levels}
    if not restart:
        expected|={(stage,1,0,0,k) for stage in ('RESET_PRE','RESET_POST') for k in levels}
    if events.keys()!=expected:
        raise ValueError(f'exact event roster mismatch missing={len(expected-events.keys())} extra={len(events.keys()-expected)}')
    for step in steps:
        for k in levels:
            before=events.get(('RESET_PRE',step,0,0,k),events[('UDM_ENTRY',step,0,0,k)])
            for field,slot in ((0,slot_nn),(1,slot_nc)):
                if events[('RK_POST',step,3,slot,k)][0][0]!=before[0][field]:
                    raise ValueError('final actual RK update does not join actual UDM consumer')
                initial=post[k] if step==steps[0] else events[('UDM_RETURN',step-1,0,0,k)]
                if events[('RK_PRE',step,1,slot,k)][0][0]!=initial[0][field]:
                    raise ValueError('actual returned/input number does not join next transport step')
    if any(pre[k][0][:3]!=post[k][0][:3] for k in pre) and restart:
        raise ValueError('restart start_em changed supplied numbers')
    residuals = []
    nonzero_tendencies = 0
    rk_stages = set()
    for key, (bits, vals) in events.items():
        stage, step, rk, slot, level = key
        if stage == 'RK_PRE':
            other = events.get(('RK_POST',step,rk,slot,level))
            if other is None:
                raise ValueError('missing actual RK update pair')
            if rk<3:
                following=events[('RK_PRE',step,rk+1,slot,level)]
                if other[0][:2]!=following[0][:2]:
                    raise ValueError('actual inter-RK scalar/old-buffer join mismatch')
            value, old, adv, source, pold, pnew, dt, mapy = map(np.float32,vals)
            base = value if rk==1 else old
            # Same source order; roundoff bound allows compiler contraction,
            # not a physical acceptance tolerance or archived-output fit.
            expected = np.float32(np.float32(np.float32(pold*base) + np.float32(dt*np.float32(np.float32(adv*mapy)+source)))/pnew)
            got = np.float32(other[1][0])
            rel = abs(float(got)-float(expected))/max(abs(float(expected)),1.)
            if rel > 8*np.finfo(np.float32).eps:
                raise ValueError(f'actual RK identity mismatch {key}: {got}, {expected}, {rel}')
            residuals.append(rel)
            nonzero_tendencies += int(adv != 0)
            rk_stages.add(rk)
        elif stage=='UDM_ENTRY':
            reset = events.get(('RESET_POST',step,0,0,level))
            if reset is not None and bits[:3]!=reset[0][:3]:
                raise ValueError('reset post and actual UDM entry do not join')
        elif stage=='HELPER_IN':
            out = events.get(('HELPER_OUT',step,0,0,level))
            ret = events.get(('UDM_RETURN',step,0,0,level))
            if out is None or ret is None:
                raise ValueError('missing actual helper/UDM return join')
            if bits[:5]+bits[6:] != out[0][:5]+out[0][6:]:
                raise ValueError('radius helper changed input tuple')
            # Same NN/NC/NR/QC/density, then native radius and temperature.
            if out[0][:7] != ret[0][:7]:
                raise ValueError('helper output does not join actual driver return')
    if rk_stages != {1,2,3} or not residuals:
        raise ValueError(f'full RK stages absent: {rk_stages}')
    if not nonzero_tendencies:
        raise ValueError('connected transport requires a nonzero actual advection tendency')
    if restart and ('RESET_PRE' in counts or 'RESET_POST' in counts):
        raise ValueError('unexpected first-step constant reset on restart')
    return {'stage_rows':dict(counts), 'actual_RK_stages':sorted(rk_stages),
            'RK_update_pairs':len(residuals), 'nonzero_advection_tendency_rows':nonzero_tendencies,
            'max_RK_relative_residual':max(residuals),
            'exact_stage_step_slot_layer_roster':True,
            'actual_Registry_number_slots':{'QNN':slot_nn,'QNC':slot_nc},
            'input_return_transport_consumer_join_bitwise':True,
            'inter_RK_scalar_old_buffer_join_bitwise':True,
            'same_cell_helper_to_driver_return_bitwise':True,
            'restart_without_first_step_reset':restart}


def verify_input_numbers(events, input_path, *, empty_qnn=False, restart=False):
    """Join all three REAL32 file numbers and immediate initialization pairs.

    This is a raw-bit contract, not a number-unit or population definition.
    Transport lies between START_POST and RESET_PRE: do not compare that pair.
    """
    levels = range(1, 60)
    start_step = 6 if restart else 0
    names = ('QNCCN', 'QNCLOUD', 'QNRAIN')
    with netCDF4.Dataset(input_path) as ds:
        ds.set_auto_mask(False)
        supplied = []
        for name in names:
            variable = ds.variables[name]
            values = np.asarray(variable[0, :, 0, 0])
            if variable.dtype.kind != 'f' or variable.dtype.itemsize != 4 or values.shape != (59,):
                raise ValueError(f'{name}: expected REAL32 59-layer file input')
            if not np.isfinite(values).all():
                raise ValueError(f'{name}: nonfinite file input')
            supplied.append(np.ascontiguousarray(values, dtype=np.float32).view(np.uint32))
    constant = struct.unpack('!I', struct.pack('!f', 1.e8))[0]
    for level in levels:
        before = events[('START_PRE', start_step, 0, 0, level)][0]
        after = events[('START_POST', start_step, 0, 0, level)][0]
        for idx, name in enumerate(names):
            if before[idx] != int(supplied[idx][level-1]):
                raise ValueError(f'{name}: file does not join START_PRE at layer {level}')
        if before[1:3] != after[1:3]:
            raise ValueError(f'QNC/QNR changed across start_em initialization at layer {level}')
        expected_nn = constant if empty_qnn and not restart else before[0]
        if after[0] != expected_nn:
            raise ValueError('start_em QNN guard behavior mismatch')
        if not restart:
            reset_pre = events[('RESET_PRE', 1, 0, 0, level)][0]
            reset_post = events[('RESET_POST', 1, 0, 0, level)][0]
            if reset_pre[1:3] != reset_post[1:3]:
                raise ValueError(f'QNC/QNR changed across first driver QNN reset at layer {level}')
            if reset_post[0] != constant:
                raise ValueError('actual first driver constant QNN reset not observed')
    return {'input_to_start_em_exact': True, 'input_number_variables': list(names),
            'input_number_layers': 59, 'input_number_comparison': 'REAL32_BITS',
            'start_em_QNC_QNR_preserved_bitwise': True,
            'first_driver_QNC_QNR_preserved_bitwise': not restart,
            'first_driver_constant_reset_observed': not restart,
            'start_em_supplied_nonuniform_preserved': not empty_qnn,
            'empty_QNN_initialized': empty_qnn and not restart}


def verify_input_negative_controls(events, input_path, work):
    """Reject file-only and immediate-pair mutations without extra model runs."""
    work.mkdir(parents=True, exist_ok=False)
    original = pin(input_path)
    verify_join(events)
    verify_input_numbers(events, input_path)
    rejected = {}
    def reject(label, changed_events, changed_file, message):
        try:
            verify_input_numbers(changed_events, changed_file)
        except ValueError as error:
            if message not in str(error):
                raise ValueError(f'{label}: rejected at unexpected boundary: {error}') from error
            rejected[label] = str(error)
        else:
            raise ValueError(f'{label}: mutated evidence was accepted')
    for name in ('QNCCN', 'QNCLOUD', 'QNRAIN'):
        changed_file = work / (name + '.nc')
        shutil.copy2(input_path, changed_file)
        with netCDF4.Dataset(changed_file, 'r+') as ds:
            variable = ds.variables[name]
            old = np.float32(variable[0, 9, 0, 0])
            variable[0, 9, 0, 0] = np.nextafter(old, np.float32(np.inf))
        # Original downstream observations are unchanged and still join.
        verify_join(events)
        reject('file_only_' + name, events, changed_file, name + ': file does not join START_PRE')
    for stage, step, message in (
            ('START_POST', 0, 'changed across start_em'),
            ('RESET_POST', 1, 'changed across first driver')):
        for idx, name in ((1, 'QNCLOUD'), (2, 'QNRAIN')):
            changed = dict(events)
            key = (stage, step, 0, 0, 10)
            bits, values = changed[key]
            new_values = list(values)
            new_values[idx] = float(np.nextafter(np.float32(values[idx]), np.float32(np.inf)))
            new_bits = list(bits)
            new_bits[idx] = struct.unpack('!I', struct.pack('!f', new_values[idx]))[0]
            changed[key] = (tuple(new_bits), tuple(new_values))
            reject(stage + '_' + name, changed, input_path, message)
    if pin(input_path) != original:
        raise ValueError('negative controls changed the original model input')
    return {'status': 'PASS', 'rejected_count': len(rejected), 'rejections': rejected,
            'original_downstream_join_passes': True, 'original_input_unchanged': True,
            'additional_model_runs': 0}


def history(path):
    with netCDF4.Dataset(path) as ds:
        ds.set_auto_mask(False)
        return {n:np.asarray(v[:]).copy() for n,v in ds.variables.items()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wrf-source',type=Path,required=True)
    p.add_argument('--binary-dir',type=Path,required=True)
    p.add_argument('--workdir',type=Path,required=True)
    a = p.parse_args()
    root, binaries, work = a.wrf_source.resolve(), a.binary_dir.resolve(), a.workdir.resolve()
    work.mkdir(parents=True,exist_ok=False)
    env = os.environ.copy()
    for name in list(env):
        if name.startswith(('WRF_RRTMGP_','WRF_UDM_HOST_','OMP_','GOMP_','KMP_')):
            del env[name]
    run = Runner(work,300,env,10)
    result = {'status':'STARTING','scope':'full WRF serial REAL32 periodic SCM connected host trace',
              'physical_units_approved':False,'production_accepted':False,
              'actual_lateral_boundary':'NOT_RUN: periodic x/y manufactured SCM',
              'executables':{n:pin(binaries/n) for n in ('ideal','wrf')},'arms':{}}
    write_json(work/'receipt.json',result)
    def namelist(seconds=60,restart=False):
        text=make_namelist(root,37,37)
        for key,value,group in [('run_minutes',str(1 if restart else seconds//60),'time_control'),
                               ('restart_interval','1','time_control'),
                               ('end_minute',str(seconds//60),'time_control'),
                               ('restart','.true.' if restart else '.false.','time_control'),
                               ('scalar_adv_opt','0','dynamics'),('ccn_conc','100000000.','physics')]:
            text=set_assignment(text,key,value,group=group)
        if restart:
            text=set_assignment(text,'start_minute','1',group='time_control')
        return text
    def launch(case,on,kind):
        run.environment=dict(env,WRF_UDM_HOST_TRACE='1' if on else '0')
        log=run.run([str(binaries/'ideal' if kind=='ideal' else binaries/'wrf')],case,kind)
        if ('SUCCESS COMPLETE IDEAL INIT' if kind=='ideal' else 'SUCCESS COMPLETE WRF') not in log.read_text(errors='replace'):
            raise ValueError('model success marker absent')
        return log
    try:
        seed=work/'seed'
        prepare_case(root,seed,namelist())
        launch(seed,False,'ideal')
        original=seed/'wrfinput_d01'
        with netCDF4.Dataset(original,'r') as ds:
            ds.set_auto_mask(False)
            if not {'QNCCN','QNCLOUD','QNRAIN'} <= ds.variables.keys():
                raise ValueError('ideal producer missing actual number slots')
        for arm,on,empty in [('nonuniform-off',False,False),('nonuniform-on',True,False),('empty-qnn-on',True,True),
                             ('warm-cloud-off',False,False),('warm-cloud-on',True,False)]:
            case=work/arm
            prepare_case(root,case,namelist())
            shutil.copy2(original,case/'wrfinput_d01')
            with netCDF4.Dataset(case/'wrfinput_d01','r+') as ds:
                ds.set_auto_mask(False)
                number=np.asarray(ds.variables['QNCCN'][:])
                t,k,j,i=np.indices(number.shape)
                number[:]=0. if empty else 1.e8+1.e6*k+3.e6*i+5.e6*j
                ds.variables['QNCCN'][:]=number
                ds.variables['QNCLOUD'][:]=5.e7+1.e5*k+1.e6*i+1.e6*j
                # Retain ideal thermodynamics and winds; this trace is not a
                # manufactured activation or native-radius accuracy experiment.
                # Positive raw sentinel detects unintended zeroing; no PSD/units claim.
                ds.variables['QNRAIN'][:]=1.e4+100.*k+300.*i+500.*j
                if arm.startswith('warm-cloud'):
                    pressure=np.asarray(ds.variables['P'][:])+np.asarray(ds.variables['PB'][:])
                    temperature=(np.asarray(ds.variables['T'][:])+300.)*(pressure/100000.)**(287./1004.)
                    warm=temperature>275.
                    es=610.78*np.exp(17.2693882*(temperature-273.15)/(temperature-35.86))
                    qsat=(287./461.6)*es/(pressure-es)
                    qv=np.asarray(ds.variables['QVAPOR'][:]).copy()
                    qc=np.asarray(ds.variables['QCLOUD'][:]).copy()
                    qv[warm]=1.002*qsat[warm]
                    qc[warm]=2.e-4
                    ds.variables['QVAPOR'][:]=qv
                    ds.variables['QCLOUD'][:]=qc
            input_pin=pin(case/'wrfinput_d01')
            log=launch(case,on,'forecast-'+arm)
            files=sorted(case.glob('wrfout_d01*'))
            if len(files)!=1:
                raise ValueError('one initial/60s history expected')
            result['arms'][arm]={'input':input_pin,'namelist':pin(case/'namelist.input'),
                                'log':pin(log),'history':pin(files[0])}
            if on:
                events=parse(log)
                check=verify_join(events)
                check.update(verify_input_numbers(events, case/'wrfinput_d01', empty_qnn=empty))
                if arm == 'nonuniform-on':
                    result['input_contract_negative_controls'] = verify_input_negative_controls(
                        events, case/'wrfinput_d01', work/'input-negative-controls')
                positive=[row for key,row in events.items() if key[0]=='HELPER_IN' and row[1][1]>0 and row[1][3]>0]
                check['positive_QNC_QC_helper_rows']=len(positive)
                if arm.startswith('warm-cloud') and not positive:
                    raise ValueError('warm-cloud arm did not reach positive actual number/mass helper input')
                result['arms'][arm]['joined_checks']=check
                write_json(work/(arm+'-joined.json'),check)
            write_json(work/'receipt.json',result)
        result['observer_passivity']={}
        for population in ('nonuniform','warm-cloud'):
            off,on=(result['arms'][n] for n in (population+'-off',population+'-on'))
            if off['input']['sha256']!=on['input']['sha256']:
                raise ValueError('OFF/ON inputs differ')
            arrays=[history(Path(r['history']['path'])) for r in (off,on)]
            if arrays[0].keys()!=arrays[1].keys() or any(arrays[0][n].tobytes()!=arrays[1][n].tobytes() for n in arrays[0]):
                raise ValueError('observer OFF/ON history arrays differ')
            if off['history']['sha256']!=on['history']['sha256']:
                raise ValueError('observer OFF/ON complete history bytes differ')
            result['observer_passivity'][population]={'history_arrays_bitwise':len(arrays[0]),
                                      'history_file_bytes_equal':off['history']['sha256']==on['history']['sha256']}
        restart_case=work/'restart-on'
        prepare_case(root,restart_case,namelist(120,True))
        checkpoints=sorted((work/'warm-cloud-on').glob('wrfrst_d01*'))
        if len(checkpoints)!=1:
            raise ValueError('one actual 60s checkpoint expected')
        shutil.copy2(checkpoints[0],restart_case/checkpoints[0].name)
        checkpoint_pin=pin(restart_case/checkpoints[0].name)
        with netCDF4.Dataset(restart_case/checkpoints[0].name) as ds:
            if any(np.unique(np.asarray(ds.variables[n][:])).size<=1 for n in ('QNCCN','QNCLOUD')):
                raise ValueError('restart must contain actual nonuniform QNN and QNC')
        log=launch(restart_case,True,'restart')
        events=parse(log)
        check=verify_join(events,restart=True)
        check.update(verify_input_numbers(events, restart_case/checkpoints[0].name, restart=True))
        result['arms']['restart-on']={'input':checkpoint_pin,'log':pin(log),'joined_checks':check,
                                      'namelist':pin(restart_case/'namelist.input')}
        result.update(status='PASS',limitations=['No real.exe or external-analysis ingestion',
            'No actual specified lateral boundary', 'No approved number units or population',
            'Positive-cloud native radius linkage observed; physical radius accuracy not tested',
            'No continuous/restart forecast endpoint equivalence claim'])
    except BaseException as error:
        result.update(status='FAIL',error=repr(error))
        raise
    finally:
        result['commands']=run.commands
        write_json(work/'receipt.json',result)


if __name__=='__main__':
    main()
