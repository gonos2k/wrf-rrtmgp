#!/usr/bin/env python3
"""Read saved diagnostic snapshots and verify all45layer spectral identity."""
import argparse,collections,hashlib,importlib.util,json,math,struct
from pathlib import Path
R=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP');D=R/'build/udm37-lblrtm-panel-trace-v1'
S=R/'build/udm37-lblrtm-negative-od-diagnostic-v2/analyze_negative_od.py'
sp=importlib.util.spec_from_file_location('raw',S);raw=importlib.util.module_from_spec(sp);sp.loader.exec_module(raw)
def sha(p):return raw.sha(p)
def records(p):
 with p.open('rb') as f:
  while True:
   b=raw.read_record(f)
   if b is None:break
   yield b
ints=['stage','layer','max1','max2','max3','nlo','nhi','jrad','nlim1','nlim2','nlim3','n1r1','n2r1','n1r2','n2r2','n1r3','n2r3','nshift','nlim']
reals=['pave','tave','dv','v1p','v2p','dvp','dvr2','dvr3','target']
def trace(p):
 it=iter(records(p));groups=collections.defaultdict(list)
 for h in it:
  assert len(h)==232 and h[:8]==b'UDMTRC1 '
  d=dict(zip(ints,struct.unpack_from('<19q',h,8)));d.update(zip(reals,struct.unpack_from('<9d',h,160)))
  assert d['jrad']==0 and d['layer'] in (21,44)
  assert d['nhi']-d['nlo']+1==d['nlim']
  for k in (1,2,3):
   b=next(it);n=d[f'max{k}'];assert len(b)==n*8
   vals=struct.unpack(f'<{n}d',b);assert all(math.isfinite(x) for x in vals);d[f'r{k}']=vals;d[f'r{k}_bytes']=b
  groups[(d['layer'],d['v1p'],d['v2p'],d['dv'])].append(d)
 for key,g in groups.items():assert [x['stage'] for x in g]==[1,2,3,4],(key,[x['stage'] for x in g])
 assert {k[0] for k in groups}=={21,44}
 return groups

