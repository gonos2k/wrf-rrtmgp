#!/usr/bin/env python3
"""Read only the pinned existing long-B32 logs; never run or modify WRF."""
import collections
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CASE = ROOT / 'build/udm37-restart-cloud-diagnostics-runtime-v2/runs-v2/cases/long-b32'
SOURCE = ROOT / 'build/udm37-restart-cloud-diagnostics-gnu-v1/source-v4/WRF'
EXECUTION = ROOT / 'build/udm37-restart-cloud-diagnostics-runtime-v2/runs-v2/execution.json'
EXECUTION_SHA = '6229e7d6964618fda7b93fd3c9d8788ce86cccabc0f3bb905ef2d5397e08d65e'
TAG = re.compile(r'(LW|SW) (RRTMGP_(?:UDM_CF0_OMITTED|UDM_LUT_CLIP|CU_POPULATION|CU_LUT_CLIP))\b')
FIELD = re.compile(r'([A-Za-z][A-Za-z0-9_]*)\s*=\s*(.*?)(?=\s+[A-Za-z][A-Za-z0-9_]*\s*=|$)')
REQUIRED = {
    'RRTMGP_UDM_CF0_OMITTED': 'phase tile_i tile_j layers sum_layer_grid_wp_g_m2 max_layer_grid_wp_g_m2',
    'RRTMGP_UDM_LUT_CLIP': 'phase tile_i tile_j low_layers high_layers low_clipped_layer_wp_sum_g_m2 high_clipped_layer_wp_sum_g_m2 eligible_layer_wp_sum_g_m2 clip_grid_wp_fraction max_low_g_m2 max_high_g_m2',
    'RRTMGP_CU_POPULATION': 'phase tile_i tile_j accepted_grid_sum_g_m2 rejected_grid_sum_g_m2 rejected_grid_max_g_m2 omitted_cf0_count omitted_cf0_sum_g_m2 omitted_cf0_max_g_m2 negative_source_count negative_active_count',
    'RRTMGP_CU_LUT_CLIP': 'phase low_layers low_grid_path_g_m2 high_layers high_grid_path_g_m2 eligible_grid_path_g_m2 clipped_grid_path_fraction max_low_g_m2 max_high_g_m2',
}

def pin(path):
    b = path.read_bytes()
    return {'path': str(path.relative_to(ROOT)), 'size': len(b), 'sha256': hashlib.sha256(b).hexdigest()}

def parse_line(line):
    m = TAG.search(line)
    if not m:
        return None
    fields = {}
    for k, v in FIELD.findall(line[m.end():]):
        if k in fields: raise ValueError('duplicate field: ' + k)
        v = v.strip()
        if k == 'phase':
            if v not in ('LIQ', 'ICE', 'RAIN', 'SNOW'): raise ValueError(v)
            fields[k] = v
        elif k.startswith('tile_'):
            if not re.fullmatch(r'\d+\s*:\s*\d+', v): raise ValueError(v)
            fields[k] = [int(x) for x in v.split(':')]
        else:
            n = float(v.replace('D', 'E'))
            if not math.isfinite(n) or n < 0: raise ValueError((k, v))
            fields[k] = n
    if 'phase' not in fields: raise ValueError('missing phase')
    if set(fields) != set(REQUIRED[m.group(2)].split()): raise ValueError('unexpected or missing fields')
    if m.group(2) != 'RRTMGP_CU_LUT_CLIP' and not {'tile_i', 'tile_j'} <= fields.keys():
        raise ValueError('missing tile identity')
    return {'phase': m.group(1), 'tag': m.group(2), 'fields': fields}

def validate_record_identities(records):
    identities = [(r['rank'], r['line']) for r in records]
    if len(set(identities)) != len(identities): raise ValueError('duplicate rank/line record')

def phase_rows(records, phase, population):
    return [r for r in records if r['phase'] == phase and r['fields']['phase'] == population]

