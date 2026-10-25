"""Reuse hourly native history; compile unchanged UDM saturation table/functions only."""
from pathlib import Path
import importlib.util,json,subprocess,hashlib
import numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-sterling-thermodynamics-v2';O.mkdir(exist_ok=False)
s=importlib.util.spec_from_file_location('runner',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
text=(R/'WRF/phys/module_mp_udm.F').read_text();params=text[text.index('   integer, parameter                  ::  nxsvp'):text.index('!-------------------------------------------------------------------------------\n! inline expansion table',text.index('   integer, parameter                  ::  nxsvp'))];params=params.replace(', private','')
routines=text[text.index('   subroutine udm_funct_svp_setup'):text.index('end module module_mp_udm')]
helper='module native_svp\n implicit none\n'+params+'\ncontains\n'+routines+'\nend module\nprogram main\n use native_svp\n implicit none\n real::p,q,pert,t,e1,e2,qs1,qs2\n integer::ios\n call udm_funct_svp_setup\n do\n read(*,*,iostat=ios)p,q,pert\n if(ios/=0)exit\n t=(pert+300.)*(p/100000.)**(287./(7.*287./2.))\n e1=fsvp_water(t,p);e2=fsvp(t,p)\n qs1=(287./461.6)*e1/(p-e1);qs2=(287./461.6)*e2/(p-e2)\n write(*,\'(7(es25.16e3,1x))\')t,e1,e2,qs1,qs2,q/qs1,q/qs2\n enddo\nend program\n'
(O/'native_saturation.f90').write_text(helper);rows=[]
file=B/'udm37-vapor-corrected-day-v2/host/wrfout_d01_2016-10-06_00:00:00'
with Dataset(file) as d:
 d.set_auto_maskandscale(False)
 meta={n:{'description':getattr(d[n],'description',''),'units':getattr(d[n],'units','')} for n in ['T','THM','P','PB','QVAPOR']}
 for hour in range(15,20):
  for j in range(89,100):
   for k in range(1,45):
    rows.append({'hour_UTC':hour,'j':j,'k':k,'pressure_Pa':float(np.float32(d['P'][hour,k-1,j-1,36]+d['PB'][hour,k-1,j-1,36])),'qv':float(d['QVAPOR'][hour,k-1,j-1,36]),'dry_perturbation_theta':float(d['T'][hour,k-1,j-1,36]),'condensate':{n:float(d[n][hour,k-1,j-1,36]) for n in ['QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL']}})
(O/'input.txt').write_text(''.join(f"{r['pressure_Pa']:.17g} {r['qv']:.17g} {r['dry_perturbation_theta']:.17g}\n" for r in rows))
runner=h.Runner(O,120,None,2);runner.run(['gfortran','-O2','-ffree-line-length-none',O/'native_saturation.f90','-o',O/'saturation'],O,'compile_unchanged_extracted_UDM_saturation_functions')
runner.run(['bash','-c','exec "$1" < "$2"','svp',O/'saturation',O/'input.txt'],O,'evaluate_actual_hourly_profiles_with_native_saturation_functions')
values=[list(map(float,l.split())) for l in (O/'command-02.stdout').read_text().splitlines()];assert len(values)==len(rows)
for r,v in zip(rows,values):r.update(dict(zip(['actual_T_K','es_water_Pa','es_native_phase_Pa','qs_water','qs_native_phase','RH_water_ratio','RH_native_phase_ratio'],v)))
summary=[]
for hour in range(15,20):
 for j in range(95,99):
  z=[r for r in rows if r['hour_UTC']==hour and r['j']==j];summary.append({'hour_UTC':hour,'j':j,'max_RH_water':max(x['RH_water_ratio'] for x in z),'max_RH_native_phase':max(x['RH_native_phase_ratio'] for x in z),'positive_condensate_layers':sum(sum(x['condensate'].values())>0 for x in z)})
result={'history':h.pin(file),'native_source':h.pin(R/'WRF/phys/module_mp_udm.F'),'metadata':meta,'commands':runner.commands,'profiles':rows,'summary':summary,'interpretation':'hourly dry theta diagnostic T plus300, native pressure and R_d/cp; unchanged UDM180–330K saturation lookup; native phase uses ice below273.16K and water above, not warm ice extrapolation; snapshot subsaturation is not a substep microphysics attribution','new_WRF_processes':0,'production_changes':False};(O/'thermodynamics.json').write_text(json.dumps(result,indent=2)+'\n');print('NATIVE_HOURLY_SATURATION',len(rows))
