#!/usr/bin/env python3
"""Future read-only audit scaffold for the locked positive-N2 point case.

This file has not been run. Its source/table-ledger checks are adapted from the
reviewed N2-absent audit; the future authorization/output pins must be supplied
and reviewed before it is used.
"""
import hashlib, json, math, pathlib, sys, re, gzip
import numpy as np
from netCDF4 import Dataset

ROOT=pathlib.Path.cwd()
BASE=ROOT/'build/udm37-bon-night-normal-positive-n2-math-v1'
AUTH=BASE/'root-authorization.json'
EXE=BASE/'execution-v1/execution.json'
PLAN=ROOT/'build/udm37-bon-night-normal-positive-n2-plan-v3/plan.json'
CON=BASE/'run-v1/construction.json.gz'
CON_RECEIPT=BASE/'run-v1/construction-receipt.json'
CMP=BASE/'run-v1/comparison.json'
STATE=BASE/'run-v1/execution-state.json'
INPUT=ROOT/'build/udm37-legacy-lw-source-export-bon-audit-v2/cases/SOURCE_OFF/trace/lw_000001.input'
TARGET=ROOT/'build/udm37-legacy-lw-source-export-bon-audit-v2/cases/SOURCE_OFF/trace/lw_000001.result'
TABLE_ROOT=ROOT/'build/udm37-legacy-lw-source-export-serial-build-v1/source/WRF'
COEFF=TABLE_ROOT/'run/rrtmgp-gas-lw-g128.nc'
DRIVER=TABLE_ROOT/'phys/module_ra_rrtmgp.F'
MANIFEST=ROOT/'build/udm37-legacy-lw-source-export-serial-build-v1/source-manifest.json'
CONST=TABLE_ROOT/'external/rte_rrtmgp/gas-optics/mo_gas_optics_constants.F90'
OUT=ROOT/'build/udm37-normal-positive-n2-opacity-terminal-audit-v2/terminal-audit.json'
ADAPT=ROOT/'build/udm37-normal-positive-n2-opacity-draft-v1/adaptation.json'

def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def checkpin(pin):
 p=pathlib.Path(pin['path'])
 if not p.is_absolute(): p=ROOT/p
 if pin.get('is_symlink'):
  assert p.is_symlink(), f'expected symlink: {p}'
  target=p.resolve(strict=True)
  expected=pathlib.Path(pin['resolved_path'])
  if not expected.is_absolute(): expected=ROOT/expected
  assert target==expected.resolve(strict=True), f'symlink target mismatch: {p}'
  b=target.read_bytes()
  assert len(b)==pin['target_size_bytes'] and hashlib.sha256(b).hexdigest()==pin['target_sha256'], f'symlink target pin mismatch: {p}'
  return
 b=p.read_bytes()
 assert len(b)==pin['size_bytes'] and hashlib.sha256(b).hexdigest()==pin['sha256'], f'pin mismatch: {p}'

def exact(a,b,label):
 if float(a)!=float(b): raise AssertionError(f'{label}: {a!r} != {b!r}')

def parse_sections(path, requested):
 lines=pathlib.Path(path).read_text(encoding='ascii').splitlines()
 found={}
 for i,line in enumerate(lines):
  f=line.split()
  if not f or f[0] not in requested: continue
  try: shape=tuple(int(x) for x in f[1:])
  except ValueError: continue
  if not shape or any(x<1 for x in shape): continue
  n=math.prod(shape); vals=[]; j=i+1
  while len(vals)<n and j<len(lines):
   for token in lines[j].split(): vals.append(float(token.replace('D','E').replace('d','e')))
   j+=1
  assert len(vals)==n, f'{f[0]} count'
  assert f[0] not in found, f'duplicate {f[0]}'
  found[f[0]]=(shape,np.asarray(vals,dtype=np.float64).reshape(shape,order='F'))
 missing=set(requested)-set(found)
 assert not missing, f'missing input sections {missing}'
 return {k:v[1] for k,v in found.items()}

