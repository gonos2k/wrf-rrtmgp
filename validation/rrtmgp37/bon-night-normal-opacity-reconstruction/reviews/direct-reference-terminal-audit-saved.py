#!/usr/bin/env python3
"""Read-only consistency audit of a frozen normal-carrier point construction."""
import hashlib, json, math, pathlib, sys
import numpy as np
from netCDF4 import Dataset

ROOT=pathlib.Path.cwd()
BASE=ROOT/'build/udm37-bon-night-normal-opacity-math-v1/execution-v1'
AUTH=BASE/'authorization.json'
EXE=BASE/'execution.json'
CON=BASE/'output/construction.json'
CMP=BASE/'output/normal-target-comparison.json'
CTX=BASE/'output/pfrac-context-crosscheck.json'
INPUT=ROOT/'build/udm37-current-bon-night-serial-audit-v2/cases/OFF/trace/lw_000001.input'
TARGET=ROOT/'build/udm37-bon-night-independent-replay-v1/run-v1/lw_000001.result'
COEFF=ROOT/'build/udm37-export-selection-serial-build-v1/source/WRF/run/rrtmgp-gas-lw-g128.nc'
INV=ROOT/'build/udm37-bon-night-independent-replay-v1/inventory.json'
EXPECTED={
 'execution.json':'04f8c221e92cbe04396582f0173d611db1f335c95ad6110ec8b9b26ded00b05c',
 'construction.json':'35e177c63e3339c82d9c612e8d320d1543f7d5f52b49607ceb0d12090468244a',
 'normal-target-comparison.json':'71d681933322a85388f8698fe4232b506d51188278ec5e0121e139386d1daa2f',
 'pfrac-context-crosscheck.json':'1fa2f3dc66ce2665bda79cf8dc0f0bc1213f938124b63b5a361c284453a99d32',
}

def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def checkpin(pin):
 p=pathlib.Path(pin['path'])
 if not p.is_absolute(): p=ROOT/p
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

# Pin the exact frozen execution inputs and all 138 authorized artifacts twice.
auth=json.loads(AUTH.read_text()); execution=json.loads(EXE.read_text())
assert auth['status']=='AUTHORIZED_DIAGNOSTIC_ONLY'
assert execution['actual_child_return_code']==0 and not execution['timed_out']
assert execution['new_WRF']==execution['new_RTE']==execution['new_REAL']==execution['new_builds']==0
assert execution['bounded_python_invocations']==1
assert len(auth['artifact_pins'])==138
for nm,h in EXPECTED.items():
 p=BASE/nm if nm=='execution.json' else (BASE/'output'/nm)
 assert sha(p)==h, f'{nm} expected pin mismatch'
for label in ('point_source','runner_source','source_review','runner_review'):
 checkpin(auth[label])
assert auth['source_review_status']=='PASS_SCOPED_LOCKED_SOURCE_REVIEW'
# The authorization pins are live-checked before and after all parsing below.
def verify_artifacts():
 for item in auth['artifact_pins']: checkpin(item)
verify_artifacts()

con=json.loads(CON.read_text()); cmp=json.loads(CMP.read_text()); ctx=json.loads(CTX.read_text())
assert con['status']=='POINT_ARRAYS_CONSTRUCTED_TARGETS_NOT_OPENED'
assert con['normal_carrier_scope']=='32 native mass values plus 13 pressure-derived extensions'
assert cmp['status']=='DIAGNOSTIC_COMPLETE_NO_NUMERICAL_VERDICT'
assert cmp['interpretation'].find('No tolerance')>=0
assert len(con['cases'])==1 and con['cases'][0]['case_id']=='normal-n2-absent'
case=con['cases'][0]
assert 'n2' not in case['available_gases'] and case['n2_override'] is None
assert len(case['available_gases'])==10
assert len(con['dry_column_source_order_terms'])==45

# Input source-order dry-column reconstruction, from raw input fields and host constants.
inp=parse_sections(INPUT,{'H2O','PLEV','NATIVE_DRY_LAYER_MASS_KG_M2','GRAVITY','MOL_WEIGHT_DRY','CP_DRY','PLAY','TLAY',
                          'CO2','O3','N2O','CH4','O2','VMR_CFC11','VMR_CFC12','VMR_CFC22','VMR_CCL4'})
