#!/usr/bin/env python3
"""Retain completed new calculations; never launch a scientific process."""
from pathlib import Path
import gzip,json,hashlib,importlib.util,sys,platform
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;MIE=B/'udm37-matched-reference-v1';RTE=B/'udm37-matched-reference-rte-v1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def jwrite(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def save(name,data):
 path=P/'saved'/(name+'.gz');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(gzip.compress(data,mtime=0))
if __name__=='__main__':
 ref=json.loads((MIE/'result.json').read_text());assert ref['completed']
 for name in ['plan.json','result.json','definition-controls.json','cross-plan.json','cross-result.json','process-observation.json']:save('mie/'+name,(MIE/name).read_bytes())
 for name in ['plan.json','run_reference.py','check_definitions.py','cross_quadratures.py','propagate_reference.py']:save('executed/'+name,(P/name).read_bytes())
 save('water/Segelstein.yml',(B/'udm37-matched-optics-inputs/Segelstein.yml').read_bytes())
 for log,label in [('udm37-matched-reference-v1.log','reference'),('udm37-matched-reference-controls.log','definition-controls'),('udm37-matched-reference-cross-v1.log','cross'),('udm37-matched-reference-rte-v1.log','rte'),('udm37-matched-reference-acceptance.log','local-acceptance')]:save('logs/'+label+'.log',(B/log).read_bytes())
 receipt=json.loads((RTE/'receipt.json').read_text());assert len(receipt['runs'])==18 and all(c['actual_returncode']==0 for c in receipt['commands'])
 save('rte-journal/receipt.json',(RTE/'receipt.json').read_bytes())
 for p in RTE.glob('command-*'):save('rte-journal/'+p.name,p.read_bytes())
 for row in receipt['runs']:
  name=row['case']+'_'+row['mode']+'_'+row['grid'];ph=row['case'].rsplit('_',1)[1]
  for n in ['input.dat','optics.dat']:save(name+'/'+n,(RTE/name/n).read_bytes())
  for n in [ph+'.input',ph+'.result']:save(name+'/'+n,(RTE/name/'capture'/n).read_bytes())
 refs={}
 for case in ['night_peak_lw','day_peak_lw','day_peak_sw']:
  ph=case.rsplit('_',1)[1]
  for mode in ['B','C']:
   for name in ['input.dat','optics.dat',ph+'.input',ph+'.result']:
    key=case+'_'+mode+'/'+name;path=R/'validation/rrtmgp37/liquid-endpoint-optics/saved'/(key+'.gz');refs[key]={'path':str(path.relative_to(R)),'sha256':sha(path)}
 for key,path in [('old_mie',R/'validation/rrtmgp37/liquid-endpoint-optics/saved/mie/result.json.gz')]:refs[key]={'path':str(path.relative_to(R)),'sha256':sha(path)}
 jwrite(P/'prior-evidence.json',refs)
 old=json.loads((R/'validation/rrtmgp37/liquid-endpoint-optics/identity.json').read_text())
 assert all(sha(R/n)==s for n,s in old['source_files'].items())
 assert all(sha(R/n)==s for n,s in old['coefficient_files'].items())
 assert all(sha(B/'deps/miepython-3.2.0'/n)==s for n,s in old['Mie_source_files'].items())
 assert sha(Path(receipt['executable']['path']))==old['diagnostic_build']['executable']['sha256']==receipt['executable']['sha256']
 ident={'baseline_main':'9ef7947ea2a74bd2954c36e093d75559d0f8559d','baseline_tree':'2db3b591300c43512f7b6b9d9a2d964c46c3fa29','runtime_source_files':old['source_files'],'coefficient_files':old['coefficient_files'],'Mie_source_files':old['Mie_source_files'],'reused_executable':receipt['executable'],'reused_executable_build_identity':'../liquid-endpoint-optics/identity.json#diagnostic_build','new_WRF_runs':0,'new_Fortran_compiles':0,'new_RTE_processes':18,'new_reference_axis_evaluations':sum(3*len(r['levels']) for r in ref['records']),'new_crossed_method_evaluations':16,'shared_Mie_kernel':'miepython3.2.0; not a second independent Mie implementation','external_commit':'fe1faba475479c873c88bc98755bcb8c5bb911b1','external_unmodified_source_sha256':ref['source_pin'],'external_executed_source_sha256':ref['compiled_external_sha256'],'external_sources_not_vendored':True,'water_sha256':ref['water_sha256'],'environment':{'python':platform.python_version(),'platform':platform.platform(),'source':'inspected after completed execution in same environment; process observation retained during run'},'production_source_defaults_coefficients_changed':False,'production_accepted':False,'new_full_152_combination_or_24h_campaign':False}
 import numpy,scipy,netCDF4
 ident['environment'].update(numpy=numpy.__version__,scipy=scipy.__version__,netCDF4=netCDF4.__version__,miepython='3.2.0 (source hashes checked)')
 jwrite(P/'identity.json',ident)
 s=importlib.util.spec_from_file_location('matched_analysis',P/'analyze_saved.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
 read=lambda n:gzip.decompress((P/'saved'/(n+'.gz')).read_bytes());prior=lambda n:gzip.decompress((R/refs[n]['path']).read_bytes())
 result=a.analyze(read,prior,json.loads((P/'plan.json').read_text()));jwrite(P/'result.json',result)
 sealed={str(p.relative_to(P)):sha(p) for p in (P/'saved').rglob('*') if p.is_file()}
 for n in ['plan.json','identity.json','prior-evidence.json']:sealed[n]=sha(P/n)
 jwrite(P/'manifest.json',{'files':sealed,'purpose':'retained numerical reference evidence integrity, not scientific approval'})
 print('RETAINED_MATCHED_REFERENCE',result['coefficient_scope']['qualified_total'],result['transport']['axis_numerical_screen_passed'])
