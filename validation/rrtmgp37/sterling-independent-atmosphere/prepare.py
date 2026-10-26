"""Attach native water-saturation diagnostics to real observations and saved model states."""
from pathlib import Path
import json,importlib.util,os,shutil,hashlib
from parse import sounding,metars,require
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-sterling-independent-atmosphere-analysis-v1';N=B/'udm37-sterling-independent-atmosphere-saturation-v1'
def main():
 N.mkdir(exist_ok=False)
 hs=importlib.util.spec_from_file_location('runner',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(hs);hs.loader.exec_module(h)
 obs=[sounding(p.read_bytes()) for p in sorted((P/'raw').glob('sounding-*.txt'))];model=json.loads((O/'model-profiles.json').read_text());met=metars((P/'raw/asos.csv').read_bytes());inputs=[]
 for arm,sonde in enumerate(obs):
  for level in sonde['levels']:
   if level['p_Pa'] is None or level['T_K'] is None or level['z_agl_m'] is None or not 0<=level['z_agl_m']<=3000:continue
   for kind in ['T_K','Td_K']:
    if level[kind] is None:continue
    inputs.append({'kind':'observation_'+kind,'arm':arm,'record':level['record'],'T_K':level[kind],'p_Pa':level['p_Pa'],'qv_kg_kg':0.})
 for arm,row in enumerate(model['profiles']):
  for level in row['profiles']:
   if not 0<=level['z_agl_m']<=3000:continue
   inputs.append({'kind':'model','arm':arm,'record':level['record'],'T_K':level['T_K'],'p_Pa':level['p_Pa'],'qv_kg_kg':level['qv_kg_kg']})
 (N/'input.json').write_text(json.dumps(inputs,indent=2)+'\n');(N/'input.txt').write_text(''.join(f"{r['T_K']:.17g} {r['p_Pa']:.17g} {r['qv_kg_kg']:.17g}\n" for r in inputs))
 # Reproduce the already qualified scalar helper source from unchanged native functions.
 old=B/'udm37-sterling-cloud-loss-thermo-v1/native_saturation.f90';native=(R/'WRF/phys/module_mp_udm.F').read_text();a=native.index('   integer, parameter                  ::  nxsvp');params=native[a:native.index('!-------------------------------------------------------------------------------\n! inline expansion table',a)].replace(', private','');routines=native[native.index('   subroutine udm_funct_svp_setup'):native.index('end module module_mp_udm')]
 prefix='module native_svp\n implicit none\n'+params+'\ncontains\n'+routines+'\nend module\n';oldtext=old.read_text();require(oldtext.startswith(prefix),'native saturation functions changed')
 helper=N/'native_saturation.f90';helper.write_text(prefix+oldtext[len(prefix):]);run=h.Runner(N,120,os.environ.copy(),2)
 run.run(['gfortran','-O2','-ffree-line-length-none',helper,'-o',N/'saturation'],N,'compile_unchanged_native_scalar_saturation_functions')
 run.run(['bash','-c','exec "$1" < "$2"','svp',N/'saturation',N/'input.txt'],N,'actual_observation_and_existing_model_humidity_diagnostics')
 values=[list(map(float,l.split())) for l in (N/'command-02.stdout').read_text().splitlines()];require(len(values)==len(inputs),'native helper output count')
 for x,v in zip(inputs,values):
  if x['kind']=='model':model['profiles'][x['arm']]['profiles'][x['record']-1].update(es_water_Pa=v[0],qs_water_kg_kg=v[1],RH_water_ratio=v[2])
  else:
   row=obs[x['arm']]['levels'][x['record']-1]
   if x['kind']=='observation_T_K':row.update(es_water_Pa=v[0],qs_water_kg_kg=v[1])
   else:row['qv_from_dewpoint_kg_kg']=v[1]
 for sonde in obs:
  for level in sonde['levels']:
   level['RH_water_from_dewpoint_ratio']=level['qv_from_dewpoint_kg_kg']/level['qs_water_kg_kg'] if level.get('qv_from_dewpoint_kg_kg') is not None and level.get('qs_water_kg_kg') else None
 result={'soundings':obs,'surface_reports':met,'model':model,'humidity_convention':'observed qv derived from native water saturation mixing ratio at measuredTd and measuredp; observedRH_native=qv(Td,p)/qs(T,p), reportedIGRARH retained separately. ModelT diagnostic drytheta conversion is read asREAL32 by the same native helper; no missing data fill or supersaturation clipping','native_helper':{'commands':run.commands,'source':h.pin(helper),'executable':h.pin(N/'saturation'),'input':h.pin(N/'input.txt'),'input_schema':h.pin(N/'input.json'),'native_functions_match_prior_source':True,'native_MP_source':h.pin(R/'WRF/phys/module_mp_udm.F')},'new_WRF_RTE_Mie_runs':0}
 (O/'enriched.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');(N/'receipt.json').write_text(json.dumps(result['native_helper'],indent=2)+'\n');print('ACTUAL_OBSERVATION_NATIVE_SATURATION_EVALUATED',len(inputs),len(met))
if __name__=='__main__':main()
