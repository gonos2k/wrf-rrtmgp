#!/usr/bin/env python3
"""Read-only reconstruction of one captured LW/SW dry-air column.

No model, solver, or compiler is invoked. Text inputs are immutable captured
records; native 44 layers are evaluated from REAL32 kg m-2 values promoted to
REAL64, while upper extension layers remain the recorded pressure/VMR policy.
"""
from __future__ import annotations
import hashlib, json, math, struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / 'build/udm37-rrtmg4-export-runtime-v1/NEW_ON'
BUILD = ROOT / 'build/udm37-rrtmg4-export-serial-build-v1/source/WRF'
OUT = Path(__file__).resolve().parent
FILES = {
    'lw_input': CASE/'trace/lw_000001.input', 'lw_raw': CASE/'trace/lw_000001.raw',
    'lw_result': CASE/'trace/lw_000001.result', 'sw_input': CASE/'trace/sw_000001.input',
    'sw_raw': CASE/'trace/sw_000001.raw', 'sw_result': CASE/'trace/sw_000001.result',
    'gas_wrapper': BUILD/'phys/module_ra_rrtmgp.F',
    'legacy_lw': BUILD/'phys/module_ra_rrtmg_lw.F',
    'legacy_sw': BUILD/'phys/module_ra_rrtmg_sw.F',
    'gas_constants': BUILD/'external/rte_rrtmgp/gas-optics/mo_gas_optics_constants.F90',
    'lw_export': CASE/'export/rrtmg4_d01_i24_j55_step2161_lw.txt',
    'sw_export': CASE/'export/rrtmg4_d01_i24_j55_step2161_sw.txt',
}
AVOGAD_NATIVE = 6.02214076e23
AMD = 28.9660
AMW = 18.0160
AVOGAD_LEGACY = 6.02214199e23
GRAV_LEGACY = 9.8066


