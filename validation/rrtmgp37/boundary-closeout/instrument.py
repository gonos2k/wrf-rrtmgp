"""Exact private IO-only transformation of unchanged native sources."""
import re
def instrument(public_bc,public_solve):
 bc=public_bc.replace('MODULE module_bc\n','MODULE module_bc\n   USE module_boundary_closeout_probe, ONLY: cbo_selected,cbo_emit\n',1)
 assign='''              field_tend(i,k,j) = field_tend(i,k,j) &
                                + fcx(b_dist+1)*fls0 &
                                - gcx(b_dist+1)*(fls1+fls2+fls3+fls4-4.*fls0)'''
 start=bc.index('   SUBROUTINE relax_bdytend_core');end=bc.index('   END SUBROUTINE relax_bdytend_core',start);part=bc[start:end];assert part.count(assign)==4
 before='''              IF(cbo_selected(i,k,j,1)) CALL cbo_emit('relax-before', &
                [field_tend(i,k,j),field(i,k,j),field_bdy_ys(i,k,b_dist+1), &
                 field_bdy_tend_ys(i,k,b_dist+1),dtbc,fcx(b_dist+1),gcx(b_dist+1), &
                 fls0,fls1,fls2,fls3,fls4])
'''
 after="\n              IF(cbo_selected(i,k,j,1)) CALL cbo_emit('relax-after',[field_tend(i,k,j)])"
 # Only the first (YS) arm is observed; all native assignments stay verbatim.
 part=part.replace(assign,before+assign+after,1);bc=bc[:start]+part+bc[end:]
 start=bc.index('   SUBROUTINE spec_bdy_final');end=bc.index('   END SUBROUTINE spec_bdy_final',start);part=bc[start:end]
 assignment='              field(i,k,j) = xmsf*bfield/xmu';assert part.count(assignment)==4
 part=part.replace(assignment,assignment+'''\n              IF(cbo_selected(i,k,j,2)) CALL cbo_emit('final', &
                [field_bdy_ys(i,k,b_dist+1),field_bdy_tend_ys(i,k,b_dist+1), &
                 dtbc,bfield,xmu,xmsf,field(i,k,j),mu(i,j),c1(k),c2(k)])''',1)
 bc=bc[:start]+part+bc[end:]
 solve=public_solve.replace('   USE module_state_description','   USE module_boundary_closeout_probe, ONLY:cbo_context,cbo_clear,cbo_emit\n   USE module_state_description',1)
 for kind,needle in [('relax','CALL relax_bdy_scalar ( scalar_tend'),('final','CALL spec_bdy_final   ( scalar(ims,kms,jms,is), grid%muts')]:
  pos=solve.index(needle);line=solve.rfind('\n',0,pos)+1;ending=re.search(r'k_start\s*,\s*k_end\s*\)',solve[pos:]);assert ending;end=pos+ending.end()
  code="""               CALL cbo_clear()
               IF(is==P_QNC)CALL cbo_context(1,curr_secs_r8,rk_step)
               IF(is==P_QNR)CALL cbo_context(2,curr_secs_r8,rk_step)
"""
  tail="\n               CALL cbo_clear()"
  if kind=='relax':
   code+="               IF(is==P_QNC.OR.is==P_QNR)CALL cbo_emit('wrapper-before',[scalar_tend(24,1,2,is)])\n"
   tail="\n               IF(is==P_QNC.OR.is==P_QNR)CALL cbo_emit('wrapper-after',[scalar_tend(24,1,2,is)])"+tail
  else:tail="\n               IF(is==P_QNC.OR.is==P_QNR)CALL cbo_emit('solve-final', &\n                 [scalar(24,1,1,is),grid%muts(24,1),grid%mu_2(24,1),grid%mub(24,1), &\n                  grid%c1h(1),grid%c2h(1),grid%dtbc])"+tail
  solve=solve[:line]+code+solve[line:end]+tail+solve[end:]
 return bc,solve
