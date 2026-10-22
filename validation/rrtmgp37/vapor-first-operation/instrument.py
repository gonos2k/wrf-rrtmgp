from pathlib import Path
import importlib.util
P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('budget_instrument',P.parent/'real-case-budget/instrument.py');I=importlib.util.module_from_spec(s);s.loader.exec_module(I)
def transform(root, source=None):
 s=source if source is not None else (root/'WRF/dyn_em/solve_em.F').read_text()
 s=s.replace('   USE module_state_description','   USE module_vapor_first_probe, ONLY:begin_step,capture,examine\n   USE module_state_description',1)
 s=s.replace('   Runge_Kutta_loop:  DO rk_step = 1, rk_order',' CALL begin_step(curr_secs_r8)\n   Runge_Kutta_loop:  DO rk_step = 1, rk_order',1)
 sl=I.SL;hh=I.H;v=I.V
 def cap(tag,field,dt='dt_rk',rk='rk_step',adv=None,mnew='grid%mu_2'):
  adv=adv or f'moist_tend({sl},P_QV)*0.'
  return f" IF(im==P_QV)CALL capture('{tag}',{rk},{dt},{field}({sl},P_QV),moist_old({sl},P_QV), &\n moist_tend({sl},P_QV),{adv},grid%mu_1({hh}),{mnew}({hh}),grid%mub({hh}), &\n grid%c1h({v}),grid%c2h({v}),grid%msfty({hh}))\n"
 def end(field):return f' IF(im==P_QV)CALL examine({field}({sl},P_QV))\n'
 s=I.surround(s,'CALL rk_update_scalar_pd( im, im,',before=cap('pd','moist_old',mnew='grid%mu_1'),after=end('moist_old'))
 s=I.surround(s,'CALL rk_update_scalar( scs=im,',before=cap('rk','moist',adv=f'advect_tend({sl})'),after=end('moist'))
 # Microphysics/final assignments are separately bounded. Their generic operand
 # fields are not interpreted as the scalar-update formula in analysis.
 before=cap('micro','moist',dt='grid%dt',rk='0').replace('IF(im==P_QV)','')
 after=end('moist').replace('IF(im==P_QV)','')
 s=I.surround(s,'CALL microphysics_driver(',before=before,after=after)
 s=I.surround(s,'CALL spec_bdy_final   ( moist(ims,kms,jms,im)',before=cap('final_bdy','moist'),after=end('moist'))
 return s
