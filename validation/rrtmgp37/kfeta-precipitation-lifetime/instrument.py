from pathlib import Path
import importlib.util
P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('kf_budget_i',P.parent/'real-case-budget/instrument.py');I=importlib.util.module_from_spec(s);s.loader.exec_module(I)
def transform(root):
 s=(root/'WRF/dyn_em/solve_em.F').read_text().replace('   USE module_state_description','   USE module_kfeta_lifetime_probe,ONLY:trace\n   USE module_state_description',1)
 hh=I.H
 def call(tag):return f" CALL trace('{tag}',curr_secs_r8,grid%dt,grid%rainc({hh}),grid%raincv({hh}), &\n grid%pratec({hh}),grid%nca({hh}),grid%cuppt({hh}))\n"
 s=I.surround(s,'CALL first_rk_step_part1 (',before=call('physics_before'),after=call('physics_after'))
 return I.surround(s,'CALL advance_ppt(',before=call('ppt_before'),after=call('ppt_after'))
