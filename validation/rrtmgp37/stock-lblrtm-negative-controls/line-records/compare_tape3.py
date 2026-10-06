#!/usr/bin/env python3
"""Read-only raw TAPE3 NOCPL-vs-CPL comparator; no LNFL/LBLRTM invocation."""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, math, os, struct, sys
from pathlib import Path

ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
CPL_RUN=ROOT/'build/udm37-lblrtm-common-band-line-generation-v1/run-v6'
CPL_PLAN=ROOT/'build/udm37-lblrtm-common-band-line-generation-v1/plan-v6.json'
CPL_PLAN_SHA='7ee1eddd5d1c0970503d2dc7730c494f77bb2f919bf822795f6252d57248e6f6'
CPL_TAPE3_SHA='56bd55fa256ed3b3a672bd4bcd88034cd7086d4fbef2a1def9480199dab2b388'
CPL_TAPE5_SHA='697357190795f9451e83afe232675dcfd4dc1ddf1c036f1f347c261d973ba970'
CPL_POSTFLIGHT_SHA='7d7fc12accebe46b2e5a0d220cc82c8ba103d6b2d2f36953181f45e75534217e'
CPL_EXEC_SHA='881dc5bdf2716df7d3e11d404910ba9f1142df23dd754fa68fc8da60e47ebe60'
NOCPL_PLAN=ROOT/'build/udm37-lblrtm-nocpl-control-v2/plan.json'
NOCPL_PLAN_SHA='2bc461ba52d6ffab7b5be9f4cba08ee330723e4fec67ae45875b813847dff98b'
NOCPL_TAPE5=ROOT/'build/udm37-lblrtm-nocpl-control-v2/TAPE5'
NOCPL_TAPE5_SHA='3b16face2879d3967f47ad94eecf0eeabb3fd74ce3c6e0fb2d8b1bc7e79066eb'
CONTROL_DIFF=ROOT/'build/udm37-lblrtm-nocpl-control-v2/control-diff.json'
CONTROL_DIFF_SHA='c10110549609d57c59d6dc4309ba0afc09efe733c7eea5e954fc4491a7841261'
LNFL=ROOT/'build/udm37-lblrtm-reference-stage-v1/sources/LNFL/src/lnfl.f'
LNFL_SHA='d47b7b296b747837bbec8df06a7c8ea1df2ec241546b1db4a15f6b02b98a4ad6'
UTIL=ROOT/'build/udm37-lblrtm-reference-stage-v1/sources/LNFL/aer_rt_utils/util_gfortran.f90'
UTIL_SHA='64d679afbffa23f81c5faf3289c562b37ee65019d5ff176dd19528cef71b99e2'
DOC=ROOT/'build/udm37-lblrtm-reference-stage-v1/sources/LNFL/docs/lnfl_instructions'
DOC_SHA='e044ed5eb774a99d2dd1086ff98ec879cbd5440dc816bd305a37e66548682601'
LINEFILE=ROOT/'build/udm37-lblrtm-reference-stage-v1/data/aer_v_3.8.1/line_file/aer_v_3.8.1'
LINEFILE_SHA='d0ec800cfaeaaa7ab7af7b8168f45b205e383272e147373df6d0eed2677f2bd3'
BINARY=ROOT/'build/udm37-lblrtm-stock-build-v1/attempt-2/run/LNFL/lnfl_v3.2_linux_gnu_sgl'
BINARY_SHA='825d05dcc530a5bb196f4a95a353f624787089d5b9be75a6696fd0b7c6542586'
EXPECTED_CPL_MAIN=648464
EXPECTED_CPL_COUPLED=128015
NWORDS=9750
NLINE=250
REC_BYTES=NWORDS*4

FIELD_OFFSETS={
 'vnu':(0,8), 'strength':(2000,4), 'air_width':(3000,4), 'lower_energy':(4000,4),
 'molecule_isotope':(5000,4), 'self_width':(6000,4), 'temperature_exponent':(7000,4),
 'pressure_shift':(8000,4), 'iflg_coupling_flag':(9000,4),
 'additional_broadening_flags':(10000,28), 'additional_broadening_data':(17000,84),
 'speed_dependence_data':(38000,4)
}
PHYSICAL_FIELDS=tuple(k for k in FIELD_OFFSETS if k!='iflg_coupling_flag')

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()

