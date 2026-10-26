"""Add read-only bounded calls; leave every native arithmetic statement intact."""
from pathlib import Path
import importlib.util
V='5:12';C='37,5:12,119'
def helpers(root):
 s=importlib.util.spec_from_file_location('budget_helpers',root/'validation/rrtmgp37/real-case-budget/instrument.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h);return h
def state(tag,t='grid%t_2',q='moist',mu='grid%mu_2'):
 return f" CALL td_state('{tag}',{t}({C}),{q}({C},P_QV),{mu}(37,119),grid%mub(37,119), &\n grid%c1h({V}),grid%c2h({V}),grid%dnw({V}),grid%p({C}),grid%pb({C}))\n"
def qstock(tag,field='moist',mu='grid%mu_2'):
 return f" IF(im==P_QV)THEN\n DO kk=5,12\n CALL td_row('{tag}',2,kk,[{field}(37,kk,119,im), &\n grid%c1h(kk)*({mu}(37,119)+grid%mub(37,119))+grid%c2h(kk),grid%dnw(kk)])\n ENDDO\n ENDIF\n"
def qtend(tag):return f" IF(im==P_QV)CALL td_col('{tag}',2,moist_tend({C},im))\n"
def neighbors(tag):return f""" IF(mod(nint(curr_secs_r8),3600)==0)THEN
 DO jj=116,122
 DO kk=4,13
 DO ii=34,40
 CALL td_row('{tag}',0,kk,[real(ii),real(jj),grid%t_2(ii,kk,jj),moist(ii,kk,jj,P_QV), &
 moist(ii,kk,jj,P_QC),grid%u_2(ii,kk,jj),grid%v_2(ii,kk,jj),grid%w_2(ii,kk,jj)])
 ENDDO
 ENDDO
 ENDDO
 ENDIF
"""
def transform(root):
 h=helpers(root);s=(root/'WRF/dyn_em/solve_em.F').read_text();s=s.replace('   USE module_state_description','   USE module_thermodynamic_probe\n   USE module_state_description',1)
 marker='   Runge_Kutta_loop:  DO rk_step = 1, rk_order';assert s.count(marker)==1
 s=s.replace(marker," CALL td_setup(curr_secs_r8)\n CALL td_context(0)\n"+state('start')+neighbors('neighbor_start')+marker+'\n CALL td_context(rk_step)\n',1)
 s=h.surround(s,'CALL first_rk_step_part2 (',before=state('before_part2'),after=state('after_part2'))
 s=h.surround(s,'CALL rk_tendency (',before=f" CALL td_col('tf_before_rktendency',1,t_tendf({C}))\n",after=f" CALL td_col('tf_after_rktendency',1,t_tendf({C}))\n")
 s=h.surround(s,'CALL rk_addtend_dry(',before=f" CALL td_col('theta_rhs_before',1,t_tend({C}))\n",after=f" CALL td_col('theta_rhs_after',1,t_tend({C}))\n DO kk=5,12\n CALL td_row('theta_rhs_operands',1,kk,[t_tendf(37,kk,119),grid%h_diabatic(37,kk,119), &\n grid%c1h(kk)*grid%mut(37,119)+grid%c2h(kk),grid%msfty(37,119)])\n ENDDO\n")
 s=h.surround(s,'CALL small_step_prep(',before=state('before_smallprep'),after=" DO kk=5,12\n CALL td_row('smallprep',1,kk,[grid%t_2(37,kk,119),grid%t_save(37,kk,119), &\n grid%c1h(kk)*grid%mut(37,119)+grid%c2h(kk),grid%c1h(kk)*grid%muts(37,119)+grid%c2h(kk)])\n ENDDO\n")
 s=h.surround(s,'CALL small_step_finish(',before=" DO kk=5,12\n CALL td_row('smallfinish_before',1,kk,[grid%t_2(37,kk,119),grid%t_save(37,kk,119), &\n grid%c1h(kk)*grid%mut(37,119)+grid%c2h(kk),grid%c1h(kk)*grid%muts(37,119)+grid%c2h(kk), &\n grid%h_diabatic(37,kk,119),dts_rk,real(number_of_small_timesteps)])\n ENDDO\n",after=state('after_smallfinish'))
 s=h.surround(s,'CALL rk_scalar_tend (  im, im,',before=" CALL td_mode(0)\n IF(im==P_QV)CALL td_mode(2)\n"+qtend('q_scalar_before'),after=qtend('q_scalar_after'))
 s=h.surround(s,'CALL rk_update_scalar_pd( im, im,',before=qstock('q_pd_before','moist_old','grid%mu_1')+qtend('q_pd_source'),after=qstock('q_pd_after','moist_old','grid%mu_1'))
 s=h.surround(s,'CALL rk_update_scalar( scs=im,',before=" IF(rk_step==rk_order.AND.im==P_QV)THEN\n"+qstock('q_rk_base','moist_old','grid%mu_1')+qtend('q_rk_source')+f" CALL td_col('q_rk_advect',2,advect_tend({C}))\n DO kk=5,12\n CALL td_row('q_rk_factors',2,kk,[dt_rk,grid%msfty(37,119)])\n ENDDO\n ENDIF\n",after=" IF(rk_step==rk_order)THEN\n"+qstock('q_rk_after')+' ENDIF\n')
 s=s.replace('ENDDO moist_variable_loop','ENDDO moist_variable_loop\n CALL td_mode(0)',1)
 s=s.replace('   END DO Runge_Kutta_loop','   END DO Runge_Kutta_loop\n CALL td_context(0)\n'+state('after_rk'),1)
 s=h.surround(s,'CALL microphysics_driver(',before=state('micro_before')+" DO kk=5,12\n CALL td_row('micro_env_before',0,kk,[th_phy(37,kk,119),pi_phy(37,kk,119),p_phy(37,kk,119)])\n ENDDO\n",after=state('micro_after')+" DO kk=5,12\n CALL td_row('micro_env_after',0,kk,[th_phy(37,kk,119),pi_phy(37,kk,119),p_phy(37,kk,119)])\n ENDDO\n")
 s=h.surround(s,'CALL moist_physics_finish_em(',before=state('before_moistfinish'),after=state('after_moistfinish'))
 s=s.replace('   RETURN\n\nEND SUBROUTINE solve_em',state('end')+'   RETURN\n\nEND SUBROUTINE solve_em',1)
 ph=(root/'WRF/phys/module_physics_addtendc.F').read_text();ph=ph.replace('MODULE module_physics_addtendc','MODULE module_physics_addtendc\n USE module_thermodynamic_probe,ONLY:td_col',1)
 for name,label in [('phy_ra_ten','rad'),('phy_bl_ten','pbl'),('phy_cu_ten','cu')]:
  a,b=h.bounds(ph,'CALL '+name+'(');a=ph.rfind('\n   if ',0,a)+1
  snap=lambda tag:f" CALL td_col('{tag}_theta',1,rt_tendf({C}))\n CALL td_col('{tag}_qv',2,moist_tendf({C},P_QV))\n"
  ph=ph[:a]+snap(label+'_before')+ph[a:b]+'\n'+snap(label+'_after')+ph[b:]
 part2=(root/'WRF/dyn_em/module_first_rk_step_part2.F').read_text();part2=part2.replace('   USE module_state_description','   USE module_thermodynamic_probe,ONLY:td_col,td_row\n   USE module_state_description',1)
 if 'USE module_thermodynamic_probe' not in part2:
  m=part2.index('\n',part2.index('MODULE module_first_rk_step_part2'));part2=part2[:m]+'\n USE module_thermodynamic_probe,ONLY:td_col,td_row'+part2[m:]
 before=f" CALL td_col('convert_before_theta',1,t_tendf({C}))\n CALL td_col('convert_before_qv',2,moist_tend({C},P_QV))\n CALL td_col('convert_old_qv',2,moist_old({C},P_QV))\n CALL td_col('convert_old_t',1,grid%t_1({C}))\n"
 part2=h.surround(part2,'CALL conv_t_tendf_to_moist (',before=before,after=f" CALL td_col('convert_after_theta',1,t_tendf({C}))\n")
 em=(root/'WRF/dyn_em/module_em.F').read_text();em=em.replace('MODULE module_em\n','MODULE module_em\n USE module_thermodynamic_probe,ONLY:td_mode\n',1)
 # Only the theta call in rk_tendency, not scalar diffusion/advection calls.
 a=em.index('SUBROUTINE rk_tendency ');b=em.index('END SUBROUTINE rk_tendency',a);part=em[a:b]
 part=h.surround(part,'CALL advect_scalar ( t, t,',before=' CALL td_mode(1)\n',after=' CALL td_mode(0)\n');em=em[:a]+part+em[b:]
 ad=(root/'WRF/dyn_em/module_advect_em.F').read_text();ad=ad.replace('MODULE module_advect_em\n','MODULE module_advect_em\n USE module_thermodynamic_probe,ONLY:td_col,td_row\n',1)
 a=ad.index('SUBROUTINE advect_scalar   (');b=ad.index('END SUBROUTINE advect_scalar\n',a);part=ad[a:b]
 snap=lambda tag:f"\n CALL td_col('{tag}',-1,tendency({C}))\n"
 part=part.replace('!  begin with horizontal flux divergence',snap('theta_adv_pre')+'!  begin with horizontal flux divergence',1)
 part=part.replace('!-------------------- vertical advection',snap('theta_adv_h')+'!-------------------- vertical advection',1);part+=snap('theta_adv_z');ad=ad[:a]+part+ad[b:]
 a=ad.index('SUBROUTINE advect_scalar_pd ');b=ad.index('END SUBROUTINE advect_scalar_pd',a);part=ad[a:b]
 part=part.replace('! add in the pd-limited flux divergence',snap('q_adv_pre')+'! add in the pd-limited flux divergence',1);part=part.replace('! x flux divergence',snap('q_adv_z')+'! x flux divergence',1);part=part.replace('! y flux divergence',snap('q_adv_x')+'! y flux divergence',1);part+=snap('q_adv_y');ad=ad[:a]+part+ad[b:]
 small=(root/'WRF/dyn_em/module_small_step_em.F').read_text();small=small.replace('MODULE module_small_step_em','MODULE module_small_step_em\n USE module_thermodynamic_probe,ONLY:td_row',1)
 a=small.index('SUBROUTINE advance_mu_t(');b=small.index('END SUBROUTINE advance_mu_t',a);part=small[a:b]
 # Point calls stay inside original loops where wdtn is valid for this j.
 line='       t_ave(i,k,j) = t(i,k,j)';assert part.count(line)==1
 part=part.replace(line,"       IF(i==37.AND.j==119.AND.k>=5.AND.k<=12) &\n       CALL td_row('ac_before',step,k,[t(i,k,j),msfty(i,j),dts,ft(i,k,j)])\n"+line,1)
 line='       t   (i,k,j) = t(i,k,j) + msfty(i,j)*dts*ft(i,k,j)';part=part.replace(line,line+"\n       IF(i==37.AND.j==119.AND.k>=5.AND.k<=12) &\n       CALL td_row('ac_rhs_after',step,k,[t(i,k,j)])",1)
 marker='       ! multiplication by msfty uncouples result for Theta';assert part.count(marker)==1
 part=part.replace(marker,"""       IF(i==37.AND.j==119.AND.k>=5.AND.k<=12)THEN
       CALL td_row('ac_flux_operands',step,k,[dts,msfty(i,j),msftx(i,j),rdy,rdx,rdnw(k), &
       v(i,k,j+1),v(i,k,j),u(i+1,k,j),u(i,k,j), &
       t_1(i,k,j+1),t_1(i,k,j),t_1(i,k,j-1),t_1(i+1,k,j),t_1(i-1,k,j),wdtn(i,k+1),wdtn(i,k)])
       ENDIF
"""+marker,1)
 marker='             + rdnw(k)*( wdtn(i,k+1)-wdtn(i,k) ) )';assert part.count(marker)==1
 part=part.replace(marker,marker+"\n       IF(i==37.AND.j==119.AND.k>=5.AND.k<=12) &\n       CALL td_row('ac_flux_after',step,k,[t(i,k,j)])",1);small=small[:a]+part+small[b:]
 return {'solve_em.F':s,'module_physics_addtendc.F':ph,'module_first_rk_step_part2.F':part2,'module_em.F':em,'module_advect_em.F':ad,'module_small_step_em.F':small}