def sha(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()


def section(path: Path, name: str) -> list[float]:
    lines=path.read_text().splitlines()
    for i,line in enumerate(lines):
        tok=line.split()
        if tok and tok[0] == name:
            try: dims=[int(x) for x in tok[1:]]
            except ValueError: continue
            n=math.prod(dims)
            vals=[]
            for row in lines[i+1:]:
                for word in row.split():
                    try: vals.append(float(word.replace('D','E').replace('d','e')))
                    except ValueError: pass
                    if len(vals)==n: return vals
            raise ValueError(f'{path}: truncated {name}, expected {n}, got {len(vals)}')
    raise KeyError(f'{path}: missing section {name}')


def export_section(path: Path, name: str) -> list[float]:
    lines=path.read_text().splitlines()
    for i,line in enumerate(lines):
        tok=line.split()
        if tok and tok[0].lower() == name.lower():
            n=int(tok[-1]); vals=[]
            for row in lines[i+1:]:
                for word in row.split():
                    try: vals.append(float(word.replace('D','E').replace('d','e')))
                    except ValueError: pass
                    if len(vals)==n: return vals
            raise ValueError(f'{path}: truncated export {name}, expected {n}, got {len(vals)}')
    raise KeyError(f'{path}: missing export section {name}')

def metrics(reference, actual):
    diffs=[a-r for r,a in zip(reference,actual)]
    rel=[d/r for r,d in zip(reference,diffs) if r != 0.0]
    return {'count':len(diffs),'max_abs':max(map(abs,diffs)),
            'mean_abs':sum(map(abs,diffs))/len(diffs),
            'max_abs_relative_to_reference':max(map(abs,rel)),
            'mean_abs_relative_to_reference':sum(map(abs,rel))/len(rel),
            'first_value_difference':diffs[0], 'last_value_difference':diffs[-1]}


def run(phase: str):
    inp=FILES[f'{phase}_input']; raw=FILES[f'{phase}_raw']; res=FILES[f'{phase}_result']
    h2o=section(inp,'H2O')
    plev=section(inp,'PLEV')
    native=section(inp,'NATIVE_DRY_LAYER_MASS_KG_M2')
    grav_input=section(inp,'GRAVITY')[0]
    mdry_input=section(inp,'MOL_WEIGHT_DRY')[0]
    recorded=section(res,'GAS_COL_DRY')
    rawgrav=section(raw,'GRAVITY')[0]
    # GAS_COL_DRY native formula, matching gas_dry_column: REAL32 native mass
    # promoted to wp, then multiplied by avogad/(initialized_mol_weight_dry*10000).
    native_rebuilt=[m*(AVOGAD_NATIVE/(mdry_input*10000.0)) for m in native]
    # Legacy RRTMG4 COLDRY formula at the same bottom-first layers. It uses
    # h2ovmr from the wrapper, hPa interface pressure, legacy constants, and
    # (1+wkl) moist-air correction exactly as the pinned LW/SW source.
    legacy=[]
    legacy_f32=[]
    f32=lambda x: struct.unpack('<f',struct.pack('<f',float(x)))[0]
    def add32(a,b): return f32(f32(a)+f32(b))
    def mul32(a,b): return f32(f32(a)*f32(b))
    def div32(a,b): return f32(f32(a)/f32(b))
    n_native=len(native)
    for k in range(len(h2o)):
        w=h2o[k]
        amm=(1.0-w)*AMD+w*AMW
        dp=plev[k]-plev[k+1]
        legacy.append(dp*1.0e3*AVOGAD_LEGACY/(1.0e2*GRAV_LEGACY*amm*(1.0+w)))
        # Reproduce the pinned default-REAL (REAL32) legacy expression with
        # rounding after each primitive operation, retaining source grouping.
        w4=f32(w); amd4=f32(AMD); amw4=f32(AMW); dp4=f32(dp)
        amm4=add32(mul32(f32(1.0)-w4,amd4),mul32(w4,amw4))
        num4=mul32(mul32(dp4,f32(1.0e3)),f32(AVOGAD_LEGACY))
        den4=mul32(mul32(mul32(f32(1.0e2),f32(GRAV_LEGACY)),amm4),add32(f32(1.0),w4))
        legacy_f32.append(div32(num4,den4))
    if len(recorded) != len(h2o) or len(plev) != len(h2o)+1:
        raise ValueError(f'{phase}: shape mismatch h2o={len(h2o)}, plev={len(plev)}, result={len(recorded)}')
    native_recorded=recorded[:n_native]
    legacy_ratio=[(l/n)-1.0 for l,n in zip(legacy[:n_native],native_recorded)]
    legacy_export = export_section(FILES[f'{phase}_export'],'COLDRY')
    legacy_formula_vs_export = metrics(legacy_export, legacy)
    legacy_export_f32=[f32(x) for x in legacy_export]
    def fbits(x): return struct.unpack('<I',struct.pack('<f',f32(x)))[0]
    ulps=[abs(fbits(a)-fbits(b)) for a,b in zip(legacy_export,legacy_f32)]
    legacy_source_arithmetic={'precision':'default REAL / REAL32, IEEE binary32 simulation, with source-expression grouping',
      'max_ulp_difference_vs_actual_export':max(ulps),'nonzero_ulp_count':sum(x!=0 for x in ulps),
      'max_relative_difference_vs_actual_export':max(abs(a-b)/abs(a) for a,b in zip(legacy_export,legacy_f32) if a),
      'first_ulp_differences':ulps[:min(10,len(ulps))],
      'caveat':'Software REAL32 emulation rounds each source operation; actual compiler may contract or retain intermediates. The exported series is the authoritative comparison.'}
    native_vs_recorded=[a-b for a,b in zip(native_rebuilt,native_recorded)]
    # The recorded RRTMGP result uses native mass only in the native prefix;
    # extra levels are retained separately and not compared with this formula.
    return {
      'phase':phase.upper(),'native_levels':n_native,'input_levels':len(h2o),
      'extension_levels':len(h2o)-n_native,
      'captured_constants':{'wrapper_gravity_m_s2_real32_promoted':grav_input,
                            'wrapper_mol_weight_dry_kg_mol_real64':mdry_input,
                            'legacy_gravity_m_s2_source_constant':GRAV_LEGACY,
                            'legacy_amd_g_mol':AMD,'legacy_amw_g_mol':AMW,
                            'legacy_avogadro_mol_minus1':AVOGAD_LEGACY,
                            'rrtmgp_avogadro_mol_minus1':AVOGAD_NATIVE},
      'native_formula_vs_recorded_gas_col_dry_molecule_cm2':metrics(native_recorded,native_rebuilt),
      'legacy_formula_vs_actual_exported_coldry_molecule_cm2':legacy_formula_vs_export,
      'legacy_source_real32_arithmetic_vs_actual_export':legacy_source_arithmetic,
      'legacy_actual_export_layers':len(legacy_export),
      'legacy_actual_export_layer_note':f'Export includes {len(legacy_export)} levels: {n_native} overlapping native levels plus {len(legacy_export)-n_native} pressure/VMR upper extension level(s).',
      'legacy_coldry_vs_native_gas_col_dry_molecule_cm2':{
          'max_relative_difference':max(map(abs,legacy_ratio)),
          'mean_relative_difference':sum(legacy_ratio)/len(legacy_ratio),
          'min_relative_difference':min(legacy_ratio),
          'max_relative_difference_signed':max(legacy_ratio),
          'by_layer':[
            {'native_layer_bottom_first':i+1,'h2o_vmr':h2o[i],
             'delta_pressure_hpa':plev[i]-plev[i+1],
             'native_dry_mass_kg_m2':native[i],
             'native_gas_col_dry_molecule_cm2':native_recorded[i],
             'reconstructed_native_gas_col_dry_molecule_cm2':native_rebuilt[i],
             'legacy_coldry_molecule_cm2':legacy[i],
             'legacy_minus_native_relative':legacy_ratio[i]}
             for i in range(n_native)]},
      'native_formula_output_rounding_difference':{
          'max_abs_molecule_cm2':max(map(abs,native_vs_recorded)),
          'max_abs_relative':max(abs(d/r) for d,r in zip(native_vs_recorded,native_recorded) if r)},
      'upper_extension_comparison':{
          'layers':len(recorded)-n_native,
          'by_layer_bottom_first':[
            {'layer':k+1,'legacy_coldry_molecule_cm2':legacy[k],
             'rrtmgp_gas_col_dry_molecule_cm2':recorded[k],
             'legacy_minus_rrtmgp_relative':legacy[k]/recorded[k]-1.0}
            for k in range(n_native,len(recorded))],
          'legacy_minus_rrtmgp_relative_min':min(legacy[k]/recorded[k]-1.0 for k in range(n_native,len(recorded))),
          'legacy_minus_rrtmgp_relative_max':max(legacy[k]/recorded[k]-1.0 for k in range(n_native,len(recorded)))},
      'extension_policy_note':'GAS_COL_DRY layers 45+ are not reconstructed here; source retains pressure/VMR get_col_dry policy above the native 44-layer mass prefix.'
    }


def main():
    missing=[str(p) for p in FILES.values() if not p.is_file()]
    if missing: raise SystemExit('missing pinned inputs: '+', '.join(missing))
    hashes={k:{'path':str(p),'size_bytes':p.stat().st_size,'sha256':sha(p)} for k,p in FILES.items()}
    script_hash=sha(Path(__file__))
    result={'schema':'udm37-rrtmg4-dry-column-reconstruction-v2',
      'scope':'single captured selected column (domain 1, i=24, j=55), step 2161, source time 129600 s; offline arithmetic only',
      'method':'Compare exact wrapper native mass conversion against GAS_COL_DRY output and separately reconstruct legacy RRTMG4 COLDRY from the same input pressure and H2O VMR. No tolerance was imposed.',
      'units':'dry column molecules cm-2; input layer mass kg m-2; interfaces hPa; H2O VMR mol mol-1',
      'inputs':hashes,
      'analysis_script':{'path':str(Path(__file__).resolve()),'sha256':script_hash},
      'source_anchors':{'gas_wrapper':'module_ra_rrtmgp.F:574-586',
        'legacy_lw':'module_ra_rrtmg_lw.F:11394-11415,11449-11476',
        'legacy_sw':'module_ra_rrtmg_sw.F:9894-9909,9970-9998',
        'native_constants':'mo_gas_optics_constants.F90:37,48,51,58-67'},
      'phases':[run('lw'),run('sw')]}
    out=OUT/'dry-column-reconstruction.json'
    post={k:{'path':str(p),'size_bytes':p.stat().st_size,'sha256':sha(p)} for k,p in FILES.items()}
    result['input_immutability']={'before_after_identical':hashes==post,'after':post}
    if hashes != post: raise RuntimeError('captured inputs/source changed during analysis')
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(out)
    for x in result['phases']:
        print(x['phase'], 'native recon maxrel',x['native_formula_vs_recorded_gas_col_dry_molecule_cm2']['max_abs_relative_to_reference'],
              'legacy/native mean',x['legacy_coldry_vs_native_gas_col_dry_molecule_cm2']['mean_relative_difference'],
              'maxabs',x['legacy_coldry_vs_native_gas_col_dry_molecule_cm2']['max_relative_difference'],
              'legacy/formula export maxrel',x['legacy_formula_vs_actual_exported_coldry_molecule_cm2']['max_abs_relative_to_reference'],
              'formula-export ULP max',x['legacy_source_real32_arithmetic_vs_actual_export']['max_ulp_difference_vs_actual_export'],
              'nonzero ULPs',x['legacy_source_real32_arithmetic_vs_actual_export']['nonzero_ulp_count'])

if __name__=='__main__': main()
