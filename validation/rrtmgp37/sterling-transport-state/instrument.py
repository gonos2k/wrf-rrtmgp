"""Capture only missing final-RK face operands/coordinates, with original arithmetic untouched."""
from pathlib import Path
import importlib.util,re

def transform(root):
 spec=importlib.util.spec_from_file_location('h',root/'validation/rrtmgp37/real-case-budget/instrument.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
 s=(root/'WRF/dyn_em/solve_em.F').read_text();s=s.replace('   USE module_state_description','   USE module_transport_probe\n   USE module_state_description',1)
 marker='   Runge_Kutta_loop:  DO rk_step = 1, rk_order';assert s.count(marker)==1
 s=s.replace(marker,' CALL ts_setup(curr_secs_r8)\n'+marker+'\n CALL ts_context(rk_step)\n',1)
 geometry=""" DO kk=4,12
 CALL ts_row('geometry',0,kk,[grid%t_2(37,kk,119),moist(37,kk,119,P_QV), &
 grid%p(37,kk,119),grid%pb(37,kk,119),grid%ph_2(37,kk,119),grid%phb(37,kk,119), &
 grid%w_2(37,kk,119),grid%ww(37,kk,119),grid%mu_2(37,119),grid%mub(37,119), &
 grid%mut(37,119),grid%c1h(kk),grid%c2h(kk),grid%c1f(kk),grid%c2f(kk), &
 grid%dnw(kk),grid%znu(kk),grid%znw(kk),grid%msfty(37,119)])
 ENDDO
"""
 s=h.surround(s,'CALL rk_tendency (',before=geometry)
 s=h.surround(s,'CALL rk_scalar_tend (  im, im,',before=' CALL ts_mode(0)\n IF(im==P_QV)CALL ts_mode(2)\n',after=' CALL ts_mode(0)\n')
 em=(root/'WRF/dyn_em/module_em.F').read_text().replace('MODULE module_em\n','MODULE module_em\n USE module_transport_probe,ONLY:ts_mode\n',1)
 a=em.index('SUBROUTINE rk_tendency ');b=em.index('END SUBROUTINE rk_tendency',a);part=em[a:b];part=h.surround(part,'CALL advect_scalar ( t, t,',before=' CALL ts_mode(1)\n',after=' CALL ts_mode(0)\n');em=em[:a]+part+em[b:]
 ad=(root/'WRF/dyn_em/module_advect_em.F').read_text().replace('MODULE module_advect_em\n','MODULE module_advect_em\n USE module_transport_probe,ONLY:ts_row\n',1)
 a=ad.index('SUBROUTINE advect_scalar   (');b=ad.index('END SUBROUTINE advect_scalar\n',a);part=ad[a:b]
 # vflux is a j-local temporary. Capture inside the very loops which consume it.
 pattern=r'(?m)^(\s*tendency\(i,k,j\)=tendency\(i,k,j\)-rdzw\(k\)\*\(vflux\(i,k\+1\)-vflux\(i,k\)\))$'
 before="""       IF(i==37.AND.j==119.AND.k>=7.AND.k<=8)THEN
       CALL ts_row('theta_before',-1,k,[tendency(i,k,j),rdzw(k),rom(i,k,j),rom(i,k+1,j), &
       vflux(i,k),vflux(i,k+1),real(vert_order),real(time_step)])
       CALL ts_row('theta_stencil',-1,k,[field(i,k-3,j),field(i,k-2,j),field(i,k-1,j), &
       field(i,k,j),field(i,k+1,j),field(i,k+2,j),field(i,k+3,j)])
       ENDIF
"""
 after="""
       IF(i==37.AND.j==119.AND.k>=7.AND.k<=8) &
       CALL ts_row('theta_after',-1,k,[tendency(i,k,j)])"""
 part,n=re.subn(pattern,lambda m:before+m[0]+after,part);assert n==5,n;ad=ad[:a]+part+ad[b:]
 a=ad.index('SUBROUTINE advect_scalar_pd ');b=ad.index('END SUBROUTINE advect_scalar_pd',a);part=ad[a:b]
 snap="""
 DO k=7,8
 CALL ts_row('q_before',-1,k,[tendency(37,k,119),rdzw(k),rom(37,k,119),rom(37,k+1,119), &
 fqz(37,k,119),fqz(37,k+1,119),fqzl(37,k,119),fqzl(37,k+1,119), &
 dt,msfty(37,119),real(config_flags%v_sca_adv_order)])
 CALL ts_row('q_stencil',-1,k,[field(37,k-3,119),field(37,k-2,119),field(37,k-1,119), &
 field(37,k,119),field(37,k+1,119),field(37,k+2,119),field(37,k+3,119)])
 CALL ts_row('q_old_stencil',-1,k,[field_old(37,k-3,119),field_old(37,k-2,119),field_old(37,k-1,119), &
 field_old(37,k,119),field_old(37,k+1,119),field_old(37,k+2,119),field_old(37,k+3,119)])
 ENDDO
"""
 part=part.replace('! add in the pd-limited flux divergence',snap+'\n! add in the pd-limited flux divergence',1)
 part=part.replace('! x flux divergence'," DO k=7,8\n CALL ts_row('q_after',-1,k,[tendency(37,k,119)])\n ENDDO\n! x flux divergence",1);ad=ad[:a]+part+ad[b:]
 return {'solve_em.F':s,'module_em.F':em,'module_advect_em.F':ad}
if __name__=='__main__':
 r=Path(__file__).resolve().parents[3]
 for n,s in transform(r).items():print(n,len(s))