def evaluate(g):
 a,b,c,d=g;idx=a['nlo']+round((a['target']-a['v1p'])/a['dv']);assert a['nlo']<=idx<=a['nhi']
 j=a['nlo']+4*((idx-a['nlo'])//4);j2=(j-1)//4+1;r=idx-j;v=b['r2'];positions=[j2-1,j2,j2+1,j2+2];sv=[v[x-1] for x in positions]
 x00=-7/128;x01=105/128;x02=35/128;x03=-5/128;x10=-1/16;x11=9/16
 before=b['r1'][idx-1]
 if r==0: after=before+v[j2-1];weights=[0,1,0,0]
 elif r==1:after=before+x00*sv[0]+x01*sv[1]+x02*sv[2]+x03*sv[3];weights=[x00,x01,x02,x03]
 elif r==2:after=before+x10*(sv[0]+sv[3])+x11*(sv[1]+sv[2]);weights=[x10,x11,x11,x10]
 else:after=before+x03*sv[0]+x02*sv[1]+x01*sv[2]+x00*sv[3];weights=[x03,x02,x01,x00]
 assert a['r1_bytes']==b['r1_bytes'] and a['r3_bytes']==b['r3_bytes']
 assert b['r2_bytes']==c['r2_bytes']==d['r2_bytes'] and b['r3_bytes']==c['r3_bytes']==d['r3_bytes']
 actual=c['r1'][idx-1];final=d['r1'][idx-1];assert actual==after,(actual,after)
 multiplier=final/actual if actual else None;assert multiplier is None or multiplier>0
 created=(before>=0 and min(sv)>=0 and actual<0)
 return {'layer':a['layer'],'PAVE_mbar':a['pave'],'TAVE_K':a['tave'],'V1P':a['v1p'],'V2P':a['v2p'],'DV':a['dv'],'target_requested':a['target'],'actual_wavenumber':a['v1p']+(idx-a['nlo'])*a['dv'],'array_index_1based':idx,'stencil_phase':r,'R1_before_interpolation':before,'R2_stencil_indices_1based':positions,'R2_stencil_values':sv,'stencil_weights':weights,'R1_after_R2_interpolation':actual,'R1_after_RADFNI':final,'reconstruction_bitwise_exact':True,'RADFNI_multiplier':multiplier,'negative_created_from_nonnegative_R1_R2_stencil':created,'pre_Panel_R1_global_min':min(a['r1']),'pre_Panel_R2_global_min':min(a['r2']),'pre_Panel_R3_global_min':min(a['r3']),'post_R3_to_R2_global_min':min(b['r2']),'post_R2_to_R1_global_min':min(c['r1']),'final_sample_le_hex':struct.pack('<d',final).hex()}

def compare_outputs(new,old,groups):
 result=[];count=0
 for n in range(1,46):
  np=new/f'ODdeflt_{n:03}';op=old/f'ODdeflt_{n:03}';ni=iter(records(np));oi=iter(records(op));nh=next(ni);oh=next(oi);assert len(nh)==len(oh)==177*8
  # Physical header words10:167 include secant,p,T,gas names/amounts,
  # faces,broadener,spectral/physics flags,NMOL,LAYER,YI1. Other changes are reported.
  assert nh[10*8:167*8]==oh[10*8:167*8],n
  diff=[{'word_zero_based':i,'old_hex':oh[i*8:(i+1)*8].hex(),'new_hex':nh[i*8:(i+1)*8].hex()} for i in range(177) if nh[i*8:(i+1)*8]!=oh[i*8:(i+1)*8]]
  panels=samples=0;rawvalueshash=hashlib.sha256()
  while True:
   ph=next(ni);qh=next(oi);assert ph==qh,(n,panels,'panelheader')
   if ph==struct.pack('<6q',*([-99]*6)):break
   assert len(ph)==32;v1,v2,dv,ns=struct.unpack('<3dq',ph)
   values=next(ni);oldvalues=next(oi);assert values==oldvalues and len(values)==ns*8,(n,panels,'samples')
   rawvalueshash.update(values);panels+=1;samples+=ns
   key=(n,v1,v2,dv)
   if key in groups:
    g=groups[key];assert values==g[3]['r1_bytes'][(g[3]['nlo']-1)*8:g[3]['nhi']*8]
    g[3]['matched_raw_panel']=True
  assert next(ni,None) is None and next(oi,None) is None
  count+=samples;result.append({'layer':n,'new_file_sha256':sha(np),'baseline_file_sha256':sha(op),'physical_header_bitwise_exact':True,'entire_header_bitwise_exact':not diff,'header_changed_words':diff,'panels':panels,'samples':samples,'spectral_samples_and_panel_headers_bitwise_exact':True,'spectral_payload_sha256':rawvalueshash.hexdigest()})
 assert count==63838065,count
 assert all(g[3].get('matched_raw_panel') for g in groups.values())
 return result,count

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--case',choices=['cpl','nocpl'],required=True);args=ap.parse_args()
 c=args.case;new=R/f'build/udm37-lblrtm-held-state-paneltrace-{c}-od-run-v1/runs/od-v1';old=R/f'build/udm37-lblrtm-held-state-{"continuum" if c=="cpl" else "nocpl"}-od-run-v1/runs/od-v1'
 e=json.loads((new/'execution.json').read_text());assert e['actual_child_returncode']==0
 g=trace(new/'UDM37_PANEL_TRACE');points=[evaluate(x) for x in g.values()];rows,count=compare_outputs(new,old,g)
 hdrdiff=any(x['header_changed_words'] for x in rows)
 out={'schema':'UDM37_LBLRTM_PANEL_STAGE_DIAGNOSIS_V1','status':'SPECTRAL_BITWISE_EQUAL_HEADER_METADATA_REVIEW_PENDING' if hdrdiff else 'PASS_SCOPED_ALL45_SPECTRAL_AND_HEADER_BITWISE_EQUAL','case':c,'trace_sha256':sha(new/'UDM37_PANEL_TRACE'),'executable_sha256':json.loads((new/'prepared.json').read_text())['executable']['sha256'],'solver_actual_child_returncode':0,'layers_compared':45,'samples_bitwise_compared':count,'stage_groups':len(g),'duplicate_target_panels':len(g)>2,'points':points,'layers':rows,'physical_reference_acceptance':'FAIL_ORIGINAL_NEGATIVE_OD_PRESERVED','limitations':['PANEL snapshot diagnosis only; does not isolate GI versus YI/SPPSP before PANEL.','No flux residual attribution or UDM optical-parameter accuracy acceptance.','All raw trace spectra remain private.','Header metadata differences, if any, require source-specific review before full noninterference acceptance.']}
 (D/f'{c}-trace-analysis.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print(out['status'],c,count,[(x['layer'],x['R1_after_RADFNI'],x['negative_created_from_nonnegative_R1_R2_stencil']) for x in points])
if __name__=='__main__':main()
