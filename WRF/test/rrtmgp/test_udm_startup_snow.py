#!/usr/bin/env python3
"""Source-extracted native startup snow and unchanged precipitation-cutoff test.

Compiles the actual UDM declaration prefix, udminit, rgmma, native radius and
startup helper, plus actual LW/SW precipitation optics. Extracted wrapper snow
blocks test the background-only selector. No microphysics step or WRF forecast.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time


def pin(path: Path) -> dict:
    b=path.read_bytes()
    return {"path":str(path),"sha256":hashlib.sha256(b).hexdigest(),"size_bytes":len(b)}


def extract(text: str, name: str, function: bool=False) -> str:
    start=rf"^\s*real\s+function\s+{name}\b" if function else rf"^\s*subroutine\s+{name}\b"
    end=rf"^\s*end\s+{'function' if function else 'subroutine'}\s+{name}\s*$"
    matches=list(re.finditer(start+r".*?"+end,text,re.I|re.M|re.S))
    if len(matches)!=1: raise ValueError(f"expected one source routine: {name}")
    return matches[0].group(0)


def wrapper_block(text: str) -> str:
    start=text.index("               gp_snow_bootstrap=0.")
    end=text.index("               ! UDM-only:",start)
    block=text[start:end]
    if block.count("CALL udm_startup_snow_radius")!=1: raise ValueError("missing source fallback call")
    return block


def host_bits_source(text: str, phase: str) -> tuple[str, str]:
    declaration = "   REAL :: gp_host_real_bits(1)"
    statements = ("                  gp_host_real_bits(1)=REAL(STORAGE_SIZE(1.))\n"
                  f"                  CALL trace_raw('{phase.upper()}','HOST_REAL_BITS',gp_host_real_bits)")
    if text.count(declaration) != 1 or text.count(statements) != 1:
        raise ValueError("host-real-bit source declaration/assignment/call changed")
    return declaration, statements


def wiring(wrf: Path) -> dict:
    first=(wrf/'dyn_em/module_first_rk_step_part1.F').read_text()
    driver=(wrf/'phys/module_radiation_driver.F').read_text()
    required="udm_dry_density(i,mass_k,j) = 1./(grid%al(i,mass_k,j)+grid%alb(i,mass_k,j))"
    if first.count(required)!=1: raise ValueError("native dry density grouping changed")
    allocation=first.index("ALLOCATE(udm_dry_density")
    gate=first.rfind("IF (config_flags%ra_lw_physics == RRTMGP_LWSCHEME",0,allocation)
    if gate<0 or 'RRTMGP_SWSCHEME' not in first[gate:allocation]: raise ValueError("allocation not gated to 37")
    if 'UDM_DRY_DENSITY=udm_dry_density' not in first: raise ValueError("missing first caller forwarding")
    count=driver.count('udm_dry_density=udm_dry_density, &')
    if count!=6: raise ValueError(f"expected all six driver forwarding sites, got {count}")
    for phase in ['lw','sw']:
        text=(wrf/f'phys/module_ra_rrtmg_{phase}.F').read_text()
        if 'udm_qmin => epsilon, udm_t0c => svpt0' not in text: raise ValueError('native host constants not aliased')
        block=wrapper_block(text)
        for token in ['re_snow(i,k,j)==RE_QS_BG','qs1d(k)>0.','cldfrac(ncol,k)>0.',
                      'IF (ICLOUD /= 0)', 'udm_dry_density(i,k:k,j)', 't3d(i,k:k,j),qs3d(i,k:k,j)']:
            if token not in block: raise ValueError('missing source selector/input: '+token)
        # The extracted block is reached only in the RRTMGP alternative of
        # the existing legacy-vs-RRTMGP cloud optics branch.
        prev=text.rfind('IF (.NOT.run_rrtmgp)',0,text.index(block))
        if prev<0 or 'ELSE' not in text[prev:text.index(block)]: raise ValueError('legacy branch isolation missing')
        for field in ['SOURCE_DRY_RHO','STARTUP_SNOW_BOOTSTRAP','STARTUP_SNOW_RADIUS_M','HOST_REAL_BITS']:
            if text.count("'"+field+"'")!=1: raise ValueError('missing/duplicate raw diagnostic')
        host_bits_source(text, phase)
    return {'same_native_dry_density_operation':True,'six_driver_forwardings':count,
            'only_37_cloudy_wet_background_selector':True,'host_qmin_t0c_aliases':True}


PROGRAM=r'''
program startup_snow
 use module_mp_udm
 use module_model_constants, only: epsilon,svpt0,rhoair0,rhowater,rhosnow,cliq,cpv,RE_QS_BG
 use module_ra_rrtmgp_precip
 use mo_rte_kind, only: wp
 use, intrinsic :: ieee_arithmetic
 implicit none
 integer,parameter :: n=12
 real :: t(n),qs(n),rho(n),radius(n),native(n),zero(n),rc(n),ri(n),before_t(n),before_qs(n),before_rho(n)
 real :: one(1),nan,save_pid,rad_out(n),flags(n),ice_proxy(n),t3d(1,n,1),qs3d(1,n,1),den3d(1,n,1),re3d(1,n,1)
 real :: cld(1,n),re_before(1,n,1),rho_saved(1,n,1)
 real(wp) :: rwp(1,n),swp(1,n),rs(1,n),lw(1,n,16),sw(1,n,14),ssa(1,n,14),gg(1,n,14)
 real(wp) :: lw_bands(2,16),sw_bands(2,14),sw_floor(1,n,14),zero_path(1,n)
 integer :: ierr,k,host_bits_checks
 host_bits_checks=0
 if(storage_size(1.)/=32) error stop 1
 t=[240.,260.,280.,270.,250.,280.,265.,285.,300.,300.,300.,300.]
 qs=[1.e-30,1.e-15,1.e-12,1.e-10,1.e-8,1.e-6,1.e-4,1.e-3,.02,.01,.03,.1]
 rho=[.5,.8,1.,1.,.9,.8,1.,.7,1.,1.,1.,1.]
 zero=0.;radius=25.e-6
 call udm_startup_snow_radius(t,qs,rho,epsilon,svpt0,radius,n,ierr)
 if(ierr/=3) error stop 2
 call udminit(rhoair0,rhowater,rhosnow,cliq,cpv,100.,.false.)
 before_t=t;before_qs=qs;before_rho=rho
 call udm_startup_snow_radius(t,qs,rho,epsilon,svpt0,radius,n,ierr)
 if(ierr/=0) error stop 3
 native=25.e-6;rc=2.51e-6;ri=5.01e-6
 call udm_mp_effective_radius(t,zero,zero,qs,rho,epsilon,svpt0,zero,rc,ri,native,1,n,0,0)
 if(any(transfer(radius,[0],n)/=transfer(native,[0],n))) error stop 4
 if(any(transfer(t,[0],n)/=transfer(before_t,[0],n)).or. &
    any(transfer(qs,[0],n)/=transfer(before_qs,[0],n)).or. &
    any(transfer(rho,[0],n)/=transfer(before_rho,[0],n))) error stop 5
 if(radius(1)/=25.e-6.or.radius(n)/=999.e-6) error stop 6
 do k=1,n
   call udm_startup_snow_radius(t(k:k),qs(k:k),rho(k:k),epsilon,svpt0,one,1,ierr)
   if(ierr/=0.or.transfer(one(1),0)/=transfer(radius(k),0)) error stop 7
   write(*,'(A,1X,I0,1X,ES24.16,1X,I0)') 'NATIVE_SNOW',k,radius(k),transfer(radius(k),0)
 enddo
 rwp=0._wp;swp=1._wp;rs=10._wp
 call rrtmgp_precip_lw_band_bounds(lw_bands)
 call rrtmgp_precip_sw_band_bounds(sw_bands)
 call rrtmgp_precip_lw_optics(rwp,swp,rs,lw_bands,lw,ierr)
 if(ierr/=0.or.any(lw/=0._wp)) error stop 8
 call rrtmgp_precip_sw_optics(rwp,swp,rs,sw_bands,sw,ssa,gg,ierr,apply_delta_scale=.false.)
 if(ierr/=0) error stop 9
 ! The unchanged SW module applies its own 1e-12 numerical floor. Old 10um
 ! has no physical snow contribution: it equals a zero-path module control.
 zero_path=0._wp
 call rrtmgp_precip_sw_optics(rwp,zero_path,rs,sw_bands,sw_floor,ssa,gg,ierr,apply_delta_scale=.false.)
 if(ierr/=0.or.any(sw/=sw_floor)) error stop 9
 write(*,'(A)') 'PASS_OLD10_SW_EQUALS_ZERO_PATH_FLOOR'
 rs(1,:)=real(radius*1.e6,wp)
 call rrtmgp_precip_lw_optics(rwp,swp,rs,lw_bands,lw,ierr)
 if(ierr/=0.or.any(lw<=0._wp)) error stop 10
 call rrtmgp_precip_sw_optics(rwp,swp,rs,sw_bands,sw,ssa,gg,ierr,apply_delta_scale=.false.)
 if(ierr/=0.or.any(sw<=sw_floor)) error stop 11
 ! Compile the actual wrapper selector blocks; preserve diagnosed source RE,
 ! zero/cloud-free/clear inputs, and source mass fields exactly.
 t3d(1,:,1)=t;qs3d(1,:,1)=qs;den3d(1,:,1)=rho;re3d=RE_QS_BG;cld=1.;ice_proxy=30.
 re_before=re3d;rho_saved=den3d
 call apply_lw(t3d,qs3d,den3d,re3d,cld,qs,ice_proxy,1,1,rad_out,flags,n)
 if(any(transfer(rad_out,[0],n)/=transfer(radius*1.e6,[0],n)).or.any(flags/=1.)) error stop 12
 call apply_sw(t3d,qs3d,den3d,re3d,cld,qs,ice_proxy,1,1,rad_out,flags,n)
 if(any(transfer(rad_out,[0],n)/=transfer(radius*1.e6,[0],n)).or.any(flags/=1.)) error stop 13
 if(any(re3d/=re_before).or.any(den3d/=rho_saved).or.any(qs3d(1,:,1)/=before_qs)) error stop 14
 re3d=80.e-6
 call apply_lw(t3d,qs3d,den3d,re3d,cld,qs,ice_proxy,1,1,rad_out,flags,n)
 if(any(rad_out/=80.e-6*1.e6).or.any(flags/=0.)) error stop 15
 call apply_sw(t3d,qs3d,den3d,re3d,cld,qs,ice_proxy,1,1,rad_out,flags,n)
 if(any(rad_out/=80.e-6*1.e6).or.any(flags/=0.)) error stop 16
 re3d=RE_QS_BG;cld=0.
 call apply_lw(t3d,qs3d,den3d,re3d,cld,qs,ice_proxy,1,1,rad_out,flags,n)
 if(any(flags/=0.)) error stop 17
 cld=1.
 call apply_sw(t3d,qs3d,den3d,re3d,cld,qs,ice_proxy,1,0,rad_out,flags,n)
 if(any(flags/=0.)) error stop 18
 zero=0.
 call apply_lw(t3d,qs3d,den3d,re3d,cld,zero,ice_proxy,1,1,rad_out,flags,n)
 if(any(flags/=0.)) error stop 19
 ! Invalid inputs are rejected before native arithmetic, not clipped.
 nan=ieee_value(0.,ieee_quiet_nan)
 call udm_startup_snow_radius([nan],[1.e-4],[1.],epsilon,svpt0,one,1,ierr)
 if(ierr/=2) error stop 20
 call udm_startup_snow_radius([0.],[1.e-4],[1.],epsilon,svpt0,one,1,ierr)
 if(ierr/=2) error stop 21
 call udm_startup_snow_radius([280.],[-1.e-4],[1.],epsilon,svpt0,one,1,ierr)
 if(ierr/=2) error stop 22
 call udm_startup_snow_radius([280.],[1.e-4],[0.],epsilon,svpt0,one,1,ierr)
 if(ierr/=2) error stop 23
 call udm_startup_snow_radius([280.],[1.e-4],[nan],epsilon,svpt0,one,1,ierr)
 if(ierr/=2) error stop 24
 call udm_startup_snow_radius([280.],[huge(1.)],[2.],epsilon,svpt0,one,1,ierr)
 if(ierr/=2) error stop 25
 call udm_startup_snow_radius([280.],[0.],[huge(1.)],epsilon,svpt0,one,1,ierr)
 if(ierr/=2) error stop 26
 call udm_startup_snow_radius([280.],[1.e-4],[1.],epsilon,svpt0,radius,1,ierr)
 if(ierr/=1) error stop 27
 save_pid=pidn0s;pidn0s=nan
 call udm_startup_snow_radius([280.],[1.e-4],[1.],epsilon,svpt0,one,1,ierr)
 if(ierr/=3) error stop 28
 pidn0s=save_pid
 call udm_startup_snow_radius([1.],[1.e-4],[1.],epsilon,huge(1.),one,1,ierr)
 if(ierr/=2) error stop 29
 pidn0s=huge(1.)
 call udm_startup_snow_radius([240.],[1.e-4],[1.],epsilon,svpt0,one,1,ierr)
 if(ierr/=2) error stop 30
 pidn0s=save_pid
 if(host_bits_checks/=7) error stop 31
 write(*,'(A)') 'PASS_HOST_REAL_BITS_ORIGIN'
 write(*,'(A)') 'PASS_STARTUP_SNOW_NATIVE_AND_PRECIP_CONTRACT'
contains
'''


def make_sources(wrf: Path, work: Path) -> tuple[list[Path],dict]:
    udm_path=wrf/'phys/module_mp_udm.F'; udm=udm_path.read_text()
    prefix=udm[:re.search(r'^contains\s*$',udm,re.M|re.I).start()]
    routines=[extract(udm,'udminit'),extract(udm,'rgmma',True),
              extract(udm,'udm_startup_snow_radius'),extract(udm,'udm_mp_effective_radius')]
    native=work/'native_snow_extracted.f90'
    native.write_text(prefix+'\ncontains\n'+'\n'.join(routines)+'\nend module module_mp_udm\n')
    # Only wrf_debug's output dependency is stubbed; the actual radar module,
    # UDM initializer, declarations and model constants are compiled unchanged.
    stub=work/'module_wrf_error.f90'
    stub.write_text('module module_wrf_error\ncontains\nsubroutine wrf_debug(level,text)\ninteger::level\ncharacter(*)::text\nend subroutine\nend module\n')
    blocks={phase:wrapper_block((wrf/f'phys/module_ra_rrtmg_{phase}.F').read_text()) for phase in ['lw','sw']}
    tail=''
    for phase,block in blocks.items():
        declaration, bits_statements = host_bits_source((wrf/f'phys/module_ra_rrtmg_{phase}.F').read_text(), phase)
        tail+=f'''subroutine apply_{phase}(t3d,qs3d,udm_dry_density,re_snow,cldfrac,qs1d,gp_rei,has_reqs,ICLOUD,gp_res,gp_snow_bootstrap,nlay)
 use module_model_constants, only: RE_QS_BG,udm_qmin=>epsilon,udm_t0c=>svpt0
 integer,intent(in)::nlay,has_reqs,ICLOUD
 real,intent(in)::t3d(1,nlay,1),qs3d(1,nlay,1),udm_dry_density(1,nlay,1),re_snow(1,nlay,1)
 real,intent(in)::cldfrac(1,nlay),qs1d(nlay),gp_rei(nlay)
 real,intent(out)::gp_res(nlay),gp_snow_bootstrap(nlay)
 real::gp_startup_snow_m(1),gp_snow_bootstrap_m(nlay)
{declaration}
 character(256)::gp_errmsg
 integer::i,j,k,kts,kte,ncol,gp_reason
 i=1;j=1;kts=1;kte=nlay;ncol=1
{block}
{bits_statements}
end subroutine apply_{phase}
'''
    tail+='''subroutine trace_raw(phase,field,values)
 character(*),intent(in)::phase,field
 real,intent(in)::values(:)
 if(phase/='LW'.and.phase/='SW') error stop 32
 if(field/='HOST_REAL_BITS'.or.size(values)/=1) error stop 33
 if(values(1)/=REAL(STORAGE_SIZE(1.))) error stop 34
 host_bits_checks=host_bits_checks+1
end subroutine trace_raw
'''
    tail+='subroutine rrtmgp_fatal(message,file)\ncharacter(*)::message,file\nerror stop 98\nend subroutine\nend program startup_snow\n'
    program=work/'test_startup_snow.f90';program.write_text(PROGRAM+tail)
    sources=[wrf/'phys/module_gfs_machine.F',stub,wrf/'phys/module_mp_radar.F',
             wrf/'share/module_model_constants.F',wrf/'external/rte_rrtmgp/rte-frontend/mo_rte_kind.F90',
             native,wrf/'phys/module_ra_rrtmgp_precip.F',program]
    origins={str(p):pin(p) for p in sources if p not in [native,stub,program]}
    origins['UDM_original']=pin(udm_path)
    return sources,{'origins':origins,'extracted_routine_SHA256':{name:hashlib.sha256(s.encode()).hexdigest() for name,s in zip(['udminit','rgmma','startup_snow','native_radius'],routines)},'wrapper_block_SHA256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in blocks.items()},'host_bits_source_SHA256':{k:hashlib.sha256('\n'.join(host_bits_source((wrf/f'phys/module_ra_rrtmg_{k}.F').read_text(), k)).encode()).hexdigest() for k in blocks},'generated':[pin(p) for p in [native,stub,program]],'wrf_debug_stub_only':True}


def execute(command: list[str], work: Path, name: str) -> dict:
    with (work/(name+'.stdout')).open('xb') as out,(work/(name+'.stderr')).open('xb') as err:
        proc=subprocess.Popen(command,cwd=work,stdout=out,stderr=err)
        rc=proc.wait();out.flush();os.fsync(out.fileno());err.flush();os.fsync(err.fileno())
    record={'command':command,'pid':proc.pid,'actual_returncode':rc,'stdout':pin(work/(name+'.stdout')),'stderr':pin(work/(name+'.stderr'))}
    with (work/(name+'.json')).open('x') as stream:
        json.dump(record,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    return record


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wrf-root',type=Path,default=Path(__file__).resolve().parents[2])
    p.add_argument('--workdir',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--compiler',default=shutil.which('gfortran') or 'gfortran')
    p.add_argument('--prepare-only',action='store_true',help='write source-derived fixture and plan without invoking compiler')
    args=p.parse_args();wrf=args.wrf_root.resolve()
    cleanup=None
    if args.workdir:
        work=args.workdir.resolve();work.mkdir(parents=True,exist_ok=False)
    else:
        cleanup=tempfile.TemporaryDirectory(prefix='udm-startup-snow-');work=Path(cleanup.name)
    receipt={'status':'PREPARING','compiles':0,'fixture_runs':0,'WRF_builds':0,'forecasts':0,'RTE_calls':0,'scope':'Manufactured source-extracted radius/wrapper-selector/precipitation optics fixture only.'}
    try:
        receipt['wiring']=wiring(wrf);sources,receipt['source']=make_sources(wrf,work)
        commands=[[args.compiler,opt,'-cpp','-DEM_CORE=1','-ffree-form','-ffree-line-length-none','-fcheck=all','-ffpe-trap=invalid,zero,overflow','-I',str(work),'-J',str(work),*[str(s) for s in sources],'-o',str(work/('test_'+opt[1:]))] for opt in ['-O0','-O2']]
        receipt['planned_compile_commands']=commands
        receipt['executions']=[]
        if args.prepare_only:receipt['status']='PREPARED_NO_COMPILER_OR_EXECUTABLE_INVOCATIONS'
        else:
            for index,command in enumerate(commands):
                opt=['O0','O2'][index]
                c=execute(command,work,'compile_'+opt);receipt['compiles']+=1;receipt['executions'].append(c)
                if c['actual_returncode']!=0:raise RuntimeError('compile failed '+opt)
                r=execute([str(work/('test_'+opt))],work,'run_'+opt);receipt['fixture_runs']+=1;receipt['executions'].append(r)
                if r['actual_returncode']!=0:raise RuntimeError('fixture failed '+opt)
                output=(work/('run_'+opt+'.stdout')).read_text()
                if output.count('PASS_STARTUP_SNOW_NATIVE_AND_PRECIP_CONTRACT')!=1:raise RuntimeError('missing success marker')
                rows=[line.split() for line in output.splitlines() if line.startswith('NATIVE_SNOW')]
                if len(rows)!=12 or [int(r[1]) for r in rows]!=list(range(1,13)):raise RuntimeError('invalid radius roster')
            receipt['status']='PASS_SCOPED_SOURCE_EXTRACTED_STARTUP_SNOW_FIXTURE'
    except Exception as exc:
        receipt['status']='FAIL';receipt['error']=str(exc)
    finally:
        destination=args.output.resolve() if args.output else work/'receipt.json'
        with destination.open('x') as stream:json.dump(receipt,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        print(json.dumps({'status':receipt['status'],'receipt':str(destination),'compiles':receipt['compiles'],'fixture_runs':receipt['fixture_runs']}))
        if cleanup is not None:cleanup.cleanup()
    return 1 if receipt['status']=='FAIL' else 0

if __name__=='__main__':raise SystemExit(main())
