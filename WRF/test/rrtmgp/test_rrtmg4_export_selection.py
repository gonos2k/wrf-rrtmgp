#!/usr/bin/env python3
"""Exercise the actual bounded export module without a WRF or radiation run."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

PREFIX = 'WRF_RRTMGP_RRTMG4_EXPORT_'
DEFAULT = ('1','24','55','2161','129600')
CUSTOM = ('1','13','46','721','43200')
KEYS = ('DOMAIN','I','J','STEP','SECONDS')
DRIVER = '''program probe
 use module_rrtmg4_optics_export
 use, intrinsic :: ieee_arithmetic, only: ieee_value,ieee_quiet_nan
 implicit none
 character(128) :: arg,mode
 integer :: domain,i,j,step,ios,n
 real :: seconds
 real :: x(2)=[1.25,2.5],y(1,2)=reshape([3.,4.],[1,2])
 integer :: z(2)=[7,8]
 do n=1,5
  call get_command_argument(n,arg)
  select case(n)
  case(1);read(arg,*,iostat=ios) domain
  case(2);read(arg,*,iostat=ios) i
  case(3);read(arg,*,iostat=ios) j
  case(4);read(arg,*,iostat=ios) step
  case(5);read(arg,*,iostat=ios) seconds
  end select
  if(ios/=0) stop 2
 end do
 call get_command_argument(6,mode)
 select case(trim(mode))
 case('sw-night');call rrtmg4_export_begin('sw',domain,step,seconds,i,j,solar_cosine=-0.2)
 case('sw-zero');call rrtmg4_export_begin('sw',domain,step,seconds,i,j,solar_cosine=0.)
 case('sw-day');call rrtmg4_export_begin('sw',domain,step,seconds,i,j,solar_cosine=0.6)
 case('sw-missing');call rrtmg4_export_begin('sw',domain,step,seconds,i,j)
 case('sw-nan');call rrtmg4_export_begin('sw',domain,step,seconds,i,j, &
    solar_cosine=ieee_value(0.,ieee_quiet_nan))
 case default;call rrtmg4_export_begin('lw',domain,step,seconds,i,j)
 end select
 if(rrtmg4_export_active()) then
  if(trim(mode)=='nested') call rrtmg4_export_begin('lw',domain,step,seconds,i,j)
  call rrtmg4_export_stage('INPUT')
  call rrtmg4_export_real1('input','K',x)
  call rrtmg4_export_stage('CLOUD')
  call rrtmg4_export_real2('cloud','1',y)
  call rrtmg4_export_stage('GAS')
  call rrtmg4_export_int1('gas',z)
  if(rrtmg4_export_lw_source_active()) call rrtmg4_export_real1('lw-source-probe','1',x)
  if(trim(mode)/='incomplete') then
   call rrtmg4_export_stage('RESULT')
   call rrtmg4_export_real1('result','W_m2',x)
  end if
  call rrtmg4_export_end()
 end if
 if(rrtmg4_export_lw_source_active()) stop 4
 if(any(x/=[1.25,2.5]).or.any(y/=reshape([3.,4.],[1,2])).or.any(z/=[7,8])) stop 3
end program
subroutine wrf_error_fatal(message)
 character(*),intent(in) :: message
 print '(A)',trim(message)
 stop 17
end subroutine
'''

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--fc',default='gfortran')
    ap.add_argument('--work-dir',type=Path,default=Path('build/rrtmg4-export-selector-tests'))
    args=ap.parse_args();args.work_dir.mkdir(parents=True,exist_ok=True)
    compiler=shutil.which(args.fc)
    if compiler is None: raise SystemExit(f'compiler unavailable: {args.fc}')
    source=Path(__file__).resolve().parents[2]/'phys/module_ra_rrtmgp_audit.F'
    module=source.read_text().split('MODULE module_rrtmg4_optics_export\n',1)[1]
    clean_env={k:v for k,v in os.environ.items() if not k.startswith('WRF_RRTMGP_')}
    cases=[]
    with tempfile.TemporaryDirectory(prefix='rrtmg4-export-selector-',dir=args.work_dir.resolve()) as td:
        root=Path(td);(root/'export.F90').write_text('MODULE module_rrtmg4_optics_export\n'+module)
        (root/'probe.f90').write_text(DRIVER)
        exes={}
        for variant,flags in [('serial',[]),('dm',['-DDM_PARALLEL']),('omp',['-fopenmp'])]:
            exe=root/f'probe-{variant}'
            subprocess.run([compiler,'-cpp','-ffree-line-length-none','-fcheck=all',*flags,
                            'export.F90','probe.f90','-o',str(exe)],cwd=root,check=True,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            exes[variant]=exe
        def run(name,call=DEFAULT,selection=None,fail=None,variant='serial',directory=True,extra=None,mode='',collision=False):
            out=root/name;out.mkdir()
            if collision:(out/'rrtmg4_d01_i24_j55_step2161_lw.txt').write_text('preserve existing bytes')
            env={**clean_env,'OMP_NUM_THREADS':'1'}
            if directory:env[PREFIX+'DIR']=str(out)
            if selection is not None:env.update({PREFIX+k:v for k,v in selection.items()})
            if extra:env.update(extra)
            p=subprocess.run([str(exes[variant]),*call,mode],cwd=root,env=env,text=True,
                             stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            files=list(out.iterdir())
            if fail:
                assert p.returncode!=0 and fail in p.stdout,(name,p.returncode,p.stdout)
            else:
                assert p.returncode==0,(name,p.stdout)
            if collision:
                assert len(files)==1
                assert files[0].read_text()=='preserve existing bytes'
            cases.append({'name':name,'returncode':p.returncode,'files':len(files)})
            return out,files
        out,files=run('historical-default')
        assert [f.name for f in files]==['rrtmg4_d01_i24_j55_step2161_lw.txt']
        text=files[0].read_text();assert text.count('\nstage ')==4 and 'source_seconds' in text
        assert '1.2500000000000000E+000' in text
        source_key=PREFIX+'LW_SOURCE'
        _,zero_files=run('lw-source-zero',extra={source_key:'0'})
        assert zero_files[0].read_text()==text
        _,source_files=run('lw-source-one',extra={source_key:'1'})
        assert '\nlw-source-probe 1 2\n' in source_files[0].read_text()
        _,day_files=run('lw-source-sw-no-record',extra={source_key:'1'},mode='sw-day')
        assert 'lw-source-probe' not in day_files[0].read_text()
        assert not run('lw-source-nonselected',call=CUSTOM,extra={source_key:'1'})[1]
        run('lw-source-no-directory',directory=False,extra={source_key:'1'},
            fail='LW_SOURCE_REQUIRES_EXPORT_DIRECTORY')
        for label,value in [('empty',''),('invalid','2'),('nan','NaN'),('trailing','1 0'),('overflow','1'*30)]:
            run('lw-source-'+label,extra={source_key:value},fail='INVALID_LW_SOURCE_FLAG')
        for n in range(5):
            call=list(DEFAULT);call[n]=str(float(call[n])+1) if n==4 else str(int(call[n])+1)
            assert not run(f'nonselected-{KEYS[n]}',call=call)[1]
        chosen=dict(zip(KEYS,CUSTOM));_,files=run('custom-bon',call=CUSTOM,selection=chosen)
        assert [f.name for f in files]==['rrtmg4_d01_i13_j46_step721_lw.txt']
        assert not run('export-disabled',call=CUSTOM,selection={'I':'invalid'},directory=False)[1]
        for key in KEYS:
            values={k:v for k,v in chosen.items() if k!=key}
            run('missing-'+key,call=CUSTOM,selection=values,fail='REQUIRES_ALL_FIVE_KEYS')
        invalid=[('zero','I','0','NONPOSITIVE_INTEGER'),('negative','STEP','-1','INVALID_INTEGER'),
                 ('overflow','STEP','999999999999999999999999','INVALID_INTEGER'),
                 ('trailing-integer','I','13 99','INVALID_INTEGER'),
                 ('empty','SECONDS','','EMPTY_SELECTOR'),('nan','SECONDS','NaN','INVALID_SECONDS'),
                 ('trailing-seconds','SECONDS','43200,1','INVALID_SECONDS'),
                 ('negative-seconds','SECONDS','-1','NEGATIVE_SECONDS'),
                 ('too-long','I','1'*129,'SELECTOR_TOO_LONG'),
                 ('domain-range','DOMAIN','100','DOMAIN_OUT_OF_RANGE')]
        for name,key,value,error in invalid:
            values={**chosen,key:value};run(name,call=CUSTOM,selection=values,fail=error)
        assert not run('sw-night',mode='sw-night')[1]
        assert not run('sw-zero',mode='sw-zero')[1]
        _,files=run('sw-day',mode='sw-day')
        assert [f.name for f in files]==['rrtmg4_d01_i24_j55_step2161_sw.txt']
        run('sw-missing',mode='sw-missing',fail='MISSING_SOLAR_COSINE')
        run('sw-nan',mode='sw-nan',fail='NONFINITE_SOLAR_COSINE')
        run('collision',collision=True,fail='OUTPUT_CREATE_FAILED')
        run('nested',mode='nested',fail='NESTED_BEGIN')
        run('incomplete',mode='incomplete',fail='INCOMPLETE_CAPTURE')
        run('dm',variant='dm',fail='REQUIRES_SERIAL_EXECUTION')
        run('omp',variant='omp',extra={'OMP_NUM_THREADS':'2'},fail='REQUIRES_ONE_OPENMP_THREAD')
    print(json.dumps({'status':'PASS','cases':cases,'case_count':len(cases),'module_compiles':3,
                      'WRF_REAL_radiation_calls':0,'compiler':compiler},indent=2))

if __name__=='__main__':main()
