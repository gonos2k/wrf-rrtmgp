#!/usr/bin/env python3
"""Observe full current UDM in manufactured partial-CF/activation cells.

Compiles pristine and a reversible observer-only snapshot, not a WRF host.
No number-unit, population, PSD, radiation or physical acceptance is inferred.
"""
from __future__ import annotations

import argparse
import copy
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
HELPER = Path(__file__).with_name('test_netcdf_zz.py')
spec = importlib.util.spec_from_file_location('durable_test_runner', HELPER)
runner_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner_module)
pin, write_json, Runner = runner_module.pin, runner_module.write_json, runner_module.Runner

STATE = ('nn', 'nc', 'nr', 'qv', 'qc', 'qi', 'qr', 'qs', 'qg', 'qh', 't', 'p', 'rho', 'cf')
RATE = ('alpha', 'ncact', 'pcact', 'dt', 'rdt', 'ccnmin', 'ncmin', 'ncmax',
        'qmin', 'pi', 'denr', 'actr', 'cpm', 'xlv', 'satmax', 'actk', 'rh')
STAGES = ('ADJUST_IN', 'ADJUST_OUT', 'CF_IN', 'CF_DIV', 'CF_RESTORE_IN', 'CF_RESTORED',
          'ACT_PRE', 'ACT_RATE', 'ACT_POST', 'HELPER_IN', 'HELPER_OUT')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def real32(x):
    return struct.unpack('!f', struct.pack('!f', x))[0]


def add(a, b):
    return real32(a + b)


def mul(a, b):
    return real32(a * b)


def div(a, b):
    return real32(a / b)


def observer_snapshot(original):
    """Insert only calls/imports; stripping marked blocks restores all bytes."""
    text = original.decode('utf-8')
    inserted = []

    def insert(anchor, block, before=False):
        nonlocal text
        require(text.count(anchor) == 1, f'ambiguous observer anchor: {anchor!r}')
        wrapped = '! UDM_PARTIAL_TEST_BEGIN\n' + block + '! UDM_PARTIAL_TEST_END\n'
        inserted.append({'anchor': anchor, 'before': before})
        text = text.replace(anchor, wrapped + anchor if before else anchor + wrapped)

    insert('  module module_mp_udm\n', '   use udm_test_observer, only: capture\n')
    state = '[ncr(k,i,1),ncr(k,i,2),ncr(k,i,3),q(k,i),qci(k,i,1),qci(k,i,2),' \
            'qrs(k,i,1),qrs(k,i,2),qrs(k,i,3),qrs(k,i,4),t(k,i),p(k,i),den(k,i),cldf(k)]'

    def rows(tag):
        return f'   do k=kts,ktop\n     call capture("{tag}",i,k,loop,{state})\n   enddo\n'

    insert('   call adjust_number_concent(ktopqr,kdim,qrs(:,i,1),ncr(:,i,3),den(:,i),      &\n', rows('ADJUST_IN'), True)
    insert('        pidnc,one_1,qcmin,ncmin,ncmax,di15,  dcmin, dcmax)\n', rows('ADJUST_OUT'))
    insert('   if (present(udm_cf_top)) udm_cf_top(i)=ktop\n', rows('CF_IN'))
    insert('! update the slope parameters for microphysics computation\n', rows('CF_DIV'))
    # Restore happens before activation; preserve and label that stage explicitly.
    restore = '     qci(k,i,1) = qci(k,i,1) * cldf(k)\n'
    insert(restore, f'     call capture("CF_RESTORE_IN",i,k,loop,{state})\n', True)
    insert('     qrs(k,i,4) = qrs(k,i,4) * cldf(k)\n',
           f'     call capture("CF_RESTORED",i,k,loop,{state})\n')
    insert('     if(rh_mul(k)>1.) then\n', f'     call capture("ACT_PRE",i,k,loop,{state})\n', True)
    extra = 'temp,ncact(k),pcact(k),dtcld,rdtcld,ccnmin,ncmin,ncmax,qmin,pi,denr,actr,cpm(k,i),xlv(k,i),satmax,actk,rh_mul(k)'
    insert('                     (3.*den(k,i)),max(q(k,i),0.)*rdtcld)\n',
           f'       call capture("ACT_RATE",i,k,loop,{state[:-1]},{extra}])\n')
    insert('       t(k,i) = t(k,i) + pcact(k)*xlv(k,i)/cpm(k,i)*dtcld\n',
           f'       call capture("ACT_POST",i,k,loop,{state})\n')
    helper = '[nc1d(k),qc1d(k),den1d(k),t1d(k),qi1d(k),qs1d(k)]'
    insert('            call udm_mp_effective_radius(t1d,qc1d,qi1d,qs1d,den1d,qmin, t0c    &\n',
           '            do k=kts,kte\n' + f'              call capture("HELPER_IN",i,k,0,{helper})\n' + '            enddo\n', True)
    insert('                               ,re_qc, re_qi, re_qs, kts, kte, i, j)\n',
           '            do k=kts,kte\n' + f'              call capture("HELPER_OUT",i,k,0,{helper[:-1]},re_qc(k),re_qi(k),re_qs(k)])\n' + '            enddo\n')
    stripped = re.sub(r'! UDM_PARTIAL_TEST_BEGIN\n.*?! UDM_PARTIAL_TEST_END\n', '', text, flags=re.S)
    require(stripped.encode('utf-8') == original, 'observer cannot be stripped exactly')
    return text.encode('utf-8'), inserted


