#!/usr/bin/env python3
"""Read-only aggregation of unique per-rank RRTMGP CF=0 omitted-path diagnostics."""
from __future__ import annotations
import argparse, hashlib, json, re
from collections import defaultdict, deque
from decimal import Decimal
from pathlib import Path

PHASES = ('LIQ', 'ICE', 'RAIN', 'SNOW')
NUMBER = r'[+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+\-]?\d+)?'
PHASE_RE = re.compile(
    rf'(?P<band>LW|SW) RRTMGP_UDM_PHASE_PATH phase=(?P<phase>LIQ|ICE|RAIN|SNOW) '
    rf'tile_i=(?P<i0>\d+):(?P<i1>\d+) tile_j=(?P<j0>\d+):(?P<j1>\d+) '
    rf'domain=(?P<domain>\S+) radiation_step=(?P<step>\S+) '
    rf'source_time_seconds=(?P<time>\S+) overlap=(?P<overlap>\d+) '
    rf'native_grid_path_sum_g_m2=\s*(?P<native>{NUMBER}) '
    rf'cf0_omitted_grid_path_sum_g_m2=\s*(?P<omitted>{NUMBER}) '
    rf'cf0_omitted_layer_count=\s*(?P<count>\d+) '
    rf'cf0_grid_path_fraction=\s*(?P<fraction>{NUMBER})')
OMIT_RE = re.compile(
    rf'(?P<band>LW|SW) RRTMGP_UDM_CF0_OMITTED phase=(?P<phase>LIQ|ICE|RAIN|SNOW) '
    rf'tile_i=(?P<i0>\d+):(?P<i1>\d+) tile_j=(?P<j0>\d+):(?P<j1>\d+) '
    rf'layers=\s*(?P<count>\d+) sum_layer_grid_wp_g_m2=\s*(?P<sum>{NUMBER}) '
    rf'max_layer_grid_wp_g_m2=\s*(?P<maximum>{NUMBER})')
CU_RE = re.compile(
    rf'(?P<band>LW|SW) RRTMGP_CU_POPULATION phase=(?P<phase>LIQ|ICE) '
    rf'tile_i=\s*(?P<i0>\d+)\s*:\s*(?P<i1>\d+)\s+tile_j=\s*(?P<j0>\d+)\s*:\s*(?P<j1>\d+) '
    rf'.*?omitted_cf0_count=\s*(?P<count>\d+)\s+omitted_cf0_sum_g_m2=\s*(?P<sum>{NUMBER})\s+'
    rf'omitted_cf0_max_g_m2=\s*(?P<maximum>{NUMBER}).*?domain=(?P<domain>\S+) '
    rf'radiation_step=(?P<step>\S+) source_time_seconds=(?P<time>\S+) overlap=(?P<overlap>\d+)')

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def dec(s: str) -> Decimal:
    return Decimal(s.replace('D','E').replace('d','e'))

def dstr(x: Decimal) -> str:
    return format(x, 'f')

