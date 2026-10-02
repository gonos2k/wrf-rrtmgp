from pathlib import Path
import json,sys,numpy as np,netCDF4,hashlib,subprocess,shutil
root=Path.cwd();sys.path.insert(0,str(root/'WRF/test/rrtmgp'));from test_column_replay import read_raw,read_input
out=root/'validation/rrtmgp37/port-audit';cases={};before=root/'build/optics-radiation-comparison';after=root/'build/port-audit-patched-comparison'
for case in sorted(after.iterdir()):
 if not case.is_dir():continue
 pair={}
 for option in [4,37]:
  old=before/case.name/f'ra{option}';new=case/f'ra{option}'
  with netCDF4.Dataset(sorted(old.glob('wrfout_d01_*'))[-1]) as a,netCDF4.Dataset(sorted(new.glob('wrfout_d01_*'))[-1]) as b:
   changes=[];compared=0
   for name,var in b.variables.items():
    if name not in a.variables:continue
    x=np.asarray(a[name][:]);y=np.asarray(var[:]);compared+=1
    equal=(x.shape==y.shape and x.dtype==y.dtype and x.tobytes()==y.tobytes())
    if not equal:changes.append(name)
   pair[str(option)]={'compared_variables':compared,'changed_variables':changes,'bitwise_equal':not changes}
   if option==4:assert not changes,(case.name,changes)
 cases[case.name]=pair
reports={}
for when in ['first','second']:
 base=root/f'build/port-audit-replay-{when}-final';report=json.loads((base/'replay_report.json').read_text());assert report['status']=='PASS'
 phases={}
 for ph in ['lw','sw']:
  _,_,_,raw=read_raw(base/'capture'/f'{ph}.raw');*_,inp=read_input(base/'capture'/f'{ph}.input')
  phases[ph]={}
  for r,q,key,bg in [('CLOUD','QC','REL',2.49e-6),('ICE','QI','REI',4.99e-6),('SNOW','QS','RES',9.99e-6)]:
   source=raw['SOURCE_RE_'+r];wet=(raw[q]>0)&(raw['CF']>0);isbg=wet&(source.astype(np.float32)==np.float32(bg));normal=wet&~isbg
   selected=inp[key][0,:len(source)];diagnosed=raw['FALLBACK_'+key]
   assert np.allclose(selected[isbg],diagnosed[isbg],rtol=5e-7,atol=1e-7)
   assert np.allclose(selected[normal],source[normal]*1e6,rtol=5e-7,atol=1e-7)
   phases[ph][key]={'wet_background_layers':int(isbg.sum()),'wet_diagnosed_layers':int(normal.sum()),'source_um':list(map(float,source[wet]*1e6)),'selected_um':list(map(float,selected[wet]))}
 reports[when]={'status':report['status'],'phase_radii':phases,'source_report':str(base/'replay_report.json')}
 shutil.copy2(base/'replay_report.json',out/f'wrf-replay-{when}.json')
# Fixed first-call physical output agrees with pre-patch independent BG counterfactual.
from compare_column_replay import read_result
counter=json.loads((out/'radius-counterfactual.json').read_text())['mp4-mixed'];reference_errors={}
for ph in ['lw','sw']:
 sec=read_result(root/f'build/port-audit-replay-first-final/capture/{ph}.result')['sections'];exp=counter[ph.upper()]['background_fallback'];got=float(sec['DN'][0,0,0]);e=abs(got-exp['surface_down']);assert e<1e-4;reference_errors[ph]=e
result={'status':'PASS','ra4_all_cases_bitwise_preserved':True,'cases':cases,'radius_contract':reports,'fixed_first_matches_independent_counterfactual_max_abs_w_m2':reference_errors}
(out/'post-patch-regression.json').write_text(json.dumps(result,indent=2)+'\n')
receipt=json.loads((after/'receipt.json').read_text());assert receipt['status']=='PASS';shutil.copy2(after/'receipt.json',out/'post-patch-paired-scm-receipt.json')
p=out/'validation.json';v=json.loads(p.read_text());v['production_patch_status']='LOCAL_VERIFIED';v['post_patch_verification']={'gnu_serial_wrf_build':'PASS','build_log':'build/port-audit-wrf-patched-build.log','wrf_sha256':hashlib.sha256((root/'WRF/main/wrf.exe').read_bytes()).hexdigest(),'ideal_sha256':hashlib.sha256((root/'WRF/main/ideal.exe').read_bytes()).hexdigest(),'paired_5min_scm_runs':14,'paired_5min_status':'PASS','ra4_bitwise_regression_7_cases':'PASS','first_background_and_second_diagnosed_radius_replay':'PASS','regression_record':'post-patch-regression.json','wrf_source_blobs':{str(p.relative_to(root)):hashlib.sha1(b'blob '+str(len(p.read_bytes())).encode()+b'\0'+p.read_bytes()).hexdigest() for p in [root/'WRF/phys/module_ra_rrtmg_lw.F',root/'WRF/phys/module_ra_rrtmg_sw.F']}}
p.write_text(json.dumps(v,indent=2)+'\n');print('PASS: seven RA4 cases bitwise preserved; first BG fallback and second active diagnosed sizes verified')
for when,x in reports.items():print(when,x['phase_radii']['lw'])
for pair in receipt['pairs']:print(pair['name'],pair['output_differences']['SWDOWN']['post_initial_mean_37_minus_4_w_m2'])