def parse(text):
    lines = text.splitlines()
    observations, inputs, outputs, tags = {}, {}, {}, {}
    cursor = 0
    while cursor < len(lines):
        words = lines[cursor].split()
        cursor += 1
        if not words or words[0] not in ('OBS', 'INPUT', 'RETURN', 'TAGS'):
            continue  # Native setup information is not an observation record.
        if words[0] == 'TAGS':
            require(len(words) == 4, 'invalid tags')
            require(int(words[1]) not in tags, 'duplicate tags')
            tags[int(words[1])] = list(map(int, words[2:]))
            continue
        require(cursor < len(lines), 'truncated hexadecimal record')
        values = lines[cursor].split()
        cursor += 1
        require(len(values) == int(words[-1]), 'wrong state-vector size')
        require(all(re.fullmatch(r'[0-9A-F]{8}', w) for w in values), 'malformed REAL32 words')
        decoded = [struct.unpack('!f', bytes.fromhex(w))[0] for w in values]
        require(all(map(math.isfinite, decoded)), 'nonfinite observation')
        if words[0] == 'OBS':
            require(len(words) == 7 and words[1] in STAGES, 'unexpected observation stage')
            key = (words[1], *map(int, words[2:6]))
            require(key not in observations, 'duplicate stage identity')
            observations[key] = decoded
        elif words[0] == 'INPUT':
            require(len(words) == 4 and len(values) == 15, 'invalid input record')
            key = tuple(map(int, words[1:3]))
            require(key not in inputs, 'duplicate input')
            inputs[key] = decoded
        else:
            require(len(words) == 3 and len(values) == 73, 'invalid return record')
            key = int(words[1])
            require(key not in outputs, 'duplicate return')
            outputs[key] = values
    require(set(inputs) == {(c,k) for c in range(1,5) for k in range(1,5)}, 'input roster mismatch')
    require(set(outputs) == set(tags) == set(range(1,5)), 'return roster mismatch')
    return {'observations': observations, 'inputs': inputs, 'outputs': outputs, 'tags': tags}