native=inp['NATIVE_DRY_LAYER_MASS_KG_M2'].reshape(-1)
h2o=inp['H2O'].reshape(-1); plev=inp['PLEV'].reshape(-1)
assert native.size==32 and h2o.size==45 and plev.size==46
assert float(inp['GRAVITY'].item())==9.8100004196166992
assert float(inp['MOL_WEIGHT_DRY'].item())==0.02896600030362606
avog=6.02214076e23; mdry=float(inp['MOL_WEIGHT_DRY'].item()); mh2o=0.018016; grav=float(inp['GRAVITY'].item())
source_terms=con['dry_column_source_order_terms']; constructed_dry=case['dry_column_molecule_cm2']
expected_dry=[]; pressure_derived=[]
for k in range(45):
 p0=float(plev[k])*100.0; p1=float(plev[k+1])*100.0
 dp=abs(p0-p1); fact=1.0/(1.0+float(h2o[k])); mair=(mdry+mh2o*float(h2o[k]))*fact
 pdry=10.0*dp*avog*fact/(1000.0*mair*100.0*grav)
 pressure_derived.append(pdry)
 selected=(float(native[k])*avog/(mdry*10000.0)) if k<32 else pdry
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

# Independently parse the authenticated target output; do not use its GAS_TAU as input.
target=read_result(TARGET)
assert target['GAS_COL_DRY'].shape==(1,45,1)
assert target['GAS_TAU_RAW'].shape==(1,45,128) and target['GAS_TAU'].shape==(1,45,128)
assert np.array_equal(np.asarray(constructed_dry).reshape(1,45,1),target['GAS_COL_DRY'])
point=np.asarray(case['tau_point'],dtype=np.float64)
assert point.shape==(45,128)
assert np.array_equal(point,target['GAS_TAU_RAW'][0,:,:])
assert np.array_equal(point,target['GAS_TAU'][0,:,:])
for comp in cmp['comparisons']:
 arr=np.asarray(comp['candidate_tau'],dtype=np.float64)
 tar=np.asarray(comp['target_tau'],dtype=np.float64)
 assert comp['case_id']=='normal-n2-absent'
 assert comp['target_section'] in {'GAS_TAU_RAW','GAS_TAU'}
 assert np.array_equal(arr,point) and np.array_equal(tar,point)
 assert comp['summary']['cells']==5760 and comp['summary']['max_absolute_residual']==0.0
 assert comp['summary']['max_absolute_ordered_ulp_delta']==0
assert len(cmp['comparisons'])==2

