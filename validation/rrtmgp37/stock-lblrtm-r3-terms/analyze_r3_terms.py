"""One saved-only R3 accounting and full-spectrum noninterference reader."""
import collections,hashlib,importlib.util,json,math,re,struct
from pathlib import Path
R=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
D=R/'build/udm37-lblrtm-r3-term-trace-v1'
NEW=R/'build/udm37-lblrtm-held-state-r3terms-cpl-od-run-v1/runs/od-v1'
OLD=R/'build/udm37-lblrtm-held-state-continuum-od-run-v1/runs/od-v1'
PRIOR=R/'build/udm37-lblrtm-held-state-paneltrace-cpl-od-run-v1/runs/od-v1'
S=R/'build/udm37-lblrtm-panel-trace-v1/analyze_panel_trace.py'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bits(x):return struct.pack('<d',x)
sp=importlib.util.spec_from_file_location('panel',S);panel=importlib.util.module_from_spec(sp);sp.loader.exec_module(panel)
SI=['seq','stage','layer','max3','nlim1','nlim3','ilo','ihi','ipanel','istop','n1r3','n2r3','nlo','nhi','nshift','icntnm','ilblf4','ixsect','ir4']
SR=['vft','dv','dvr3','pave','tave']
TI=['seq','stage','layer','batch','i','j1','j3','molecule','isotope','flag','izeta','iz3','j3shft','jmin1','jmax1']
TR=['vft','dvr3','vnu','sp','sppsp','recalf','str','f3','z','before','after','zslope','zint','conf3','sui','gi','yi','pavp0','pavp2','alfl','zeta','meta_vnu']
def trace():
 it=iter(panel.records(NEW/'UDM37_R3_TERM_TRACE'));rows=[]
 for b in it:
  if b[:8]==b'UDMR3S1 ':
   assert len(b)==200,len(b)
   d=dict(zip(SI,struct.unpack_from('<19q',b,8)));d.update(zip(SR,struct.unpack_from('<5d',b,160)));d['kind']='snapshot'
   a=next(it);assert len(a)==8*d['max3'];d['array_bytes']=a;d['r3']=struct.unpack(f"<{d['max3']}d",a)
   assert all(math.isfinite(x) for x in d['r3'])
  else:
   assert b[:8]==b'UDMR3T1 ' and len(b)==304,(b[:8],len(b))
   d=dict(zip(TI,struct.unpack_from('<15q',b,8)));d.update(zip(TR,struct.unpack_from('<22d',b,128)));d['kind']='term'
   assert all(math.isfinite(d[k]) for k in TR)
  assert d['seq']==len(rows)+1 and d['layer']==21
  rows.append(d)
 assert rows
 return rows
def key(d,j):return bits(d['vft']),j
def in_window(d,j):return 666.1<=d['vft']+(j-1)*d['dvr3']<=666.7
def summarize_term(d):
 names=['seq','stage','batch','i','molecule','isotope','flag','vnu','vft','j3','sui','gi','yi','pavp0','pavp2','sp','sppsp','before','after']
 return {**{k:d[k] for k in names},'R3_grid_wavenumber':d['vft']+(d['j3']-1)*d['dvr3'],'actual_operand':d['operand'],'GI_strength_multiplier':1+d['gi']*d['pavp2']}
