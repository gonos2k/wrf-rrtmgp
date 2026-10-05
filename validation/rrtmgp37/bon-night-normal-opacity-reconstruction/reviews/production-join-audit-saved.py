#!/usr/bin/env python3
"""Read-only audit of the saved native-mass source expression and WRF join."""
import hashlib, json, math
from pathlib import Path
import numpy as np

ROOT = Path.cwd()
OUT = ROOT / 'build/udm37-bon-night-normal-production-join-review-v1'
OUT.mkdir(parents=True, exist_ok=True)
PLAN = ROOT / 'build/udm37-bon-night-normal-production-join-v1/plan.json'
JOIN = ROOT / 'build/udm37-bon-night-normal-production-join-v1/result.json'
SOURCE = ROOT / 'build/udm37-export-selection-serial-build-v1/source/WRF/phys/module_ra_rrtmgp.F'
MANIFEST = ROOT / 'build/udm37-export-selection-serial-build-v1/source-manifest.json'
INPUT = ROOT / 'build/udm37-current-bon-night-serial-audit-v2/cases/OFF/trace/lw_000001.input'
PRODUCTION = ROOT / 'build/udm37-current-bon-night-serial-audit-v2/cases/OFF/trace/lw_000001.result'
CONSTRUCTION = ROOT / 'build/udm37-bon-night-normal-opacity-math-v1/execution-v1/output/construction.json'
AUTH = ROOT / 'build/udm37-bon-night-normal-opacity-math-v1/execution-v1/authorization.json'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):
    b=Path(p).read_bytes()
    return {'path':str(Path(p).relative_to(ROOT)), 'sha256':hashlib.sha256(b).hexdigest(), 'size_bytes':len(b)}

pins=[pin(p) for p in (PLAN,JOIN,SOURCE,MANIFEST,INPUT,PRODUCTION,CONSTRUCTION,AUTH)]
expected_join='81b64b14eb6aa648e33b6f9e7e17262c1e8422f0a2aebdec7da34060d22d24f5'
plan=json.loads(PLAN.read_text()); saved=json.loads(JOIN.read_text())
for entry in plan['pins'].values():
    p=ROOT/entry['path']; b=p.read_bytes()
    assert len(b)==entry['size_bytes'] and hashlib.sha256(b).hexdigest()==entry['sha256'], entry['path']
assert saved['plan_sha256']==expected_join
assert saved['status']=='DIAGNOSTIC_COMPLETE_NO_NUMERICAL_VERDICT'
assert plan['numerical_verdict']=='NONE_DIAGNOSTIC_RESIDUAL_ULP_NO_TOLERANCE'
assert saved['new_point_RTE_model_compile']==0

# Bind the production source file to the actual source manifest and the source
# line that implements the native-mass prefix. No code is executed here.
manifest=json.loads(MANIFEST.read_text())
assert manifest['commit']=='f731bb993a86a1836a64152d9b936edb7c315c19'
entry=next(x for x in manifest['tracked_files'] if x['path']=='WRF/phys/module_ra_rrtmgp.F')
assert entry['sha256']==sha(SOURCE) and entry['size_bytes']==SOURCE.stat().st_size
source=SOURCE.read_text()
needle='col_dry(:,1:SIZE(native_mass,2))=REAL(native_mass,wp)* &\n        (avogad/(initialized_mol_weight_dry*10000._wp))'
assert needle in source
source_lines=source.splitlines()
line=next(i+1 for i,x in enumerate(source_lines) if 'col_dry(:,1:SIZE(native_mass,2))=REAL(native_mass,wp)* &' in x)

def sections(path, wanted):
    lines=Path(path).read_text().splitlines(); got={}
    for i,line in enumerate(lines):
        f=line.split()
        if not f or f[0] not in wanted: continue
        shape=tuple(map(int,f[1:])); n=math.prod(shape); vals=[]; j=i+1
        while len(vals)<n:
            vals.extend(float(t.replace('D','E').replace('d','e')) for t in lines[j].split()); j+=1
        assert len(vals)==n and f[0] not in got
        got[f[0]]=np.array(vals,dtype=np.float64).reshape(shape,order='F')
    assert set(got)==set(wanted)
    return got

inp=sections(INPUT,{'NATIVE_DRY_LAYER_MASS_KG_M2','MOL_WEIGHT_DRY'})
target=sections(PRODUCTION,{'GAS_COL_DRY','GAS_TAU_RAW','GAS_TAU'})
mass=inp['NATIVE_DRY_LAYER_MASS_KG_M2'].reshape(-1)
mdry=float(inp['MOL_WEIGHT_DRY'].item()); avog=6.02214076e23
assert mass.size==32 and target['GAS_COL_DRY'].shape==(1,45,1)
native_target=target['GAS_COL_DRY'].reshape(-1)[:32]

# Compare both source parenthesizations in binary64 to the saved default-REAL
# production output. This checks the operation ordering's scale, not the exact
# Fortran binary result or a causal explanation for the tau residual.
factored=[float(m)*(avog/(mdry*10000.0)) for m in mass]
left_associated=[(float(m)*avog)/(mdry*10000.0) for m in mass]
def ordered_ulp(a,b):
    ai=np.asarray(a,dtype=np.float64).view(np.uint64)
    bi=np.asarray(b,dtype=np.float64).view(np.uint64)
    return np.abs(ai.astype(object)-bi.astype(object))