def read_result(path):
 lines=pathlib.Path(path).read_text(encoding='ascii').splitlines()
 assert lines[0].strip()=='RRTMGP_RESULT_V1'
 phase,nc,nl=lines[1].split(); assert (phase,int(nc),int(nl))==('LW',1,45)
 out={}; i=2
 while i<len(lines):
  f=lines[i].split(); i+=1
  if not f: continue
  assert len(f)==4, f'bad result header {f}'
  name=f[0]; shape=tuple(int(x) for x in f[1:]); n=math.prod(shape); vals=[]
  while len(vals)<n:
   assert i<len(lines),f'truncated {name}'
   vals.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split()); i+=1
  assert len(vals)==n and name not in out, f'bad values or duplicate {name}'
  arr=np.asarray(vals,dtype=np.float64).reshape(shape,order='F')
  assert np.isfinite(arr).all()
  out[name]=arr
 return out

def strings(a):
 out=[]
 for row in np.asarray(a):
  parts=[]
  for x in np.ravel(row):
   if isinstance(x,(bytes,np.bytes_)): parts.append(bytes(x).decode('ascii'))
   else: parts.append(str(x))
  out.append(''.join(parts).strip())
 return out

def f32same(a,b):
 return float(a)==float(b)

auth=json.loads(AUTH.read_text()); execution=json.loads(EXE.read_text())
plan=json.loads(PLAN.read_text()); receipt=json.loads(CON_RECEIPT.read_text())
comparison=json.loads(CMP.read_text()); state=json.loads(STATE.read_text())
return_receipt_path=ROOT/execution['return_code_receipt']['path']
return_receipt=json.loads(return_receipt_path.read_text())
assert auth['authorized'] is True and auth['schema']=='udm37-bon-night-normal-positive-n2-execution-authorization-v3'
assert execution['actual_return_code']==0 and execution['new_model_RTE_compile_invocations']==0
assert execution['new_point_invocations_authorized']==1 and execution['numerical_output_read_by_parent'] is False
assert execution['authorization']['sha256']==sha(AUTH)
assert return_receipt['actual_return_code']==0 and return_receipt['numerical_output_read_by_parent'] is False
assert auth['plan_sha256']==sha(PLAN)==plan['sha256'] if 'sha256' in plan else auth['plan_sha256']==sha(PLAN)
assert receipt['plan_sha256']==auth['plan_sha256'] and receipt['point_invocations']==1
assert receipt['status']=='CONSTRUCTION_DURABLE_TARGET_NOT_YET_READ'
assert state['actual_return_code']==0 and state['point_invocations']==1 and state['target_reads']==1
assert comparison['status']=='DESCRIPTIVE_COMPARISON_COMPLETE_NO_ACCEPTANCE_THRESHOLD'
assert comparison['target_result_sha256']==sha(TARGET)
assert auth['artifact_pin_count']==108 and state['verified_pin_count']==108
assert state['construction_receipt_sha256']==sha(CON_RECEIPT)
assert state['comparison_sha256']==sha(CMP)
assert state['authorization_sha256']==sha(AUTH)
assert len(plan['pinned_artifacts'])==31
for item in plan['pinned_artifacts'].values(): checkpin(item)
adaptation=json.loads(ADAPT.read_text())
assert adaptation['status']=='LOCKED_DRAFT_NO_EXECUTION_NO_TARGET_READ'
assert adaptation['pins']['input_packet']['sha256']==sha(INPUT)
assert INPUT.read_text(encoding='ascii').splitlines()[0].strip()=='RRTMGP_REPLAY_V13'
manifest=json.loads(MANIFEST.read_text())
assert manifest['commit']=='085618aa60b9dcf473c2b26eb17b2123d5c7762c'
driver_entry=next(x for x in manifest['tracked_files'] if x['path']=='WRF/phys/module_ra_rrtmgp.F')
assert driver_entry['sha256']==sha(DRIVER)
# The plan and adaptation pins are live-checked before/after parsing.
def verify_artifacts():
 for item in plan['pinned_artifacts'].values(): checkpin(item)
 for item in adaptation['pins'].values(): checkpin(item)
verify_artifacts()

