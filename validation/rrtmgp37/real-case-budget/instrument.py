"""Private calls only, numerical public statements retained verbatim."""
from pathlib import Path
import re
SPEC=['P_QV','P_QC','P_QR','P_QI','P_QS','P_QG','P_QH']
SL='ids:ide-1,kds:kde-1,jds:jde-1'
H='ids:ide-1,jds:jde-1'
V='kds:kde-1'
def stock(tag,field='moist',mu='grid%mu_2'):
 return '\n'.join(f" CALL stock('{tag}',{n},{field}({SL},{p}),{mu}({H}), &\n grid%mub({H}),grid%c1h({V}),grid%c2h({V}))" for n,p in enumerate(SPEC,1))+'\n'
def one_stock(tag,field='moist',mu='grid%mu_2'):
 return f" CALL stock('{tag}',im,{field}({SL},im),{mu}({H}), &\n grid%mub({H}),grid%c1h({V}),grid%c2h({V}))\n"
def tend(tag): return f" CALL tend('{tag}',im,moist_tend({SL},im))\n"
def bounds(s,needle):
 pos=s.index(needle);start=s.rfind('\n',0,pos)+1;n=0;beg=False
 for j in range(s.index('(',pos),len(s)):
  if s[j]=='(':n+=1;beg=True
  if s[j]==')':n-=1
  if beg and n==0:return start,j+1
 raise ValueError(needle)
def surround(s,needle,before='',after=''):
 a,b=bounds(s,needle);return s[:a]+before+s[a:b]+'\n'+after+s[b:]
