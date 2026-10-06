import hashlib,importlib.util,json,math,re,struct
from pathlib import Path
R=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP');D=R/'build/udm37-lblrtm-panel-trace-v1'
P=D/'analyze_panel_trace.py';spec=importlib.util.spec_from_file_location('stage_reader',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
src=R/'build/udm37-lblrtm-stock-build-v1/attempt-1/source/LBLRTM/src/lblrtm.f90';s=src.read_text();assert '(YID(2),HTIME)' in s and 'CALL FTIME (HTIME)' in s
allcases=[]
for c in ('cpl','nocpl'):
 prev=D/f'{c}-trace-analysis.json';q=json.loads(prev.read_text());assert q['status']=='SPECTRAL_BITWISE_EQUAL_HEADER_METADATA_REVIEW_PENDING'
 C=R/f'build/udm37-lblrtm-held-state-paneltrace-{c}-od-run-v1/runs/od-v1';B=R/f'build/udm37-lblrtm-held-state-{"continuum" if c=="cpl" else "nocpl"}-od-run-v1/runs/od-v1'
 clocks=set()
 for row in q['layers']:
  assert len(row['header_changed_words'])==1;v=row['header_changed_words'][0];assert v['word_zero_based']==168
  old=bytes.fromhex(v['old_hex']).decode('ascii');new=bytes.fromhex(v['new_hex']).decode('ascii');assert re.fullmatch(r'\d\d:\d\d:\d\d',old) and re.fullmatch(r'\d\d:\d\d:\d\d',new)
  assert old in (B/'TAPE6').read_text() and new in (C/'TAPE6').read_text();clocks.add((old,new))
 assert len(clocks)==1
 groups=m.trace(C/'UDM37_PANEL_TRACE');proof=[]
 for key,g in groups.items():
  a,b,cc,dd=g;pt=next(x for x in q['points'] if x['layer']==a['layer']);limlo=a['n1r2']+(4 if a['n1r2']==1 else 0);limhi=a['nhi']//4+1
  stencils=[]
  for idx in pt['R2_stencil_indices_1based']:
   j=limlo+4*((idx-limlo)//4);assert limlo<=j<=limhi;j3=(j-1)//4+1;r=idx-j;pos=[j3-1,j3,j3+1,j3+2];sv=[a['r3'][x-1] for x in pos];before=a['r2'][idx-1]
   x00=-7/128;x01=105/128;x02=35/128;x03=-5/128;x10=-1/16;x11=9/16
   if r==0:calc=before+sv[1];w=[0,1,0,0]
   elif r==1:calc=before+x00*sv[0]+x01*sv[1]+x02*sv[2]+x03*sv[3];w=[x00,x01,x02,x03]
   elif r==2:calc=before+x10*(sv[0]+sv[3])+x11*(sv[1]+sv[2]);w=[x10,x11,x11,x10]
   else:calc=before+x03*sv[0]+x02*sv[1]+x01*sv[2]+x00*sv[3];w=[x03,x02,x01,x00]
   after=b['r2'][idx-1];assert struct.pack('<d',calc)==struct.pack('<d',after),(calc,after)
   stencils.append({'R2_index_1based':idx,'phase':r,'R2_before':before,'R3_indices_1based':pos,'R3_values':sv,'weights':w,'R2_after':after,'reconstruction_bitwise_exact':True,'negative_created_from_nonnegative_stencil':before>=0 and min(sv)>=0 and after<0})
  proof.append({'layer':a['layer'],'all_pre_PANEL_grids_nonnegative':min(a['r1'])>=0 and min(a['r2'])>=0 and min(a['r3'])>=0,'negative_after_R3_to_R2':min(b['r2'])<0,'negative_stencils':sum(x['negative_created_from_nonnegative_stencil'] for x in stencils),'R3_to_R2_stencils':stencils})
 assert next(x for x in proof if x['layer']==44)['all_pre_PANEL_grids_nonnegative']
 assert next(x for x in proof if x['layer']==44)['negative_stencils']>=1
 allcases.append({'case':c,'prior_analysis_sha256':sha(prev),'all45_spectral_samples_and_panel_headers_bitwise_exact':True,'samples':q['samples_bitwise_compared'],'all177_header_words_exact_except_word168':True,'timestamp_old_new':list(clocks)[0],'source_field':'FILHDR YID(2) equivalenced HTIME; FTIME assigns it at run initialization (lblrtm.f90:531,661). YID begins word167; therefore word168 is HTIME.','duplicate_panels':q['duplicate_target_panels'],'interpolation_proofs':proof})
out={'schema':'UDM37_PANEL_TRACE_LOCAL_SOURCE_CAUSAL_PROOF_V1','status':'PASS_SCOPED_INSTRUMENTATION_NONINTERFERENCE_AND_LOCAL_INTERPOLATION_PROOF','source_pins':{'lblrtm_f90_sha256':sha(src),'stock_oprop_sha256':sha(R/'build/udm37-lblrtm-stock-build-v1/attempt-1/source/LBLRTM/src/oprop.f90'),'trace_patch_sha256':sha(D/'instrumentation.patch')},'cases':allcases,'conclusions':['Both instrumented cases preserve all45-layer output values/panel headers bitwise, with only the documented HTIME header field changing.','At the captured layer44 minimum, all three pre_PANEL arrays are nonnegative; negative R2 values are introduced by the signed R3-to-R2 stencil, then propagate through R2-to-R1 and positive RADFNI scaling. Exact stencil evaluations reconstruct captured negatives bitwise.','At layer21 with coupling enabled, negative R1/R2/R3 entries already exist before PANEL; this mechanism is different from the layer44 interpolation overshoot.','NOCPL suppresses both GI strength correction and YI/SPPSP terms; GI versus YI and individual molecular contributions are not yet isolated.'],'physical_reference_acceptance':'FAIL_NEGATIVE_OD_RETAINED','WRF4_37_flux_residual_attributed':False,'no_new_models_or_builds':True}
(D/'local-diagnosis-proof.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print(out['status'],[(x['case'],[(y['layer'],y['negative_stencils']) for y in x['interpolation_proofs']]) for x in allcases])
