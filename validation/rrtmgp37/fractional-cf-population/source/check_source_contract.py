from pathlib import Path
import re,json,hashlib,ast,subprocess
R=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP');P=R/'build/udm37-fractional-cf-population-observer-preparation-v1';S=R/'build/udm37-fractional-cf-population-observer-source-v1';B=R/'build/udm37-positive-nc-stage-observer-source-v2'
s=(S/'WRF/phys/module_mp_udm.F').read_text();b=(B/'WRF/phys/module_mp_udm.F').read_text()
checks=[]
def check(name,predicate):
 assert predicate,name;checks.append(name)
blocks=re.findall(r'^! BEGIN UDM_CF_POPULATION_OBSERVER\n(.*?)^! END UDM_CF_POPULATION_OBSERVER\n',s,flags=re.S|re.M)
check('Five additive blocks exactly',len(blocks)==5)
check('Full parent bytes recovered by marker strip',re.sub(r'^! BEGIN UDM_CF_POPULATION_OBSERVER\n.*?^! END UDM_CF_POPULATION_OBSERVER\n','',s,flags=re.S|re.M)==b)
check('Parent source hash locked',hashlib.sha256(b.encode()).hexdigest()=='9f25a1aaebd0d29ba3ecdf86c9fe65065cf920fc187bdfd904e8b8192bc7e3c8')
check('Only UDM path changed',subprocess.check_output(['git','diff','--name-only'],cwd=S,text=True).splitlines()==['WRF/phys/module_mp_udm.F'])
check('Existing NUMBER context unchanged',s[s.index('  type :: udm_number_observer_context'):s.index('  end type udm_number_observer_context')]==b[b.index('  type :: udm_number_observer_context'):b.index('  end type udm_number_observer_context')])
# Above comment says no SAVE; check executable declarations/statements instead.
for phase in range(1,5):
 q=blocks[phase-1]
 check('Phase%d identity and context guard'%phase,('itimestep,%d,loop'%phase) in q and 'if(udm_number_selected(number_observer,i,i,lat)) then' in q)
 check('Phase%d read-only full14 vector order'%phase,'qci(kts:kte,i,1),qci(kts:kte,i,2)' in q and 'qrs(kts:kte,i,3),qrs(kts:kte,i,4)' in q and 'ncr(kts:kte,i,1),ncr(kts:kte,i,2),ncr(kts:kte,i,3)' in q)
check('Four hooks ordered around original loops',s.index('itimestep,1,loop')<s.index('qci(k,i,1) = qci(k,i,1) / cldf(k)')<s.index('itimestep,2,loop')<s.index('itimestep,3,loop')<s.index('qci(k,i,1) = qci(k,i,1) * cldf(k)')<s.index('itimestep,4,loop'))
helper=blocks[-1]
check('All source payload arguments intentIN','intent(inout)' not in helper.lower() and 'intent(out)' not in helper.lower())
check('Separate new extension and identity','".cfpop"' in helper and "status='new'" in helper and 'storage_size(1.)' in helper and 'UDM37CFPOP1' in helper)
check('13 integer header3 clock14 real row format',"'(13(i0,1x))'" in helper and "'(3(es26.17e3,1x))'" in helper and "'(3(i0,1x),14(es26.17e3,1x))'" in helper)
check('Original branch mask recorded','if(k<=top_used.and.cf(l)>0.) applied=1' in helper)
check('Finite rows and bounds not clipping','all(udm_num_is_finite(values))' in helper and 'if(cf(l)<0..or.cf(l)>1.) error stop' in helper)
for q in blocks:
 executable='\n'.join(x for x in q.splitlines() if not x.lstrip().startswith('!'))
 check('Additive block has no module SAVE/new env call',not re.search(r'\b(save|get_environment_variable)\b',executable,re.I))
check('New lines within132 columns',all(len(x)<=132 for q in blocks for x in q.splitlines()))
runner=R/'build/udm37-fractional-cf-population-observer-build-runner-v1.py';ast.parse(runner.read_text());check('Build runner AST parse',True)
j=json.loads((P/'plan.json').read_text());check('Build source output paths match runner',str(S)==j['source_path'] and str(R/'build/udm37-fractional-cf-population-observer-build-v1')==j['output_path'])
report={'status':'PASS_SOURCE_CONTRACT_STATIC_ONLY','checks':checks,'check_count':len(checks),'compile_calls':0,'model_calls':0,'limits':['No Fortran compile or actual packet acceptance has been performed.','Input source certificate cannot guarantee runtime fractionalCF after transport/adjustment.','Number equality is a division/restoration checkpoint expectation only; intervening microprocesses may change it.','No physical unit/PSD/LUT approval.']}
(P/'source-contract-check.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