compressed=CON.read_bytes()
assert hashlib.sha256(compressed).hexdigest()==receipt['artifact']['sha256']
assert len(compressed)==receipt['artifact']['size_bytes']
construction_bytes=gzip.decompress(compressed)
assert hashlib.sha256(construction_bytes).hexdigest()==receipt['artifact']['uncompressed_sha256']
assert len(construction_bytes)==receipt['artifact']['uncompressed_size_bytes']
con=json.loads(construction_bytes)
assert con['status']=='POINT_ARRAYS_CONSTRUCTED_TARGETS_NOT_OPENED'
assert con['normal_carrier_scope']=='32 native mass values plus 13 pressure-derived extensions'
assert con['source_pins']['input']['sha256']==sha(INPUT)
assert con['source_pins']['coefficients']['sha256']==sha(COEFF)
assert con['source_pins']['constants']['sha256']==sha(CONST)
assert con['source_pins']['frontend']['sha256']==sha(adaptation['pins']['gas_frontend']['path'])
assert con['source_pins']['kernel']['sha256']==sha(adaptation['pins']['gas_kernel']['path'])
assert con['source_pins']['loader']['sha256']==sha(adaptation['pins']['coefficient_loader']['path'])
assert len(con['cases'])==1 and con['cases'][0]['case_id']=='normal-positive-n2-captured-input'
case=con['cases'][0]
assert case['n2_source']=='captured VMR_N2 input section; no scalar override or averaging'
assert len(case['available_gases'])==11 and 'n2' in case['available_gases']
assert len(con['dry_column_source_order_terms'])==45

# Input source-order dry-column reconstruction, from raw input fields and host constants.
inp=parse_sections(INPUT,{'H2O','PLEV','NATIVE_DRY_LAYER_MASS_KG_M2','GRAVITY','MOL_WEIGHT_DRY','CP_DRY','PLAY','TLAY',
                          'CO2','O3','N2O','CH4','O2','VMR_N2','VMR_CFC11','VMR_CFC12','VMR_CFC22','VMR_CCL4'})
native=inp['NATIVE_DRY_LAYER_MASS_KG_M2'].reshape(-1)
h2o=inp['H2O'].reshape(-1); plev=inp['PLEV'].reshape(-1)
assert native.size==32 and h2o.size==45 and plev.size==46
assert inp['VMR_N2'].shape==(1,45)
assert np.isfinite(inp['VMR_N2']).all() and np.all(inp['VMR_N2']>=0.0)
const_text=CONST.read_text(encoding='ascii')
def source_literal(name):
 m=re.search(rf'\b{name}\s*=\s*([0-9.]+(?:[Ee][+-]?\d+)?)_wp',const_text,re.I)
 assert m, f'missing pinned constant {name}'
 return float(m.group(1))
avog=source_literal('avogad'); mh2o=source_literal('m_h2o')
mdry=float(inp['MOL_WEIGHT_DRY'].item()); grav=float(inp['GRAVITY'].item())
source_terms=con['dry_column_source_order_terms']; constructed_dry=case['dry_column_molecule_cm2']
expected_dry=[]; pressure_derived=[]
for k in range(45):
 p0=float(plev[k])*100.0; p1=float(plev[k+1])*100.0
 dp=abs(p0-p1); fact=1.0/(1.0+float(h2o[k])); mair=(mdry+mh2o*float(h2o[k]))*fact
 pdry=10.0*dp*avog*fact/(1000.0*mair*100.0*grav)
 pressure_derived.append(pdry)
 selected=(float(native[k])*(avog/(mdry*10000.0))) if k<32 else pdry
 expected_dry.append(selected)
 row=source_terms[k]
 assert row['layer_fortran']==k+1
 assert row['source']==('native_mass_prefix' if k<32 else 'pressure_extension')
 exact(row['delta_pressure_pa'],dp,f'dry Δp k={k+1}')
 exact(row['vmr_h2o'],h2o[k],f'dry H2O k={k+1}')
 exact(row['dry_fraction'],fact,f'dry fact k={k+1}')
 exact(row['moist_molar_mass_kg_mol'],mair,f'dry m_air k={k+1}')
 exact(row['pressure_derived_molecule_cm2'],pdry,f'pressure-derived dry k={k+1}')
 if k<32: exact(row['native_mass_kg_m2'],native[k],f'native mass k={k+1}')
 exact(row['selected_molecule_cm2'],selected,f'selected dry k={k+1}')
 exact(constructed_dry[k],selected,f'construction dry k={k+1}')

