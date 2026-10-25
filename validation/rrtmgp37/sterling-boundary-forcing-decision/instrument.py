"""Private observation of real native north relaxation and PD source boundaries."""
from pathlib import Path
import importlib.util
P=Path(__file__).resolve().parent

def transform(root):
 x=(root/'WRF/share/module_bc.F').read_text();needle='\nMODULE module_bc\n';assert x.count(needle)==1;x=x.replace(needle,needle+' USE module_sterling_boundary_probe,ONLY:core\n',1)
 a=x.index('   SUBROUTINE relax_bdytend_core');b=x.index('   END SUBROUTINE relax_bdytend_core',a);part=x[a:b];part=part.replace('      REAL       :: fls0, fls1, fls2, fls3, fls4','      REAL       :: fls0, fls1, fls2, fls3, fls4\n      REAL       :: obs_before',1)
 pos=part.index('! Y-end boundary');tail=part[pos:];needle='              field_tend(i,k,j) = field_tend(i,k,j) &';assert tail.count(needle)==3
 pos2=tail.index(needle);end=tail.index('\n',tail.index('- gcx(b_dist+1)*(fls1+fls2+fls3+fls4-4.*fls0)',pos2));tail=tail[:end]+'''
              CALL core(i,j,k,b_dist+1,dtbc,fcx(b_dist+1),gcx(b_dist+1),obs_before,field_tend(i,k,j), &
               [field(i,k,j),field(im1,k,j),field(ip1,k,j),field(i,k,j+1),field(i,k,j-1)], &
               [field_bdy_ye(i,k,b_dist+1),field_bdy_ye(im1,k,b_dist+1),field_bdy_ye(ip1,k,b_dist+1), &
                field_bdy_ye(i,k,b_dist),field_bdy_ye(i,k,b_dist+2)], &
               [field_bdy_tend_ye(i,k,b_dist+1),field_bdy_tend_ye(im1,k,b_dist+1),field_bdy_tend_ye(ip1,k,b_dist+1), &
                field_bdy_tend_ye(i,k,b_dist),field_bdy_tend_ye(i,k,b_dist+2)], &
               [fls0,fls1,fls2,fls3,fls4])
'''+tail[end:];tail=tail[:pos2]+'              obs_before=field_tend(i,k,j)\n'+tail[pos2:];part=part[:pos]+tail;x=x[:a]+part+x[b:]
 solve=(root/'WRF/dyn_em/solve_em.F').read_text();needle='   USE module_state_description';assert needle in solve;solve=solve.replace(needle,'   USE module_sterling_boundary_probe,ONLY:begin_call,accepted,pdpoint\n'+needle,1)
 s=importlib.util.spec_from_file_location('native_bounds',P.parent/'real-case-budget/instrument.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
 a,b=m.bounds(solve,'CALL relax_bdy_scalar ( moist_tend');before=''' CALL begin_call(im,[P_QV,P_QC,P_QI,P_QR,P_QS,P_QG,P_QH],rk_step,curr_secs_r8, &
  grid%dt,dt_rk,grid%spec_zone,grid%relax_zone,config_flags%spec_exp,grid%fcx(2:5),grid%gcx(2:5))
''';after='''
 CALL accepted(moist(37,kds:kde-1,95:98,im),moist_tend(37,kds:kde-1,95:98,im), &
  grid%mut(37,95:98),grid%c1h(kds:kde-1),grid%c2h(kds:kde-1))
''';solve=solve[:a]+before+solve[a:b]+after+solve[b:]
 a,b=m.bounds(solve,'CALL rk_update_scalar_pd( im, im')
 def snap(label):return f" CALL pdpoint('{label}',curr_secs_r8,im,dt_rk,grid%c1h(kds:kde-1),grid%c2h(kds:kde-1), &\n (grid%mu_1(37,95:98)+grid%mub(37,95:98)),moist_old(37,kds:kde-1,95:98,im),moist_tend(37,kds:kde-1,95:98,im))\n"
 solve=solve[:a]+snap('pd_before')+solve[a:b]+'\n'+snap('pd_after')+solve[b:]
 return {'module_bc.F':x,'solve_em.F':solve}