def expect(path:Path,digest:str):
 if not path.is_file() or sha(path)!=digest: raise ValueError(f'pin mismatch: {path}')

def read_record(f, path):
 start=f.tell(); lead=f.read(4)
 if not lead: return None
 if len(lead)!=4: raise ValueError(f'truncated leading marker {path}:{start}')
 n=struct.unpack('<i',lead)[0]
 if n<0 or n>10_000_000: raise ValueError(f'invalid record length {n} at {path}:{start}')
 payload=f.read(n); tail=f.read(4)
 if len(payload)!=n or len(tail)!=4: raise ValueError(f'truncated sequential record {path}:{start}')
 if struct.unpack('<i',tail)[0]!=n: raise ValueError(f'record marker mismatch {path}:{start}')
 return start,n,payload

def value(payload, name, i):
 off,width=FIELD_OFFSETS[name]
 b=payload[off+width*i:off+width*(i+1)]
 if len(b)!=width: raise ValueError(f'field truncation {name} row {i}')
 if name=='vnu': return struct.unpack('<d',b)[0]
 if name in ('molecule_isotope','iflg_coupling_flag'): return struct.unpack('<i',b)[0]
 return struct.unpack('<f',b)[0]

def signature(payload,i):
 return {name:payload[o+w*i:o+w*(i+1)] for name,(o,w) in FIELD_OFFSETS.items() if name!='iflg_coupling_flag'}

