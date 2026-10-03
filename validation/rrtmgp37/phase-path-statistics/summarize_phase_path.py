#!/usr/bin/env python3
"""Rebuild compact phase/path observations from immutable run receipts and coefficient files."""
import argparse, hashlib, json, re
from pathlib import Path
from netCDF4 import Dataset

PATTERN = re.compile(r'^d01\s+(\S+)\s+(LW|SW)\s+RRTMGP_UDM_(CF0_OMITTED|LUT_CLIP)\s+phase=(LIQ|ICE|RAIN|SNOW)')
NUMBER = re.compile(r'([A-Za-z0-9_]+)=\s*([0-9.Ee+\-]+)')

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''): h.update(block)
    return h.hexdigest()

def read_json(path): return json.loads(Path(path).read_text())

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ra37-receipt',required=True,type=Path)
    ap.add_argument('--ra37-comparison',required=True,type=Path)
    ap.add_argument('--ra4-receipt',required=True,type=Path)
    ap.add_argument('--ra4-comparison',required=True,type=Path)
    ap.add_argument('--build-receipt',required=True,type=Path)
    ap.add_argument('--recheck',required=True,type=Path)
    ap.add_argument('--coefficient-dir',required=True,type=Path)
    ap.add_argument('--test-source',required=True,type=Path)
    ap.add_argument('--test-dir',required=True,type=Path)
    ap.add_argument('--output',required=True,type=Path)
    a=ap.parse_args()
    build=read_json(a.build_receipt)
    recheck=read_json(a.recheck)
    summary={
      'scope':'Fresh GNU serial32/nest0 em_real build of workspace baseline plus phase/path diagnostics; compared against completed workspace actual outputs. Diagnostics do not change physical outputs in tested runs.',
      'build':build,
      'cases':{},
      'root_independent_whole_file_recheck':{'path':str(a.recheck.resolve()),'sha256':sha(a.recheck),'status':recheck['status'],'pairs':recheck['pairs']},
      'lut_coordinate_bounds_um':{},
      'diagnostic_interpretation':{
        'cf0_counts':'Layer-cell instances with positive omitted LIQ/ICE/RAIN/SNOW grid-mean path at the recorded radiation calls. LW and SW are separate wrapper calls and must not be added as unique mass.',
        'clip_counts':'Only LIQ/ICE, positive path and cloud fraction, nonzero overlap. Strict comparisons to LUT bounds; equality is not clipped.',
        'path_sums':'Unweighted sums over eligible layer-cell grid paths in g/m2; not horizontal-area-integrated mass, time accumulation, or domain-total mass.',
        'scope':'Noninterference for the tested serial cases only. The statistics do not estimate flux error. SW is reported only when its wrapper executes in daylight; ranks are not reduced.'}}
    for phase,receipt_path,comparison_path in [('ra37',a.ra37_receipt,a.ra37_comparison),('ra4',a.ra4_receipt,a.ra4_comparison)]:
        rec=read_json(receipt_path)
        if rec.get('status')!='COMPLETE_BITWISE_PASS' or rec.get('comparison_status')!='BITWISE_PASS' or not rec.get('success_marker'):
            raise SystemExit(f'{phase} run receipt is not a complete bitwise pass')
        log=Path(rec['run'])/'wrf.stdout.log'
        if sha(log)!=rec['log_sha256']: raise SystemExit(f'{phase} stdout hash mismatch')
        if not rec.get('diagnostics_environment_cleared'): raise SystemExit(f'{phase} diagnostics environment was not cleared')
        comp=read_json(comparison_path)
        if comp['status']!='BITWISE_PASS' or comp['differences']: raise SystemExit(f'{phase} detailed comparison is not clean')
        item={'status':rec['status'],'comparison_status':comp['status'],'history_count':len(comp['history_files']),'differing_fields_or_metadata':len(comp['differences']),'executable_sha256':rec['executable_sha256'],'stdout_path':str(log.resolve()),'stdout_sha256':rec['log_sha256'],'diagnostic_line_count':len(rec.get('phase_path_diagnostics',[])),'diagnostics_selected_calls':{}}
        for line in rec.get('phase_path_diagnostics',[]):
            m=PATTERN.search(line)
            if not m: raise SystemExit('unrecognized diagnostic line: '+line)
            t,band,kind,phase_name=m.groups();fields={}
            for key,value in NUMBER.findall(line):
                if key not in ('tile_i','tile_j'): fields[key]=float(value)
            tile=re.search(r'tile_i=(\S+)\s+tile_j=(\S+)',line)
            if tile: fields['tile_i_range'],fields['tile_j_range']=tile.groups()
            item['diagnostics_selected_calls'][f'{t}/{band}/{kind}/{phase_name}']=fields
        if phase=='ra37' and len(item['diagnostics_selected_calls'])!=24: raise SystemExit('expected 24 diagnostic records for two LW/SW calls')
        if phase=='ra4' and item['diagnostic_line_count']!=0: raise SystemExit('RA4 should not emit option-37 diagnostics')
        summary['cases'][phase]=item
    for band in ('lw','sw'):
        path=a.coefficient_dir/f'rrtmgp-clouds-{band}-bnd.nc'
        with Dataset(path) as nc:
            keys=('radliq_lwr','radliq_upr','diamice_lwr','diamice_upr')
            bounds={key:float(nc[key][...]) for key in keys}
        summary['lut_coordinate_bounds_um'][band]={'coefficient_file':str(path.resolve()),'coefficient_sha256':sha(path),'liquid_effective_radius':[bounds['radliq_lwr'],bounds['radliq_upr']],'ice_effective_diameter':[bounds['diamice_lwr'],bounds['diamice_upr']]}
    summary['standalone_statistics_test']={'result':'PASS','test_source':str(a.test_source.resolve()),'test_source_sha256':sha(a.test_source),'command':'ctest --test-dir '+str(a.test_dir.resolve())+' -R ^udm_phase_path_statistics$ --output-on-failure'}
    if recheck['status']!='PASS_WHOLE_FILE_BYTES' or recheck['pairs']!=12: raise SystemExit('independent full-file recheck did not pass 12 pairs')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(summary,indent=2)+'\n')

if __name__=='__main__': main()
