"""Sealed PR174 study replay. Evidence integrity does not imply physical acceptance."""
import gzip,hashlib,importlib.util,json,math,re,struct
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def sha(x):return hashlib.sha256(x).hexdigest()
def require(ok,msg):
 if not ok:raise ValueError(msg)
def read(n):return gzip.decompress((B/'saved'/(n+'.gz')).read_bytes())
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def observed_records(data):
 out={};obs={};lines=data.decode().splitlines();i=0
 while i<len(lines):
  words=lines[i].split();i+=1
  if not words or words[0] not in ('RETURN','OBS'):continue
  bits=lines[i].split();i+=1;require(len(bits)==int(words[-1]),'actual switch record size')
  values=[struct.unpack('!f',bytes.fromhex(x))[0] for x in bits];require(all(math.isfinite(x) for x in values),'nonfinite actual UDM state')
  if words[0]=='RETURN':out[int(words[1])]=bits
  else:obs[words[1],*map(int,words[2:6])]=values
 require(set(out)==set(range(1,7)),'six actual UDM calls missing');return obs,out

def verify():
 seal=json.loads((B/'manifest.json').read_text());require(seal['production_accepted'] is False,'false physical approval')
 roster={str(p.relative_to(B)) for p in B.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts};require(roster==set(seal['files']),'sealed roster changed')
 for n,row in seal['files'].items():
  p=B/n;require(not p.is_symlink() and len(p.read_bytes())==row['bytes'] and sha(p.read_bytes())==row['sha256'],'sealed file differs '+n)
 identity=json.loads((B/'identity.json').read_text());require(identity['base_main']=='0da2ca008373eb9cbf149be6698968f08146535e' and not identity['production_source_changed'] and not identity['production_accepted'] and not identity['physics_gates_closed'],'study scope relabelled')
 for n,digest in identity['source_files'].items():require(sha(read('science-source/'+n))==digest,'studied source archive differs '+n)
 original=read('science-source/WRF/dyn_em/solve_em.F');observed=read('observer/solve_em.F');require(re.sub(rb'! BUDGET_OBSERVER_BEGIN\n.*?! BUDGET_OBSERVER_END\n',b'',observed,flags=re.S)==original,'observer does not reverse to original source')
 require(b'ww(i,kte,j) = 0.' in read('science-source/WRF/dyn_em/module_big_step_utilities_em.F'),'relative eta upper-boundary condition changed')
 archives=json.loads(read('observer/archive-comparison.json'));require(len(archives['original'])==len(archives['diagnostic']),'archive member roster differs')
 changed=[a['name'] for a,z in zip(archives['original'],archives['diagnostic']) if a!=z];require(changed==archives['changed_members'] and set(changed)<=set(['/','solve_em.F.o/']) and 'solve_em.F.o/' in changed,'unrelated compiled member changed')
 host=json.loads(read('host/receipt.json'));require(host['all_history_arrays_observer_OFF_ON_PR174_bytes_equal']==211 and len(host['processes'])==3,'host evidence scope')
 ob=json.loads(read('observer/receipt.json'));require(ob['executable']==host['executable'],'actual observed executable binding')
 for n,p in enumerate(host['processes'],1):
  text=read(f'host/command-{n:02d}.stdout').decode();require(p['status']=='TERMINAL' and p['actual_returncode']==0 and not p['timed_out'] and 'SUCCESS COMPLETE WRF' in text and 'FATAL CALLED' not in text,'actual host failed/unreaped')
 for name in ('on_dt10','off_dt10','on_dt5','PR174'):
  index=json.loads(read('host/'+name+'.json'));require(len(index['records'])==211 and index['attrs']['UDM_NUMBER_POLICY']==1 and index['attrs']['UDM_POPULATION_POLICY']==2,'host policy/roster')
  times=read('host/'+name+'.bin');history=load(B/'analyze_saved.py','timed_history').History(index,times);clock=history.values('Times');expected=[('1999-10-22_19:00:'+str(t).zfill(2)) if t<60 else '1999-10-22_19:01:00' for t in range(0,61,10)];require([clock[i:i+19].decode() for i in range(0,len(clock),19)]==expected,'physical history interval differs')
 require(read('host/on_dt10.bin')==read('host/off_dt10.bin')==read('host/PR174.bin'),'observer or relink changes full history arrays')
 require(json.loads(read('host/input_PR174.json'))['source_NetCDF_sha256']==identity['initial_input_sha256'],'initial input relabelled')
 sw=json.loads(read('switch/result.json'));compiled=read('switch/production.F');require(compiled==read('science-source/WRF/phys/module_mp_udm.F'),'actual switch compiled source differs')
 require(re.sub(rb'! CF0_TEST_BEGIN\n.*?! CF0_TEST_END\n',b'',read('switch/observed.F'),flags=re.S)==compiled,'actual switch observer not reversible')
 datasets={}
 for n,p in enumerate(sw['processes'],1):
  require(p['status']=='TERMINAL' and p['actual_returncode']==0 and not p['timed_out'],'UDM compile/process failed')
  if p['kind'].startswith('UDM_'):datasets[p['kind']]=observed_records(read(f'switch/command-{n:02d}.stdout'))
 for dt in ('.01','10.'):
  require(datasets['UDM_'+dt+'_observed_on'][1]==datasets['UDM_'+dt+'_observed_off'][1]==datasets['UDM_'+dt+'_production_off'][1],'switch observer changes final UDM state')
  obs=datasets['UDM_'+dt+'_observed_on'][0]
  for row in sw['rows']:
   if row['dt_seconds']!=float(dt):continue
   loc=obs['SWITCH_LOCAL',row['case'],1,1,1];require(loc[0]==row['diagnosed_CF'] and loc[1]==row['footprint'] and loc[7]*loc[1]==row['grid_nr_self_collection_rate'],'reported actual nonlinear rate differs')
 mie=json.loads(read('mie/result.json'));require(mie['miepython_version']=='3.2.0' and mie['water_temperature_K']==298.15 and mie['effective_variance']==.1 and mie['k']==8,'independent PSD/temperature changed')
 require(sha(read('mie/Hale.yml'))==mie['water_source_sha256'],'refractive index bytes changed')
 require(b'9 passed, 64 deselected' in read('mie/udm37-mie-wiscombe-tests.log'),'classical Mie reference tests not recorded')
 nodes=json.loads(read('mie/tables.json'))['table_nodes']
 for phase,nb in (('lw',16),('sw',14)):
  orig=json.loads(read(f'mie/{phase}-original-coefficients.json'));alt=json.loads(read(f'mie/{phase}-scoped_mie-coefficients.json'));require(sha(read(f'mie/rrtmgp-clouds-{phase}-bnd.nc'))==alt['file_sha256'],'actual alternate NetCDF bytes differ')
  for field in ('extliq','ssaliq','asyliq'):
   before=orig['arrays'][field]['values'];after=alt['arrays'][field]['values'];require(len(after)==nb*20,'optical coefficient dimensions')
   for i,(x,y) in enumerate(zip(before,after)):
    band,ri=divmod(i,20);radius=2.5+ri
    if band!=5 or not 9.5<=radius<=20.5:require(x==y,'held coefficient changed')
    else:
     value=next(r for r in nodes if r['phase']==phase and r['reff_um']==radius)['Planck'];expected=value['ext'] if field=='extliq' else value['sca']/value['ext'] if field=='ssaliq' else value['g'];require(math.isclose(y,expected,rel_tol=3e-7),'independent Mie table value differs')
 flux=json.loads(read('flux/receipt.json'));require(len(flux['commands'])==4 and all(p['status']=='TERMINAL' and p['actual_returncode']==0 and not p['timed_out'] for p in flux['commands']),'independent optical RTE execution failed')
 a=load(B/'analyze_saved.py','policy2_analysis');result=a.analyze(read);require(result==json.loads((B/'result.json').read_text()),'raw study replay differs')
 require(result['decisions']['production_radius_changed'] is False and all(x['full_energy_closed'] is False for x in result['host'].values()),'false energy/optical approval')
 require(json.loads((B/'closure-conditions.json').read_text())==json.loads((ROOT/'validation/rrtmgp37/cf0-warm-transition/closure-conditions.json').read_text()),'seven closure conditions changed')
 return {'status':'PASS_STUDY_INTEGRITY_ONLY','host_water_budget_approved':False,'full_host_energy_closed':False,'Gamma_LUT_equivalence_approved':False,'actual_host_processes':3,'actual_UDM_calls':36,'independent_optical_RTE_columns':4,'fresh_model_runs_in_replay':0,'studied_source':'PR174 retained snapshot','production_accepted':False}
if __name__=='__main__':print(json.dumps(verify()))