def transform(root):
 s=(root/'WRF/dyn_em/solve_em.F').read_text()
 s=s.replace('   USE module_state_description','   USE module_real_budget_probe, ONLY:setup,stock,tend,adv,surface,radiation,frozen_end\n   USE module_state_description',1)
 needle='   Runge_Kutta_loop:  DO rk_step = 1, rk_order'
 setup=f" CALL setup(curr_secs_r8,grid%dt,grid%dx,grid%dy,grid%msftx({H}),grid%msfty({H}),grid%dnw({V}))\n"
 surf=lambda tag:f" CALL surface('{tag}',grid%rainc({H})+grid%rainnc({H}),grid%aclhf({H}),grid%qfx({H}))\n"
 rad=lambda tag:f" CALL radiation('{tag}',grid%rthraten({SL}),pi_phy({SL}),grid%mut({H}), &\n grid%c1h({V}),grid%c2h({V}),moist({SL},P_QV))\n"
 s=s.replace(needle,setup+stock('start')+surf('surface_start')+needle,1)
 s=surround(s,'CALL first_rk_step_part1 (',after=rad('rad_raw')+surf('surface_physics')+' CALL frozen_end()\n')
 s=surround(s,'CALL first_rk_step_part2 (',after=rad('rad_coupled'))
 s=surround(s,'CALL relax_bdy_scalar ( moist_tend',before=tend('before_relax'),after=tend('after_relax'))
 s=surround(s,'CALL spec_bdy_scalar  ( moist_tend',after=tend('after_spec_tend'))
 s=surround(s,'CALL rk_update_scalar_pd( im, im,',before=one_stock('pd_before','moist_old','grid%mu_1')+tend('pd_tendency'),after=one_stock('pd_after','moist_old','grid%mu_1'))
 s=surround(s,'CALL rk_update_scalar( scs=im,',before=" IF(rk_step==rk_order)THEN\n"+one_stock('rk_base','moist_old','grid%mu_1')+tend('rk_other_tendency')+f" CALL adv(im,advect_tend({SL}),grid%msfty({H}),dt_rk)\n ENDIF\n",after=" IF(rk_step==rk_order)THEN\n"+one_stock('rk_after')+' ENDIF\n')
 s=s.replace('   END DO Runge_Kutta_loop','   END DO Runge_Kutta_loop\n'+stock('after_rk'),1)
 s=surround(s,'CALL microphysics_driver(',before=stock('micro_before')+surf('surface_micro_before'),after=stock('micro_after')+surf('surface_micro_after'))
 s=surround(s,'CALL spec_bdy_final   ( grid%mu_2',before=stock('final_mu_before'),after=stock('final_mu_after'))
 s=surround(s,'CALL spec_bdy_final   ( moist(ims,kms,jms,im)',before=one_stock('final_q_before'),after=one_stock('final_q_after'))
 s=s.replace('   RETURN\n\nEND SUBROUTINE solve_em',stock('end')+surf('surface_end')+'   RETURN\n\nEND SUBROUTINE solve_em',1)
 ph=(root/'WRF/phys/module_physics_addtendc.F').read_text()
 ph=ph.replace('MODULE module_physics_addtendc','MODULE module_physics_addtendc\n USE module_real_budget_probe,ONLY:thermal,tend',1)
 ph=surround(ph,'CALL add_a2a(rt_tendf,RTHRATEN',before=" CALL thermal('thermal_before',rt_tendf(its:MIN(ite,ide-1),kts:MIN(kte,kde-1),jts:MIN(jte,jde-1)))\n",after=" CALL thermal('thermal_after',rt_tendf(its:MIN(ite,ide-1),kts:MIN(kte,kde-1),jts:MIN(jte,jde-1)))\n")
 for name,label in [('phy_bl_ten','pbl'),('phy_cu_ten','cumulus')]:
  def group(tag):
   return '\n'.join(f" CALL tend('{tag}',{n},moist_tendf(ids:ide-1,kds:kde-1,jds:jde-1,{p}))" for n,p in enumerate(SPEC,1))+'\n'
  a,b=bounds(ph,'CALL '+name+'(')
  a=ph.rfind('\n   if ',0,a)+1
  ph=ph[:a]+group(label+'_before')+ph[a:b]+'\n'+group(label+'_after')+ph[b:]
 em=(root/'WRF/dyn_em/module_em.F').read_text()
 em=em.replace('MODULE module_em\n','MODULE module_em\n USE module_real_budget_probe,ONLY:rhs\n',1)
 a=em.index('SUBROUTINE rk_addtend_dry');b=em.index('END SUBROUTINE rk_addtend_dry',a)
 part=em[a:b]
 # Observations surround the native thermal RHS loop; retained assignments are verbatim.
 needle='     IF(rk_step == 1)t_tendf(i,k,j) = t_tendf(i,k,j) +  t_save(i,k,j)'
 start=part.rfind('   DO j =',0,part.index(needle))
 part=part[:start]+" CALL rhs('before',rk_step,t_tend(ids:ide-1,kds:kde-1,jds:jde-1),msfty(ids:ide-1,jds:jde-1))\n"+part[start:]
 pos=part.index('   DO j =',part.index(needle)+len(needle))
 part=part[:pos]+" CALL rhs('after',rk_step,t_tend(ids:ide-1,kds:kde-1,jds:jde-1),msfty(ids:ide-1,jds:jde-1))\n"+part[pos:]
 em=em[:a]+part+em[b:]
 out={'solve_em.F':s,'module_physics_addtendc.F':ph,'module_em.F':em}
 for kind,short in [(1,'lw'),(2,'sw')]:
  p=root/f'WRF/phys/module_ra_rrtmg_{short}.F';s=p.read_text()
  # This source contains several old modules; attach use to the host module containing the scatter routine.
  pos=s.index(f'   SUBROUTINE scatter_{short}_column');mod=s.rfind('\nmodule ',0,pos)
  if mod<0:mod=s.rfind('\nMODULE ',0,pos)
  e=s.index('\n',mod+1)
  s=s[:e]+"\n USE module_real_budget_probe,ONLY:column,frozen"+s[e:]
  needle=f'      INTEGER, INTENT(IN) :: dest_i,dest_j';a=s.index(needle,s.index(f'   SUBROUTINE scatter_{short}_column'))+len(needle)
  up,dn=('uflx','dflx') if kind==1 else ('swuflx','swdflx')
  heat='hr' if kind==1 else 'swhr'
  code=f"\n         IF(run_rrtmgp)CALL column({kind},dest_i,dest_j,kte,real({up}(1,:),8), &\n          real({dn}(1,:),8),real({heat}(1,:),8),real(plev(1,:),8), &\n          real(udm_dry_layer_mass(dest_i,kts:kte,dest_j),8))"
  s=s[:a]+code+s[a:]
  if kind==1:
   needle='         IF(gp_batch_enabled) THEN'
   pos=s.index(needle,s.index('gp_seed=rrtmgp_column_seed'))
   code="""         IF(run_rrtmgp.AND.gp_frozen)THEN
          CALL frozen(i,j,real(tlay(1,kts:kte),8),real(gp_gwp(1,kts:kte),8),real(gp_lambda_g(1,kts:kte),8),1)
          CALL frozen(i,j,real(tlay(1,kts:kte),8),real(gp_hwp(1,kts:kte),8),real(gp_lambda_h(1,kts:kte),8),2)
         ENDIF
"""
   s=s[:pos]+code+s[pos:]
  out[p.name]=s
 return out
