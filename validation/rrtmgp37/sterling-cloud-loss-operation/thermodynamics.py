"""Native saturation functions at actual microphysics input/output states only."""
from pathlib import Path
import importlib.util,json,os
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent
s=importlib.util.spec_from_file_location('native_analysis',P/'analyze.py');A=importlib.util.module_from_spec(s);s.loader.exec_module(A)
def evaluate(text,output):
 output.mkdir(exist_ok=False)
 hs=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(hs);hs.loader.exec_module(h)
 native=(R/'WRF/phys/module_mp_udm.F').read_text();a=native.index('   integer, parameter                  ::  nxsvp');params=native[a:native.index('!-------------------------------------------------------------------------------\n! inline expansion table',a)].replace(', private','')
 routines=native[native.index('   subroutine udm_funct_svp_setup'):native.index('end module module_mp_udm')]
 helper='module native_svp\n implicit none\n'+params+'\ncontains\n'+routines+'\nend module\nprogram main\n use native_svp\n implicit none\n real::t,p,q,e,qs\n integer::ios\n call udm_funct_svp_setup\n do\n read(*,*,iostat=ios)t,p,q\n if(ios/=0)exit\n e=fsvp_water(t,p)\n qs=(287./461.6)*e/(p-e)\n write(*,\'(3(es25.16e3,1x))\')e,qs,q/qs\n enddo\nend program\n'
 (output/'native_saturation.f90').write_text(helper);d,_,_=A.parse(text);rows=[]
 for t in range(60600,65400,60):
  for stage in ['before','after']:
   for k in [5,6,7]:
    th,pi,p=d[t,'micro_env_'+stage,0,0,k];q=d[t,'micro_'+stage,0,1,k][0]
    rows.append({'source_seconds':t,'stage':stage,'k':k,'theta_K':th,'Exner':pi,'actual_T_from_native_product_K':A.f32(th*pi),'p_Pa':p,'qv':q})
 (output/'input.txt').write_text(''.join(f"{r['actual_T_from_native_product_K']:.17g} {r['p_Pa']:.17g} {r['qv']:.17g}\n" for r in rows))
 run=h.Runner(output,120,{**os.environ},2)
 run.run(['gfortran','-O2','-ffree-line-length-none',output/'native_saturation.f90','-o',output/'saturation'],output,'compile_unchanged_extracted_UDM_saturation_functions')
 run.run(['bash','-c','exec "$1" < "$2"','native-svp',output/'saturation',output/'input.txt'],output,'native_saturation_at_actual_local_microphysics_states')
 vals=[list(map(float,l.split())) for l in (output/'command-02.stdout').read_text().splitlines()];A.require(len(vals)==len(rows),'native saturation output count')
 for r,v in zip(rows,vals):r.update(dict(zip(['es_water_Pa','qs_water_kg_kg','RH_water_ratio'],v)))
 result={'native_source':h.pin(R/'WRF/phys/module_mp_udm.F'),'helper':h.pin(output/'native_saturation.f90'),'commands':run.commands,'states':rows,'scope':'same unchanged native saturation lookup only, at recorded actualmicrophysics theta,Exner,pressure andmoisture; f32(theta*Exner) reconstructs the driver temperature convention; no full UDM/WRF/Mie/RTE launch and no tuning','new_model_runs':0}
 (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
 evaluate((B/'udm37-sterling-cloud-loss-run-v1/host/cloud_operations.txt').read_text(),B/'udm37-sterling-cloud-loss-thermo-v1')
