#!/usr/bin/env python3
"""Read existing outputs; build compact evidence/index proposal without engines or git edits."""
import hashlib,importlib.util,json,shutil,sys
from pathlib import Path
import numpy as np
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP');HERE=Path(__file__).resolve().parent;PKG=HERE/'package'
sys.dont_write_bytecode=True
V=ROOT/'build/udm-frozen-replay-validator-work/WRF/test/rrtmgp'
PINS={'test_column_replay':'823120117dc9f9b47578c8626b4ef40d89ea415cc889f27aa07b1e7fd94e0671','test_cloud_scm':'f58163c6d530851aa9f830a1b7a42b4bd6a4aa16245643ef0b66ae19315d889d','test_surface_scm':'67870eb8ab3e844ab8272ec5c6aeec700b560c0730de3f3205a1304ed0ea85b1','compare_column_replay':'300c25de26330c0ac413c6e3d82434374457b10fbae1da77680d2d9db3601454'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):return dict(original_workspace_path=str(Path(p).relative_to(ROOT)),sha256=sha(p),bytes=Path(p).stat().st_size)
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,sort_keys=True,allow_nan=False)+'\n')
for name,h in PINS.items():assert sha(V/(name+'.py'))==h
sys.path.insert(0,str(V));import test_column_replay as replay,compare_column_replay as cmp
assert not PKG.exists();PKG.mkdir()
artifacts={};inputs={};snapshots={}
def retain(source,local):
 source=ROOT/source if not Path(source).is_absolute() else Path(source)
 d=PKG/local;assert not d.exists();d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,d)
 assert sha(d)==sha(source);info=pin(source);artifacts[local]=info;inputs[str(source)]=info['sha256'];return local
plans=[ROOT/'build/udm-stratified-capture-plan-v5/plan.json',ROOT/'build/udm-stratified-replacement-plan-v1/plan.json']
assert sha(plans[0])=='4f9e642fad9b648f352805ac6f9d71363945df0388c1e0acc608b3740f374279'
assert sha(plans[1])=='cec533569e04e9acef90ffd1f1a48cc88dd9d47cc22f1183d160c01ab2fd5cdf'
old,new=[json.loads(p.read_text()) for p in plans]
lookup={p['name']:p for p in old['points']+new['points']}
cases=[('cf0_rain_low_cloud_proxy','canonical','build/udm-stratified-captures-v3'),('material_cf0_snow_daylight_proxy','canonical','build/udm-stratified-replacement-captures-v1'),('ice_clip_low_cloud_proxy','canonical','build/udm-stratified-captures-v4'),('ice_clip_high_cloud_proxy','canonical','build/udm-stratified-captures-v4'),('clear_control','canonical','build/udm-stratified-captures-v4'),('daylight_unclipped_liquid_cloud_control','canonical','build/udm-stratified-replacement-captures-v1'),('cf0_snow_high_cloud_proxy','historical_audit','build/udm-stratified-captures-v4'),('unclipped_cloud_control','historical_audit','build/udm-stratified-captures-v4')]
from netCDF4 import Dataset
history=Path(old['runtime_template'])/'wrfout_d01_2010-06-11_12:01:00';assert sha(history)=='7a76a430f1d37ba88ee2692c5cb076a271f3d525a1190b5cd824df3790225025'
with Dataset(history) as nc:
 nc.set_auto_maskandscale(False);mu=np.asarray(nc['COSZEN'][0],float)