ulp_fact=ordered_ulp(factored,native_target)
ulp_left=ordered_ulp(left_associated,native_target)
dry_audit={
 'native_layers':32,
 'expression_from_source':'REAL(native_mass,wp) * (avogad / (initialized_mol_weight_dry * 10000._wp))',
 'source_line_1based':line,
 'source_file_sha256':sha(SOURCE),
 'parenthesized_factored_binary64_vs_saved':{
  'exact_equal_cells':int(np.count_nonzero(np.asarray(factored)==native_target)),
  'max_abs':float(np.max(np.abs(np.asarray(factored)-native_target))),
  'max_relative_to_saved':float(np.max(np.abs((np.asarray(factored)-native_target)/native_target))),
  'max_ordered_ulp':int(max(ulp_fact)),
 },
 'direct_left_associated_binary64_vs_saved':{
  'exact_equal_cells':int(np.count_nonzero(np.asarray(left_associated)==native_target)),
  'max_abs':float(np.max(np.abs(np.asarray(left_associated)-native_target))),
  'max_relative_to_saved':float(np.max(np.abs((np.asarray(left_associated)-native_target)/native_target))),
  'max_ordered_ulp':int(max(ulp_left)),
 },
 'interpretation_limit':'Python binary64 arithmetic is not a bit-exact model of the production Fortran wp evaluation. These comparisons verify the source grouping against saved values descriptively; they do not establish causality for opacity residuals.'
}

# Recompute summary statistics from saved arrays, separately for native and
# pressure-extension layers. The prior join is an input for comparison only.
con=json.loads(CONSTRUCTION.read_text())['cases'][0]
expected=np.asarray(con['tau_point'],dtype=np.float64)
raw=target['GAS_TAU_RAW'][0]
prepared=target['GAS_TAU'][0]
assert expected.shape==raw.shape==prepared.shape==(45,128)
def stats(actual, reference, sl):
    a=actual[sl]; b=reference[sl]; diff=a-b
    nonzero=b!=0
    ai=a.view(np.uint64); bi=b.view(np.uint64)
    ulp=np.abs(ai.astype(object)-bi.astype(object))
    return {'cells':int(a.size),'exact_cells':int(np.count_nonzero(diff==0)),
            'max_abs':float(np.max(np.abs(diff))),
            'rms':float(np.sqrt(np.mean(diff*diff))),
            'max_rel_nonzero':float(np.max(np.abs(diff[nonzero]/b[nonzero]))) if np.any(nonzero) else None,
            'max_ordered_ulp':int(max(ulp.flat))}
tau_audit={}
for name,arr in [('GAS_TAU_RAW',raw),('GAS_TAU',prepared)]:
    tau_audit[name]={'all45':stats(arr,expected,slice(0,45)),
                     'native32':stats(arr,expected,slice(0,32)),
                     'extension13':stats(arr,expected,slice(32,45))}

# Reconcile the independently recomputed summary to the frozen saved-only join.
for name in ('GAS_TAU_RAW','GAS_TAU'):
    for region, sl in [('all45',slice(0,45)),('native32',slice(0,32)),('extension13',slice(32,45))]:
        prior=saved['tau'][name][region]['summary']
        now=tau_audit[name][region]
        assert now['cells']==prior['cells']
        assert now['max_abs']==prior['max_absolute_residual']
        assert now['rms']==prior['rms_residual']
        assert math.isclose(now['max_rel_nonzero'],prior['max_absolute_relative_residual_nonzero_target'],rel_tol=1e-14,abs_tol=0.0)
        assert now['max_ordered_ulp']==prior['max_absolute_ordered_ulp_delta']

report={
 'schema':'UDM37_NORMAL_PRODUCTION_JOIN_SOURCE_AND_SAVED_ARRAY_REVIEW_V1',
 'status':'PASS_SCOPED_SOURCE_GROUPING_AND_SAVED_STATISTICS_NO_NUMERICAL_VERDICT',
 'artifact_pins':pins,
 'source_manifest_entry':entry,
 'production_dry_expression_audit':dry_audit,
 'saved_tau_statistics_recomputed':tau_audit,
 'join_result_pin':pin(JOIN),
 'interpretation':'The production adapter source groups the native-mass conversion as mass*(Avogadro/(Mdry*10000)); the direct reference path uses mass*Avogadro/(Mdry*10000). Saved-result statistics reproduce the already-recorded join. Neither observation identifies the cause of the small native-layer tau differences or establishes a physical-accuracy verdict.',
 'counts':{'new_opacity_reconstructions':0,'new_reference_RTE_calls':0,'new_WRF_models':0,'new_compiles':0}
}
# Recheck all inputs after parsing.
for p in pins:
    b=(ROOT/p['path']).read_bytes()
    assert len(b)==p['size_bytes'] and hashlib.sha256(b).hexdigest()==p['sha256']
dest=OUT/'review.json'
with dest.open('x') as f: json.dump(report,f,indent=2,sort_keys=True); f.write('\n')
print(json.dumps({'status':report['status'],'review':str(dest.relative_to(ROOT)),'sha256':sha(dest),
                  'native_dry':dry_audit,'tau':tau_audit,'counts':report['counts']},sort_keys=True))
