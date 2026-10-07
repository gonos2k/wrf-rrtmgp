#!/usr/bin/env python3
"""Actual cloud-radius kernels with conditional number definitions, not WRF.

Full modules are compiled. Reversible test bridges initialize only the private
Thompson cloud-kernel flag/exponent, bypassing thompson_init and all tables.
Production helpers and UDM27-only gate remain unchanged. No unit authority or
PSD/LUT compatibility is inferred from these comparisons.
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

sys.dont_write_bytecode=True
HELPER=Path(__file__).with_name('test_netcdf_zz.py')
spec=importlib.util.spec_from_file_location('radius_durable_runner',HELPER)
runner_module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner_module)
pin,write_json,Runner=runner_module.pin,runner_module.write_json,runner_module.Runner

def require(condition,message):
    if not condition:
        raise ValueError(message)

def r32(value):
    return struct.unpack('!f',struct.pack('!f',value))[0]

def snapshot(original,scheme,observed):
    text=original.decode('utf-8')
    def insert(anchor,body,before=False):
        nonlocal text
        require(text.count(anchor)==1,'ambiguous test anchor: '+anchor)
        block='! RADIUS_TEST_BEGIN\n'+body+'! RADIUS_TEST_END\n'
        text=text.replace(anchor,block+anchor if before else anchor+block)
    if scheme=='thompson':
        require('      obmr = 1./bm_r\n' in text and
                '      is_aerosol_aware = .FALSE.\n' in text and
                '      if (PRESENT(nwfa2d) .AND. PRESENT(nwfa) .AND. PRESENT(nifa)) is_aerosol_aware = .TRUE.\n' in text,
                'native Thompson cloud initialization changed')
        insert('END MODULE module_mp_thompson',
               'subroutine radius_test_setup(aerosol,constants)\n'
               'logical,intent(in)::aerosol\nreal,intent(out)::constants(7)\n'
               'is_aerosol_aware=aerosol\nobmr=1./bm_r\n'
               'constants=[am_r,bm_r,obmr,Nt_c,Nt_c_max,2.51e-6,50.e-6]\nend subroutine\n',True)
        if observed:
            insert('      MODULE module_mp_thompson\n','use radius_test_observer, only: radius_capture\n')
            insert('         re_qc1d(k) = MAX(2.51E-6, MIN(SNGL(0.5D0 * DBLE(3.+inu_c)/lamc), 50.E-6))\n',
                   '         call radius_capture("THOMPSON",[rho(k),rc(k),nc(k),real(inu_c),real(lamc),re_qc1d(k)])\n')
    else:
        insert('end module module_mp_udm',
               'subroutine radius_test_constants(constants)\nreal,intent(out)::constants(7)\n'
               'constants=[pidnc,3.,1./3.,0.,0.,recmin,recmax]\nend subroutine\n',True)
        if observed:
            insert('  module module_mp_udm\n','use radius_test_observer, only: radius_capture\n')
            insert('       re_qc(k) = max(recmin,min(0.5*(1./lamc),recmax))\n',
                   '       call radius_capture("UDM",[rho(k),rqc(k),rnc(k),nc(k),real(lamc),re_qc(k)])\n')
    stripped=re.sub(r'! RADIUS_TEST_BEGIN\n.*?! RADIUS_TEST_END\n','',text,flags=re.S)
    require(stripped.encode('utf-8')==original,'test hooks cannot be stripped exactly')
    return text.encode('utf-8')

def parse(text):
    cases,observations={},{}
    lines=iter(text.splitlines())
    for line in lines:
        words=line.split()
        if not words or words[0] not in ('CASE','OBS'):
            continue
        require(len(words)==4,'invalid record header')
        values=next(lines).split()
        require(len(values)==int(words[-1]) and all(re.fullmatch('[0-9A-F]{8}',v) for v in values),'invalid REAL32 record')
        numbers=[struct.unpack('!f',bytes.fromhex(v))[0] for v in values]
        require(all(map(math.isfinite,numbers)),'nonfinite record')
        if words[0]=='CASE':
            require(len(values)==19,'case width differs')
            key=int(words[1]); require(key not in cases,'duplicate case')
            cases[key]={'mode':int(words[2]),'bits':values,'values':numbers}
        else:
            require(len(values)==6,'observation width differs')
            key=int(words[2]); require(key not in observations,'duplicate observation')
            observations[key]={'scheme':words[1],'values':numbers}
    require(set(cases)==set(range(1,13)),'case roster differs')
    return {'cases':cases,'observations':observations}

def check(data):
    require(set(data['observations'])==set(range(1,13)),'observation roster differs')
    rows=[]
    for c in range(1,13):
        case=data['cases'][c]; v=case['values']; mode=case['mode']
        expected_mode=8 if c in (1,2,11) else 28 if c in (3,4,5,6,12) else 27
        require(mode==expected_mode,'kernel mode differs')
        t,p,qv,qc,raw,qi,ni,qs,rho=v[:9]
        mass,bm,exponent,nt,maximum,lower,upper=v[9:16]
        rec,rei,res=v[16:]
        base=1 if c==11 else 3 if c==12 else c
        target=r32(.7 if base%2 else 1.1)
        require(t==285. and qv==r32(.008) and qc==r32(1.e-4),'manufactured thermodynamic inputs differ')
        require(math.isclose(rho,target,rel_tol=3e-7) and
                math.isclose(p,rho*287.04*t*(qv+.622)/.622,rel_tol=3e-7),'density/EOS differs')
        expected_raw=r32(rho*5.e7) if base>=9 else 3.e8 if base in (5,6) else 5.e7
        require(raw==expected_raw,'conditional number input arm differs')
        require(qi==ni==qs==0. and qc>0. and raw>0. and lower<rec<upper,'non-cloud branch or radius clamp')
        require(bm==3. and exponent==r32(1./3.),'wrong kernel exponent')
        require(math.isclose(mass,math.pi*1000./6.,rel_tol=2e-7),'mass coefficient differs')
        obs=data['observations'][c]
        require(obs['scheme']==('UDM' if mode==27 else 'THOMPSON'),'observer scheme differs')
        x=obs['values']
        require(x[0]==rho and x[1]==r32(qc*rho) and x[5]==rec,'helper/fixture state join differs')
        if mode in (8,28):
            require(nt==1.e8 and maximum==r32(1999.e6) and
                    lower==r32(2.51e-6) and upper==r32(50.e-6),'Thompson kernel constants differ')
            require(rei==r32(4.99e-6) and res==r32(9.99e-6),'inactive Thompson phases differ')
            nv=nt if mode==8 else r32(raw*rho)
            require(2.<nv<maximum and x[2]==nv,'number transform or cap differs')
            # All selected values avoid NINT half-way ties. An independent
            # gamma-moment ratio replaces the source lookup table.
            mu=min(15,int(r32(1.e9/nv)+.5)+2)
            require(x[3]==mu,'gamma shape differs')
            ratio=(mu+1)*(mu+2)*(mu+3)
            base=r32(r32(r32(nv*mass)*ratio)/x[1])
            slope=base**exponent
            expected=.5*(mu+3)/slope
            ideal=((qc*rho)/(nv*(math.pi*1000./6.)*ratio))**(1./3.)*(mu+3)/2.
        else:
            require(rei==res==-99.,'inactive UDM output was changed')
            nv=raw; mu=None
            require(x[2]==r32(raw*rho) and x[3]==raw,'UDM raw/guard number differs')
            base=r32(r32(mass*raw)/x[1]); slope=base**exponent
            expected=.5/slope
            ideal=.5*((qc*rho)/(math.pi*1000./6.*raw))**(1./3.)
        require(math.isclose(x[4],slope,rel_tol=2e-6),'native slope differs')
        require(math.isclose(rec,expected,rel_tol=2e-6),'bounded source-association radius differs')
        require(math.isclose(rec,ideal,rel_tol=3e-6),'independent moment algebra differs')
        rows.append({'case':c,'mode_label':{8:'fixed-volume Thompson kernel',28:'aerosol-aware Thompson kernel',27:'UDM kernel'}[mode],
                     'rho_d':rho,'raw_input_number':raw,'slope_number':nv,'gamma_shape':mu,
                     'radius_um':rec*1e6,'independent_algebra_um':ideal*1e6,'clamps_inactive':True})
    get=lambda c:data['cases'][c]['values'][16]
    density_ratio=data['cases'][8]['values'][8]/data['cases'][7]['values'][8]
    require(math.isclose(get(3),get(4),rel_tol=3e-6),'Thompson fixed-mass number cancellation differs')
    require(math.isclose(get(9),get(10),rel_tol=3e-6),'conditional UDM volume-number cancellation differs')
    require(math.isclose(get(8)/get(7),density_ratio**(1./3.),rel_tol=3e-6),'UDM fixed-raw density response differs')
    require(math.isclose(get(2)/get(1),density_ratio**(1./3.),rel_tol=3e-6),'Thompson fixed-volume density response differs')
    require(data['cases'][1]['bits']==data['cases'][11]['bits'] and
            data['cases'][3]['bits']==data['cases'][12]['bits'],'kernel mode state leaked')
    return rows

STUBS='''module module_wrf_error
character(1024)::wrf_err_message
contains
subroutine wrf_debug(level,text)
integer,intent(in)::level
character(*),intent(in)::text
end subroutine
end module
module module_timing
end module
module module_domain
end module
module module_dm
end module
'''

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('wrf_root',type=Path); ap.add_argument('--workdir',type=Path,required=True)
    ap.add_argument('--compiler',default='gfortran'); args=ap.parse_args()
    wrf=args.wrf_root.resolve(strict=True); work=args.workdir.resolve(); work.mkdir(parents=True,exist_ok=False)
    compiler=Path(shutil.which(args.compiler) or args.compiler).resolve(strict=True)
    fixture=Path(__file__).with_suffix('.f90').resolve()
    paths=[wrf/'phys/module_mp_udm.F',wrf/'phys/module_mp_thompson.F',wrf/'phys/module_mp_radar.F',
           wrf/'phys/module_gfs_machine.F',wrf/'share/module_model_constants.F',fixture,Path(__file__).resolve(),HELPER.resolve()]
    before=[pin(p) for p in paths]
    report={'schema':'UDM_THOMPSON_CLOUD_KERNEL_V1','status':'PREPARED','source_pins_before':before,
            'compiler':pin(compiler),'scientific_acceptance':False,'remaining_physical_gates':7,
            'full_WRF_builds':0,'WRF_host_runs':0,'RTE_runs':0,'thompson_init_calls':0}
    result=work/'receipt.json'; write_json(result,report)
    runner=Runner(work,120,{**os.environ,'LC_ALL':'C','OMP_NUM_THREADS':'1'},40)
    try:
        snapshots={}
        for scheme,source in zip(('udm','thompson'),paths[:2]):
            original=source.read_bytes()
            for variant,observed in (('bridge',False),('observed',True)):
                dest=work/f'{scheme}-{variant}.F'; dest.write_bytes(snapshot(original,scheme,observed))
                snapshots[(scheme,variant)]=dest
        version=runner.run([compiler,'--version'],work,'compiler_version')
        report['compiler_version']=version.read_text(); report['snapshot_pins']=[pin(p) for p in snapshots.values()]
        results={}; executable_pins=[]
        for opt in ('-O0','-O2'):
            directory=work/opt[1:]; directory.mkdir()
            flags=[opt,'-g','-cpp','-ffree-form','-ffree-line-length-none','-fcheck=all',
                   '-finit-real=snan','-ffpe-trap=invalid,zero,overflow','-ffunction-sections','-fdata-sections',
                   '-J',str(directory),'-I',str(directory)]
            stub=directory/'stubs.f90'; stub.write_text(STUBS)
            objects=[]
            for source,extra in ((paths[3],['-ffixed-form']),(stub,[]),(paths[2],[]),(paths[4],[]),(fixture,['-DOBSERVER_ONLY'])):
                obj=directory/(source.stem+'.o'); runner.run([compiler,*flags,*extra,'-c',source,'-o',obj],directory,'compile'); objects.append(obj)
            variants={}
            for variant in ('bridge','observed'):
                pair=[]
                for scheme in ('udm','thompson'):
                    obj=directory/f'{scheme}-{variant}.o'
                    runner.run([compiler,*flags,'-c',snapshots[(scheme,variant)],'-o',obj],directory,'compile'); pair.append(obj)
                exe=directory/variant
                runner.run([compiler,*flags,fixture,*objects,*pair,'-Wl,--gc-sections','-o',exe],directory,'link')
                exe_pin=pin(exe)
                for mode in (('off',) if variant=='bridge' else ('off','on')):
                    stdout=runner.run([exe,mode],directory,'actual_radius_fixture'); variants[variant+'-'+mode]=parse(stdout.read_text())
                require(pin(exe)==exe_pin,'executable mutated'); executable_pins.append(exe_pin)
            baseline=variants['bridge-off']['cases']
            require(all(v['cases']==baseline for v in variants.values()),'observer changed kernel returns')
            require(not variants['bridge-off']['observations'] and not variants['observed-off']['observations'],'OFF observations')
            rows=check(variants['observed-on']); negatives={}
            for label in ('wrong-number','missing-observation','wrong-shape','clamped-radius','wrong-input-arm'):
                changed=copy.deepcopy(variants['observed-on'])
                if label=='wrong-number': changed['observations'][3]['values'][2]*=1.1
                elif label=='missing-observation': del changed['observations'][3]
                elif label=='wrong-shape': changed['observations'][3]['values'][3]=2.
                elif label=='clamped-radius': changed['cases'][3]['values'][16]=changed['cases'][3]['values'][15]
                else: changed['cases'][9]['values'][4]=5.e7
                try: check(changed)
                except ValueError as error: negatives[label]=str(error)
                else: raise ValueError('negative control accepted: '+label)
            results[opt[1:]]={'rows':rows,'bridge_OFF_ON_returns_bitwise_equal':True,'negative_controls_rejected':negatives}
        require([pin(p) for p in paths]==before,'original sources changed')
        report.update(status='PASS_SCOPED_ACTUAL_CLOUD_RADIUS_KERNELS',source_pins_after=before,results=results,
                      processes=runner.commands,executable_pins=executable_pins,
                      counts={'compiler_or_link_processes':sum(p['kind'] in ('compile','link') for p in runner.commands),
                              'fixture_processes':sum(p['kind']=='actual_radius_fixture' for p in runner.commands),
                              'compiler_version_queries':1,
                              'actual_helper_calls':72,'observed_cloud_cells':24},
                      limits=['Private Thompson cloud state is initialized by a test bridge, not thompson_init or WRF.',
                              'Only liquid kernels. No ice/snow optics, CF, activation, producer/storage/transport or forecast.',
                              'Conditional raw volume-number arm is an input hypothesis, not an approved UDM conversion.',
                              'Gamma-moment algebra checks Thompson liquid convention; UDM PSD/LUT equivalence remains open.',
                              'Python binary64 pow/division with REAL32 operands is tolerance-bounded, not exact native-kind/ULP replay.',
                              'Thompson mass-number cancellation requires the same gamma shape; high-number arms explicitly change shape.',
                              'Mode labels describe kernel state, not enabled mp_physics=8/28 with production37.'])
        write_json(result,report); print(json.dumps({'status':report['status'],'receipt':pin(result),'counts':report['counts']})); return 0
    except BaseException as error:
        report.update(status='FAIL_PRESERVED_STOPPED',error=f'{type(error).__name__}: {error}',processes=runner.commands)
        write_json(result,report); print(json.dumps({'status':report['status'],'error':report['error'],'receipt':str(result)})); return 1

if __name__=='__main__':
    sys.exit(main())
