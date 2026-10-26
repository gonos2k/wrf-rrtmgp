"""Insert bounded read-only calls, leaving native arithmetic statements intact."""
import importlib.util
from pathlib import Path
SPEC=['P_QV','P_QC','P_QR','P_QI','P_QS','P_QG','P_QH']
V='kds:kde-1';I='37';J='119';COL=f'{I},{V},{J}'
def helpers(root):
 p=root/'validation/rrtmgp37/real-case-budget/instrument.py'
 s=importlib.util.spec_from_file_location('budget_ins',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def stock(tag,field='moist',mu='grid%mu_2',one=False):
 pairs=[('im','im')] if one else list(enumerate(SPEC,1))
 return ''.join(f" CALL cl_stock('{tag}',{n},{field}({COL},{p}),{mu}(37,119),grid%mub(37,119), &\n grid%c1h({V}),grid%c2h({V}),grid%dnw({V}))\n" for n,p in pairs)
def tend(tag):return f" CALL cl_tend('{tag}',im,moist_tend({COL},im))\n"
def envrow(tag):
 return f""" DO kk=kds,kde-1
 CALL cl_row('{tag}',0,kk,[th_phy(37,kk,119),pi_phy(37,kk,119),p_phy(37,kk,119)])
 ENDDO
 CALL cl_row('{tag}_precip',0,0,[grid%rainc(37,119),grid%rainnc(37,119),grid%raincv(37,119),grid%rainncv(37,119)])
"""
def neighbors(tag):
 return f""" DO jj=116,122
 DO kk=5,7
 DO ii=34,40
 CALL cl_row('{tag}',P_QC,kk,[real(ii),real(jj),moist(ii,kk,jj,P_QV),moist(ii,kk,jj,P_QC), &
 moist(ii,kk,jj,P_QR),grid%u_2(ii,kk,jj),grid%v_2(ii,kk,jj),grid%w_2(ii,kk,jj)])
 ENDDO
 ENDDO
 ENDDO
"""
def transform(root):
 h=helpers(root)
 s=(root/'WRF/dyn_em/solve_em.F').read_text()
 s=s.replace('   USE module_state_description','   USE module_cloud_loss_probe\n   USE module_state_description',1)
 needle='   Runge_Kutta_loop:  DO rk_step = 1, rk_order'
 assert s.count(needle)==1
 s=s.replace(needle," CALL cl_setup(curr_secs_r8)\n CALL cl_context(0,0)\n"+stock('start')+neighbors('neighbor_start')+needle,1)
 s=h.surround(s,'CALL rk_scalar_tend (  im, im,',before=" CALL cl_context(rk_step,im)\n"+tend('scalar_before'),after=tend('scalar_after'))
 s=h.surround(s,'CALL rk_update_scalar_pd( im, im,',before=" CALL cl_context(rk_step,im)\n"+stock('pd_before','moist_old','grid%mu_1',True)+tend('pd_source'),after=stock('pd_after','moist_old','grid%mu_1',True))
 s=h.surround(s,'CALL rk_update_scalar( scs=im,',before=" IF(rk_step==rk_order)THEN\n"+stock('rk_base','moist_old','grid%mu_1',True)+tend('rk_source')+f" CALL cl_tend('rk_advect',im,advect_tend({COL}))\n DO kk=kds,kde-1\n CALL cl_row('rk_factors',im,kk,[dt_rk,grid%msfty(37,119)])\n ENDDO\n ENDIF\n",after=" IF(rk_step==rk_order)THEN\n"+stock('rk_after',one=True)+' ENDIF\n')
 s=s.replace('ENDDO moist_variable_loop','ENDDO moist_variable_loop\n CALL cl_context(0,0)',1)
 s=s.replace('   END DO Runge_Kutta_loop','   END DO Runge_Kutta_loop\n'+stock('after_rk'),1)
 s=h.surround(s,'CALL microphysics_driver(',before=stock('micro_before')+envrow('micro_env_before'),after=stock('micro_after')+envrow('micro_env_after'))
 s=s.replace('   RETURN\n\nEND SUBROUTINE solve_em',stock('end')+neighbors('neighbor_end')+'   RETURN\n\nEND SUBROUTINE solve_em',1)
 ph=(root/'WRF/phys/module_physics_addtendc.F').read_text()
 ph=ph.replace('MODULE module_physics_addtendc','MODULE module_physics_addtendc\n USE module_cloud_loss_probe,ONLY:cl_tend',1)
 for name,label in [('phy_bl_ten','pbl'),('phy_cu_ten','cumulus')]:
  def group(tag):return ''.join(f" CALL cl_tend('{tag}',{n},moist_tendf({COL},{p}))\n" for n,p in enumerate(SPEC,1))
  a,b=h.bounds(ph,'CALL '+name+'(');a=ph.rfind('\n   if ',0,a)+1
  ph=ph[:a]+group(label+'_before')+ph[a:b]+'\n'+group(label+'_after')+ph[b:]
 em=(root/'WRF/dyn_em/module_advect_em.F').read_text()
 em=em.replace('MODULE module_advect_em\n','MODULE module_advect_em\n USE module_cloud_loss_probe,ONLY:cl_row\n',1)
 # Context species passed through module state: capture only this actual PD routine.
 a=em.index('SUBROUTINE advect_scalar_pd ');b=em.index('END SUBROUTINE advect_scalar_pd',a)
 part=em[a:b]
 # Direction boundaries are after completed native loops, not reevaluated tendencies.
 def snap(tag):return f"\n DO k=kts,ktf\n CALL cl_row('{tag}',-1,k,[tendency(37,k,119)])\n ENDDO\n"
 part=part.replace('! add in the pd-limited flux divergence',snap('adv_pre')+'! add in the pd-limited flux divergence',1)
 part=part.replace('! x flux divergence',snap('adv_z')+'! x flux divergence',1)
 part=part.replace('! y flux divergence',snap('adv_x')+'! y flux divergence',1)
 part+=snap('adv_y')+"""
 DO k=kts,ktf
 CALL cl_row('faces',-1,k,[fqx(37,k,119),fqx(38,k,119),fqxl(37,k,119),fqxl(38,k,119), &
 fqy(37,k,119),fqy(37,k,120),fqyl(37,k,119),fqyl(37,k,120), &
 fqz(37,k,119),fqz(37,k+1,119),fqzl(37,k,119),fqzl(37,k+1,119), &
 rdx,rdy,rdzw(k),msftx(37,119),msfty(37,119)])
 ENDDO
"""
 em=em[:a]+part+em[b:]
 return {'solve_em.F':s,'module_physics_addtendc.F':ph,'module_advect_em.F':em}