# Independently parse the actual saved WRF output; use its opacity only as a
# comparison target, never as an input to the coefficient reconstruction.
target=read_result(TARGET)
assert target['GAS_COL_DRY'].shape==(1,45,1)
assert target['GAS_TAU_RAW'].shape==(1,45,128) and target['GAS_TAU'].shape==(1,45,128)
point=np.asarray(case['tau_point'],dtype=np.float64)
assert point.shape==(45,128)
assert np.isfinite(point).all()
target_dry=target['GAS_COL_DRY'][0,:,0]
dry_signed=np.asarray(constructed_dry,dtype=np.float64)-target_dry
dry_summary={}
for label,sl in [('all45',slice(0,45)),('native32',slice(0,32)),('extension13',slice(32,45))]:
 d=dry_signed[sl]; ref=target_dry[sl]
 dry_summary[label]={'count':int(d.size),'exact':int(np.count_nonzero(d==0.0)),
                     'max_abs_residual':float(np.max(np.abs(d))),
                     'rms_residual':float(np.sqrt(np.mean(d*d))),
                     'max_relative_to_saved':float(np.max(np.abs(d/ref))),
                     'max_relative_to_construction':float(np.max(np.abs(d/np.asarray(constructed_dry,dtype=np.float64)[sl])))}
tau_summary={}
for name in ('GAS_TAU_RAW','GAS_TAU'):
 diff=point-target[name][0]
 tau_summary[name]={}
 for label,sl in [('native32',slice(0,32)),('extension13',slice(32,45)),('all45',slice(0,45))]:
  d=diff[sl]; ref=target[name][0,sl]; nz=ref!=0
  ai=point[sl].view(np.uint64); bi=ref.view(np.uint64)
  ulps=np.abs(ai.astype(object)-bi.astype(object))
  tau_summary[name][label]={'cells':int(d.size),'exact_cells':int(np.count_nonzero(d==0.0)),
     'max_abs_residual':float(np.max(np.abs(d))),
     'rms_residual':float(np.sqrt(np.mean(d*d))),
     'max_relative_nonzero_saved':float(np.max(np.abs(d[nz]/ref[nz]))) if np.any(nz) else None,
     'max_relative_nonzero_construction':float(np.max(np.abs(d[point[sl]!=0.0]/point[sl][point[sl]!=0.0]))) if np.any(point[sl]!=0.0) else None,
     'max_ordered_ulp':int(max(ulps.flat))}
# Reconcile the independently recomputed residual summaries with the saved
# descriptive comparison receipt; this is consistency, not a tolerance gate.
for name, actual in [('GAS_COL_DRY',dry_summary),('GAS_TAU_RAW',tau_summary['GAS_TAU_RAW']),
                     ('GAS_TAU',tau_summary['GAS_TAU'])]:
 for region, summary in actual.items():
  comparison_region='pressure_extensions13' if region=='extension13' else region
  prior=comparison['comparisons'][name][comparison_region]
  assert prior['elements']==summary.get('cells',summary.get('count'))
  assert prior['absolute']['max']==summary['max_abs_residual']
  assert prior['absolute']['rms']==summary['rms_residual']
  assert prior['relative_to_construction']['max_abs_nonzero_denominator']==summary['max_relative_to_construction'] if name=='GAS_COL_DRY' else prior['relative_to_construction']['max_abs_nonzero_denominator']==summary['max_relative_nonzero_construction']

