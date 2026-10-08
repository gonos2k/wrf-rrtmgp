#!/usr/bin/env python3
"""Execute unchanged full UDM in dry manufactured cells around native CCN bounds.

This is an engineering/process-policy observation, not number-unit authority,
PSD accuracy, forecast validation, or a proposed change to production bounds.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import sys

sys.dont_write_bytecode = True


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    raw = path.read_bytes()
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest(),
            'bytes': len(raw)}


def replace_once(text, old, new):
    require(text.count(old) == 1, 'fixture/source anchor changed: ' + repr(old))
    return text.replace(old, new)


def snapshot(raw):
    text = raw.decode()
    marker = '! BOUNDS_LEDGER_BEGIN\n'
    end = '! BOUNDS_LEDGER_END\n'
    def block(body):
        return marker + body + end
    text = replace_once(text, '  module module_mp_udm\n',
                        '  module module_mp_udm\n' + block('   use udm_test_observer, only: capture\n'))
    anchor = '! initialize the surface rain, snow, graupel and etc....\n'
    entry = ('   do k=kts,ktop\n'
             '     do i=its,ite\n'
             '       call capture("ENTRY",i,k,0,[ncr1(i,k,1),ncr(k,i,1),ccnmin,ccnmax,den(k,i)])\n'
             '     enddo\n'
             '   enddo\n')
    text = replace_once(text, anchor, block(entry) + anchor)
    anchor = '       ncr1(i,k,1) = ncr(k,i,1)\n'
    exit_row = ('       call capture("EXIT",i,k,0,[ncr1(i,k,1),ncr(k,i,1),ccnmin,ccnmax,den(k,i),real(loops)])\n')
    text = replace_once(text, anchor, block(exit_row) + anchor)
    stripped = re.sub(r'! BOUNDS_LEDGER_BEGIN\n.*?! BOUNDS_LEDGER_END\n', '', text, flags=re.S)
    require(stripped.encode() == raw, 'observer removal does not restore production bytes')
    return text.encode()


def fixture_bytes(original):
    text = original.decode()
    text = replace_once(text, '  use ieee_arithmetic, only: ieee_is_finite\n',
                        '  use ieee_arithmetic, only: ieee_is_finite,ieee_next_after\n')
    text = replace_once(text, '  real::density,target_alpha,rh,sv,qsat\n',
                        '  real::density,target_alpha,rh,sv,qsat\n  real::raw_values(10)\n')
    text = replace_once(text, '  do a=1,2\n',
        '  raw_values=[0.,1.e7,ieee_next_after(5.e7,0.),5.e7,ieee_next_after(5.e7,huge(1.)), &\n'
        '       1.e8,ieee_next_after(2.e10,0.),2.e10,ieee_next_after(2.e10,huge(1.)),3.e10]\n'
        '  do a=1,2\n')
    text = replace_once(text, '    do b=1,2\n      target_alpha=.35\n      if(b==2) target_alpha=.65\n      case_id=2*(a-1)+b\n',
                        '    do b=1,10\n      target_alpha=0.\n      case_id=10*(a-1)+b\n')
    text = replace_once(text, '      rh=1.+.0048*exp(log(target_alpha)/.6)\n', '      rh=.8\n')
    text = replace_once(text, '      qc=1.e-4; qi=0.; qr=0.; qs=0.; qg=0.; qh=0.\n',
                        '      qc=0.; qi=0.; qr=0.; qs=0.; qg=0.; qh=0.\n')
    text = replace_once(text, '      nn=2.e8; nc=5.e7; nr=0.\n', '      nn=raw_values(b); nc=0.; nr=0.\n')
    text = replace_once(text, 'den=den,pii=pii,p=p,delz=delz,delt=1.,',
                        'den=den,pii=pii,p=p,delz=delz,delt=360.,')
    return text.encode()


def parse(text):
    inputs, returns, observations, tags = {}, {}, {}, {}
    lines = iter(text.splitlines())
    for line in lines:
        w = line.split()
        if not w or w[0] not in ('INPUT', 'RETURN', 'OBS', 'TAGS'):
            continue
        if w[0] == 'TAGS':
            require(int(w[1]) not in tags, 'duplicate tag')
            tags[int(w[1])] = w[2:]
            continue
        words = next(lines).split()
        require(len(words) == int(w[-1]), 'state length mismatch')
        require(all(re.fullmatch('[0-9A-F]{8}', x) for x in words), 'bad REAL32 word')
        values = [struct.unpack('!f', bytes.fromhex(x))[0] for x in words]
        require(all(map(math.isfinite, values)), 'nonfinite record')
        if w[0] == 'INPUT':
            key = (int(w[1]), int(w[2])); target = inputs; item = words
        elif w[0] == 'RETURN':
            key = int(w[1]); target = returns; item = words
        else:
            require(w[1] in ('ENTRY', 'EXIT'), 'unexpected observer stage')
            key = (w[1], *map(int, w[2:6])); target = observations; item = values
        require(key not in target, 'duplicate record')
        target[key] = item
    require(set(inputs) == {(c,k) for c in range(1,21) for k in range(1,5)}, 'input roster mismatch')
    require(set(returns) == set(tags) == set(range(1,21)), 'output roster mismatch')
    return {'inputs': inputs, 'returns': returns, 'observations': observations, 'tags': tags}


def verify(data):
    obs = data['observations']
    expected = ({('ENTRY',c,1,k,0) for c in range(1,21) for k in range(1,4)} |
                {('EXIT',c,1,k,0) for c in range(1,21) for k in range(1,5)})
    require(set(obs) == expected,
            'active stage/case/layer roster differs')
    rows = []
    for case in range(1,21):
        for layer in range(1,4):
            before, after = obs[('ENTRY',case,1,layer,0)], obs[('EXIT',case,1,layer,0)]
            raw, clipped, lo, hi, rho = before
            require(lo == 5.e7 and hi == 2.e10, 'native CCN constants changed')
            expected = min(max(raw,lo),hi)
            require(clipped == expected, 'native entry projection differs')
            require(after[:5] == before and after[5] == 2., 'dry export or two subcycles differ')
            inp = struct.unpack('!f', bytes.fromhex(data['inputs'][(case,layer)][0]))[0]
            ret = struct.unpack('!f', bytes.fromhex(data['returns'][case][32+layer-1]))[0]
            require(inp == raw and ret == clipped, 'outer input/return does not join native work state')
            label = 'below' if raw < lo else 'at_lower' if raw == lo else 'above' if raw > hi else 'at_upper' if raw == hi else 'inside'
            rows.append({'case':case,'layer':layer,'density_raw':rho,'raw_NN':raw,
                         'entry_NN':clipped,'exit_NN':ret,'raw_limit_delta':clipped-raw,
                         'position':label,'subcycles':2})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('wrf_root',type=Path)
    ap.add_argument('--workdir',type=Path,required=True)
    args = ap.parse_args()
    wrf = args.wrf_root.resolve(strict=True)
    work = args.workdir.resolve(); work.mkdir(parents=True,exist_ok=False)
    helper = wrf/'test/rrtmgp/test_netcdf_zz.py'
    spec = importlib.util.spec_from_file_location('bounds_runner',helper)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    compiler = Path(shutil.which('gfortran')).resolve(strict=True)
    runner = module.Runner(work,120,{**os.environ,'LC_ALL':'C','OMP_NUM_THREADS':'1'},40)
    source = wrf/'phys/module_mp_udm.F'
    template = wrf/'test/rrtmgp/test_udm_partial_activation.f90'
    dependencies = [wrf/'phys/module_gfs_machine.F',wrf/'phys/module_mp_radar.F']
    original_pins = [digest(p) for p in [source,template,helper,*dependencies]]
    record = {'schema':'UDM37_NATIVE_CCN_BOUNDS_OBSERVATION_V1','status':'PREPARED',
              'source_pins':original_pins,'production_accepted':False,
              'source_changes':False,'units_authority':False,'full_WRF_runs':0,'RTE_runs':0,'LBLRTM_runs':0}
    def save():
        record['processes']=runner.commands
        module.write_json(work/'receipt.json',record)
    save()
    try:
        runner.run([compiler,'--version'],work,'compiler_version')
        native=work/'native_udm.F';native.write_bytes(source.read_bytes())
        observed=work/'observed_udm.F';observed.write_bytes(snapshot(source.read_bytes()))
        fixture=work/'bounds_fixture.f90';fixture.write_bytes(fixture_bytes(template.read_bytes()))
        results={}
        for opt in ('-O0','-O2'):
            directory=work/opt[1:];directory.mkdir()
            flags=[opt,'-g','-ffree-form','-ffree-line-length-none','-fcheck=all',
                   '-finit-real=snan','-ffpe-trap=invalid,zero,overflow','-J',str(directory),'-I',str(directory)]
            stub=directory/'module_wrf_error.f90'
            stub.write_text('module module_wrf_error\ncontains\nsubroutine wrf_debug(level,text)\n'
                            'integer,intent(in)::level\ncharacter(*),intent(in)::text\nend subroutine\nend module\n')
            objects=[]
            for path,extra in [(dependencies[0],['-ffixed-form']),(stub,[]),(dependencies[1],[]),(fixture,['-cpp','-DOBSERVER_ONLY'])]:
                obj=directory/(path.stem+'.o')
                runner.run([compiler,*flags,*extra,'-c',path,'-o',obj],directory,'compile');objects.append(obj)
            variants={};exe_pins=[]
            for name,path in [('native',native),('observed',observed)]:
                obj=directory/(name+'.o')
                runner.run([compiler,*flags,'-c',path,'-o',obj],directory,'compile')
                exe=directory/name
                runner.run([compiler,*flags,'-cpp',fixture,*objects,obj,'-o',exe],directory,'link')
                before=digest(exe)
                for mode in (['off'] if name=='native' else ['off','on']):
                    output=runner.run([exe,mode],directory,'actual_udm_bounds_fixture')
                    variants[name+'-'+mode]=parse(output.read_text())
                require(digest(exe)==before,'executable changed');exe_pins.append(before)
            baseline=variants['native-off']
            for name,data in variants.items():
                require(data['inputs']==baseline['inputs'] and data['returns']==baseline['returns'] and
                        data['tags']==baseline['tags'],'observer changed inputs/returns: '+name)
            require(not variants['observed-off']['observations'],'OFF produced observer rows')
            rows=verify(variants['observed-on'])
            results[opt[1:]]={'rows':rows,'native_OFF_ON_returns_bitwise_equal':True,
                              'active_cell_rows':len(rows),'exe_pins':exe_pins}
        require([digest(p) for p in [source,template,helper,*dependencies]]==original_pins,'source changed')
        record.update(status='PASS_SCOPED_NATIVE_ENTRY_BOUNDS_AND_DRY_EXPORT',results=results,
             observer_source=digest(observed),fixture_source=digest(fixture),
             counts={'manufactured_configurations':20,'fixture_processes':6,'actual_outer_udm_calls':120,
                     'compiler_link_processes':sum(x['kind'] in ('compile','link') for x in runner.commands)},
             limits=['Direct UDM manufactured dry cells, not actual host initialization/transport.',
                     'Current flgzero=true; false branch reviewed in source, not executed.',
                     'Two subcycles; inactive condensate/activation transfer in this fixture.',
                     'Entry covers three active mass layers; export also records the fourth storage level, outside the active-cell bound comparison.',
                     'No general final-return range invariant follows from this dry path.',
                     'Raw density/number effects do not establish unit/population or physical correctness.'])
        save(); print(json.dumps({'status':record['status'],'receipt':digest(work/'receipt.json'),'counts':record['counts']}))
        return 0
    except BaseException as error:
        record.update(status='FAIL_PRESERVED_STOPPED',error=type(error).__name__+': '+str(error));save()
        print(json.dumps({'status':record['status'],'error':record['error'],'receipt':str(work/'receipt.json')}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
