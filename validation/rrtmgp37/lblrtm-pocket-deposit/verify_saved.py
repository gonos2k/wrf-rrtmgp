#!/usr/bin/env python3
"""Offline verifier for the lossless selected-record deposit capsule.

Standard-library only. It reads the 45 exact saved Fortran record pairs and
the two exact OD panel-header records in this package; it does not access the
full source trace, OD samples, build tree, compiler, or solver.
"""
from __future__ import annotations
import hashlib, json, math, struct, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
TARGETS={
 1:(262,618.5730133333337),2:(339,618.8632177777781),
 3:(369,618.9762844444448),4:(416,619.1534222222226),
 5:(1200,721.6068977777784),6:(1275,721.8895644444451),
 7:(1232,721.7275022222228),8:(1350,722.1722311111117),
}
X00,X01,X02,X03=-7.0/128.0,105.0/128.0,35.0/128.0,-5.0/128.0
X10,X11=-1.0/16.0,9.0/16.0

def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def f64bits(x:float)->bytes:return struct.pack('<d',x)
def read_json(name:str):return json.loads((HERE/name).read_text())
def check(condition:bool,message:str):
 if not condition:raise ValueError(message)
def record(data:bytes,where:str):
 check(len(data)>=8,where+': short record')
 n=struct.unpack_from('<i',data,0)[0]
 check(n>0 and len(data)==n+8,where+': record length mismatch')
 check(struct.unpack_from('<i',data,len(data)-4)[0]==n,where+': trailing marker mismatch')
 return data[4:-4]
def read_snapshot(path:Path,expected_seq:int):
 data=path.read_bytes(); pos=0
 hp=record(data[pos:pos+280],str(path)+' header');pos+=280
 vp=record(data[pos:],str(path)+' values')
 check(len(hp)==272 and hp[:8]==b'POCKOWN7',str(path)+': expected POCKOWN7 payload')
 iv=struct.unpack_from('<33q',hp,8)
 rv=struct.unpack('<11d',vp)
 check(iv[0]==expected_seq,str(path)+': sequence mismatch')
 check(all(math.isfinite(x) for x in rv),str(path)+': nonfinite values')
 return {'iv':iv,'rv':rv,'raw_sha256':sha(data),'raw_size':len(data)}
def read_header(path:Path):
 data=path.read_bytes();p=record(data,str(path))
 check(len(p)==32,str(path)+': panel header payload size')
 v1,v2,dv=struct.unpack_from('<3d',p);count=struct.unpack_from('<q',p,24)[0]
 check(all(math.isfinite(x) for x in (v1,v2,dv)) and dv>0 and count>0,'bad panel header')
 return {'v1':v1,'v2':v2,'dv':dv,'n':count,'raw_sha256':sha(data)}
def close(a:float,b:float,dv:float)->bool:return abs(a-b)<=max(1e-10,abs(dv)*1e-7)
def ordered_int(x:float)->int:
 u=struct.unpack('>Q',struct.pack('>d',x))[0]
 return (~u & ((1<<64)-1)) if u>>63 else u|(1<<63)
def ulps(a:float,b:float)->int:return abs(ordered_int(a)-ordered_int(b))
def frame(iv,rv):
 # Header integer offsets from the pinned POCKOWN7 writer's WRITE list.
 return (iv[4],iv[6:9],iv[9:12],iv[12:27],iv[27:29],rv[3:7])
def interp(before:float,residue:int,r2:dict[int,float])->float:
 if residue==0:return before+r2[0]
 if residue==1:
  z=before;z=z+X00*r2[-1];z=z+X01*r2[0];z=z+X02*r2[1];z=z+X03*r2[2];return z
 if residue==2:return before+X10*(r2[-1]+r2[2])+X11*(r2[0]+r2[1])
 z=before;z=z+X03*r2[-1];z=z+X02*r2[0];z=z+X01*r2[1];z=z+X00*r2[2];return z