# Table roster, all major raw corner references/products/source-order sums.
with Dataset(COEFF) as ds:
 gas_table=strings(ds['gas_names'][:])
 available=[g for g in gas_table if g in set(case['available_gases'])]
 assert available==case['available_gases'], f'table-order gas roster {available}'
 assert len(available)==11 and 'n2' in available
 bands=np.asarray(ds['bnd_limits_gpt'][:],dtype=int)
 assert bands.shape==(16,2) and bands[0,0]==1 and bands[-1,1]==128
 assert all(bands[i+1,0]==bands[i,1]+1 for i in range(15))
 kmj=np.asarray(ds['kmajor'][:],dtype=np.float64)
 keyraw=np.asarray(ds['key_species'][:],dtype=int)
 vmrref=np.asarray(ds['vmr_ref'][:],dtype=np.float64)
 gas_to_idx={g:i+1 for i,g in enumerate(available)}
 profiles={g:inp[g].reshape(-1) for g in ('H2O','CO2','O3','N2O','CH4','O2')}
 profiles['N2']=inp['VMR_N2'].reshape(-1)
 for g,section in (('CFC11','VMR_CFC11'),('CFC12','VMR_CFC12'),('CFC22','VMR_CFC22'),('CCL4','VMR_CCL4')):
  profiles[g]=inp[section].reshape(-1)
 profiles={g.lower():v for g,v in profiles.items()}
 colgas={'dry':np.asarray(expected_dry,dtype=np.float64)}
 for g,values in profiles.items(): colgas[g]=np.asarray(values,dtype=np.float64)*colgas['dry']
 assert len(case['n2_vmr_values'])==45
 assert np.array_equal(np.asarray(case['n2_vmr_values']),profiles['n2'])
 gas_records={x['gas']:x for x in case['gas_column_records']}
 assert list(gas_records)==available
 gas_input_sections={'h2o':'H2O','co2':'CO2','o3':'O3','n2o':'N2O','ch4':'CH4','o2':'O2',
                     'n2':'VMR_N2','cfc11':'VMR_CFC11','cfc12':'VMR_CFC12',
                     'cfc22':'VMR_CFC22','ccl4':'VMR_CCL4'}
 for gas in available:
  record=gas_records[gas]
  assert record['input_section']==gas_input_sections[gas]
  assert np.array_equal(np.asarray(record['vmr_values']),profiles[gas])
  assert np.array_equal(np.asarray(record['column_molecule_cm2']),colgas[gas])
 ctxcase=case['discrete_context']; layerstates=ctxcase['layer_flavor_state']
 trop=ctxcase['tropopause_lower']
 major=case['major_terms_source_order']; assert len(major)==45*128
 running_major=np.zeros((45,128),dtype=np.float64); major_seen=set()
 major_corner_checks=major_product_checks=major_sum_checks=0
 for term in major:
  k=term['layer_fortran']-1; g=term['gpoint_fortran']-1
  assert 0<=k<45 and 0<=g<128 and (k,g) not in major_seen
  major_seen.add((k,g))
  band=next(i for i,(lo,hi) in enumerate(bands) if lo<=g+1<=hi)
  atm=0 if ctxcase['tropopause_lower'][k] else 1
  rawpair=tuple(int(x) for x in keyraw[band,atm,:])
  # Source maps (0,0) to reduced fallback (2,2).
  names=[]
  for raw in rawpair: names.append('' if raw==0 else gas_table[raw-1])
  reduced=tuple(0 if not name else gas_to_idx[name] for name in names)
  if reduced==(0,0): reduced=(2,2)
  assert list(reduced)==term['key_pair_reduced_ids']
  assert term['band_fortran']==band+1
  flavors=layerstates[k]['flavors']
  flavor=next(x for x in flavors if tuple(x['reduced_pair'])==reduced)
  assert term['flavor_fortran']==flavor['flavor_fortran']
  plane_values=[]
  for pi,plane in enumerate(term['planes']):
   idxs=plane['coefficient_indices_fortran_raw_netCDF_T_P_eta_gpt']
   assert len(idxs)==4
   coeffs=[]
   for ti,pr,eta,gpt in idxs:
    assert 1<=ti<=kmj.shape[0] and 1<=pr<=kmj.shape[1] and 1<=eta<=kmj.shape[2] and gpt==g+1
    coeff=float(kmj[ti-1,pr-1,eta-1,gpt-1]); coeffs.append(coeff); major_corner_checks+=1
   for actual,recorded in zip(coeffs,plane['corner_coefficients_same_order']): exact(recorded,actual,'major raw coefficient')
   weights=plane['weights_eta_low_pressure_low__eta_high_pressure_low__eta_low_pressure_high__eta_high_pressure_high']
   assert len(weights)==4
   products=[float(w)*float(q) for w,q in zip(weights,coeffs)]
   for actual,recorded in zip(products,plane['weighted_corner_terms_same_order']): exact(recorded,actual,'major weighted corner')
   s=((products[0]+products[1])+products[2])+products[3]
   exact(plane['weighted_corner_sum_left_associated'],s,'major corner sum')
   scaled=float(plane['col_mix'])*s
   exact(plane['scaled_plane_value'],scaled,'major scaled plane')
   plane_values.append(scaled); major_product_checks+=4; major_sum_checks+=2
  total=plane_values[0]+plane_values[1]
  exact(term['two_scaled_plane_sum'],total,'two-plane major sum')
  running_major[k,g]+=total
  exact(term['tau_after_major_add'],running_major[k,g],'major accumulation')
 assert len(major_seen)==5760

 # Verify source-table interval mapping/repacking and every minor raw coeff/corner product.
 minor_rows=ctxcase['minor_intervals']; minor_terms=case['minor_terms_source_order']
 idgas=dict(zip(strings(ds['identifier_minor'][:]),strings(ds['gas_minor'][:])))
 minor_index_checks=minor_corner_checks=minor_product_checks=minor_sum_checks=minor_scale_checks=0
 table_row_maps={}
 for suffix,atm in [('lower',0),('upper',1)]:
  ids=strings(ds[f'minor_gases_{suffix}'][:]); limits=np.asarray(ds[f'minor_limits_gpt_{suffix}'][:],dtype=int)
  starts=np.asarray(ds[f'kminor_start_{suffix}'][:],dtype=int)
  density=np.asarray(ds[f'minor_scales_with_density_{suffix}'][:],dtype=int)
  scale_gas=strings(ds[f'scaling_gas_{suffix}'][:]); complement=np.asarray(ds[f'scale_by_complement_{suffix}'][:],dtype=int)
  saved=minor_rows[suffix]; assert len(saved)==len(ids)
  removed=0; m=[]
  for i,ident in enumerate(ids):
   gas=idgas[ident]; lo,hi=map(int,limits[i]); width=hi-lo+1; keep=gas in available
   packed=int(starts[i])-removed if keep else None
   r=saved[i]
   assert r['id']==ident and r['gas']==gas and r['lo']==lo and r['hi']==hi
   assert r['width']==width and r['raw_start']==int(starts[i]) and r['packed_start']==packed
   assert r['keep']==keep and r['density']==bool(density[i])
   assert r['scale_gas']==scale_gas[i] and r['complement']==bool(complement[i])
   m.append(r)
   if not keep: removed+=width
   minor_index_checks+=1
  table_row_maps[suffix]=m
 # Direct input-backed columns used by scaling terms.
 h2o_col=colgas['h2o']; dry_col=colgas['dry']
 minor_seen=set()
 for term in minor_terms:
  suffix=term['atmosphere_lower_upper']; assert suffix in table_row_maps
  gfor=int(term['gpoint_fortran']); k=int(term['layer_fortran'])-1
  row=next(r for r in table_row_maps[suffix]
           if r['id']==term['interval_id'] and r['lo']<=gfor<=r['hi'])
  assert row['keep'] and term['absorber']==row['gas']
  assert row['lo']<=gfor<=row['hi']
  assert 0<=k<45 and 1<=gfor<=128
  goff=gfor-row['lo']
  row_key=(suffix,row['id'],k,gfor)
  assert row_key not in minor_seen, f'duplicate minor ledger term {row_key}'
  minor_seen.add(row_key)
  rawcon=row['raw_start']+goff; packedcon=row['packed_start']+goff
  assert term['raw_contributor_index_fortran']==rawcon
  assert term['packed_contributor_index_fortran']==packedcon
  band=next(i for i,(lo,hi) in enumerate(bands) if lo<=gfor<=hi)
  # RRTMGP minor absorption contributes only where table band uses this atmosphere class.
  atm=0 if suffix=='lower' else 1
  pair=tuple(ctxcase['key_species_reduced_ids'][band][atm])
  layer_flavors=layerstates[k]['flavors']; flav=next(x for x in layer_flavors if tuple(x['reduced_pair'])==pair)
  ps0,ps1=flav['reference_planes']
  expected_weights=[ps0['fminor'][0],ps0['fminor'][1],ps1['fminor'][0],ps1['fminor'][1]]
  indices=term['coefficient_indices_fortran_raw_table_temp_eta_contributor']
  packed_indices=term['coefficient_indices_fortran_packed_temp_eta_contributor']
  assert len(indices)==len(packed_indices)==4
  km=np.asarray(ds[f'kminor_{suffix}'][:],dtype=np.float64)
  coeffs=[]
  for q,(ti,eta,rawc) in enumerate(indices):
   ti2,eta2,pc=packed_indices[q]
   assert rawc==rawcon and pc==packedcon
   jt_fortran=int(ctxcase['jtemp_fortran'][k])
   assert ti==([jt_fortran]*2+[jt_fortran+1]*2)[q]
   expected_eta=[ps0['jeta'],ps0['jeta']+1,ps1['jeta'],ps1['jeta']+1][q]
   assert eta==expected_eta and eta2==eta
   assert 1<=ti<=km.shape[0] and 1<=eta<=km.shape[1] and 1<=rawc<=km.shape[2]
   coeffs.append(float(km[ti-1,eta-1,rawc-1])); minor_corner_checks+=1
  expected_terms=[w*q for w,q in zip(expected_weights,coeffs)]
  for actual,recorded in zip(expected_terms,term['minor_corner_terms_source_order']): exact(recorded,actual,'minor weighted corner')
  interp=((expected_terms[0]+expected_terms[1])+expected_terms[2])+expected_terms[3]
  exact(term['interpolated_minor_coefficient_left_associated'],interp,'minor corner sum')
  absorber=term['absorber']; base=float(colgas[absorber][k])
  exact(term['scaling_before_density'],base,'minor gas column '+term['absorber']+' layer '+str(k+1))
  scale=base
  if row['density']:
   df=0.01*(float(inp['PLAY'].reshape(-1)[k])*100.0)/float(inp['TLAY'].reshape(-1)[k])
   exact(term['density_factor'],df,'minor density factor'); scale=scale*df
   sg=row['scale_gas']; sgfactor=None
   if sg in gas_to_idx:
    vmrfact=1.0/dry_col[k]
    dryfact=1.0+h2o_col[k]*vmrfact
    dryfact=1.0/dryfact
    sgfactor=float(colgas[sg][k])*vmrfact*dryfact
   if sgfactor is not None:
    exact(term['scaling_gas_factor'],sgfactor,'minor scaling-gas factor')
    scale=scale*((1.0-sgfactor) if row['complement'] else sgfactor)
  else:
   assert term['density_factor'] is None and term['scaling_gas_factor'] is None
  exact(term['scaling_final'],scale,'minor final scale')
  added=scale*interp
  exact(term['scaled_minor_tau'],added,'minor tau product')
  running_major[k,gfor-1]+=added
  exact(term['tau_after_minor_add'],running_major[k,gfor-1],'minor accumulation')
  minor_product_checks+=4; minor_sum_checks+=1; minor_scale_checks+=1
