"""Reuse the unchanged, already compiled scalar native saturation helper once."""
from common import *
import json,subprocess,datetime as dt,os,copy
O=B/'udm37-sterling-low-level-extract-v2';N=B/'udm37-sterling-low-level-native-v2'
def main():
 N.mkdir(exist_ok=False);data=json.loads((O/'extracted.json').read_text());inputs=[]
 groups=[('model',data['model']),('transect',data['transect']),('initial',[data['initial']])]
 for kind,group in groups:
  for arm,row in enumerate(group):
   for level in row['profiles']:
    if 0<=level['z_agl_m']<=3000:inputs.append({'group':kind,'arm':arm,'record':level['record'],'T_K':level['T_K'],'p_Pa':level['p_Pa'],'qv_kg_kg':level['qv_kg_kg']})
 for arm,row in enumerate(data['forcing']):
  for level in row['met_em']['profiles']:inputs.append({'group':'met_em','arm':arm,'record':level['record'],'T_K':level['T_K'],'p_Pa':level['p_Pa'],'qv_kg_kg':level['qv_kg_kg_REAL_method1_diagnostic']})
 (N/'input.json').write_text(json.dumps(inputs,indent=2)+'\n');text=''.join(f"{r['T_K']:.17g} {r['p_Pa']:.17g} {r['qv_kg_kg']:.17g}\n" for r in inputs);(N/'input.txt').write_text(text)
 prior=B/'udm37-sterling-independent-atmosphere-saturation-v1';exe=prior/'saturation';receipt=json.loads((prior/'receipt.json').read_text());require(pin(exe)['sha256']==receipt['executable']['sha256'],'helper executable changed')
 helper=(prior/'native_saturation.f90').read_bytes();require(hashlib.sha256(helper).hexdigest()==receipt['source']['sha256'],'helper source changed');(N/'native_saturation.f90').write_bytes(helper)
 source=(R/'WRF/phys/module_mp_udm.F').read_text();a=source.index('   integer, parameter                  ::  nxsvp');params=source[a:source.index('!-------------------------------------------------------------------------------\n! inline expansion table',a)].replace(', private','');routines=source[source.index('   subroutine udm_funct_svp_setup'):source.index('end module module_mp_udm')];require(helper.decode().startswith('module native_svp\n implicit none\n'+params+'\ncontains\n'+routines+'\nend module\n'),'native functions differ')
 started=dt.datetime.now(dt.timezone.utc).isoformat();proc=subprocess.Popen([str(exe)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,cwd=N);out,err=proc.communicate(text,timeout=120);(N/'stdout.txt').write_text(out);(N/'stderr.txt').write_text(err);require(proc.returncode==0,'scalar helper failed')
 command={'argv':[str(exe)],'pid':proc.pid,'started_UTC':started,'finished_UTC':dt.datetime.now(dt.timezone.utc).isoformat(),'returncode':proc.returncode,'executed_existing_binary':pin(exe),'helper_source':pin(N/'native_saturation.f90'),'input':pin(N/'input.txt'),'records':len(inputs),'compile_processes':0,'scalar_processes':1,'new_model_runs':0};(N/'receipt.json').write_text(json.dumps(command,indent=2)+'\n')
 values=[list(map(float,l.split())) for l in out.splitlines()];require(len(values)==len(inputs),'helper row count')
 for x,v in zip(inputs,values):
  group=next((g for n,g in groups if n==x['group']),None)
  if group is not None:row=group[x['arm']]['profiles'][x['record']-1]
  else:row=next(r for r in data['forcing'][x['arm']]['met_em']['profiles'] if r['record']==x['record'])
  row.update(es_water_Pa=v[0],qs_water_kg_kg=v[1],RH_water_ratio=v[2])
 data['native_helper']=command;(O/'enriched.json').write_text(json.dumps(data,indent=2,allow_nan=False)+'\n');print('UNCHANGED_SCALAR_SATURATION_EVALUATED',len(inputs))
if __name__=='__main__':main()
