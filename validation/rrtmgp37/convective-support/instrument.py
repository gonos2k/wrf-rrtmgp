"""Reuse the completed PR191 observer; add bounded CU/precipitation reductions only."""
from pathlib import Path
import importlib.util
P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('prior_budget_instrument',P.parent/'real-case-budget/instrument.py');I=importlib.util.module_from_spec(s);s.loader.exec_module(I)
def transform(root):
 out=I.transform(root);s=out['solve_em.F'];H=I.H;SL=I.SL
 s=s.replace('ONLY:setup,stock,tend,adv,surface,radiation,frozen_end','ONLY:setup,stock,tend,adv,surface,radiation,frozen_end,precip,cu_context,cu_expiry')
 def prec(tag):return f" CALL precip('{tag}',grid%rainc({H}),grid%rainnc({H}),grid%rainsh({H}),grid%qfx({H}))\n"
 s=s.replace('   Runge_Kutta_loop:  DO rk_step = 1, rk_order',prec('precip_start')+'   Runge_Kutta_loop:  DO rk_step = 1, rk_order',1)
 s=I.surround(s,'CALL first_rk_step_part2 (',before=f" CALL cu_context(grid%nca({H}),grid%pratec({H}),grid%pratesh({H}))\n")
 args=f"grid%nca({H}),grid%pratec({H}),grid%rqvcuten({SL}), &\n grid%rqccuten({SL}),grid%rqrcuten({SL}),grid%rqicuten({SL}),grid%rqscuten({SL})"
 s=I.surround(s,'CALL advance_ppt(',before=prec('precip_before_advance')+f" CALL cu_expiry('expiry_before',grid%dt,{args})\n",after=prec('precip_after_advance')+f" CALL cu_expiry('expiry_after',grid%dt,{args})\n")
 s=I.surround(s,'CALL microphysics_driver(',before=prec('precip_micro_before'),after=prec('precip_micro_after'))
 s=s.replace('   RETURN\n\nEND SUBROUTINE solve_em',prec('precip_end')+'   RETURN\n\nEND SUBROUTINE solve_em',1);out['solve_em.F']=s
 ph=out['module_physics_addtendc.F'].replace('ONLY:thermal,tend','ONLY:thermal,tend,cu_columns')
 args='RQVCUTEN(ids:ide-1,kds:kde-1,jds:jde-1),RQCCUTEN(ids:ide-1,kds:kde-1,jds:jde-1), &\n RQRCUTEN(ids:ide-1,kds:kde-1,jds:jde-1),RQICUTEN(ids:ide-1,kds:kde-1,jds:jde-1), &\n RQSCUTEN(ids:ide-1,kds:kde-1,jds:jde-1)'
 ph=I.surround(ph,'CALL phy_cu_ten(',after=f" CALL cu_columns({args})\n")
 # Preserve the native IF/CALL continuation: the addition is after the completed call.
 out['module_physics_addtendc.F']=ph
 return out
