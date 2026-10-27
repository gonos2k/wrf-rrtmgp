#!/usr/bin/env python3
"""Compile actual LW/SW packing blocks with the real UDM input builder.

This is a source-block regression, not a full WRF or radiation-engine run.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

WRF = Path(__file__).resolve().parents[2]


def fixture(source):
    start = source.index('         DO K=kts,kte\n            QV1D(K)=0.')
    reset = source[start:source.index('         ENDDO', start) + len('         ENDDO')]
    start = source.index('         IF (ICLOUD .ne. 0) THEN', start)
    packing = source[start:source.index('! mji - For MP option 5', start)] + '\nEND IF\n'
    start = source.index('               gp_qh=')
    hail = source[start:source.index('               ! Active sizes', start)]
    cu = re.findall(r'^\s*use_cu_population=\(ICLOUD /= 0\)\s*$', source, re.M)
    if len(cu) != 1:
        raise ValueError('cloud-off CU selection missing or ambiguous')
    return '''program cloud_off
use module_ra_rrtmgp_input
use, intrinsic :: ieee_arithmetic
implicit none
integer, parameter :: kts=1,kte=2
integer :: icloud,k,i,j,mode,pass,reason
logical :: use_cu_population, frozen
real :: qc1d(2),qr1d(2),qi1d(2),qs1d(2),qg1d(2),qv1d(2),cldfra1d(2),qndrop1d(2),gp_qh(2)
real :: grid(2,6),rad(2,6),sizes(2,3),dp(2),r(2),mass(2),lg(2),lh(2)
real :: qc(1,2,1),qr(1,2,1),qi(1,2,1),qs(1,2,1),qg(1,2,1),qh(1,2,1),cf(1,2,1)
real :: qn(1,2,1),nativeqc(1,2,1),nativeqi(1,2,1)
character(256) :: message
i=1;j=1;dp=20.;mass=200.;r=10.
qc=1.e-4;qr=2.e-4;qi=3.e-4;qs=4.e-4;qg=5.e-4;qh=6.e-4;cf=.5;qn=100.
nativeqc=qc;nativeqi=qi
do mode=0,1
 frozen=mode==1
 do pass=1,4
  ! Test poisoned first use, then cloudy-to-clear reuse of the same arrays.
  icloud=mod(pass,2)
  if(pass<=2) qg1d=ieee_value(0.,ieee_quiet_nan)
  call pack(qc,qr,qi,qs,qg,qh,cf,qn,nativeqc,nativeqi,.true.,.true.,.true.,.true.,.true.,.true.)
  if(icloud==0) then
   if(use_cu_population) stop 10
   if(any(qc1d/=0.).or.any(qr1d/=0.).or.any(qi1d/=0.).or.any(qs1d/=0.).or.any(qg1d/=0.).or.any(gp_qh/=0.)) stop 11
  else
   if(.not.use_cu_population) stop 12
   if(any(qg1d/=qg(1,:,1)).or.any(gp_qh/=qh(1,:,1))) stop 13
  endif
  call rrtmgp_build_udm_inputs(dp,cldfra1d,qc1d,qr1d,qi1d,qs1d,qg1d,gp_qh,r,r,r,9.81, &
       grid,rad,sizes,reason,message,allow_clear_condensate=.true.,dry_layer_mass_kg_m2=mass,frozen_uniform=frozen)
  if(.not.frozen.and.icloud/=0) then
   if(reason/=RRTMGP_INPUT_UDM_HAIL_UNSUPPORTED) stop 20
   cycle
  endif
  if(reason/=RRTMGP_INPUT_OK.and.reason/=RRTMGP_INPUT_CLEAR) then
   print *,trim(message)
   stop 14
  endif
  if(.not.all(ieee_is_finite(grid)).or..not.all(ieee_is_finite(rad))) stop 15
  if(icloud==0.and.(any(grid/=0.).or.any(rad/=0.))) stop 16
  if(icloud/=0.and.any(grid<=0.)) stop 17
  if(frozen) then
   call rrtmgp_udm_frozen_lambdas(qg1d,gp_qh,[1.,1.],lg,lh,reason,message)
   if(reason/=RRTMGP_INPUT_OK) stop 18
   if(icloud==0.and.(any(lg/=20000.).or.any(lh/=20000.))) stop 19
  endif
 enddo
enddo
print *, 'CLOUD_ON_OFF_PASS'
contains
subroutine pack(qc3d,qr3d,qi3d,qs3d,qg3d,qh3d,cldfra3d,qndrop3d,native_qc3d,native_qi3d, &
                f_qc,f_qr,f_qi,f_qs,f_qg,f_qndrop)
real,optional :: qc3d(:,:,:),qr3d(:,:,:),qi3d(:,:,:),qs3d(:,:,:),qg3d(:,:,:),qh3d(:,:,:)
real,optional :: cldfra3d(:,:,:),qndrop3d(:,:,:),native_qc3d(:,:,:),native_qi3d(:,:,:)
logical,optional :: f_qc,f_qr,f_qi,f_qs,f_qg,f_qndrop
logical :: run_rrtmgp=.true.,warm_rain=.false.,predicate
real :: t1d(2)=280.
''' + cu[0] + '\n' + reset + '\n' + packing + '\n' + hail + '''
end subroutine
end program
subroutine wrf_error_fatal3(file,line,message)
character(*) :: file,message
integer :: line
print *,trim(message)
stop 2
end subroutine
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', default='gfortran')
    args = parser.parse_args()
    output = WRF.parent / 'build'
    output.mkdir(exist_ok=True)
    for phase in ('lw', 'sw'):
        source = (WRF / f'phys/module_ra_rrtmg_{phase}.F').read_text()
        original = fixture(source)
        mutations = {
            'current': original,
            'missing_qg_reset': original.replace('            QG1D(K)=0.', ''),
            'cu_always_on': original.replace('use_cu_population=(ICLOUD /= 0)', 'use_cu_population=.TRUE.'),
            'unguarded_hail': original.replace('IF(ICLOUD /= 0) gp_qh=', 'gp_qh='),
        }
        for optimization in ('-O0', '-O2'):
            for case, body in mutations.items():
                with tempfile.TemporaryDirectory(prefix='cloud-off-', dir=output) as tmp:
                    path = Path(tmp)
                    (path / 'fixture.f90').write_text(body)
                    subprocess.run([args.compiler, optimization, '-ffree-form', '-ffree-line-length-none', '-fcheck=all',
                                    '-x', 'f95-cpp-input', str(WRF / 'phys/module_ra_rrtmgp_input.F'),
                                    str(path / 'fixture.f90'), '-o', str(path / 'test')], cwd=path, check=True,
                                   text=True)
                    result = subprocess.run([str(path / 'test')], capture_output=True, text=True)
                    if (result.returncode == 0) != (case == 'current'):
                        raise AssertionError((phase, optimization, case, result.stdout, result.stderr))
                    if case == 'current' and 'CLOUD_ON_OFF_PASS' not in result.stdout:
                        raise AssertionError('missing terminal success')
                print(phase, optimization, case, 'PASS' if case == 'current' else 'REJECTED')


if __name__ == '__main__':
    main()
