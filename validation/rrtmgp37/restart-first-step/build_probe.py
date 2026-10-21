#!/usr/bin/env python3
from pathlib import Path
import importlib.util,json,os,shutil,hashlib
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-restart-first-probe-build-v1';O.mkdir(exist_ok=False);M=O/'modules';M.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
base=B/'udm37-specified-number-build-v1';receipt=json.loads((base/'receipt.json').read_text())
sp=importlib.util.spec_from_file_location('old_source',R/'validation/rrtmgp37/historical-source/binding.py');hist=importlib.util.module_from_spec(sp);sp.loader.exec_module(hist)
old_bytes=hist.historical_bytes(R,'WRF/dyn_em/solve_em.F',receipt['sources']['dyn_em/solve_em.F']['sha256'])
original=old_bytes.decode();text=original.replace('   USE module_state_description','   USE module_restart_first_step_probe\n   USE module_state_description',1)
local3='ru_tendf rv_tendf rw_tendf ph_tendf t_tendf rw_tend ph_tend t_tend w_save ph_save c2a pm1 cqu cqv cqw'.split()
def call(tag,rk='rk_step',iteration='0',locals=False):
 out=f"\n IF(curr_secs_r8==21540.d0.OR.curr_secs_r8==21600.d0)THEN\n CALL begin_probe('{tag}',grid,curr_secs_r8,curr_secs2_r8,{rk},{iteration})\n"
 if locals:
  for n in local3:out+=f" CALL array3('{n}',{n}(max(ims,19):min(ime,27),1:min(kme,kde),max(jms,jde-8):min(jme,jde)))\n"
  for n in ['mu_tend','mu_tendf','mu_save']:out+=f" CALL array2('{n}',{n}(max(ims,19):min(ime,27),max(jms,jde-8):min(jme,jde)))\n"
 for field,idx,n in [('moist','P_QV','qv'),('scalar','P_QNC','qnc'),('scalar','P_QNR','qnr'),('scalar','P_QNN','qnn')]:out+=f" CALL array3('{n}',{field}(max(ims,19):min(ime,27),1:min(kme,kde),max(jms,jde-8):min(jme,jde),{idx}))\n"
 return out+' CALL end_probe()\n ENDIF\n'
def after(anchor,tag,**kw):
 global text
 assert text.count(anchor)==1,(tag,text.count(anchor))
 text=text.replace(anchor,anchor+call(tag,**kw),1)
after('   curr_mins2 = REAL( curr_secs2_r8 / 60.0d0 )','entry',rk='0')
for anchor,tag in [('BENCH_END(step_prep_tim)','rk_prep'),('BENCH_END(set_phys_bc_tim)','pre_physics')]:after(anchor,tag)
after('                             , feedback_is_ready=feedback_is_ready    &\n                            )','physics_part1',locals=True)
after('     END IF rk_step_is_one','physics_part2',locals=True)
for anchor,tag in [('BENCH_END(rk_tend_tim)','rk_tend'),('BENCH_END(relax_bdy_dry_tim)','dry_boundaries'),('BENCH_END(small_step_prep_tim)','small_prep'),('BENCH_END(small_step_finish_tim)','small_finish')]:after(anchor,tag,locals=True)
after('BENCH_END(phys_bc_tim)','acoustic_end',iteration='iteration',locals=True)
after('BENCH_END(bc_end_tim)','rk_end',locals=True)
(O/'solve_em_probe.F').write_text(text)
runner=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},8)
argv=receipt['commands'][3]['argv'];assert str(argv[-3]).endswith('solve_em.F')
# Reuse exact solve flags; new probe modules come first, while unchanged modules
# come from the same retained general build as the original failed trajectory.
opts=argv[1:-4];opts=[x for x in opts if not x.startswith('-J')]+['-I'+str(M),'-J'+str(M)]
# Insert the current probe module search path before all inherited module paths.
opts=['-I'+str(M)]+opts
for src,obj in [(P/'probe.f90',O/'probe.o'),(O/'solve_em_probe.F',O/'solve_em.F.o')]:runner.run(['gfortran',*opts,'-c',src,'-o',obj],O,'compile_'+obj.stem)
lib=O/'libWRF_Core.a';shutil.copyfile(base/'libWRF_Core.a',lib);runner.run(['ar','r',lib,O/'solve_em.F.o',O/'probe.o'],O,'replace_probe_object')
link=[str(x).replace(str(base/'libWRF_Core.a'),str(lib)).replace(str(base/'wrf'),str(O/'wrf')) for x in receipt['commands'][-1]['argv']];runner.run(link,O,'link_probe_WRF')
h.write_json(O/'receipt.json',{'commands':runner.commands,'original_solve':{'sha256':hashlib.sha256(old_bytes).hexdigest(),'source_scope':'historical_PR188_snapshot'},'instrumented':h.pin(O/'solve_em_probe.F'),'probe':h.pin(P/'probe.f90'),'base_library':h.pin(base/'libWRF_Core.a'),'executable':h.pin(O/'wrf'),'purpose':'diagnostic only; no public production edits','production_accepted':False})
print('FIRST_STEP_PROBE_BUILD_COMPLETE')
