"""Only three read-only observer calls; all production assignments retained."""
from pathlib import Path
import importlib.util
P=Path(__file__).resolve().parent

def transform(root):
 sw=(root/'WRF/phys/module_ra_rrtmg_sw.F').read_text();marker='   USE module_ra_rrtmgp_trace, ONLY: trace_start'
 assert sw.count(marker)==1;sw=sw.replace(marker,'   USE module_sterling_cloud_probe,ONLY:inputs,returns\n'+marker,1)
 pos=sw.index('         IF(gp_batch_enabled) THEN',sw.index('gp_seed=rrtmgp_column_seed'))
 call='''         IF(run_rrtmgp.AND.use_cu_population)CALL inputs(i,j,audit_time,t3d(i,kts:kte,j), &
          p3d(i,kts:kte,j),udm_dry_layer_mass(i,kts:kte,j),qv3d(i,kts:kte,j), &
          qc3d(i,kts:kte,j),qi3d(i,kts:kte,j),qr3d(i,kts:kte,j),qs3d(i,kts:kte,j), &
          qg3d(i,kts:kte,j),qh3d(i,kts:kte,j),cldfrac(1,kts:kte),cldfra3d(i,kts:kte,j), &
          udm_cldfra(i,kts:kte,j),gp_grid,gp_rad,gp_sizes,gp_cu_grid,gp_cu_lwp(1,kts:kte), &
          gp_cu_iwp(1,kts:kte),gp_cu_rel(1,kts:kte),gp_cu_rei(1,kts:kte))
'''
 sw=sw[:pos]+call+sw[pos:];marker='   END SUBROUTINE scatter_sw_column';assert sw.count(marker)==1
 sw=sw.replace(marker,'''      IF(run_rrtmgp)CALL returns(dest_i,dest_j,audit_time,coszrs,swdflx(1,1),swdflxc(1,1), &
       swdkdir_predelta(1,1),swdkdirc_predelta(1,1),swdkdir(1,1),swdkdirc(1,1))
'''+marker,1)
 first=(root/'WRF/dyn_em/module_first_rk_step_part1.F').read_text();first=first.replace('MODULE module_first_rk_step_part1\n','MODULE module_first_rk_step_part1\n USE module_sterling_cloud_probe,ONLY:held\n',1)
 s=importlib.util.spec_from_file_location('bounds',P.parent/'real-case-budget/instrument.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
 a,b=m.bounds(first,'CALL radiation_driver(')
 first=first[:b]+'''\n      CALL held(curr_secs,grid%dt,grid%swdnb(37,89:99),grid%swdnbc(37,89:99), &
       grid%swddir(37,89:99),grid%swddif(37,89:99),grid%acswdnb(37,89:99),grid%acswdnbc(37,89:99))
'''+first[b:]
 return {'module_ra_rrtmg_sw.F':sw,'module_first_rk_step_part1.F':first}
