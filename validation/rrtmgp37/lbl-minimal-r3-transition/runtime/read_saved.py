from pathlib import Path
import json,struct,hashlib,collections,math
BASE=Path(__file__).resolve().parent
DONOR=BASE.parents[1]/'build/udm37-lblrtm-negative-pocket-observer-v10-run-v1/runs/od-v10'
def require(x,msg):
 if not x:raise ValueError(msg)
def records(p):
 raw=p.read_bytes();pos=0;out=[]
 while pos<len(raw):
  require(pos+8<=len(raw),'truncated marker')
  n=struct.unpack_from('<i',raw,pos)[0]
  require(n>=0 and pos+n+8<=len(raw),'record extent')
  require(struct.unpack_from('<i',raw,pos+n+4)[0]==n,'record trailer')
  out.append(raw[pos+4:pos+4+n]);pos+=n+8
 return out
comparison=[]
for p in sorted((BASE/'case-v3-on').glob('ODdeflt_*')):
 off=records(BASE/'case-v3-off'/p.name); on=records(p); prior=records(DONOR/p.name)
 require(len(off)==len(on)==len(prior),'record count')
 require(all(a==b==c for a,b,c in zip(off[1:],on[1:],prior[1:])),'scientific record mismatch')
 require(len(on[0])==1416,'known stock FILHDR extent')
 deltas=[]
 for arm,other in [('OFF',off),('PRIOR',prior)]:
  where=[i for i,(a,b) in enumerate(zip(on[0],other[0])) if a!=b]
  require(all(1336<=i<1352 for i in where),'non-timestamp file-header mismatch')
  deltas.append({'arm':arm,'byte_offsets0':where,'time_date16_ascii':other[0][1336:1352].decode('ascii')})
 numerical=b''.join(on[1:])
 comparison.append({'path':p.name,'file_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'records':len(on),'post_FILHDR_record_sha256':hashlib.sha256(numerical).hexdigest(),'post_FILHDR_bytes':len(numerical),'all_scientific_records_equal':True,'whole_file_equal':False,'header_differences':deltas})
require(len(comparison)==45,'45 OD files')
# Explicitly preserve the failed whole-file comparison, while qualifying the source-mapped timestamp difference.
comp={'schema':'UDM37_MIN_R3_SCIENTIFIC_RECORD_COMPARISON_V1','status':'PASS_SCOPED_PANEL_AND_OD_RECORDS_FULL_FILE_DIFFERENCES_RETAINED','whole_file_bitwise_status':'FAIL_PRESERVED_TIMESTAMP_DIFFERENCES','header_exception':{'byte_offset0':1336,'length':16,'meaning':'YID(1)=HDATE and YID(2)=HTIME; source calls LBLDAT/LBLTIM','source':'stock lblrtm.f90 FILHDR COMMON/EQUIVALENCE and initialization'},'scientific_records_total':sum(x['records']-1 for x in comparison),'all_45_files_scientific_records_equal':True,'files':comparison,'physical_reference_accepted':False}
(BASE/'scientific-record-comparison-v1.json').write_text(json.dumps(comp,indent=2)+'\n')
trace=BASE/'case-v3-on/UDM37_MIN_R3';rows=[]
for line in trace.read_text().splitlines():
 a=line.split();require(len(a)>=14,'record width')
 ints=list(map(int,a[1:12])); vals=list(map(float,a[12:]));require(len(vals)==ints[-1]+2,'value count')
 require(all(math.isfinite(v) for v in vals),'finite trace')
 rows.append({'tag':a[0],'sequence':ints[0],'layer':ints[1],'panel':ints[2],'target_index':ints[3],'MAX3':ints[4],'destination':ints[5],'source_index':ints[6],'line_slot':ints[7],'phase':ints[8],'flags':ints[9],'VFT':vals[0],'DVR3':vals[1],'values':vals[2:]})
require([r['sequence'] for r in rows]==list(range(1,len(rows)+1)),'sequence coverage')
require(all(r['layer']==21 and r['MAX3']==283 for r in rows),'observed owner and extent')
init=rows[0]; require(init['tag']=='INIT' and init['values']==[0.,1.,1.,0.],'ILBLF4/IXSECT/ICNTNM/IR4')
require(all(r['flags']==0 for r in rows if r['tag']=='RSYM_GATE'),'RSYM was active')
chosen=[r for r in rows if r['target_index']>0]
require(all(abs(r['VFT']+(r['target_index']-1)*r['DVR3']-618.6144711111115)<1e-7 for r in chosen),'target coordinate')
mutations=[r for r in chosen if r['tag'] in ('CN_WRITE','XINT_WRITE','CARRY','CLEAR')]
require(mutations and mutations[0]['tag']=='CLEAR','target defined by tail clear')
last=None; origin=None; firstnegative=None;replays=0;prefix=[];source_complete=True
for r in mutations:
 v=r['values'];before,after=v[:2]
 if r['tag']=='CLEAR': last=after;origin=r
 else:
  require(last is not None and struct.pack('<d',before)==struct.pack('<d',last),'mutation chain breaks')
  if r['tag']=='CN_WRITE':
   term=v[2]*v[3]
   if r['phase']==2:term=term*v[4]
   expect=before+term;replays+=1
   require(struct.pack('<d',expect)==struct.pack('<d',after),'CN source-order replay')
  elif r['tag']=='CARRY':require(before==after,'carry value')
  elif r['tag']=='XINT_WRITE':
   require(before+v[2]*v[3]==after,'computed XINT contribution replay')
   if firstnegative is None:source_complete=False
  last=after
 prefix.append(r)
 if firstnegative is None and before>=0>after:firstnegative=r;prefix_at_negative=list(prefix)
require(firstnegative is not None,'no first negative')
# State snapshots independently enforce equality to the preceding target mutation.
state=None
for r in chosen:
 if r['tag']=='CLEAR':state=r['values'][1]
 elif r['tag'] in ('CN_WRITE','XINT_WRITE','CARRY'):
  require(state is not None and state==r['values'][0],'state continuity');state=r['values'][1]
 elif r['tag'] in ('CN_PRE','CN_POST','PANEL_PRE','SHIFT_PRE','SHIFT_POST','INIT_STATE'):
  require(state is not None and state==r['values'][0],'unobserved target mutation')
# Match the historical R3(20) entry value by physical coordinate, without identifying owner_header with panel ordinal.
matching=[r for r in chosen if r['target_index']==20 and r['tag']=='CN_PRE' and r['values'][0]==-1.686827144352549e-5]
require(matching,'historical target state not joined')
result={'schema':'UDM37_MIN_R3_DYNAMIC_PREFIX_RESULT_V1','status':'PASS_SCOPED_DEFINED_ACCUMULATOR_PREFIX_AND_FIRST_NEGATIVE','trace':{'sha256':hashlib.sha256(trace.read_bytes()).hexdigest(),'bytes':trace.stat().st_size,'rows':len(rows)},'tag_counts':dict(collections.Counter(r['tag'] for r in rows)),'selected_rows':len(chosen),'selected_mutations':len(mutations),'all_CN_selected_mutations_bitwise_replayed':replays,'initialized_target':origin,'first_negative':firstnegative,'prefix_mutations_to_first_negative':len(prefix_at_negative),'unsupported_XINT_source_write_before_first_negative':not source_complete,'historical_R3_20_state_matches':matching[:1],'R4_gate_observed':0,'RSYM_gate_all_inactive':True,'target_index_path':sorted(set(r['target_index'] for r in chosen)),'selected_accumulator_prefix_closed':source_complete,'all_operand_generation_ancestry_complete':False,'full_LBLRTM_reference_accepted':False,'negative_OD_status':'FAIL_PRESERVED','production_accepted':False,'scope':'One layer21 physical-frequency accumulator. This identifies a signed coupling transition, not an erroneous coupling term or full spectral cancellation/reference approval.'}
(BASE/'dynamic-prefix-result-v1.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'status':result['status'],'CN_replays':replays,'first_negative_sequence':firstnegative['sequence'],'first_negative_phase':firstnegative['phase'],'first_negative_before_after':firstnegative['values'][:2],'target_indices':result['target_index_path'],'scientific_records':comp['scientific_records_total'],'OD_files':45,'physical_reference_accepted':False}))
