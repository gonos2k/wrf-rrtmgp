from pathlib import Path
import importlib.util,json,os,re,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-frozen-important-rte-v2';O.mkdir(exist_ok=False)
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=load('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');p=load('selected_packets',P/'packets.py')
cap=B/'udm37-frozen-selected-capture-v1/host/capture';head,x=p.read((cap/'lw.input').read_bytes(),'input');_,raw=p.read((cap/'lw.raw').read_bytes(),'raw');_,actual=p.read((cap/'lw.result').read_bytes(),'result')
target=json.loads((B/'udm37-frozen-selected-selection-v1/target.json').read_text());reference=json.loads((B/'udm37-frozen-important-reference-v2/result.json').read_text());original=json.loads((B/'udm37-frozen-important-original-v1/result.json').read_text())
assert reference['completed'] and reference['all_numerical_axes_qualified'];assert raw['SOURCE_TIME_SECONDS']['values']==[3000.] and raw['RADIATION_STEP']['values']==[51.]
nl=head[2];nn=x['NATIVE_DRY_LAYER_MASS_KG_M2']['shape'][1];k=target['native_layer']-1
assert x['TLAY']['values'][k]==target['temperature_K'] and x['HWP']['values'][k]==target['layer_hail_path_g_m2'] and x['LAMBDA_H']['values'][k]==target['lambda_m_1']
assert 'NATIVE_CAPACITY_J_M2_K' not in actual and 'UNIFORM_CF0_LWP' not in raw
assert x['EMIS']['shape']==[1,16] and x['CU_POPULATION_POLICY']['values']==[1.]
fields=['PLAY','PLEV','TLAY','TLEV','TSFC','EMIS','H2O','CO2','O3','N2O','CH4','O2','VMR_CFC11','VMR_CFC12','VMR_CFC22','VMR_CCL4','CF','LWP','IWP','SWP','RWP','REL','REI','RES','NATIVE_DRY_LAYER_MASS_KG_M2','GWP','HWP','LAMBDA_G','LAMBDA_H','CU_LWP','CU_IWP','CU_REL','CU_REI']
text=' '.join(map(str,[nl,nn,head[4],head[3],head[5],int(x['ICE_ROUGHNESS']['values'][0])]))+'\n'+' '.join(format(x[n]['values'][0],'.17e') for n in ['GRAVITY','CP_DRY','MOL_WEIGHT_DRY'])+'\n'+'\n'.join(' '.join(format(v,'.17e') for v in x[n]['values']) for n in fields)+'\n'
(O/'input.dat').write_text(text)
nml=(B/'udm37-frozen-selected-capture-v1/host/namelist.input').read_text();data=Path(re.search(r"rrtmgp_data_path\s*=\s*'([^']+)'",nml,re.I)[1]);table=Path(re.search(r"rrtmgp_udm_frozen_table\s*=\s*'([^']+)'",nml,re.I)[1])
env={k:v for k,v in os.environ.items() if not k.startswith(('WRF_RRTMGP_','WRF_UDM_','WRF_RESEARCH_','WRF_RADIATION_ENERGY'))};env.update(LD_LIBRARY_PATH=str(B/'deps/netcdf/lib'),OMP_NUM_THREADS='1')
r=h.Runner(O,180,env,6);receipt={'input_capture':h.pin(cap/'lw.input'),'actual_result':h.pin(cap/'lw.result'),'state':target,'reference':h.pin(B/'udm37-frozen-important-reference-v2/result.json'),'original_direct':h.pin(B/'udm37-frozen-important-original-v1/result.json'),'table':h.pin(table),'runs':[],'commands':[],'new_WRF_runs':0,'physical_accuracy_approved':False}
for mode in ['public_A','diagnostic_A','original_direct','fine','radius_half','spectral_half']:
 d=O/mode;d.mkdir();(d/'capture').mkdir();shutil.copyfile(O/'input.dat',d/'input.dat');coefficient='-'
 if mode not in ['public_A','diagnostic_A']:
  if mode=='original_direct':coeff=[b['moments'][3][0]/912. for b in original['bands']]
  else:coeff=[b['levels'][-1][mode]['moments_m2_kg']['abs'] for b in reference['records']]
  line=' '.join(format(target[n],'.17e') if n!='native_layer' else str(target[n]) for n in ['native_layer','temperature_K','lambda_m_1','layer_hail_path_g_m2'])
  (d/'coefficients.dat').write_text(line+'\n'+' '.join(format(v,'.17e') for v in coeff)+'\n');coefficient=str(d/'coefficients.dat')
 exe=B/'udm37-frozen-reference-column-v2'/('public' if mode=='public_A' else 'diagnostic');r.environment.update(WRF_RRTMGP_CAPTURE_DIR=str(d/'capture'),WRF_RRTMGP_CAPTURE_CALL='1')
 log=r.run([exe,data,d/'input.dat',table,coefficient],d,mode).read_text();assert 'ACTUAL_FROZEN_STATE_COLUMN_COMPLETE' in log
 _,got=p.read((d/'capture/lw.result').read_bytes(),'result')
 if mode in ['public_A','diagnostic_A']:
  for name,v in actual.items():
   if not name.startswith('WRF_'):assert got[name]==v,(mode,name)
 for name in ['GAS_COL_DRY','VMR_N2','GAS_TAU','NATIVE_CLOUD_TAU','CU_CLOUD_TAU','PRECIP_TAU','CLOUD_TAU','PREPARED_TAU','RL_USED','DI_USED','DS_USED','MASK','GRAUPEL_TAU_ABS','UPC','DNC','HRC']:
  assert got[name]==actual[name],(mode,name)
 if mode not in ['public_A','diagnostic_A']:
  shape=actual['HAIL_TAU_ABS']['shape'];n=shape[1]
  for band in range(16):
   for level in range(n):
    if level!=k:assert got['HAIL_TAU_ABS']['values'][level+n*band]==actual['HAIL_TAU_ABS']['values'][level+n*band]
 receipt['runs'].append({'mode':mode,'executable':h.pin(exe),'input':h.pin(d/'input.dat'),'coefficients':h.pin(d/'coefficients.dat') if coefficient!='-' else None,'result':h.pin(d/'capture/lw.result'),'unchanged_nonselected_and_clear_fields':True});receipt['commands']=r.commands;h.write_json(O/'receipt.json',receipt);print('ACTUAL_COLUMN',mode,'PASS',flush=True)