rows=[];capture_inventories={}
for name,role,parent in cases:
 folder=ROOT/parent/name;point=lookup[name];rec=json.loads((folder/'receipt.json').read_text());assert rec['returncode']==0 and rec['history_sha256']==sha(history) and rec['postflight_pins_unchanged']
 local=f'evidence/{role}/{name}'
 receipt=retain(folder/'receipt.json',local+'/original-execution-receipt.json')
 row=dict(case=name,role=role,i=point['i'],j=point['j'],original_case_directory=str(folder.relative_to(ROOT)),original_execution_receipt=receipt,original_execution_status=rec['status'],history_file_sha256=rec['history_sha256'],history_geometry=[289,189,39],history_physics=[27,37,37],numeric_history_variables=210,history_all_numeric_raw_decoded_finite_unmasked=True,pins_unchanged=True,history_COSZEN=float(mu[point['j']-1,point['i']-1]),phases={},existing_root_receipts=[])
 for rootproof in sorted(folder.glob('root-*.json')):row['existing_root_receipts'].append(retain(rootproof,local+'/root/'+rootproof.name))
 if name=='cf0_rain_low_cloud_proxy':reportfiles={'LW':folder/'replay-recovery-v2/strict-lw.json','SW':folder/'replay-recovery-v3/strict-sw.json'};recoveryfolders=[folder/'replay-recovery-v2',folder/'replay-recovery-v3']
 elif name=='cf0_snow_high_cloud_proxy':reportfiles={'LW':folder/'recovery-v1/strict-lw-reanalysis.json','SW':folder/'recovery-v2/strict-sw.json'};recoveryfolders=[folder/'recovery-v1',folder/'recovery-v2']
 else:reportfiles={p:folder/('strict-'+p.lower()+'.json') for p in ['LW','SW']};recoveryfolders=[]
 row['linked_recovery_receipts']=[]
 for recovery in recoveryfolders:
  for f in sorted(recovery.glob('*receipt.json')):row['linked_recovery_receipts'].append(retain(f,local+'/recovery/'+recovery.name+'/'+f.name))
 ci={}
 for f in sorted((folder/'capture').iterdir()):
  if f.is_file() and f.suffix in ['.raw','.input','.result']:ci[f.name]=pin(f);inputs[str(f)]=sha(f)
 capture_inventories[name]=ci
 for phase in ['LW','SW']:
  rawfile=folder/'capture'/(phase.lower()+'.raw')
  if not rawfile.exists():
   assert role=='historical_audit' and name=='unclipped_cloud_control' and phase=='SW' and row['history_COSZEN']<0 and not reportfiles[phase].exists()
   row['phases'][phase]=dict(status='SW_NOT_RUN_AT_NIGHT_EXPECTED_PRODUCTION_GATE',actual_reference_calls=0,strict_sections=0);continue
  rp,i,j,raw=replay.read_raw(rawfile);ip,nc,nl,overlap,seed,iceflag,inp=replay.read_input(folder/'capture'/(phase.lower()+'.input'))
  assert (rp,ip,i,j,nc,raw['DP_HPA'].size)==(phase,phase,point['i'],point['j'],1,39)
  report=json.loads(reportfiles[phase].read_text());assert report['reference_comparison']['passed'] and report['reference_comparison']['sections_compared']==(20 if phase=='LW' else 46)
  strictfile=retain(reportfiles[phase],local+'/strict-'+phase.lower()+'.json')
  if 'files' in report:
   reference_file=Path(report['files']['reference_result'])
   for label,suffix in [('raw','.raw'),('input','.input'),('production_result','.result')]:assert sha(Path(report['files'][label]))==sha(folder/'capture'/(phase.lower()+suffix))
  else:
   assert name=='cf0_snow_high_cloud_proxy' and phase=='LW' and report['operation']=='REUSE_EXISTING_OUTPUT_NO_PROCESS' and report['new_reference_engine_calls']==0
   reference_file=reportfiles[phase].parent/'capture/lw.reference.result'
   for suffix in ['raw','input','result']:assert sha(reference_file.parent/('lw.'+suffix))==sha(folder/'capture'/('lw.'+suffix))
  ci[phase.lower()+'.reference.result']=pin(reference_file);inputs[str(reference_file)]=sha(reference_file)
  prod=cmp.read_result(folder/'capture'/(phase.lower()+'.result'));ref=cmp.read_result(reference_file)
  assert cmp.compare(prod,ref)==report['reference_comparison'] and np.array_equal(prod['sections']['MASK'],ref['sections']['MASK'])
  cf=raw['CF'];mass=raw['DRY_LAYER_MASS_KG_M2'];corrected={q:replay.corrected_hydrometeor(raw,q,path,39) for q,path in [('QC','LWP'),('QI','IWP'),('QR','RWP'),('QS','SWP'),('QG','GWP'),('QH','HWP')]}
  grid={q:v*mass*1000 for q,v in corrected.items()}
  ia=(cf>0)&(inp['IWP'][0,:39]>0)&(corrected['QI']>0);la=(cf>0)&(inp['LWP'][0,:39]>0)&(corrected['QC']>0)
  di=2*inp['REI'][0,:39];clip=ia&(di>180);realized=prod['sections']['MASK'][0,:39,:].any(1)
  stats=dict(actual_cf0_grid_phase_mass_g_m2={q:float(x[cf==0].sum()) for q,x in grid.items()},actual_cf_positive_grid_phase_mass_g_m2={q:float(x[cf>0].sum()) for q,x in grid.items()},actual_raw_omitted_rain_g_m2=float(raw['RWP_OMITTED'].sum()),actual_raw_omitted_snow_g_m2=float(raw['SWP_OMITTED'].sum()),active_liquid_native_grid_mass_g_m2=float(grid['QC'][la].sum()),active_liquid_radius_um=inp['REL'][0,:39][la].tolist(),active_liquid_layers=int(la.sum()),active_ice_layers=int(ia.sum()),active_requested_ice_diameter_um=di[ia].tolist(),eligible_ice_above180_grid_mass_g_m2=float(grid['QI'][clip].sum()),eligible_ice_above180_layers=int(clip.sum()),realized_mask_ice_above180_grid_mass_g_m2=float(grid['QI'][clip&realized].sum()),realized_mask_ice_above180_layers=int((clip&realized).sum()),active_liquid_inside_lookup=bool(((inp['REL'][0,:39][la]>=2.5)&(inp['REL'][0,:39][la]<=21.5)).all()),radius_mapping_selection_counts=report['adapter_input_checks']['radii']['selection_counts'])
  snap=dict(case=name,phase=phase,i=i,j=j,native_layers=39,adapter_layers=nl,overlap=overlap,captured_column_seed=seed,iceflag=iceflag,raw_CF=cf.tolist(),native_dry_mass_kg_m2=mass.tolist(),corrected_native_q={q:v.tolist() for q,v in corrected.items()},raw_native_q={q:raw[q].tolist() for q in corrected},native_source_radius_m={p:raw[p].tolist() for p in ['SOURCE_RE_CLOUD','SOURCE_RE_ICE','SOURCE_RE_SNOW']},radius_capability={p:float(raw[p].item()) for p in ['HAS_REQC','HAS_REQI','HAS_REQS']},host_fallback_radius_um={p:raw[p].tolist() for p in ['FALLBACK_REL','FALLBACK_REI','FALLBACK_RES']},adapter={p:inp[p][0].tolist() for p in ['CF','REL','REI','RES','LWP','IWP','RWP','SWP','GWP','HWP']},raw_mapped_radius_um={p:raw[p].tolist() for p in ['REL','REI','RES']},raw_frozen_phase_paths={p:raw[p].tolist() for p in ['GWP_GRID','GWP_OMITTED','GWP_RADIATION','HWP_GRID','HWP_OMITTED','HWP_RADIATION']},production_RL_USED_um=prod['sections']['RL_USED'][0,:39,0].tolist(),production_DI_USED_um=prod['sections']['DI_USED'][0,:39,0].tolist(),actual_eligibility_and_mass=stats,frozen_mode=float(inp['FROZEN_MODE'].item()),frozen_occurrence=float(inp['FROZEN_OCCURRENCE'].item()),table_sha256=''.join(chr(int(x)) for x in inp['FROZEN_TABLE_SHA256_BYTES'].ravel()),step=int(raw['RADIATION_STEP'].item()),source_seconds=float(raw['SOURCE_TIME_SECONDS'].item()),captured_MP_PHYSICS=int(raw['MP_PHYSICS'].item()),input_header=(folder/'capture'/(phase.lower()+'.input')).read_text().splitlines()[0])
  snapfile=local+'/profiles-'+phase.lower()+'.json';write(PKG/snapfile,snap);artifacts[snapfile]=dict(derived_from_capture_inventory_case=name,sha256=sha(PKG/snapfile),bytes=(PKG/snapfile).stat().st_size)
  row['phases'][phase]=dict(status='STRICT_PASS',strict_sections=report['reference_comparison']['sections_compared'],strict_report=strictfile,actual_profile_snapshot=snapfile,actual_reference_calls=1,actual_eligibility_and_mass=stats,captured_column_seed=seed,adapter_layers=nl,recorded_MASK_exact_equal_reference=True)
 rows.append(row)
