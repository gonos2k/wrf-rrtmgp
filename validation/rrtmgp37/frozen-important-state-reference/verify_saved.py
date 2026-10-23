"""Portable replay of the actual conditional frozen reference; no scientific rerun."""
from pathlib import Path
import gzip,hashlib,io,json,tarfile,importlib.util,math
P=Path(__file__).resolve().parent;R=P.parents[2]
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
E=load('frozen_evaluate',P/'evaluate.py');I=load('frozen_selection_source',P/'instrument.py');require=E.require
sha=lambda b:hashlib.sha256(b).hexdigest()

def compare_inventory(c):
 require(c['pairs']==450 and not c['differences'],'host observation/capture changed results')
 require(len(c['inventory'])==2 and sum(map(len,c['inventory'].values()))==450,'omitted actual comparison arrays')
 require(all(v['equal'] and v['left_sha256']==v['right_sha256'] for rows in c['inventory'].values() for v in rows.values()),'host comparison hash')

def data():
 ident=json.loads((P/'identity.json').read_text());raw=(P/'saved/evidence.tar.gz').read_bytes();require(sha(raw)==ident['archive']['sha256'],'archive hash')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(raw)),mode='r:') as tar:
  require(set(tar.getnames())==set(ident['files']),'archive roster');d={n:tar.extractfile(n).read() for n in ident['files']}
 for n,p in ident['files'].items():require(sha(d[n])==p['sha256'] and len(d[n])==p['bytes'],'payload '+n)
 for n,p in ident['current_sources'].items():require(sha((R/n).read_bytes())==p['sha256'],'current source '+n)
 require(d['plan.json']==(P/'plan.json').read_bytes(),'plan changed')
 base_ident=json.loads((P.parent/'vapor-first-operation/identity.json').read_text());base=j=lambda name:json.loads(d[name])
 for name,old in [('base-public-receipt.json','public/receipt.json'),('base-day-receipt.json','day/receipt.json')]:require(sha(d['context/'+name])==base_ident['files'][old]['sha256'],'retained baseline identity')
 public=base('context/base-public-receipt.json');day=base('context/base-day-receipt.json');build=base('column_build/receipt.json');selected=base('selection_build/receipt.json')
 require(build['unchanged_public_library']['sha256']==public['library']['sha256'],'numerical library changed')
 require(d['selection_build/module_ra_rrtmg_lw.F']==I.transform(R).encode(),'selection observer changed beyond bounded insertion')
 require(d['selection_build/selection_probe.f90']==(P/'selection_probe.f90').read_bytes(),'compiled selection helper differs')
 require(sha(d['selection_build/module_ra_rrtmg_lw.F'])==selected['observer_source']['sha256'],'compiled observer source pin')
 adapter=(R/'WRF/phys/module_ra_rrtmgp.F').read_text().replace('MODULE module_ra_rrtmgp','MODULE module_frozen_reference_adapter')
 adapter=adapter.replace('  USE mo_rte_kind, ONLY: wp, i8','  USE reference_hail_hook,ONLY:apply_reference\n  USE mo_rte_kind, ONLY: wp, i8',1)
 needle="    IF(status/=0) CALL require(frozen_error('RRTMGP_FROZEN_LW_HAIL',message,frozen_context))";require(adapter.count(needle)==1,'frozen substitution anchor')
 adapter=adapter.replace(needle,needle+'\n    CALL apply_reference(ht,tlay,hwp,lambda_h)',1)
 require(d['column_build/module_frozen_reference_adapter.F']==adapter.encode(),'diagnostic adapter differs beyond one frozen boundary')
 for name in ['hail_hook.f90','column.f90']:require(d['column_build/'+name]==(P/name).read_bytes(),'compiled client source')
 require(d['column_build/diagnostic_column.f90']==(P/'column.f90').read_text().replace('use module_ra_rrtmgp,only:','use module_frozen_reference_adapter,only:',1).encode(),'diagnostic caller input path differs')
 for name in ['selection','capture']:
  rec=base(name+'/receipt.json');require(rec['status']=='SUCCESS' and not rec['error'],'actual host did not complete')
  require(rec['initial']['sha256']==day['initial']['sha256'] and rec['forcing']['sha256']==day['forcing']['sha256'],'original forcing changed')
  compare_inventory(base(name+'/history-comparison.json'))
  expected=selected['executable']['sha256'] if name=='selection' else public['executable']['sha256'];require(rec['executable']['sha256']==expected,'wrong host executable')
  for c in rec['commands']:require(c['actual_returncode']==0 and not c['timed_out'],'actual model failed')
 for rec in [selected,build,base('rte/receipt.json')]:
  for c in rec['commands']:require(c['actual_returncode']==0 and not c['timed_out'],'build/column command failed')
 ref=base('reference/result.json');old_kernel=json.loads((P.parent/'frozen-optics-reference/checks/independent-mie.json').read_text())
 require(old_kernel['status']=='PASS' and old_kernel['independent_implementation']['version']=='3.0.2','existing kernel reference altered')
 for name in ['core.py','mie_jit.py','mie_nojit.py']:
  require(sha(d['dependencies/miepython/'+name])==old_kernel['independent_implementation']['source_tree_sha256'][name],'independent kernel source changed')
 for name,h in ref['source_pins'].items():
  n=Path(name).name
  if n=='reference.py':require(sha((P/n).read_bytes())==h,'executed reference source changed')
  elif n=='IOP_2008_ASCIItable.dat':require(h=='891d0e0690cc6c6ed2dfe81291fa20a3af177fa85ef93127c58c5f86d3c370af','material source differs')
  else:require(sha(d['dependencies/miepython/'+n])==h,'independent source pin mismatch')
 original=base('original/result.json');context=base('context/original-table-context.json')
 require(original['completed'] and original['state']==base('selection/target.json') and original['density_kg_m3']==912. and not original['physical_accuracy_approved'],'original direct definition/state differs')
 require(original['ice_sha256']==context['input_sources']['IOP_2008_ASCIItable.dat']['sha256'] and original['laguerre_sha256']==sha((R/'tools/udm_frozen_optics/laguerre.py').read_bytes()),'original direct material/quadrature differs')
 require([r['band'] for r in original['bands']]==list(range(16)) and all(r['phase']=='LW' and r['slope']==original['state']['lambda_m_1'] for r in original['bands']),'original direct band/query roster')
 require(original['library_sha256']==context['kernel_binary_sha256'] and original['generator_sha256']==context['generator_sha256'] and context['order']==original['order']==128 and context['max_spectral_step_cm_inv']==original['spectral_max_step_cm_1']==50.,'original direct control differs from table generator')
 require(sha((R/'tools/udm_frozen_optics/generate.py').read_bytes())==context['generator_sha256'],'original generator source differs')
 require(context['table_sha256']==base('rte/receipt.json')['table']['sha256'],'actual table not original context table')
 _,inp=E.F.read(d['capture/host/capture/lw.input'],'input');frozen_sha=''.join(chr(int(v)) for v in inp['FROZEN_TABLE_SHA256_BYTES']['values']);require(frozen_sha==context['table_sha256'],'capture consumed another table')
 rows=[line.split() for line in d['selection/host/frozen-selection.txt'].decode().splitlines()];require(len(rows)==8910 and len({(int(r[0]),int(r[1])) for r in rows})==8910,'missing actual selection columns')
 require(all(float(r[3])==3000 for r in rows),'selection source mismatch');best=max(rows,key=lambda r:(float(r[4]),float(r[5]),-int(r[1]),-int(r[0])));target=base('selection/target.json')
 require((int(best[0]),int(best[1]),int(float(best[6])))==(target['i'],target['j'],target['native_layer']),'selection is not the actual maximum')
 area=base('selection/area.json');A=math.fsum(v for r in area['area_m2'] for v in r);path=math.fsum(area['area_m2'][int(r[1])-1][int(r[0])-1]*float(r[4])*.001 for r in rows)/A
 require(math.isclose(path,target['warm_hail_domain_path_kg_m2'],rel_tol=5e-12),'selection area/units mismatch')
 require(abs(target['domain_path_difference_kg_m2'])<=5e-12*target['baseline_domain_path_kg_m2'],'selection disagrees with prior actual whole-domain source')
 require(not ident['production_changes'] and not ident['physical_accuracy_approved'],'scope promotion')
 return d

if __name__=='__main__':
 r=E.evaluate(data());require(r==json.loads((P/'result.json').read_text()),'saved result changed')
 print(json.dumps({k:r[k] for k in ['status','reference_LW_bands','independent_axis_evaluations','original_direct_evaluations','WRF_capture_array_pairs_equal','only_selected_hail_absorption_changed','frozen_real_particle_accuracy_approved','production_changes','new_model_runs_in_saved_replay']}))