def main()->int:
 m=read_json('manifest.json');result=read_json('provenance/deposit-result-v4.json')
 integrity=read_json('package-integrity.json')
 expected_paths=set(integrity['files'])
 actual_paths={p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if p.is_file() and p.relative_to(HERE).as_posix()!='package-integrity.json'}
 check(actual_paths==expected_paths,'closed package file roster')
 for rel,expected_sha in integrity['files'].items():
  check(sha((HERE/rel).read_bytes())==expected_sha,'package file hash '+rel)
 check(m.get('schema')=='UDM37_LBLRTM_POCKET_DEPOSIT_CAPSULE_V1','manifest schema')
 check(m.get('status')=='CAPSULE_EXTRACTED_FROM_SUCCESSFUL_RC0_CONTINUATION','capsule status')
 check(m.get('source_streams',{}).get('trace',{}).get('sha256')=='a28cb2e7d1487ac22287202606b69e3edc893329468f642831dd7cf3c12a6a33','successful trace pin')
 check(m.get('source_streams',{}).get('ODdeflt_021',{}).get('sha256')=='b5b097fdb7df17dcd09d141a796cea4ce5b60ff0d5a5f9c7cfdde2863ffd6619','successful OD pin')
 check(m['excluded_attempt']['used'] is False,'capped attempt must not be used')
 check((HERE/'selected-records.bin').stat().st_size==m['selected_record_capsule_size_bytes'],'capsule size')
 cap=(HERE/'selected-records.bin').read_bytes();check(sha(cap)==m['selected_record_capsule_sha256'],'capsule hash')
 hcap=(HERE/'owner-panel-headers.bin').read_bytes();check(sha(hcap)==m['owner_panel_header_capsule_sha256'],'owner header capsule hash')
 records={}
 for e in m['record_pairs']:
  p=HERE/e['path'];raw=p.read_bytes()
  check(len(raw)==e['source_pair_size'] and sha(raw)==e['capsule_pair_sha256'],'record pair pin')
  off=e['capsule_concatenated_offset'];check(cap[off:off+len(raw)]==raw,'capsule/pair byte mismatch')
  snap=read_snapshot(p,e['seq']);iv,rv=snap['iv'],snap['rv']
  check((iv[1],iv[2],iv[3],iv[4],iv[5],e['tag'])==(e['target_id'],e['stage'],e['level'],e['layer'],e['index'],'POCKOWN7'),'manifest/event identity')
  check(sha(raw[:280][4:-4])==e['header_payload_sha256'],'event header payload hash')
  check(sha(raw[280+4:-4])==e['value_payload_sha256'],'event value payload hash')
  records[e['seq']]=snap
 check(len(records)==45 and len(records)==m['selected_record_pair_count'],'selected event count')
 owner_headers={}
 for h in m['owner_panel_headers']:
  raw=(HERE/h['path']).read_bytes();off=h['capsule_offset']
  check(hcap[off:off+len(raw)]==raw and sha(raw)==h['raw_record_sha256'],'panel header capsule bytes')
  data=read_header(HERE/h['path'])
  check(data['raw_sha256']==h['raw_record_sha256'],'panel raw header hash')
  for k in ('v1','v2','dv','sample_count'):
   kk='n' if k=='sample_count' else k
   check(data[kk]==h[k],f'panel header metadata {k}')
  owner_headers[h['header_index_1based']]=data
 # Verify terminal execution/postflight/inventory and preserve all known failures.
 terminal=read_json('provenance/solver-execution.json');post=read_json('provenance/solver-postflight.json')
 inventory=read_json('provenance/solver-output-inventory.json');cmp=read_json('provenance/root-all45-od-byte-comparison.json')
 od=read_json('provenance/root-original-physics-OD21-summary.json');reader_exec=read_json('provenance/reader-execution.json')
 strict=read_json('provenance/strict-parser-v10-execution.json')
 for name,h in m['terminal_receipt_paths'].items():check(sha((HERE/h['path']).read_bytes())==h['sha256'],'terminal receipt hash '+name)
 exec_sha=m['terminal_receipt_paths']['solver-execution.json']['sha256']
 check((terminal['status'],terminal['actual_child_returncode'],terminal['reaped'],terminal['process_group_clean'],terminal['timed_out'],terminal['cap_reason_during_run'])==('TERMINAL',0,True,True,False,None),'solver terminal proof')
 check(post['status']=='POSTFLIGHT_PASS' and post['actual_child_returncode']==0 and post['execution_sha256']==exec_sha and post['inputs_unchanged'] is True and len(post['inputs_before'])==38 and len(post['inputs_after'])==38,'postflight proof')
 check(inventory['actual_child_returncode']==0 and inventory['execution_sha256']==exec_sha and inventory['physical_reference_accepted'] is False and inventory['negative_od_gate']=='REMAINS_FAIL','output inventory scope')
 om={x['path']:(x['sha256'],x['size_bytes']) for x in inventory['outputs']}
 check(om['UDM37_NEGATIVE_POCKET_TRACE']==(m['source_streams']['trace']['sha256'],m['source_streams']['trace']['size_bytes']),'trace output inventory pin')
 check(om['ODdeflt_021']==(m['source_streams']['ODdeflt_021']['sha256'],m['source_streams']['ODdeflt_021']['size_bytes']),'OD output inventory pin')
 check(cmp['all45_outside_HTIME_equal'] is True and cmp['full_file_exact_count']==0 and cmp['original_OFF_strict_full_file_FAIL_preserved'] is True and cmp['physical_reference_accepted'] is False,'all45 failure scope')
 check(od['negative_count']==654 and od['negative_min']==-4.884429085432753 and od['negative_OD_gate']=='FAIL_PRESERVED' and od['physical_reference_accepted'] is False,'OD21 failure scope')
 check(reader_exec['actual_returncode']==0 and reader_exec['reader_sha256']=='6506dcf7e44a6cf03542afe85e34794ba0fada1a97032c28e4b5e399a75a9605' and reader_exec['output_sha256']==m['root_reader_result_sha256'],'root reader execution pin')
 check(strict['actual_returncode']==2 and 'target 5 predecessor-header stage-1 R1' in strict['stderr'] and strict['physical_reference_accepted'] is False and strict['negative_OD_gate']=='FAIL_PRESERVED','strict validator failure retained')
 # Reconstruct only selected R2->R1 deposits from losslessly packaged records.
 out=[];v4targets={r['target_id']:r for r in result['targets']}
 selected_ids=[s['target_id'] for s in m['selections']]
 check(len(selected_ids)==8 and set(selected_ids)==set(range(1,9)) and len(set(selected_ids))==8,'selection target roster must be exactly IDs 1..8')
 consumed=[]
 for s in m['selections']:
  tid=s['target_id'];sample,nu=TARGETS[tid];check(sample==s['sample_index_1based'] and nu==s['target_nu'],'frozen target roster')
  head=owner_headers[s['owner_header_index_1based']]
  check(sample<=head['n'] and close(head['v1']+(sample-1)*head['dv'],nu,head['dv']),'OD owner header/sample coordinate')
  pre=records[s['stage2_r1_seq']];postr=records[s['stage3_r1_seq']]
  iv0,rv0=pre['iv'],pre['rv'];iv1,rv1=postr['iv'],postr['rv']
  consumed.extend((s['stage2_r1_seq'],s['stage3_r1_seq']))
  j1=iv0[12]+sample-1
  check(iv0[5]==j1==iv1[5]==s['r1_index_1based'],'panel local sample to global R1 index')
  check(iv0[1:5]==(tid,2,1,21) and iv1[1:5]==(tid,3,1,21),'R1 target/stage identity')
  check(frame(iv0,rv0)==frame(iv1,rv1),'R1 full frame identity')
  nlo,nhi=iv0[12],iv0[13]
  check(nlo<=j1<=nhi and iv0[14]<=j1<=iv0[15] and 1<=j1<=iv0[6],'R1 active/backing bounds')
  base=nlo+4*((j1-nlo)//4);j2=(base-1)//4+1;res=j1-base
  check(base==nlo+4*((j1-nlo)//4) and j2==(base-1)//4+1 and res==j1-base,'stencil group mapping')
  needed=[j2] if res==0 else [j2-1,j2,j2+1,j2+2]
  check({str(i):s['stage2_r2_seq_by_idx'][str(i)] for i in needed}==s['stage2_r2_seq_by_idx'],'R2 stencil roster')
  r2={}
  for idx in needed:
   seq=s['stage2_r2_seq_by_idx'][str(idx)];consumed.append(seq)
   sr=records[seq];iv,rv=sr['iv'],sr['rv']
   check(iv[1:5]==(tid,2,2,21) and iv[5]==idx,'R2 row identity')
   check(frame(iv,rv)==frame(iv0,rv0),'R2 frame matches R1 frame')
   check(iv[16]<=idx<=iv[17] and 1<=idx<=iv[7],'R2 active/backing bounds')
   check(close(rv[1],rv[3]+(idx-1)*rv[5],rv[5]),'R2 native coordinate identity')
   r2[idx-j2]=rv[2]
  pred=interp(rv0[2],res,r2);actual=rv1[2];dist=ulps(pred,actual)
  check(dist==0,f'target {tid} deposit residual {dist} ULP')
  r=v4targets[tid]
  check(f64bits(pred)==f64bits(r['predicted_after']) and f64bits(actual)==f64bits(r['r1_stage3_after']),'capsule vs root v4 result')
  out.append({'target_id':tid,'sample_index_1based':sample,'r1_index_1based':j1,'owner_header_1based':s['owner_header_index_1based'],'residue':res,'stage2_r1':rv0[2],'stage3_r1':actual,'predicted_increment':pred-rv0[2],'exact_binary64':True,'ulp_distance':dist})
 check(len(consumed)==len(records) and set(consumed)==set(records),'every selected capsule record must be consumed exactly once by the eight target selections')
 check(len(out)==8 and result['status']=='PASS_DEPOSIT_EXACT' and result['exact_matches']==8 and result['max_ulp_distance']==0,'root v4 result acceptance')
 report={'schema':'UDM37_LBLRTM_POCKET_DEPOSIT_PACKAGE_VERIFICATION_V1','status':'PASS_SAVED_CAPSULE_RECONSTRUCTION','target_count':8,'selected_record_pairs':45,'owner_panel_headers':len(owner_headers),'exact_binary64_matches':8,'max_ulp_distance':0,'all45_outside_HTIME_equal':True,'strict_full_file_OD_failure_preserved':True,'OD21_negative_count':654,'OD21_minimum':-4.884429085432753,'strict_v10_parser_returncode':2,'strict_v10_error':'target 5 predecessor-header stage-1 R1: expected exactly one record, found 0','physical_reference_accepted':False,'targets':out,'scope':'Exact reconstruction of eight selected PANEL R2-to-R1 deposits from packaged lossless records only; no full trace, physical acceptance, complete CNVFNV/continuum attribution, or RADFNI proof.'}
 print(json.dumps(report,sort_keys=True,indent=2))
 return 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as e:
  print(f'VERIFY_FAILED: {e}',file=sys.stderr);raise SystemExit(1)