def main():
 assert json.loads((NEW/'execution.json').read_text())['actual_child_returncode']==0
 rows=trace();states={};changes=collections.defaultdict(list);terms=collections.defaultdict(list);first_negative=[];counts=collections.Counter();snapshots=[];previous=None;carry_checks=0;exact_updates=0;op_changes=[]
 for d in rows:
  counts[d['stage']]+=1
  if d['kind']=='term':
   j=d['j3'];assert in_window(d,j) and d['meta_vnu']==d['vnu'];k=key(d,j)
   assert bits(states[k])==bits(d['before']),(d['seq'],'before chain')
   assert bits(d['sp'])==bits(d['sui']*(1+d['gi']*d['pavp2'])),(d['seq'],'SP')
   assert bits(d['sppsp'])==bits((d['sui']*d['yi']*d['pavp0'])/d['sp']),(d['seq'],'SPPSP')
   delta=d['str']*d['f3']
   if d['stage']==2:delta=delta*d['z']
   else:assert d['stage']==1 and d['z']==1
   assert bits(d['before']+delta)==bits(d['after']),(d['seq'],'arithmetic')
   d['operand']=delta;exact_updates+=1;states[k]=d['after'];terms[k].append(d)
   if d['before']>=0 and d['after']<0:first_negative.append(summarize_term(d))
  else:
   if d['stage']==127:
    assert previous and previous['stage']==126
    assert bits(d['vft'])==bits(previous['vft']+(previous['nlim1']-1)*previous['dv'])
    if d['istop']!=1:
     shift=d['nlim3']-1
     for j,x in enumerate(d['r3'],1):
      expected=previous['r3'][j+shift-1] if j+shift<=d['max3'] else 0.
      assert bits(x)==bits(expected),(d['seq'],j,'carry')
     carry_checks+=1
   for j,x in enumerate(d['r3'],1):
    if not in_window(d,j):continue
    k=key(d,j)
    if k in states:
     if d['stage'] in (111,120,122,124,126):assert bits(states[k])==bits(x),(d['seq'],j,'checkpoint')
     elif d['stage'] in (121,123,125):
      op_changes.append({'seq':d['seq'],'stage':d['stage'],'vft':d['vft'],'j3':j,'before':states[k],'after':x,'delta':x-states[k]})
     elif d['stage']==110:assert bits(states[k])==bits(x),(d['seq'],j,'resumption')
    else:changes[k].append({'kind':'initial_or_carry','seq':d['seq'],'value':x})
    states[k]=x
   snapshots.append(d);previous=d
 g=panel.trace(NEW/'UDM37_PANEL_TRACE')
 assert sha(NEW/'UDM37_PANEL_TRACE')==sha(PRIOR/'UDM37_PANEL_TRACE'),'inherited panel trace changed'
 targetgroup=next(v for k,v in g.items() if k[0]==21);a=targetgroup[0]
 matched=[s for s in snapshots if s['stage']==126 and bits(s['vft']+(s['nlo']-1)*s['dv'])==bits(a['v1p'])]
 assert len(matched)==1,len(matched);target=matched[0];assert target['array_bytes']==a['r3_bytes']
 targetrows=[]
 for j in [61,62,63,64]:
  k=key(target,j);ts=terms[k];assert ts
  ops=[x for x in op_changes if bits(x['vft'])==bits(target['vft']) and x['j3']==j]
  carry=changes[k][0]['value']
  base=math.fsum(x['operand'] for x in ts if x['stage']==1);coupling=math.fsum(x['operand'] for x in ts if x['stage']==2)
  cfs={st:math.fsum(x['delta'] for x in ops if x['stage']==st) for st in [121,123,125]}
  final=target['r3'][j-1];sumterms=math.fsum([carry,base,coupling,*cfs.values()]);closure=final-sumterms
  # The exact ordered chain above is the pass condition; fsum totals are derived descriptive accounting.
  targetrows.append({'R3_index_1based':j,'wavenumber':target['vft']+(j-1)*target['dvr3'],'initial_or_carried_R3':carry,'baseline_operand_sum':base,'coupling_operand_sum':coupling,'optional_XSECTM_delta':cfs[121],'LBLF4_XINT_delta':cfs[123],'continuum_XINT_delta':cfs[125],'pre_PANEL_R3':final,'descriptive_fsum_closure_residual':closure,'term_updates':len(ts),'baseline_min_operand':min(x['operand'] for x in ts if x['stage']==1),'GI_strength_multiplier_min':min(1+x['gi']*x['pavp2'] for x in ts),'GI_strength_multiplier_max':max(1+x['gi']*x['pavp2'] for x in ts),'species':dict(collections.Counter(x['molecule'] for x in ts)),'first_negative_transitions':[summarize_term(x) for x in ts if x['before']>=0 and x['after']<0][:4],'largest_negative_coupling_terms':[summarize_term(x) for x in sorted((t for t in ts if t['stage']==2),key=lambda t:t['operand'])[:3]]})
 layers,n=panel.compare_outputs(NEW,OLD,g)
 for l in layers:
  assert [x['word_zero_based'] for x in l['header_changed_words']] in ([],[168])
  for x in l['header_changed_words']:
   for side,run in [('old_hex',OLD),('new_hex',NEW)]:
    c=bytes.fromhex(x[side]);assert re.fullmatch(rb'\d\d:\d\d:\d\d',c);assert c in (run/'TAPE6').read_bytes()
 out={'schema':'UDM37_LBLRTM_R3_TERM_ACCOUNTING_V1','status':'PASS_SCOPED_EXACT_UPDATE_ACCOUNTING_AND_NONINTERFERENCE','physical_reference_acceptance':'FAIL_NEGATIVE_OD_RETAINED','raw_trace_sha256':sha(NEW/'UDM37_R3_TERM_TRACE'),'raw_trace_bytes':(NEW/'UDM37_R3_TERM_TRACE').stat().st_size,'actual_solver_child_RC':0,'trace_records':len(rows),'term_updates_reconstructed_bitwise':exact_updates,'stage_counts':dict(counts),'PANEL_carry_maps_bitwise_checked':carry_checks,'inherited_PANEL_trace_exact':True,'all45_spectral_samples_and_panel_headers_bitwise_exact':True,'samples_compared':n,'sole_file_header_exception':'zero-based word168 HTIME runtime clock; source identity retained from PR116; every changed clock matches corresponding TAPE6','target_snapshot_seq':target['seq'],'target_VFT':target['vft'],'target_R3_accounting':targetrows,'negative_crossings_in_window_count':len(first_negative),'first_negative_crossings_in_window':first_negative[:8],'layers':layers,'limitations':['Accounting of actual source terms, not GI-only/YI-only counterfactual or spectroscopic truth.','Original full-spectrum negative-OD acceptance remains FAIL; no clipping or relaxed tolerance.','Private raw traces and original line/coefficient data excluded from publication.','Exact per-write order/chain verified; fsum component totals are descriptive rounded accounting.','R3 coordinates/carry differ from output indices; inherited PANEL raw trace and full outputs verified exact.','No attribution of the held WRF4/37 flux residual or UDM physical accuracy.']}
 (D/'r3-accounting-report.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
 print(out['status'],len(rows),exact_updates,n)
 for x in targetrows:print(x['R3_index_1based'],x['baseline_operand_sum'],x['coupling_operand_sum'],x['continuum_XINT_delta'],x['pre_PANEL_R3'])
if __name__=='__main__':main()