def inspect_tape3(path:Path, mode:str):
 """Yield valid main records and fill summary; rejects incomplete or alien layout."""
 stats={'path':str(path),'sha256':sha(path),'size_bytes':path.stat().st_size,'first_header_sha256':None,
        'first_header_bytes':None,'block_count':0,'total_valid_records':0,'main_records':0,'coupled_records':0,
        'flags':{},'species_counts':{},'isotope_counts':{},'nlte_marker_counts':{},'min_vnu':None,'max_vnu':None,
        'max_block_header_lines':0,'record_count':0,'block_header_payload_hashes':[]}
 def gen():
  with path.open('rb') as f:
   first=read_record(f,path)
   if first is None: raise ValueError(f'empty TAPE3: {path}')
   _,n,header=first
   if n!=1664: raise ValueError(f'unexpected TAPE3 line header length {n}')
   stats['first_header_bytes']=n; stats['first_header_sha256']=hashlib.sha256(header).hexdigest(); stats['record_count']=1
   prev=None
   while True:
    h=read_record(f,path)
    if h is None: break
    stats['record_count']+=1
    _,hn,hdata=h
    if hn!=24: raise ValueError(f'expected 24-byte block header, found {hn} at block {stats["block_count"]+1}')
    vlo,vhi,nlines,nwords=struct.unpack('<ddii',hdata)
    if not (math.isfinite(vlo) and math.isfinite(vhi) and vlo<=vhi and 0<nlines<=NLINE and nwords==NWORDS):
     raise ValueError(f'bad block header #{stats["block_count"]+1}: {(vlo,vhi,nlines,nwords)}')
    d=read_record(f,path)
    if d is None: raise ValueError('missing data record after block header')
    stats['record_count']+=1
    _,dn,payload=d
    if dn!=REC_BYTES: raise ValueError(f'expected fixed {REC_BYTES}-byte data array, got {dn}')
    stats['block_count']+=1; stats['total_valid_records']+=nlines
    stats['max_block_header_lines']=max(stats['max_block_header_lines'],nlines)
    stats['block_header_payload_hashes'].append(hashlib.sha256(hdata).hexdigest())
    for i in range(nlines):
     flag=value(payload,'iflg_coupling_flag',i)
     stats['flags'][str(flag)]=stats['flags'].get(str(flag),0)+1
     if mode=='nocpl' and flag!=0: raise ValueError(f'NOCPL line flag is {flag}, expected zero at valid record {stats["total_valid_records"]-nlines+i+1}')
     if flag<0:
      # Coupling payload slots are not ordinary line records: their VNU/MOL
      # storage is overloaded with coupling coefficients and is not a center/species.
      stats['coupled_records']+=1
     else:
      mol=value(payload,'molecule_isotope',i)
      species=mol%100; isotope=(mol%1000)//100
      stats['species_counts'][str(species)]=stats['species_counts'].get(str(species),0)+1
      stats['isotope_counts'][str(isotope)]=stats['isotope_counts'].get(str(isotope),0)+1
      nlte=mol//1000
      stats['nlte_marker_counts'][str(nlte)]=stats['nlte_marker_counts'].get(str(nlte),0)+1
      vnu=value(payload,'vnu',i)
      if not math.isfinite(vnu): raise ValueError('nonfinite ordinary line center')
      if prev is not None and vnu<prev: raise ValueError('ordinary line centers are not nondecreasing')
      prev=vnu
      stats['min_vnu']=vnu if stats['min_vnu'] is None else min(stats['min_vnu'],vnu)
      stats['max_vnu']=vnu if stats['max_vnu'] is None else max(stats['max_vnu'],vnu)
      stats['main_records']+=1
      yield {'signature':signature(payload,i),'flag':flag,'vnu':vnu,'mol':mol,'block':stats['block_count'],'slot':i+1}
   # Force a check for exact EOF (read_record reports EOF only at record boundary).
   if f.tell()!=path.stat().st_size: raise ValueError('TAPE3 scan did not end at EOF')
  stats['record_count']=stats['record_count']
 return gen(),stats

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--nocpl-run-dir',type=Path,required=True,help='Completed authorized LNFL NOCPL run directory, containing TAPE3, TAPE5, execution.json, postflight.json, and TAPE1 symlink')
 ap.add_argument('--report',type=Path,required=True,help='New output JSON path outside both run directories')
 a=ap.parse_args(); nocpl=a.nocpl_run_dir.resolve(); report_path=a.report.resolve()
 if report_path.exists(): raise FileExistsError(f'refuse existing report: {report_path}')
 if report_path.is_relative_to(nocpl) or report_path.is_relative_to(CPL_RUN): raise ValueError('report must be outside immutable run directories')
 for p,h in [(CPL_PLAN,CPL_PLAN_SHA),(CPL_RUN/'TAPE3',CPL_TAPE3_SHA),(CPL_RUN/'TAPE5',CPL_TAPE5_SHA),(CPL_RUN/'postflight.json',CPL_POSTFLIGHT_SHA),(CPL_RUN/'execution.json',CPL_EXEC_SHA),(NOCPL_PLAN,NOCPL_PLAN_SHA),(NOCPL_TAPE5,NOCPL_TAPE5_SHA),(CONTROL_DIFF,CONTROL_DIFF_SHA),(LNFL,LNFL_SHA),(UTIL,UTIL_SHA),(DOC,DOC_SHA),(LINEFILE,LINEFILE_SHA),(BINARY,BINARY_SHA)]: expect(p,h)
 plan=json.loads(NOCPL_PLAN.read_text())
 if plan.get('status')!='PREPARED_NOT_EXECUTED':
  # The immutable prepared plan may remain unchanged after a later run; status is not runtime evidence.
  pass
 if plan['lnfl_build']['binary']['sha256']!=BINARY_SHA: raise ValueError('NOCPL plan binary pin mismatch')
 if plan['execution_policy']['invocations_max']!=1 or plan['execution_policy']['retry'] is not False: raise ValueError('NOCPL run plan scope mismatch')
 tape5=(nocpl/'TAPE5').read_bytes(); cpl_tape5=(CPL_RUN/'TAPE5').read_bytes(); expected_nc=NOCPL_TAPE5.read_bytes()
 if tape5!=expected_nc: raise ValueError('executed NOCPL TAPE5 differs from prepared NOCPL control')
 if cpl_tape5!=(ROOT/'build/udm37-lblrtm-common-band-line-generation-v1/run-v6/TAPE5').read_bytes(): raise ValueError('CPL TAPE5 unexpected')
 control=json.loads(CONTROL_DIFF.read_text())
 offsets=[x['file_offset'] for x in control['changed_bytes']]
 actual=[i for i,(x,y) in enumerate(zip(cpl_tape5,tape5)) if x!=y]
 if len(cpl_tape5)!=len(tape5) or actual!=offsets or cpl_tape5[:145]!=tape5[:145] or cpl_tape5[150:]!=tape5[150:]: raise ValueError('TAPE5 control differs beyond the preregistered NOCPL token')
 if actual!=list(range(145,150)) or cpl_tape5[145:150]!=b'     ' or tape5[145:150]!=b'NOCPL': raise ValueError('TAPE5 change is not exactly HOLIND1 NOCPL')
 for d in (CPL_RUN,nocpl):
  link=d/'TAPE1'
  if not link.is_symlink() or str(link.resolve())!=str(LINEFILE) or sha(link.resolve())!=LINEFILE_SHA: raise ValueError(f'TAPE1 identity mismatch in {d}')
 exe_run=json.loads((nocpl/'execution.json').read_text())
 launch=json.loads((nocpl/'launch.json').read_text())
 post=json.loads((nocpl/'postflight.json').read_text())
 if exe_run.get('actual_child_returncode')!=0 or exe_run.get('timed_out') is not False: raise ValueError('NOCPL LNFL child did not complete successfully')
 if post.get('actual_child_returncode')!=0 or post.get('status')!='NOCPL_TAPE3_GENERATED': raise ValueError('NOCPL postflight is not a successful generation receipt')
 if launch.get('plan_sha256')!=NOCPL_PLAN_SHA or launch.get('command',[None])[0]!=str(BINARY): raise ValueError('NOCPL launch plan/binary mismatch')
 tape3=nocpl/'TAPE3'
 if not tape3.is_file() or not tape3.stat().st_size: raise ValueError('missing/empty NOCPL TAPE3')
 tape3_post=next((o for o in post.get('outputs',[]) if o.get('path')=='TAPE3'),None)
 if tape3_post is None or tape3_post.get('sha256')!=sha(tape3) or tape3_post.get('size_bytes')!=tape3.stat().st_size: raise ValueError('NOCPL postflight TAPE3 identity mismatch')
 cpl_iter,cpl_stats=inspect_tape3(CPL_RUN/'TAPE3','cpl')
 nc_iter,nc_stats=inspect_tape3(tape3,'nocpl')
 diffs=collections.Counter(); mismatches=[]; compared=0; pair_species=collections.Counter(); flag_transitions=collections.Counter()
 for idx,(old,new) in enumerate(itertools.zip_longest(cpl_iter,nc_iter),1):
  if old is None or new is None:
   diffs['main_line_count']+=1
   if len(mismatches)<8: mismatches.append({'ordinal':idx,'kind':'missing-main-line','cpl_present':old is not None,'nocpl_present':new is not None})
   continue
  compared+=1; pair_species[str(old['mol']%100)]+=1; flag_transitions[f'{old["flag"]}->{new["flag"]}']+=1
  names=[k for k in PHYSICAL_FIELDS if old['signature'][k]!=new['signature'][k]]
  for name in names: diffs[name]+=1
  if names and len(mismatches)<8: mismatches.append({'ordinal':idx,'kind':'ordinary-line-fields-differ','fields':names,'cpl':{k:old[k] for k in ('vnu','mol','flag','block','slot')},'nocpl':{k:new[k] for k in ('vnu','mol','flag','block','slot')}})
 # Iterate both to exhaustion so framing errors are raised and final stats populated.
 exact=(not diffs and cpl_stats['main_records']==EXPECTED_CPL_MAIN and cpl_stats['coupled_records']==EXPECTED_CPL_COUPLED and compared==cpl_stats['main_records']==nc_stats['main_records'] and cpl_stats['coupled_records']>0 and nc_stats['coupled_records']==0 and all(f=='0' for f in nc_stats['flags']))
 result={'schema':'UDM37_LNFL_TAPE3_CPL_NOCPL_LINE_COMPARISON_V1','status':'PASS_SCOPED_ORDINARY_LINES_EXACT_COUPLING_SUPPRESSED' if exact else 'FAIL_SCOPED_TAPE3_LINE_COMPARISON','scope':'Compares valid ordinary line records in saved LNFL TAPE3 sequential-unformatted streams. It does not run LBLRTM, validate optical depth, or map line records to RRTMGP g-points.','provenance':{'cpl_plan_sha256':sha(CPL_PLAN),'cpl_execution_sha256':sha(CPL_RUN/'execution.json'),'cpl_postflight_sha256':sha(CPL_RUN/'postflight.json'),'cpl_tape3_sha256':sha(CPL_RUN/'TAPE3'),'nocpl_plan_sha256':sha(NOCPL_PLAN),'nocpl_execution_sha256':sha(nocpl/'execution.json'),'nocpl_launch_sha256':sha(nocpl/'launch.json'),'nocpl_postflight_sha256':sha(nocpl/'postflight.json'),'nocpl_tape3_sha256':sha(tape3),'lnfl_binary_sha256':sha(BINARY),'lnfl_source_sha256':sha(LNFL),'gfortran_buffer_source_sha256':sha(UTIL),'lnfl_instructions_sha256':sha(DOC),'line_file_sha256':sha(LINEFILE),'cpl_tape5_sha256':sha(CPL_RUN/'TAPE5'),'nocpl_tape5_sha256':sha(nocpl/'TAPE5'),'control_diff_sha256':sha(CONTROL_DIFF)},'input_control':{'changed_byte_offsets':actual,'only_change_is_holind1_nocpl':actual==list(range(145,150)) and tape5[145:150]==b'NOCPL','same_pinned_linefile_for_both_runs':True},'binary_record_layout':{'compiler_record_markers':'GNU little-endian sequential-unformatted, leading/trailing 4-byte record byte counts','header_payload_bytes':1664,'block_header':'24 bytes: little-endian REAL*8 VLO,VHI then INTEGER*4 LINES,NWDS','data_payload_bytes':REC_BYTES,'data_words':NWORDS,'line_capacity':NLINE,'field_map':FIELD_OFFSETS,'physical_comparison_fields':list(PHYSICAL_FIELDS),'coupling_flag_field':'IFLG per line, INTEGER*4; excluded from ordinary-field identity comparison'},'cpl':cpl_stats,'nocpl':nc_stats,'comparison':{'paired_ordinary_lines':compared,'physical_field_mismatch_counts':dict(diffs),'first_mismatches':mismatches,'pair_species_counts':dict(pair_species),'coupling_flag_transitions':dict(flag_transitions),'exact_ordinary_line_records':not diffs and compared==cpl_stats['main_records']==nc_stats['main_records'],'coupled_records_removed':cpl_stats['coupled_records']-nc_stats['coupled_records'],'source_expected_main_lines':EXPECTED_CPL_MAIN,'source_expected_cpl_coupled_records':EXPECTED_CPL_COUPLED},'source_semantics':{'lnfl_instructions':'NOCPL suppresses all line coupling information on TAPE3/TAPE7 (pinned documentation around lines 164-165).','lnfl_source':'MOVE sets IFG2(I)=0 under NOCPL (lnfl.f:1068), then companion records are added only for IFG2(I)>=1 / ==5 (1084-1116); output block line count and records follow BLKOUT (1191-1196).','bufout':'Pinned util_gfortran.f90 BUFOUT writes unformatted IARRAY records (lines 262-278).','Interpretation':'Block boundaries/header counts and the file header can differ because coupled lines are removed. This check compares the ordered valid ordinary lines, preserving exact source-record bytes for every non-IFLG field; it does not assert TAPE3 files byte-identical.'},'limitations':['This is a structural/raw line-record comparison only; no absorption or radiance/flux calculation.','It does not validate all TAPE3 metadata semantics or optional extensions beyond this pinned GNU LNFL v3.2 layout.','The AER line data and generated TAPE3 are controlled research-use data; keep them private and do not redistribute.']}
 report_path.parent.mkdir(parents=True,exist_ok=True)
 report_path.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
 print(result['status'],f"paired={compared}",f"CPLcoupled={cpl_stats['coupled_records']}",f"NOCPLcoupled={nc_stats['coupled_records']}",f"diff_fields={sum(diffs.values())}")
 return 0 if exact else 1

if __name__=='__main__':
 try: sys.exit(main())
 except Exception as e:
  print(f'COMPARE_ERROR:{type(e).__name__}:{e}',file=sys.stderr); sys.exit(2)