# Table roster, all major raw corner references/products/source-order sums.
with Dataset(COEFF) as ds:
 gas_table=strings(ds['gas_names'][:])
 available=[g for g in gas_table if g in set(case['available_gases'])]
 assert available==case['available_gases'], f'table-order gas roster {available}'
 assert len(available)==10
 bands=np.asarray(ds['bnd_limits_gpt'][:],dtype=int)
 assert bands.shape==(16,2) and bands[0,0]==1 and bands[-1,1]==128
 assert all(bands[i+1,0]==bands[i,1]+1 for i in range(15))
 kmj=np.asarray(ds['kmajor'][:],dtype=np.float64)
 keyraw=np.asarray(ds['key_species'][:],dtype=int)
 vmrref=np.asarray(ds['vmr_ref'][:],dtype=np.float64)
 gas_to_idx={g:i+1 for i,g in enumerate(available)}
 profiles={g:inp[g].reshape(-1) for g in ('H2O','CO2','O3','N2O','CH4','O2')}
 for g,section in (('CFC11','VMR_CFC11'),('CFC12','VMR_CFC12'),('CFC22','VMR_CFC22'),('CCL4','VMR_CCL4')):
  profiles[g]=inp[section].reshape(-1)
 profiles={g.lower():v for g,v in profiles.items()}
 colgas={'dry':np.asarray(expected_dry,dtype=np.float64)}
 for g,values in profiles.items(): colgas[g]=np.asarray(values,dtype=np.float64)*colgas['dry']
 ctxcase=case['discrete_context']; layerstates=ctxcase['layer_flavor_state']
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
 for term in minor_terms:
  suffix=term['atmosphere_lower_upper']; assert suffix in table_row_maps
  gfor=int(term['gpoint_fortran']); k=int(term['layer_fortran'])-1
  row=next(r for r in table_row_maps[suffix]
           if r['id']==term['interval_id'] and r['lo']<=gfor<=r['hi'])
  assert row['keep'] and term['absorber']==row['gas']
  assert row['lo']<=gfor<=row['hi']
  assert 0<=k<45 and 1<=gfor<=128
  goff=gfor-row['lo']
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
assert len(minor_terms)==14165
assert np.array_equal(running_major,np.asarray(case['tau_point'],dtype=np.float64))
assert np.array_equal(running_major,target['GAS_TAU_RAW'][0,:,:])
# Cross-check pfrac discrete identities are persisted as positive exact checks; fractions are diagnostic.
assert all(v.get('exact_equal') is True for v in ctx['exact_discrete_checks'].values())
# Second live-pin pass after all reads and calculations.
verify_artifacts()
report={
 'schema':'UDM37_BON_NORMAL_POINT_SAVED_OUTPUT_AUDIT_V1',
 'status':'PASS_SCOPED_SAVED_ARTIFACTS_AND_SOURCE_ORDER_TERM_AUDIT_NO_NUMERICAL_VERDICT',
 'execution':{'receipt_sha256':sha(EXE),'child_rc':execution['actual_child_return_code'],'bounded_python_invocations':1,'new_WRF':0,'new_RTE':0,'new_REAL':0,'new_builds':0},
 'pins':{'authorization_sha256':sha(AUTH),'authorization_artifact_pin_rows':138,'live_rehash_passes':2,'source_review_status':auth['source_review_status'],'source_review_sha256':auth['source_review']['sha256'],'plan_sha256':auth['plan_sha256'],'point_source':auth['point_source'],'runner_source':auth['runner_source'],'pinned_execution_artifacts_verified':True,'audit_script_sha256':sha(__file__)},
 'carrier':{'normal_v10_input_sha256':sha(INPUT),'native_mass_layers':32,'total_layers':45,'extension_layers':13,'n2_membership':'absent; source roster is ten gases'},
 'dry_column':{'source_order_rows_recomputed':45,'native_prefix_rows':32,'pressure_h2o_extension_rows':13,'saved_construction_rows_exact':45,'saved_target_GAS_COL_DRY_exact':45,'max_abs_residual':0.0},
 'target_reparse':{'path':'build/udm37-bon-night-independent-replay-v1/run-v1/lw_000001.result','sha256':sha(TARGET),'GAS_TAU_RAW_shape':[1,45,128],'GAS_TAU_shape':[1,45,128],'GAS_COL_DRY_shape':[1,45,1],'raw_tau_exact_cells':5760,'prepared_tau_exact_cells':5760,'construction_to_target_exact':True},
 'coefficient_table':{'path':'build/udm37-export-selection-serial-build-v1/source/WRF/run/rrtmgp-gas-lw-g128.nc','sha256':sha(COEFF),'major_corner_checks':major_corner_checks,'minor_corner_checks':minor_corner_checks},
 'major_terms':{'term_rows':len(major),'coefficient_table_corner_lookups':major_corner_checks,'weighted_products_recomputed':major_product_checks,'left_associated_sums_checked':major_sum_checks,'two_plane_and_accumulation_rows_checked':len(major),'band_partition_and_gas_key_membership_checked':True},
 'minor_terms':{'term_rows':len(minor_terms),'raw_interval_roster_rows_checked':minor_index_checks,'coefficient_table_corner_lookups':minor_corner_checks,'weighted_products_recomputed':minor_product_checks,'left_associated_sums_checked':minor_sum_checks,'gas_column_density_scaling_and_tau_products_checked':minor_scale_checks,'raw_vs_packed_contributor_indices_checked':len(minor_terms)*4,'final_source_order_accumulation_equals_target':True},
 'context':{'pfrac_context_crosscheck_sha256':sha(CTX),'all_persisted_exact_discrete_checks_true':True,'fraction_differences_are_diagnostic_only':True},
 'provenance_limits':['This audit authenticates saved construction arithmetic/indices against pinned coefficient tables and the direct-replay result; it is not an independent derivation of the RRTMGP coefficients or physical truth.','The normal replay’s build-receipt driver provenance mismatch is separately disclosed in build/udm37-bon-night-normal-carrier-inventory-v3/source-compatibility.json; the sidecar branch was not entered.','The direct replay result is the audited numerical target. The production WRF capture output exists but was not parsed or compared in this audit.','The construction reports exact agreement without applying a numerical tolerance or PASS threshold; this review does not promote same-table agreement to a numerical or physical accuracy verdict.','No opacity reconstruction code, solver, RTE, compiler, or model was invoked by this independent audit.']
}
out=ROOT/'build/udm37-bon-night-normal-opacity-terminal-review-v1/terminal-review-v1.json'
out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps(report,indent=2))
print('receipt_sha256',sha(out))