def check(data):
    obs, rows = data['observations'], []
    # Outer UDM diagnoses all four radii; udm2d uses ktopini=kte-1.
    expected = {(s,c,1,k,0 if s.startswith('HELPER') else 1)
                for s in STAGES for c in range(1,5)
                for k in range(1,5 if s.startswith('HELPER') else 4)}
    require(set(obs) == expected, 'exact observer case/stage/layer/subcycle roster differs')
    for c in range(1,5):
        require(data['tags'][c] == [2,3], 'unexpected CF epoch/top')
        for k in range(1,4):
            def get(s):
                values = obs[(s,c,1,k,0 if s.startswith('HELPER') else 1)]
                names = ('nc','qc','rho','t','qi','qs') if s == 'HELPER_IN' else \
                        ('nc','qc','rho','t','qi','qs','rec','rei','res') if s == 'HELPER_OUT' else \
                        STATE + RATE if s == 'ACT_RATE' else STATE
                require(len(values) == len(names), f'wrong {s} vector')
                return dict(zip(names,values))
            inp = dict(zip(STATE[:13]+('rh','target_alpha'), data['inputs'][(c,k)]))
            eos = mul(mul(inp['rho'], inp['t']), add(287., mul(461.6, inp['qv'])))
            require(eos == inp['p'], 'fixture EOS differs from actual native-kind inputs')
            adjust_in, adjust_out = get('ADJUST_IN'), get('ADJUST_OUT')
            require(adjust_in == adjust_out, 'pre-CF number adjustment/cap/floor active')
            before, divided = get('CF_IN'), get('CF_DIV')
            restore_in, restored = get('CF_RESTORE_IN'), get('CF_RESTORED')
            require(0. < before['cf'] < 1., 'not a partial preceding CF closure')
            for mass in ('qc','qi','qr','qs','qg','qh'):
                require(divided[mass] == div(before[mass], before['cf']), f'{mass} division mismatch')
                require(restored[mass] == mul(restore_in[mass], restore_in['cf']), f'{mass} restoration mismatch')
            for number in ('nn','nc','nr'):
                require(before[number] == divided[number] and restore_in[number] == restored[number],
                        'raw number changed in immediate CF transform')
            pre, rate, post = get('ACT_PRE'), get('ACT_RATE'), get('ACT_POST')
            require(before['cf'] == restored['cf'] == pre['cf'], 'preceding closure CF identity differs')
            require(pre == {n:rate[n] for n in STATE}, 'activation rate mutated entry state')
            require(0. < rate['alpha'] < 1. and rate['ncact'] > 0., 'not positive partial activation')
            ratio = div(add(rate['rh'],-1.),rate['satmax'])
            alpha = real32(math.exp(mul(real32(math.log(ratio)),rate['actk'])))
            require(abs(alpha-rate['alpha']) <= 8.*2.**-23*alpha, 'RH-to-activation fraction mismatch')
            require(abs(rate['alpha']-inp['target_alpha']) < 1.e-3, 'target partial-activation arm changed')
            total = add(pre['nn'],pre['nc'])
            rawrate = mul(max(0., add(mul(total,rate['alpha']),-pre['nc'])),rate['rdt'])
            require(rawrate < mul(pre['nn'],rate['rdt']), 'NN-rate cap active')
            require(rawrate == rate['ncact'], 'source-ordered activation rate differs')
            numerator = mul(mul(mul(mul(4.,rate['pi']),rate['denr']),
                            real32(math.exp(mul(real32(math.log(rate['actr'])),3.)))),rate['ncact'])
            # libm exp/log rounding belongs to the compiled rate. Validate the
            # recorded mass rate against the independently reconstructed value
            # with a declared REAL32 bound, not a bitwise portable libm claim.
            expected_pc = div(numerator,mul(3.,pre['rho']))
            require(abs(expected_pc-rate['pcact']) <= 8.*2.**-23*expected_pc, 'activation mass rate mismatch')
            require(rate['pcact'] < mul(pre['qv'],rate['rdt']), 'water cap active')
            increment = mul(rate['ncact'],rate['dt'])
            a_after = add(pre['nn'],-increment)
            c_after = add(pre['nc'],increment)
            require(a_after > rate['ccnmin'] and rate['ncmin'] < c_after < rate['ncmax'], 'number floor/cap active')
            require(post['nn'] == a_after and post['nc'] == c_after, 'activation NN/NC transfer differs')
            require(post['qv'] == add(pre['qv'],-mul(rate['pcact'],rate['dt'])) and
                    post['qc'] == add(pre['qc'],mul(rate['pcact'],rate['dt'])), 'activation mass transfer differs')
            expected_t = add(pre['t'],mul(div(mul(rate['pcact'],rate['xlv']),rate['cpm']),rate['dt']))
            require(post['t'] == expected_t, 'activation temperature update differs')
            require(all(post[n] == pre[n] for n in ('nr','qi','qr','qs','qg','qh','p','rho','cf')),
                    'activation changed an unassigned state field')
            residual = (post['nn']+post['nc'])-(pre['nn']+pre['nc'])
            require(abs(residual) <= 4.*2.**-23*total, 'isolated activation number budget differs')
            helper_in, helper_out = get('HELPER_IN'), get('HELPER_OUT')
            require(helper_in == {n:helper_out[n] for n in helper_in}, 'radius helper changed inputs')
            require(2.51e-6 <= helper_out['rec'] <= 50.e-6, 'radius bounds')
            returned = [struct.unpack('!f',bytes.fromhex(w))[0] for w in data['outputs'][c]]
            for name,offset in (('t',0),('qc',8),('qi',12),('qs',20),('nc',36),('rec',57),('rei',61),('res',65)):
                require(helper_out[name] == returned[offset+k-1], 'helper-to-outer-return join differs')
            rows.append({'case':c,'k':k,'rho_d':pre['rho'],'preceding_closure_cf':pre['cf'],
                         'actual_alpha':rate['alpha'],'nn_before':pre['nn'],'nc_before':pre['nc'],
                         'nn_after':post['nn'],'nc_after':post['nc'],'number_budget_residual':residual,
                         'number_and_water_caps_floors_inactive':True,'helper':helper_out})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('wrf_root',type=Path)
    ap.add_argument('--workdir',type=Path,required=True)
    ap.add_argument('--compiler',default='gfortran')
    args = ap.parse_args()
    wrf = args.wrf_root.resolve(strict=True)
    work = args.workdir.resolve()
    work.mkdir(parents=True,exist_ok=False)
    compiler = Path(shutil.which(args.compiler) or args.compiler).resolve(strict=True)
    paths = [wrf/'phys'/n for n in ('module_mp_udm.F','module_mp_radar.F','module_gfs_machine.F')]
    fixture = Path(__file__).with_suffix('.f90').resolve()
    sources = paths+[Path(__file__).resolve(),fixture,HELPER.resolve()]
    source_pins = [pin(p) for p in sources]
    runner = Runner(work,120,{**os.environ,'LC_ALL':'C','OMP_NUM_THREADS':'1'},40)
    report = {'schema':'UDM37_PARTIAL_ACTIVATION_OBSERVATION_V1','status':'PREPARED',
              'source_pins_before':source_pins,'compiler':pin(compiler),
              'full_WRF_builds':0,'WRF_host_runs':0,'RTE_runs':0,'scientific_acceptance':False,
              'remaining_physical_gates':7}
    result = work/'receipt.json'
    write_json(result,report)
    try:
        original = paths[0].read_bytes()
        observed, anchors = observer_snapshot(original)
        report['observer_anchors'] = anchors
        native = work/'native_udm.F'
        instrumented = work/'observed_udm.F'
        native.write_bytes(original)
        instrumented.write_bytes(observed)
        report['snapshots'] = [pin(native),pin(instrumented)]
        write_json(work/'plan.json',report)
        version = runner.run([compiler,'--version'],work,'compiler_version')
        report['compiler_version'] = {'text':version.read_text(),'stdout':pin(version)}
        executable_pins = []
        results = {}
        for opt in ('-O0','-O2'):
            directory = work/opt[1:]
            directory.mkdir()
            flags = [opt,'-g','-ffree-form','-ffree-line-length-none','-fcheck=all',
                     '-finit-real=snan','-ffpe-trap=invalid,zero,overflow','-J',str(directory),'-I',str(directory)]
            stub = directory/'module_wrf_error.f90'
            stub.write_text('module module_wrf_error\ncontains\nsubroutine wrf_debug(level,text)\n'
                            'integer,intent(in)::level\ncharacter(*),intent(in)::text\nend subroutine\nend module\n')
            objects = []
            for source,extra in ((paths[2],['-ffixed-form']),(stub,[]),(paths[1],[]),
                                 (fixture,['-cpp','-DOBSERVER_ONLY'])):
                obj = directory/(source.stem+'.o')
                runner.run([compiler,*flags,*extra,'-c',source,'-o',obj],directory,'compile')
                objects.append(obj)
            variants = {}
            for name,snapshot in (('native',native),('observed',instrumented)):
                obj = directory/(name+'.o')
                runner.run([compiler,*flags,'-c',snapshot,'-o',obj],directory,'compile')
                exe = directory/name
                runner.run([compiler,*flags,'-cpp',fixture,*objects,obj,'-o',exe],directory,'link')
                exe_before = pin(exe)
                for enabled in (['off'] if name=='native' else ['off','on']):
                    path = runner.run([exe,enabled],directory,'actual_udm_fixture')
                    variants[name+'-'+enabled] = parse(path.read_text())
                exe_after = pin(exe)
                require(exe_before == exe_after, 'fixture executable changed during execution')
                executable_pins.append({'before':exe_before,'after':exe_after})
            baseline = variants['native-off']
            for variant in variants.values():
                require(variant['inputs']==baseline['inputs'] and variant['outputs']==baseline['outputs'] and
                        variant['tags']==baseline['tags'], 'observer changed input/returned state')
            require(not variants['observed-off']['observations'], 'OFF produced observations')
            rows = check(variants['observed-on'])
            negatives = {}
            for label,field,value in (('forced-floor','ccnmin',3.e8),('nonpartial-alpha','alpha',1.),
                                      ('missing-stage',None,None),('temperature-update','post_t',286.)):
                altered = copy.deepcopy(variants['observed-on'])
                if field == 'post_t':
                    altered['observations'][('ACT_POST',1,1,1,1)][STATE.index('t')] = value
                elif field:
                    altered['observations'][('ACT_RATE',1,1,1,1)][len(STATE)+RATE.index(field)] = value
                else:
                    del altered['observations'][('CF_RESTORED',1,1,1,1)]
                try:
                    check(altered)
                except ValueError as error:
                    negatives[label] = str(error)
                else:
                    raise ValueError(f'negative control accepted: {label}')
            results[opt[1:]] = {'rows':rows,'pristine_OFF_ON_returns_bitwise_equal':True,
                               'negative_controls_rejected':negatives,'stage_records':len(variants['observed-on']['observations'])}
        require([pin(p) for p in sources] == source_pins, 'original sources changed')
        report.update(status='PASS_SCOPED_ACTUAL_UDM_PARTIAL_ACTIVATION',results=results,
                      source_pins_after=source_pins,processes=runner.commands,
                      executable_pins_before_and_after=executable_pins,
                      counts={'compiler_or_link_processes':sum(r['kind'] in ('compile','link') for r in runner.commands),
                              'fixture_processes':6,'compiler_version_queries':1,
                              'actual_outer_udm_calls':24,'observed_active_cells':24},
                      limits=['Direct outer UDM fixture, not producer/storage/transport/WRF integration.',
                              'CF is the preceding closure value. Its temporary mass transform is restored before activation.',
                              'Density arms use EOS-consistent p/qv, matched T and target RH, and unchanged raw number inputs.',
                              'No mass-versus-volume number unit or PSD/LUT equivalence is approved.'])
        write_json(result,report)
        print(json.dumps({'status':report['status'],'receipt':pin(result),'counts':report['counts']}))
        return 0
    except BaseException as error:
        message = f'{type(error).__name__}: {error}'
        report.update(status='FAIL_PRESERVED_STOPPED',error=message,processes=runner.commands)
        write_json(result,report)
        print(json.dumps({'status':report['status'],'error':message,'receipt':str(result)}))
        return 1


if __name__=='__main__':
    sys.exit(main())