def parse_rank(path: Path, expected_sha: str):
    if sha(path) != expected_sha:
        raise ValueError(f'log hash differs from execution receipt: {path}')
    pending=defaultdict(deque)
    cfrows=[]; pathrows=[]; curows=[]; unmatched=[]
    with path.open(errors='strict') as f:
        for lineno,line in enumerate(f,1):
            m=PHASE_RE.search(line)
            if m:
                r=m.groupdict(); r['line']=lineno
                r['rank_log']=path.name
                pathrows.append(r)
                if int(r['count'])>0:
                    key=(r['band'],r['phase'],r['i0'],r['i1'],r['j0'],r['j1'])
                    pending[key].append(r)
            m=OMIT_RE.search(line)
            if m:
                r=m.groupdict(); r['line']=lineno; r['rank_log']=path.name
                key=(r['band'],r['phase'],r['i0'],r['i1'],r['j0'],r['j1'])
                if not pending[key]:
                    unmatched.append({'line':lineno,'key':list(key),'row':line.rstrip()})
                    continue
                ctx=pending[key].popleft()
                r['context']={k:ctx[k] for k in ('domain','step','time','overlap','line','omitted','native','fraction')}
                if int(r['count']) != int(ctx['count']):
                    raise ValueError(f'layer count mismatch: {path.name}:{lineno}')
                # The compact summary is ES14.6; compare to the detailed ES24.16 row.
                context_sum=dec(ctx['omitted'])
                print_resolution=Decimal(5)*(Decimal(10)**(context_sum.adjusted()-7))
                if abs(dec(r['sum'])-context_sum) > print_resolution:
                    raise ValueError(f'per-call sum mismatch at {path.name}:{lineno}: {r["sum"]} vs {ctx["omitted"]}')
                cfrows.append(r)
            m=CU_RE.search(line)
            if m:
                r=m.groupdict(); r['line']=lineno; r['rank_log']=path.name
                curows.append(r)
    left=[{'rank_log':path.name,'key':list(k),'remaining':len(q)} for k,q in pending.items() for _ in [0] if q]
    if unmatched or left:
        raise ValueError(f'CF0 rows did not match detailed context rows in {path.name}: unmatched={len(unmatched)} left={len(left)}')
    return cfrows,pathrows,curows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--campaign',type=Path,required=True)
    ap.add_argument('--build-plan',type=Path,required=True)
    ap.add_argument('--source-copy',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args()
    campaign=a.campaign.resolve(); source=a.source_copy.resolve()
    plan=json.loads((campaign/'plan.json').read_text())
    execution=json.loads((campaign/'execution-receipt.json').read_text())
    build=json.loads(a.build_plan.read_text())
    if execution['status']!='PASS_BOTH_VALIDATED_DESCRIPTIVE' or execution['arm_results']['ra37']['status']!='PASS_VALIDATED':
        raise ValueError('campaign/RA37 execution is not the recorded successful case')
    expected_exe=plan['executable']
    exe=campaign/'ra37/wrf.exe'
    if sha(exe)!=expected_exe['sha256'] or exe.stat().st_size!=expected_exe['size_bytes']:
        raise ValueError('RA37 executable differs from the campaign executable pin')
    if sha(exe)!=sha(campaign/'ra4/wrf.exe'):
        raise ValueError('paired executables differ')
    # Confirm exact PR65 four-file production overlay used by the copied incremental build.
    overlay={r['path']:r['overlay_sha256'] for r in build['source']['production_overlay']}
    srcpins={}
    for rel,h in overlay.items():
        p=source/rel
        if not p.is_file() or sha(p)!=h:
            raise ValueError(f'production overlay mismatch: {rel}')
        srcpins[rel]={'path':str(p),'sha256':h,'size_bytes':p.stat().st_size}
    logscan=execution['arm_results']['ra37']['log_scan']['logs']
    errors={Path(x['path']).name:x for x in logscan if Path(x['path']).name.startswith('rsl.error.')}
    ranklogs=[]; all_path_records=[]
    if len(errors)!=4: raise ValueError(f'expected four unique rank error logs, found {len(errors)}')
    for rank in range(4):
        name=f'rsl.error.{rank:04d}'
        rec=errors.get(name)
        if rec is None: raise ValueError(f'missing {name}')
        path=campaign/'ra37'/name
        rows,paths,curows=parse_rank(path,rec['sha256'])
        for r in paths: r['rank']=rank
        all_path_records.extend(paths)
        ranklogs.append({'rank':rank,'path':str(path),'size_bytes':path.stat().st_size,'sha256':sha(path),
                         'native_cf0_summary_records':len(rows),'native_context_path_records':len(paths),
                         'cu_population_records':len(curows)})
    allrows=[]; all_cu_rows=[]
    for rec in ranklogs:
        rows,_,curows=parse_rank(Path(rec['path']),rec['sha256'])
        for r in rows: r['rank']=rec['rank']; allrows.append(r)
        for r in curows: r['rank']=rec['rank']
        all_cu_rows.extend(curows)
    aggregate={}
    for band in ('LW','SW'):
        aggregate[band]={}
        for phase in PHASES:
            rows=[r for r in allrows if r['band']==band and r['phase']==phase]
            detailed=[]
            detailed=[r for r in allrows if r['band']==band and r['phase']==phase]
            allpaths=[r for r in all_path_records if r['band']==band and r['phase']==phase]
            count=sum(int(r['count']) for r in detailed)
            omitted=sum((dec(r['context']['omitted']) for r in detailed),Decimal(0))
            native=sum((dec(r['context']['native']) for r in detailed),Decimal(0))
            omitted_all=sum((dec(r['omitted']) for r in allpaths),Decimal(0))
            native_all=sum((dec(r['native']) for r in allpaths),Decimal(0))
            if omitted_all != omitted:
                raise ValueError(f'CF0 summed paths disagree between detailed and compact records: {band}/{phase}')
            maximum=max((dec(r['maximum']) for r in detailed),default=Decimal(0))
            per_rank={}
            for rank in range(4):
                subset=[r for r in detailed if r['rank']==rank]
                per_rank[str(rank)]={'summary_records':len(subset),'layer_grid_count':sum(int(r['count']) for r in subset),
                    'omitted_grid_path_sum_g_m2_across_calls':dstr(sum((dec(r['context']['omitted']) for r in subset),Decimal(0))),
                    'native_grid_path_sum_g_m2_across_calls':dstr(sum((dec(r['context']['native']) for r in subset),Decimal(0))),
                    'max_logged_single_layer_grid_path_g_m2':dstr(max((dec(r['maximum']) for r in subset),default=Decimal(0)))}
            aggregate[band][phase]={
                'radiation_call_tile_phase_records_with_omission':len(detailed),
                'phase_path_records_with_positive_native_path':len(allpaths),
                'phase_path_records_without_cf0_omission':sum(int(r['count'])==0 for r in allpaths),
                'layer_grid_count_summed_over_repeated_calls_and_ranks':count,
                'cf0_omitted_grid_path_sum_g_m2_summed_over_repeated_calls_and_ranks':dstr(omitted),
                'native_grid_path_sum_g_m2_over_omission_records_only':dstr(native),
                'omitted_to_native_path_ratio_conditional_on_omission_records':dstr(omitted/native if native else Decimal(0)),
                'native_grid_path_sum_g_m2_over_all_phase_path_records':dstr(native_all),
                'omitted_to_native_path_ratio_over_all_logged_native_paths':dstr(omitted_all/native_all if native_all else Decimal(0)),
                'max_logged_single_layer_grid_path_g_m2':dstr(maximum),
                'per_rank':per_rank,
            }
    result={
      'schema':'matthew-48h-cf0-omission-audit-v1',
      'status':'PASS_LOGS_AND_SOURCE_PINNED',
      'run':{'campaign':str(campaign),'execution_receipt_sha256':sha(campaign/'execution-receipt.json'),
             'plan_sha256':sha(campaign/'plan.json'),'input_manifest_sha256':sha(campaign/'manifest.json'),
             'ra37_returncode':execution['arm_results']['ra37']['returncode'],'ra37_status':execution['arm_results']['ra37']['status'],
             'executable_path':str(exe),'executable_sha256':sha(exe),'executable_size_bytes':exe.stat().st_size,
             'radiation_configuration':{'ra_lw_physics':37,'ra_sw_physics':37,'frozen_optics_mode':1,
                 'frozen_table_sha256':plan['arms']['ra37']['table']['sha256']},
             'unique_rank_logs':ranklogs},
      'source':{'build_plan_path':str(a.build_plan.resolve()),'build_plan_sha256':sha(a.build_plan.resolve()),
                'pr65_head':build['source']['pr65_head'],'production_overlay':srcpins,
                'analysis_program':{'path':str(Path(__file__).resolve()),'sha256':sha(Path(__file__).resolve())},
                'input_builder_formula_source':{'path':str(source/'WRF/phys/module_ra_rrtmgp_input.F'),'sha256':sha(source/'WRF/phys/module_ra_rrtmgp_input.F')},
                'native_dry_layer_mass_source':{'path':str(source/'WRF/dyn_em/module_first_rk_step_part1.F'),'sha256':sha(source/'WRF/dyn_em/module_first_rk_step_part1.F')},
                'source_anchors':{
                  'module_ra_rrtmgp_input.F':'q-to-path mapping 293-295; zero-cloud-fraction omission and dry-mass path equation 455-500; frozen G/H uniform-occurrence exception 456-457,487-500',
                  'module_first_rk_step_part1.F':'native dry layer mass = -DNW*(C1H*MUT+C2H)/g at 280-287',
                  'module_ra_rrtmg_lw.F':'per-column-call native/omitted count, sum, and max accumulation at 13078-13085; per-phase contextual and compact log writes at 13458-13476',
                  'module_ra_rrtmg_sw.F':'corresponding shortwave accumulation/log path, same pattern as LW'}},
      'method':{
        'log_source':'Only rsl.error.0000 through rsl.error.0003 were parsed, one stream per MPI rank; duplicated rsl.out messages were excluded.',
        'summary_fields':'CF0_OMITTED legacy rows provide positive omitted layer counts and per-row maximum. Each was matched to its higher-precision PHASE_PATH row by rank, band, phase, tile bounds, ordering, and layer count; the compact sum was checked within its printed 6-decimal precision.',
        'grid_path_formula':'specific condensate mixing ratio (kg kg-1 dry air) × supplied native dry-layer mass (kg dry air m-2) × 1000 g kg-1.',
        'count_semantics':'Each count is a layer-grid sample accumulated across radiation-call/tile/rank log records; the same grid location may recur across calls and may appear in both spectral phases LW and SW.',
      },
      'by_band_and_phase':aggregate,
      'convective_cu_cf0_omission':{
        'description':'CU population-path logs are kept distinct from resolved/native QC/QI/QR/QS phase totals.',
        'by_band_and_phase':{
          band:{phase:{
            'cu_population_records':len([r for r in all_cu_rows if r['band']==band and r['phase']==phase]),
            'records_with_nonzero_omitted_count':sum(int(r['count'])>0 for r in all_cu_rows if r['band']==band and r['phase']==phase),
            'omitted_layer_grid_count_summed_over_records':sum(int(r['count']) for r in all_cu_rows if r['band']==band and r['phase']==phase),
            'omitted_grid_path_sum_g_m2_summed_over_records':dstr(sum((dec(r['sum']) for r in all_cu_rows if r['band']==band and r['phase']==phase),Decimal(0))),
            'max_logged_single_layer_grid_path_g_m2':dstr(max((dec(r['maximum']) for r in all_cu_rows if r['band']==band and r['phase']==phase),default=Decimal(0)))}
            for phase in ('LIQ','ICE')} for band in ('LW','SW')},
      },
      'interpretation_limits':[
        'LW and SW totals are reported separately and must not be added as unique condensate mass; they repeat radiation calls over the same evolving model state.',
        'These are summed grid-path diagnostics across repeated call/rank samples, not area-integrated mass or a unique-time/domain condensate inventory.',
        'The omitted path quantity bounds the logged condensate grid-path input associated with exactly zero cloud fraction. It does not directly bound band optical depth or flux impact; those require size/spectral optics and the actual cloud occurrence treatment.',
        'With frozen optics mode 1, graupel/hail have the separate experimental uniform-occurrence path; they are not part of the CF0 omission phase totals. No graupel-to-snow mapping is inferred.',
        'The report does not invent a new occurrence policy, infer daytime optical impact, or claim that a nonzero omitted grid path caused a measurable flux error.'
      ]
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    if a.output.exists(): raise FileExistsError(a.output)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({'status':result['status'],'output':str(a.output),'sha256':sha(a.output),'bands':{b:{p:v['radiation_call_tile_phase_records_with_omission'] for p,v in x.items()} for b,x in aggregate.items()}},indent=2))

if __name__=='__main__': main()