expected_minor_seen=set()
for suffix,rows in table_row_maps.items():
 atm=0 if suffix=='lower' else 1
 eligible=[k for k in range(45) if (0 if trop[k] else 1)==atm]
 for row in rows:
  if row['keep']:
   for k in eligible:
    for gfor in range(row['lo'],row['hi']+1): expected_minor_seen.add((suffix,row['id'],k,gfor))
assert minor_seen==expected_minor_seen, 'minor ledger completeness/uniqueness mismatch'
assert np.array_equal(running_major,np.asarray(case['tau_point'],dtype=np.float64))
# No residual threshold is applied to captured target arrays. They are parsed
# only after the independent construction ledger has been validated.
# Second live-pin pass after all reads and calculations.
verify_artifacts()
report={
 'schema':'UDM37_NORMAL_POSITIVE_N2_POINT_TERMINAL_AUDIT_V1',
 'status':'SOURCE_ORDER_LEDGER_VALIDATED_TARGET_RESIDUALS_DESCRIPTIVE_ONLY',
 'execution':{'receipt_sha256':sha(EXE),'child_rc':execution['actual_return_code'],'new_WRF':0,'new_RTE':0,'new_REAL':0,'new_builds':0,'audit_invoked_point_function':False,
              'point_invocations':execution['new_point_invocations_authorized'],'RTE_compile_invocations':execution['new_model_RTE_compile_invocations']},
 'pins':{'authorization_sha256':sha(AUTH),'authorization_artifact_pin_rows':auth['artifact_pin_count'],'direct_plan_pin_rows_rehashed':len(plan['pinned_artifacts']),'recursive_execution_pin_rows_verified_by_runner':state['verified_pin_count'],'live_rehash_passes':2,'adaptation_sha256':sha(ADAPT),'point_source':adaptation['pins']['candidate_script'],'input_sha256':sha(INPUT),'table_sha256':sha(COEFF),'source_manifest_sha256':sha(MANIFEST),'campaign_driver_sha256':sha(DRIVER),'campaign_source_manifest_entry_verified':True,'pinned_execution_artifacts_verified':True,'audit_script_sha256':sha(__file__)},
 'carrier':{'input_sha256':sha(INPUT),'packet':'LW V13','native_mass_layers':32,'total_layers':45,'extension_layers':13,'gas_membership_count':11,'n2_membership':'present from captured VMR_N2 input section; no synthetic override'},
 'gas_input_columns':{'input_gases':available,'gas_records_checked':len(gas_records),'each_input_vmr_vector_exact':True,'each_derived_molecule_column_vector_exact':True,'positive_N2_vector_exact_to_input':True},
 'dry_column':{'source_order_rows_recomputed':45,'native_prefix_rows':32,'pressure_h2o_extension_rows':13,'source_native_grouping':'mass*(avogad/(Mdry*10000))','construction_rows_source_order_exact':45,'target_comparison':dry_summary},
 'target_reparse':{'path':str(TARGET.relative_to(ROOT)),'sha256':sha(TARGET),'GAS_TAU_RAW_shape':[1,45,128],'GAS_TAU_shape':[1,45,128],'GAS_COL_DRY_shape':[1,45,1],'tau_comparison':tau_summary},
 'coefficient_table':{'path':str(COEFF.relative_to(ROOT)),'sha256':sha(COEFF),'major_corner_checks':major_corner_checks,'minor_corner_checks':minor_corner_checks},
 'major_terms':{'term_rows':len(major),'coefficient_table_corner_lookups':major_corner_checks,'weighted_products_recomputed':major_product_checks,'left_associated_sums_checked':major_sum_checks,'two_plane_and_accumulation_rows_checked':len(major),'band_partition_and_gas_key_membership_checked':True},
 'minor_terms':{'term_rows':len(minor_terms),'complete_unique_source_roster_match':True,'raw_interval_roster_rows_checked':minor_index_checks,'coefficient_table_corner_lookups':minor_corner_checks,'weighted_products_recomputed':minor_product_checks,'left_associated_sums_checked':minor_sum_checks,'gas_column_density_scaling_and_tau_products_checked':minor_scale_checks,'raw_vs_packed_contributor_indices_checked':len(minor_terms)*4,'final_source_order_accumulation_equals_construction':True},
 'provenance_limits':['This audit checks source-order mechanics against the pinned input/table and independently validates the saved WRF arrays; it is not a physical-accuracy verdict or independent verification of coefficient truth.','The captured VMR_N2 value is recorded as an input field only; this exercise does not validate its units or justify a global N2 policy.','The parent normal-carrier source-compatibility note remains applicable: build-receipt source-generation mismatch is disclosed in build/udm37-bon-night-normal-carrier-inventory-v3/source-compatibility.json.','No tolerance, residual gate, or causal attribution is applied to tau differences; native32 and extension13 are reported separately.','No point reconstruction function, solver, RTE, compiler, or model is invoked by this terminal audit.']
}
out=OUT
with out.open('x',encoding='utf-8') as f:
 f.write(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps(report,indent=2))
print('receipt_sha256',sha(out))