def run():
    for filename in ('summary.json', 'records.jsonl'):
        if (HERE / filename).exists(): raise RuntimeError('output collision')
    before = [pin(EXECUTION)]
    if before[0]['sha256'] != EXECUTION_SHA: raise RuntimeError('execution pin changed')
    receipt = json.loads(EXECUTION.read_text())
    if receipt['status'] != 'PASS_SCOPED_RESTART_DIAGNOSTIC_ARRAYS_AND_INVOCATION_METADATA':
        raise RuntimeError(receipt['status'])
    if receipt['arms']['long-b32']['status'] != 'CASE_VALIDATED': raise RuntimeError('arm not validated')
    records, duplicate_channels = [], []
    for rank in range(4):
        out, err = (CASE / f'rsl.{c}.{rank:04d}' for c in ('out', 'error'))
        before.extend((pin(out), pin(err)))
        stdout = out.read_text().splitlines()
        stderr = err.read_text().splitlines()
        out_policy = [s.strip() for s in stdout if TAG.search(s)]
        err_policy = [s.strip() for s in stderr if TAG.search(s)]
        if out_policy != err_policy: raise RuntimeError('policy channel mismatch')
        if not any('SUCCESS COMPLETE WRF' in s for s in stdout): raise RuntimeError('rank incomplete')
        duplicate_channels.append({'rank': rank, 'policy_records_each_channel': len(out_policy),
                                   'policy_channel_sequences_identical': True, 'counted_channel': 'out'})
        preceding_main_time = None
        for lineno, line in enumerate(stdout, 1):
            t = re.search(r'Timing for main: time (\S+)', line)
            if t: preceding_main_time = t.group(1)
            item = parse_line(line)
            if item:
                item.update(rank=rank, line=lineno, preceding_main_time_context=preceding_main_time)
                records.append(item)
    validate_record_identities(records)
    stats = {}
    for phase in ('LW', 'SW'):
        for population in ('LIQ', 'ICE', 'RAIN', 'SNOW'):
            subset = phase_rows(records, phase, population)
            if not subset: continue
            result = {}
            for tag in sorted({r['tag'] for r in subset}):
                rows = [r['fields'] for r in subset if r['tag'] == tag]
                sums, maxima = {}, {}
                for k in rows[0]:
                    if k in ('phase', 'tile_i', 'tile_j'): continue
                    if k.startswith('max_') or '_max_' in k:
                        maxima[k] = max(r[k] for r in rows)
                    elif 'fraction' not in k:
                        sums[k] = math.fsum(r[k] for r in rows)
                result[tag] = {'records': len(rows), 'sum_over_logged_calls': sums, 'max_over_logged_calls': maxima}
            if 'RRTMGP_UDM_LUT_CLIP' in result:
                s = result['RRTMGP_UDM_LUT_CLIP']['sum_over_logged_calls']
                result['native_pooled_logged_eligible_path_clipped_fraction'] = (
                    s['low_clipped_layer_wp_sum_g_m2'] + s['high_clipped_layer_wp_sum_g_m2']) / s['eligible_layer_wp_sum_g_m2']
            if 'RRTMGP_CU_POPULATION' in result:
                denominator = result['RRTMGP_CU_POPULATION']['sum_over_logged_calls']['accepted_grid_sum_g_m2']
                clips = result.get('RRTMGP_CU_LUT_CLIP', {}).get('sum_over_logged_calls', {})
                numerator = clips.get('low_grid_path_g_m2', 0) + clips.get('high_grid_path_g_m2', 0)
                if denominator:
                    result['cu_pooled_logged_accepted_path_clipped_fraction'] = numerator / denominator
                if numerator > denominator: raise RuntimeError('CU numerator exceeds accepted mass')
            stats[f'{phase}:{population}'] = result
    source_pins = [pin(SOURCE / p) for p in (
        'phys/module_ra_rrtmgp_input.F', 'phys/module_ra_rrtmgp.F', 'phys/module_ra_rrtmg_lw.F',
        'phys/module_ra_rrtmg_sw.F', 'phys/module_radiation_driver.F', 'dyn_em/module_first_rk_step_part1.F')]
    namelist = (CASE / 'namelist.output').read_text()
    if not re.search(r'(?im)^\s*cldovrlp\s*=\s*2\b', namelist): raise RuntimeError('cldovrlp is not 2')
    before.append(pin(CASE / 'namelist.input'))
    before.append(pin(CASE / 'namelist.output'))
    after = [pin(ROOT / x['path']) for x in before]
    if before != after: raise RuntimeError('input changed during parsing')
    summary = {'status': 'PASS_READONLY_LOG_EXTRACTION_SCOPED', 'new_model_invocations': 0,
        'execution_pin': before[0], 'counted_records': len(records), 'channel_duplication': duplicate_channels,
        'input_pins': before, 'input_pre_post_identical': True, 'source_pins': source_pins,
        'parser_pin': pin(Path(__file__).resolve()), 'statistics': stats,
        'limitations': [
            'All sums repeat material across radiation calls; neither domain-total mass nor physical domain occurrence fractions.',
            'LW and SW are separate samples; SW summaries cover wrapper execution in daylight only.',
            'Native CF0 rain/snow total grid-path denominators are not emitted; an omission fraction is unavailable.',
            'CU LUT lines lack tile/call identifiers. No adjacency pairing or per-tile CU fraction is inferred under OpenMP.',
            'preceding_main_time_context is context only, not authenticated radiation-call time.',
            'Pooled CU denominator uses all accepted CU population paths, including calls with no clipping line, valid here at cldovrlp=2.',
            'Printed native sums have six-decimal scientific mantissas; pooled values are reconstructed from displayed diagnostics.',
            'Path fractions and rejection sums do not quantify flux error or observational accuracy.',
            'No NetCDF state reconstruction, optical replay, forecast, source modification or physical-policy change.']}
    (HERE / 'records.jsonl').write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in records))
    summary['records_pin'] = pin(HERE / 'records.jsonl')
    (HERE / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': summary['status'], 'records': len(records), 'summary': pin(HERE / 'summary.json')}))

if __name__ == '__main__':
    run()