assert len([r for r in rows if r['role']=='canonical'])==6 and sum(r['phases']['SW']['actual_reference_calls'] for r in rows)==7
write(PKG/'capture-hash-inventory.json',capture_inventories);artifacts['capture-hash-inventory.json']=dict(sha256=sha(PKG/'capture-hash-inventory.json'),bytes=(PKG/'capture-hash-inventory.json').stat().st_size)
# Retain every failure scope from first-point recovery and the historical snow/night attempts.
failpaths=['build/udm-stratified-captures-v2/cf0_rain_low_cloud_proxy/receipt.json','build/udm-stratified-captures-v3/cf0_rain_low_cloud_proxy/receipt.json','build/udm-stratified-captures-v3/cf0_rain_low_cloud_proxy/replay-recovery-v1/recovery-receipt.json','build/udm-stratified-captures-v3/cf0_rain_low_cloud_proxy/replay-recovery-v2/recovery-receipt.json','build/udm-stratified-captures-v4/cf0_snow_high_cloud_proxy/receipt.json','build/udm-stratified-captures-v4/unclipped_cloud_control/receipt.json']
failures=[retain(p,'evidence/failures/'+str(i+1)+'-'+Path(p).parent.name+'-'+Path(p).name) for i,p in enumerate(failpaths)]
provenance={}
for name,key in [('old','original-six-plan'),('new','replacement-plan')]:provenance[key]=retain(plans[0 if name=='old' else 1],'provenance/'+key+'.json')
for p in ['build/udm-stratified-capture-plan-v4/capture_runner.py','build/udm-stratified-capture-plan-v5/capture_runner.py','build/udm-stratified-capture-plan-v5/test_offline_paths_and_preflight.py','build/udm-stratified-replacement-plan-v1/capture_runner.py','build/udm-stratified-replacement-plan-v1/test_offline_runner.py','build/udm-stratified-replacement-plan-v1/planning-receipt.json','build/udm-stratified-replacement-plan-v1/independent-output-readback.json','build/udm-stratified-replacement-plan-v1/execution-summary.json','build/udm-six-anchor-summary-v1/summary.json','build/udm-six-anchor-summary-v1/table.md']:
 retain(p,'provenance/'+Path(p).parent.name+'/'+Path(p).name)
