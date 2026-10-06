#!/usr/bin/env python3
"""Portable numerical tests; no solar/material downloads and no WRF run."""
from __future__ import annotations
import argparse
import ctypes
import json
import math
from pathlib import Path
import subprocess
import time

import numpy as np

import generate as gen


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error('Use a new directory to preserve evidence')
    args.output_dir.mkdir(parents=True)
    started = time.monotonic()
    sources = {str(p.relative_to(gen.ROOT)): gen.sha(p)
               for p in (Path(__file__).resolve(), gen.HERE/'generate.py', gen.HERE/'mie_dynamic_api.f90', gen.HERE/'SOURCE.json')}
    library, kernel_sources = gen.build_kernel(args.output_dir.resolve()/'kernel')
    sources.update(kernel_sources)
    lib = ctypes.CDLL(str(library))
    lib.mie_checked.argtypes = [ctypes.c_double]*3 + [ctypes.c_int] + \
        [ctypes.POINTER(ctypes.c_double)]*3 + [ctypes.POINTER(ctypes.c_int)]*2

    def call(n, k, x, limit=4_000_000, evaluator=None):
        ext, sca, asym = (ctypes.c_double() for _ in range(3))
        needed, status = ctypes.c_int(), ctypes.c_int()
        (lib.mie_checked if evaluator is None else evaluator)(n,k,x,limit,ctypes.byref(ext),ctypes.byref(sca),ctypes.byref(asym),
                                                             ctypes.byref(needed),ctypes.byref(status))
        return dict(qext=ext.value,qsca=sca.value,g=asym.value,needed=needed.value,status=status.value)

    # Du (2004), Table 1: published values are rounded. SOCRATES uses positive
    # imaginary index for absorption; that paper writes the conjugate convention.
    benchmark = []
    for name,n,k,x,qe,qs in [('i',1.5,1.,100.,2.09750,1.28370),
                           ('k',10.,10.,1.,2.53299,2.04941),
                           ('g',1.5,1.,.055,.101491,1.13169e-5)]:
        got = call(n,k,x)
        require(got['status']==0 and abs(got['qext']-qe)<5e-6 and abs(got['qsca']-qs)<5e-6,
                f'Published Mie benchmark {name}: {got}')
        benchmark.append(dict(case=name,arguments=[n,k,x],reference_qext=qe,reference_qsca=qs,
                              tolerance=5e-6,result=got))
    large = []
    for n,k,x in [(1.31,1e-8,300_000.),(1.31,1e-8,500_000.),(1.31,.001,1_000_000.)]:
        refused, got = call(n,k,x,400_000), call(n,k,x)
        require(refused['status']==3 and got['status']==0 and got['needed']>400_000,
                f'Recurrence workspace contract: {refused}, {got}')
        require(all(math.isfinite(got[v]) for v in ('qext','qsca','g')) and
                0<=got['qsca']<=got['qext']+1e-11 and -1<=got['g']<=1,
                f'Large-particle physical bounds: {got}')
        large.append(dict(arguments=[n,k,x],refused=refused,result=got))
    invalid = []
    for field in range(3):
        for value in (float('nan'),float('inf'),-float('inf')):
            values = [1.31,.001,10.]; values[field]=value
            got = call(*values)
            require(got['status']==1 and got['needed']==0, f'Nonfinite input accepted: {values}')
            invalid.append(dict(arguments=list(map(str,values)),status=got['status']))
    for values in [(0.,.001,10.,100),(-1.,.001,10.,100),(1.31,-.001,10.,100),
                   (1.31,.001,0.,100),(1.31,.001,10.,0)]:
        got=call(*values); require(got['status']==1 and got['needed']==0,'Invalid range accepted')
        invalid.append(dict(arguments=list(values),status=got['status']))
    for values in [(1.31,1e300,1e300),(1.31,.001,2e9)]:
        require(call(*values)['status']==2,'Integer/workspace overflow not rejected')

    # Actual GL32/SW12 near-transparent node exposed default COMPLEX rounding.
    # Demonstrate the failure with exact pinned bytes, then test the explicit
    # RealK constructors. Efficiencies are never projected to physical bounds.
    original_dir=args.output_dir.resolve()/'original-kernel'; original_dir.mkdir()
    original_lib=original_dir/'libmie_original.so'
    original_files=[gen.HERE/'socrates'/n for n in
                    ('realtype_rd.f90','def_std_io_icf.f90','error_pcf.f90','mie_scatter.f')]
    original_files.append(gen.HERE/'mie_dynamic_api.f90')
    subprocess.run(['gfortran','-O3','-fPIC','-shared','-ffree-line-length-none',
                    '-J',str(original_dir),'-I',str(original_dir),*map(str,original_files),'-o',str(original_lib)],check=True)
    old=ctypes.CDLL(str(original_lib)); old.mie_checked.argtypes=lib.mie_checked.argtypes
    arguments=(1.3162090691501627,6.647598667764746e-11,15.82866539592279)
    unadapted=call(*arguments,evaluator=old.mie_checked); adapted=call(*arguments)
    require(unadapted['qsca']>unadapted['qext']+1e-9,'Expected unadapted rounding counterfactual not reproduced')
    require(adapted['status']==0 and adapted['qext']>adapted['qsca'],'RealK weak-absorption regression')
    conservative=call(arguments[0],0.,arguments[2])
    require(abs(conservative['qext']-conservative['qsca'])<1e-14,'Nonabsorbing efficiency closure')

    # An analytic constant-Q sphere checks PSD normalization independently of Mie.
    # Qext=2,Qsca=1,g=.5 -> kappa*rho=lambda*[1,.5,.25,.5].
    class ConstantKernel:
        def mie_checked(self,n,k,x,limit,e,s,g,needed,status):
            e._obj.value=2.; s._obj.value=1.; g._obj.value=.5
            needed._obj.value=1; status._obj.value=0
    gen._KERNEL=ConstantKernel(); gen._ICE=np.array([[.001,1.31,1e-8],[1e6,1.31,1e-8]])
    gen._SOLAR=np.array([[190.,2.],[12500.,2.]])
    gen._U,gen._GW=gen.laguerre_rule(16); gen._MAX_TERMS=100
    analytic=[]
    for phase,lo,hi in [('SW',820.,2680.),('LW',10.,250.)]:
        row=gen.integrate((phase,0,lo,hi,2000.,[233.,250.],100.))
        wanted=np.asarray([2000.,1000.,500.,1000.])[:,None]
        require(np.max(np.abs(np.asarray(row['moments'])-wanted))<2e-10,'PSD area/mass normalization')
        nn=int(math.ceil((hi-lo)/100.))+1
        parts=[gen.integrate((phase,0,lo,hi,2000.,[233.,250.],100.,i,min(i+2,nn))) for i in range(0,nn,2)]
        joined=gen.combine_chunks(parts[::-1])[0]
        require(np.allclose(joined['moments'],row['moments'],rtol=2e-15,atol=1e-11),'Spectral chunk reconstruction')
        require(np.allclose(joined['source_integral'],row['source_integral'],rtol=2e-15),'Spectral endpoint weights')
        if len(parts)>1:
            for bad in (parts[:-1],parts+[parts[0]]):
                try:gen.combine_chunks(bad)
                except ValueError:pass
                else:raise AssertionError('Incomplete/duplicated spectral chunks accepted')
        analytic.append(row)
    class LinearKernel:
        def mie_checked(self,n,k,x,limit,e,s,g,needed,status):
            e._obj.value=x; s._obj.value=.5*x; g._obj.value=.5
            needed._obj.value=1; status._obj.value=0
    gen._KERNEL=LinearKernel()
    chunk_tests=[]
    for phase,lo,hi in [('SW',820.,2680.),('LW',10.,250.)]:
        nn=int(math.ceil((hi-lo)/100.))+1; nu=np.linspace(lo,hi,nn)
        source=gen.solar_weight(nu)[None,:] if phase=='SW' else gen.planck_weight(nu,np.array([233.,250.]))
        norm=np.trapz(source,nu,axis=1)
        wanted=150.*math.pi*np.trapz(source*nu[None,:],nu,axis=1)/norm
        for size in (1,2,7,nn+1):
            parts=[gen.integrate((phase,0,lo,hi,2000.,[233.,250.],100.,i,min(i+size,nn))) for i in range(0,nn,size)]
            joined=gen.combine_chunks(parts[::-1])[0]
            require(np.allclose(joined['moments'][0],wanted,rtol=3e-14),'Analytic varying-Q spectral integral')
            require(np.allclose(joined['source_integral'],norm,rtol=3e-15),'Independent trapezoid source integral')
            chunk_tests.append(dict(phase=phase,chunk_size=size,source_integral=joined['source_integral'],
                                    max_relative_error=float(np.max(abs(np.asarray(joined['moments'][0])/wanted-1)))))
    wn=np.linspace(820.,50000.,100001)
    sw_integral=float(np.trapz(gen.solar_weight(wn),wn))
    sw_expected=2.*(1e7/820.-1e7/50000.)
    require(abs(sw_integral/sw_expected-1)<1e-7,'Solar wavelength/wavenumber Jacobian')
    # Pointwise Planck spectral radiance transformed from wavelength to cm-1.
    h,c,k=6.62607015e-34,299792458.,1.380649e-23
    nu=np.asarray([100.,500.,1500.,3000.]); temp=250.; wave=1./(100.*nu)
    b_lambda=2*h*c*c/wave**5/np.expm1(h*c/(wave*k*temp))
    b_nu_from_lambda=b_lambda/(100.*nu**2)
    b_nu_from_generator=gen.planck_weight(nu,np.asarray([temp]))[0]*(2*h*c*c*100.**4)
    require(np.max(abs(b_nu_from_lambda/b_nu_from_generator-1))<2e-14,'Planck spectral Jacobian')
    require(all(gen.sha(gen.ROOT/p)==digest for p,digest in sources.items()),'Sources changed during tests')
    receipt=dict(status='PASS_NUMERICAL_ONLY',source_sha256=sources,kernel_binary_sha256=gen.sha(library),
                 kernel_source_adaptation=json.loads((library.parent/'source-adaptation.json').read_text()),
                 precision_counterfactual=dict(arguments=list(arguments),unadapted=unadapted,adapted=adapted,
                     nonabsorbing=conservative,unadapted_binary_sha256=gen.sha(original_lib)),
                 benchmark_reference='https://doi.org/10.1364/AO.43.001951',benchmarks=benchmark,
                 large_workspace_cases=large,invalid_inputs=invalid,analytic_psd_cases=analytic,
                 analytic_varying_efficiency_chunk_tests=chunk_tests,
                 solar_jacobian_relative_error=sw_integral/sw_expected-1,
                 planck_jacobian_max_relative_error=float(np.max(abs(b_nu_from_lambda/b_nu_from_generator-1))),
                 elapsed_seconds=time.monotonic()-started,
                 scope='Numerical kernel/PSD/source transforms, not validated graupel/hail optical model')
    (args.output_dir/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':receipt['status'],'output':str(args.output_dir/'result.json')}))


if __name__=='__main__':
    main()
