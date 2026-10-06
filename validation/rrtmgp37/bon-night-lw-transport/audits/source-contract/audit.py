#!/usr/bin/env python3
"""Read retained BON artifacts and current source only; no numerical engine."""
import gzip,hashlib,importlib.util,json,math,re,struct,sys,tempfile
from pathlib import Path
import netCDF4
sys.dont_write_bytecode=True
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP');WORK=ROOT/'build/udm37-bon-night-evidence-pr-work';OUT=ROOT/'build/udm37-bon-night-lw-source-contract-audit-v1'
NIGHT=WORK/'validation/rrtmgp37/bon-night-same-state';REPLAY=WORK/'validation/rrtmgp37/bon-night-independent-replay';DRY=WORK/'validation/rrtmgp37/bon-night-dry-column-attribution'
def pin(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size_bytes':p.stat().st_size}
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def bits(x):return struct.pack('>d',float(x))
def equal(a,b):return len(a)==len(b) and all(bits(x)==bits(y) for x,y in zip(a,b))
def summary(vals):return {'count':len(vals),'min':min(vals),'max':max(vals),'nonzero':sum(x!=0 for x in vals)}
def main():
 deps=json.loads((REPLAY/'original-payload-roster.json').read_text())['repository_dependencies']
 parser=load('source_audit_trace',WORK/deps['trace_parser']['repository_relative_path']).read_trace
 er=load('source_audit_export',NIGHT/'parser/read_export_context.py').read_export
 files={'input':NIGHT/'captures/OFF/lw_000001.input.gz','raw':NIGHT/'captures/OFF/lw_000001.raw.gz','result':NIGHT/'captures/OFF/lw_000001.result.gz','export':NIGHT/'exports/rrtmg4_d01_i13_j46_step721_lw.txt.gz','matched_result':DRY/'counterfactual/result.gz'}
 parsed={}
 with tempfile.TemporaryDirectory(prefix='bon-source-contract-') as td:
  for n,p in files.items():
   f=Path(td)/n;f.write_bytes(gzip.decompress(p.read_bytes()))
   parsed[n]=er(f,expected_phase='LW',expected_context={'domain':1,'i':13,'j':46,'step':721,'source_seconds':43200.}) if n=='export' else parser(f,n if n in ('input','raw') else 'result')
 inp=parsed['input'][1];res=parsed['result'][1];matched=parsed['matched_result'][1];ex=parsed['export']['fields']
 mapping={'PLAY':'PLAY','PLEV':'PLEV','TLAY':'TLAY','TLEV':'TLEV','TSFC':'TSFC','H2O_VMR':'H2O','CO2_VMR':'CO2','O3_VMR':'O3','N2O_VMR':'N2O','CH4_VMR':'CH4','O2_VMR':'O2','CFC11_VMR':'VMR_CFC11','CFC12_VMR':'VMR_CFC12','CFC22_VMR':'VMR_CFC22','CCl4_VMR':'VMR_CCL4','SURFACE_EMISSIVITY':'EMIS'}
 joins=[]
 for legacy,gp in mapping.items():
  a=ex['INPUT',legacy].values;b=inp[gp]['values'];assert equal(a,b),(legacy,gp)
  joins.append({'legacy':legacy,'capture':gp,'IEEE64_values_equal':True,'values':summary(a),'legacy_shape':ex['INPUT',legacy].shape,'capture_shape':inp[gp]['shape']})
 gas=[];coldry=ex['INPUT','COLDry'].values;gp_dry=res['GAS_COL_DRY']['values'];match_dry=matched['GAS_COL_DRY']['values']
 for row,name,gp in [(0,'CCl4_VMR','VMR_CCL4'),(1,'CFC11_VMR','VMR_CFC11'),(2,'CFC12_VMR','VMR_CFC12'),(3,'CFC22_VMR','VMR_CFC22')]:
  vmr=inp[gp]['values'];actual=[ex['INPUT','WX_CROSS_SECTION_COLUMNS_SCALED'].at(row,k) for k in range(45)]
  reconstructed=[coldry[k]*vmr[k]*1e-20 for k in range(45)]
  gas.append({'name':name,'VMR':summary(vmr),'legacy_WX_scaled':summary(actual),'reconstructed_scaled_columns_bit_exact':equal(actual,reconstructed),'reconstruction_max_abs':max(abs(x-y) for x,y in zip(actual,reconstructed)),'matched_GP_molecular_column_max_relative_vs_legacy':max(abs(match_dry[k]/coldry[k]-1) for k in range(45)),'limitation':'GP individual gas molecular column and minor optical contribution are not separately exported; VMR*COLDry interpretation follows pinned gas optics source.'})
 inv=json.loads((REPLAY/'receipts/inventory.json').read_text());cp=Path(inv['coefficient_files'][0]['path']);assert pin(cp)['sha256']==inv['coefficient_files'][0]['sha256']
 with netCDF4.Dataset(cp) as ds:
  metadata={n:netCDF4.chartostring(ds[n][:]).tolist() if ds[n].dtype.kind=='S' else ds[n][:].tolist() for n in ('gas_names','minor_gases_lower','minor_gases_upper','bnd_limits_wavenumber','bnd_limits_gpt')}
  metadata['gas_names']=[x.strip() for x in metadata['gas_names']];metadata['minor_gases_lower']=sorted(set(x.strip() for x in metadata['minor_gases_lower']));metadata['minor_gases_upper']=sorted(set(x.strip() for x in metadata['minor_gases_upper']));metadata['planck_tables']={n:{'shape':list(ds[n].shape),'sha256_native_array_bytes':hashlib.sha256(ds[n][:].tobytes()).hexdigest()} for n in ('totplnk','plank_fraction','temperature_Planck')}
  metadata['gpoint_count']=len(ds.dimensions['gpt'])
 legacy_bands=list(zip(ex['CLOUD','BAND_WAVENUM_LO'].values,ex['CLOUD','BAND_WAVENUM_HI'].values));gp_bands=[tuple(x) for x in metadata['bnd_limits_wavenumber']];common=[{'legacy_band':i+1,'GP_band':j+1,'edges_cm_inverse':a} for i,a in enumerate(legacy_bands) for j,b in enumerate(gp_bands) if a==b]
 legacy_map=[int(x) for x in ex['CLOUD','GPOINT_TO_BAND'].values]
 lw=WORK/'WRF/phys/module_ra_rrtmg_lw.F';text=lw.read_text()
 def coeff(name):
  values=re.search(r'data '+name+r'\s*/(.*?)/',text,re.S|re.I).group(1);return [float(x) for x in re.findall(r'[-+]?\d+(?:\.\d*)?(?=_rb)',values)]
 a0,a1,a2=map(coeff,('a0','a1','a2'));pwv=ex['INPUT','PWVCM'].values[0]
 angle=[1.66 if i in (0,3) or i>=9 else max(1.5,min(1.8,a0[i]+a1[i]*math.exp(a2[i]*pwv))) for i in range(16)]
 src_rel=['WRF/phys/module_ra_rrtmg_lw.F','WRF/phys/module_ra_rrtmgp.F','WRF/test/rrtmgp/reference_column.f90','WRF/external/rte_rrtmgp/rrtmgp-frontend/mo_gas_optics_rrtmgp.F90','WRF/external/rte_rrtmgp/rte-frontend/mo_rte_lw.F90','WRF/external/rte_rrtmgp/rte-frontend/mo_fluxes.F90']
 src=[];executed=ROOT/'build/udm37-export-selection-serial-build-v1/source'
 for n in src_rel:
  p=WORK/n;old=executed/n;src.append({'current':pin(p),'executed_source':pin(old),'byte_identical':p.read_bytes()==old.read_bytes()});assert src[-1]['byte_identical']
 return {'schema':'bon-night-lw-source-contract-audit-v1','status':'PASS_SCOPED_READONLY_CONTRACT_INVENTORY','head':'371a5f035b0390281362ffc44e9251dbbc0da10e','new_model_build_solver_calls':0,'artifact_pins':{n:pin(p) for n,p in files.items()},'source_pins':src,'coefficient_pin':pin(cp),'context':parsed['export']['metadata'],'input_joins':joins,'CFC_cross_section_contract':gas,'export_field_inventory':[{'stage':stage,'name':name,'units':f.units,'shape':f.shape} for (stage,name),f in ex.items()],'capture_input_fields':sorted(inp),'GP_result_fields':sorted(res),'solver_temperature_pressure_emissivity_joins':{n:equal(ex['INPUT',n].values,ex['INPUT',original].values) for n,original in [('SOLVER_PAVEL','PLAY'),('SOLVER_PZ','PLEV'),('SOLVER_TAVEL','TLAY'),('SOLVER_TZ','TLEV'),('SOLVER_TBOUND','TSFC'),('SOLVER_SEMISS','SURFACE_EMISSIVITY')]},'spectral_metadata':{'legacy_bands_cm_inverse':legacy_bands,'legacy_gpoint_count':len(legacy_map),'legacy_gpoint_counts_per_band':[legacy_map.count(b) for b in range(1,17)],'GP_coefficient_metadata':metadata,'common_physical_bands':common,'gpoints_not_pairable_by_index':True},'angular_transport_contract':{'legacy_PWVCM_cm':pwv,'legacy_diffusivity_reconstructed_from_source':angle,'scope':'Offline formula evaluation from retained PWVCM, not an exported actual secdiff array or flux experiment.','legacy_source_anchor':'module_ra_rrtmg_lw.F:3054-3081,3253-3261','GP_default_gauss_angles':1,'GP_default_secant':1/.6096748751,'GP_default_angular_weight':1.,'GP_anchor':'mo_rte_lw.F90:128-146,218-219; module_ra_rrtmgp.F:800,885 and reference_column.f90:674,755 supply no overrides'},'missing_same_call_arrays':['legacy planklay/planklev/plankbnd/fracs','legacy secdiff/wtdiff/delwave actual arrays','GP lay_source/lev_source/sfc_source/sfc_source_Jac','per-gpoint or per-band LW fluxes from either engine','GP individual gas molecular columns and per-gas optical depth contributions'],'source_contract_limits':['Legacy band16 broadband setcoef uses Planck integral 2600 cm-1 to infinity (istart=1); GP coefficient metadata upper edge3250 does not alone establish the coefficient Planck integration tail convention. Do not infer missing tail energy without inspecting coefficient provenance/table construction.','Legacy140 versus GP128 gpoints; 11 exact band-edge pairs, no common correlated-k point identity or portable spectral-weight exchange. Weights are encoded in engine-specific reduced coefficients/source fractions; applying an additional shared quadrature weight would double count or invent a mapping.','Legacy WX uses COLDry*VMR*1e-20 in CCl4,CFC11,CFC12,CFC22 order; all four VMRs match and GP coefficient minor lists include them. Different absorption parameterizations remain, not missing-CFC evidence.','Current10 host gases exclude coefficient-only CO,N2,HFC/CF4/NO2 from available gas lists; legacy WKL CO slot zero and pressure broadener separately handled. This is an explicit gas-list/broadening contract, not proof of equivalence of every continuum term.'],'next_bounded_design':{'root_selected_policies':['default one-angle','uniform lw_Ds=1.66','four Gauss-Jacobi angles'],'input':'Retained first-call 45-layer legacy-dry diagnostic carrier, otherwise exact immutable bytes','needed_diagnostics':['before-RTE source arrays with spectral metadata','per-policy actual angle/secant and angular weight metadata','band-resolved LW fluxes/heating derived from interfaces'],'gate':'Default must reproduce retained matched-dry result before interpreting angle sensitivities; identical gas optics/source before policy change and held input/library/table/source pins. No spectral cross-engine array swap or new production physics change.','interpretation':'Difference between policies is angular-transport sensitivity in this GP closure only. Residual against legacy remains combined source/gas/spectral/transport/implementation; no accuracy winner or physical-normal claim.'}}
if __name__=='__main__':
 result=main();p=OUT/'audit.json'
 with p.open('x') as f:json.dump(result,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
 print(json.dumps({'status':result['status'],'audit':pin(p),'joins':len(result['input_joins']),'common_bands':len(result['spectral_metadata']['common_physical_bands']),'CFC':result['CFC_cross_section_contract'],'export_fields':len(result['export_field_inventory']),'angles':result['angular_transport_contract']},indent=2))