assetpins={}
for key in ['source_manifest','build_receipt','executable','configure','strict_reference','strict_reference_source','replay_validator']:
 x=new[key];assert sha(x['path'])==x['sha256'];assetpins[key]=dict(original_workspace_path=str(Path(x['path']).relative_to(ROOT)),sha256=x['sha256'],bytes=x['bytes'])
for key in ['runtime_asset_sha256','external_asset_sha256','executor_support_scripts','state_identity','planned_namelist']:assetpins[key]=new[key]
write(PKG/'production-reference-data-pins.json',assetpins);artifacts['production-reference-data-pins.json']=dict(sha256=sha(PKG/'production-reference-data-pins.json'),bytes=(PKG/'production-reference-data-pins.json').stat().st_size)
for p,h in inputs.items():assert sha(p)==h,p
for name,h in PINS.items():assert sha(V/(name+'.py'))==h
index=dict(status='CANONICAL_SIX_TWO_PHASE_ANCHORS_INDEXED_WITH_TWO_HISTORICAL_AUDITS',future_git_base_branch='fix-udm-frozen-replay-contract',future_git_base_commit='22ab474286c7b808d6f81e08ce457ddf6ba8e9cb',proposed_package_path='validation/rrtmgp37/stratified-six-anchor-replay',canonical_count=6,historical_audit_count=2,total_actual_calls=dict(WRF=8,LW=8,SW=7,strict_reference=15),total_full_LW_SW=7,total_LW_only_night=1,rows=rows,retained_failed_receipts=failures,capture_inventory='capture-hash-inventory.json',asset_pins='production-reference-data-pins.json',shared_query_limitation='Separate reference executable replays adapter inputs; both production and reference use module_ra_rrtmgp_frozen query_lw/query_sw with the same table. Frozen agreement is a shared-query transfer/mixing regression check, not an independent physical oracle.',unresolved_scientific_policies=['CF0 rain/snow occurrence handling','cloud-ice/liquid lookup clipping; frozenG/H uses a distinct size-law/table contract'],radius_definitions='Native RE_CLOUD/RE_ICE/RE_SNOW are meters. Adapter REL/REI/RES are micrometers after explicit/background-fallback mapping. Liquid requested radiusREL is clamped2.5..21.5µm; cloud-ice requested diameter2*REI is clamped10..180µm. FrozenG/H slope lookup is distinct from this cloud-ice diameter.',new_model_or_reference_calls=0,source_edits=0,publication=False,multi_seed_extension_status='Not included; captured column seeds recorded, no multi-seed coverage claim.')
write(PKG/'index.json',index);artifacts['index.json']=dict(sha256=sha(PKG/'index.json'),bytes=(PKG/'index.json').stat().st_size)
write(PKG/'manifest.json',dict(artifacts=artifacts,canonical_artifacts_sha256=hashlib.sha256(json.dumps(artifacts,sort_keys=True,separators=(',',':')).encode()).hexdigest()))
print(json.dumps(dict(status=index['status'],artifact_count=len(artifacts),retained_payload_bytes=sum(x['bytes'] for x in artifacts.values()),omitted_raw_output_payload_bytes=sum(x['bytes'] for d in capture_inventories.values() for x in d.values()),index_sha256=sha(PKG/'index.json'),manifest_sha256=sha(PKG/'manifest.json'),model_calls=0,reference_calls=0),indent=2))
