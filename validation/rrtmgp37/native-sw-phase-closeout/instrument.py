"""Private read-only calls; production numerical statements retained verbatim."""
from pathlib import Path
import importlib.util
P=Path(__file__).resolve().parent

def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def transform(root):
 budget=load('sw_prior_budget',P.parent/'convective-support/instrument.py')
 vapor=load('sw_prior_vapor',P.parent/'vapor-first-operation/instrument.py')
 out=budget.transform(root)
 s=vapor.transform(root,out['solve_em.F'])
 s=s.replace('   USE module_state_description','   USE module_sw_phase_probe, ONLY:sw_setup,sw_held\n   USE module_state_description',1)
 H=budget.I.H;SL=budget.I.SL
 needle='   Runge_Kutta_loop:  DO rk_step = 1, rk_order'
 code=f' CALL sw_setup(curr_secs_r8,grid%dt,grid%dx,grid%dy,grid%msftx({H}),grid%msfty({H}),grid%dnw(kds:kde-1))\n'
 assert s.count(needle)==1;s=s.replace(needle,code+needle,1)
 s=budget.I.surround(s,'CALL first_rk_step_part1 (',after=f' CALL sw_held(grid%rthratensw({SL}),pi_phy({SL}),grid%mut({H}),grid%c1h(kds:kde-1),grid%c2h(kds:kde-1))\n')
 out['solve_em.F']=s
 s=out['module_ra_rrtmg_sw.F']
 marker=' USE module_real_budget_probe,ONLY:column,frozen'
 assert s.count(marker)==1
 s=s.replace(marker,marker+'\n USE module_sw_phase_probe,ONLY:sw_begin,sw_day,sw_night,sw_end',1)
 needle='  j_loop: do j = jts,jte'
 s=s.replace(needle,'  IF(run_rrtmgp)CALL sw_begin(audit_step,audit_time,its,ite,jts,jte)\n'+needle,1)
 needle='            swcf(i,j)      = 0.'
 assert s.count(needle)==1;s=s.replace(needle,needle+'\n         IF(run_rrtmgp)CALL sw_night(i,j)',1)
 needle='   IF(run_rrtmgp) CALL rrtmgp_release_workspace(gp_workspace)'
 assert s.count(needle)==1
 s=s.replace(needle,needle+'''
   IF(run_rrtmgp)THEN
    IF(.NOT.PRESENT(swupflx).OR..NOT.PRESENT(swupt))ERROR STOP 'SW observer needs returned layer and boundary arrays'
    CALL sw_end(swupflx(its:ite,kts:kte+2,jts:jte),swdnflx(its:ite,kts:kte+2,jts:jte), &
     rthratensw(its:ite,kts:kte,jts:jte),pi3d(its:ite,kts:kte,jts:jte), &
     udm_dry_layer_mass(its:ite,kts:kte,jts:jte),xcoszen(its:ite,jts:jte), &
     gsw(its:ite,jts:jte),swupb(its:ite,jts:jte),swdnb(its:ite,jts:jte), &
     swupt(its:ite,jts:jte),swdnt(its:ite,jts:jte))
   ENDIF
''',1)
 needle='   END SUBROUTINE scatter_sw_column'
 assert s.count(needle)==1
 s=s.replace(needle,'''      IF(run_rrtmgp)CALL sw_day(dest_i,dest_j,kte-kts+1,real(swuflx(1,:),8), &
       real(swdflx(1,:),8),real(swhr(1,:),8),real(plev(1,:),8), &
       real(udm_dry_layer_mass(dest_i,kts:kte,dest_j),8))
'''+needle,1)
 out['module_ra_rrtmg_sw.F']=s
 # The baseline omits optional layer-flux arrays. Supply private scratch outputs
 # through the public diagnostic arguments; native reset/scatter statements fill them.
 first=(root/'WRF/dyn_em/module_first_rk_step_part1.F').read_text()
 a,b=budget.I.bounds(first,'CALL radiation_driver(')
 call=first[a:b]
 marker='CALL radiation_driver('
 replacement='CALL radiation_driver(SWUPFLX=obs_swu,SWDNFLX=obs_swd,SWUPFLXC=obs_swuc,SWDNFLXC=obs_swdc, &\n' + \
 ' LWUPFLX=obs_lwu,LWDNFLX=obs_lwd,LWUPFLXC=obs_lwuc,LWDNFLXC=obs_lwdc, '
 call=call.replace(marker,replacement,1)
 before="""      BLOCK
       REAL :: obs_swu(ims:ime,kms:kme+2,jms:jme),obs_swd(ims:ime,kms:kme+2,jms:jme)
       REAL :: obs_swuc(ims:ime,kms:kme+2,jms:jme),obs_swdc(ims:ime,kms:kme+2,jms:jme)
       REAL :: obs_lwu(ims:ime,kms:kme+2,jms:jme),obs_lwd(ims:ime,kms:kme+2,jms:jme)
       REAL :: obs_lwuc(ims:ime,kms:kme+2,jms:jme),obs_lwdc(ims:ime,kms:kme+2,jms:jme)
"""
 first=first[:a]+before+call+'\n      END BLOCK\n'+first[b:]
 out['module_first_rk_step_part1.F']=first
 return out
