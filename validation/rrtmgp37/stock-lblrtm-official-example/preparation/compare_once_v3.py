"""Complete official example ASCII comparison; no tolerance relaxation."""
from decimal import Decimal
import hashlib
from itertools import zip_longest
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
PREP = Path(__file__).resolve().parent
RUN = ROOT / 'build/udm37-lblrtm-official-example-regression-run-v1'

def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()

def pin(p):
    return {'path':str(p.relative_to(ROOT)), 'bytes':p.stat().st_size,
            'sha256':digest(p)}

def header(f, label):
    lines = []
    for _ in range(200):
        s = f.readline()
        if not s:
            raise ValueError('Missing spectral header')
        lines.append(s.rstrip('\r\n'))
        if 'WAVENUMBER' in s:
            if label not in s:
                raise ValueError('Wrong plotted variable')
            return lines
    raise ValueError('Excess spectral header length')

def rows(f):
    previous = None
    for s in f:
        if not s.strip():
            continue
        tokens = s.split()
        if len(tokens) != 2:
            raise ValueError('Expected exactly two numeric fields')
        w,y = [Decimal(t.replace('D','E')) for t in tokens]
        if not w.is_finite() or not y.is_finite():
            raise ValueError('Nonfinite spectrum')
        if previous is not None and w <= previous:
            raise ValueError('Nonmonotonic spectrum')
        previous = w
        yield w,y,tokens

def context(lines):
    # Source-identified generation clock is the only deleted information.
    return [' '.join(re.sub(r'\b\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\b',
                 '<GENERATION_CLOCK>',s).split()) for s in lines]

def compare(current, reference, label):
    stats = {'current':pin(current),'reference':pin(reference),
             'raw_byte_identity':False,'numeric_tolerance':0,
             'points_current':0,'points_reference':0,'grid_mismatches':0,
             'value_mismatches':0,'unpaired_points':0,'current_negative_values':0,
             'max_abs_difference':0.0,'max_relative_difference':0.0,
             'difference_examples':[]}
    stats['raw_byte_identity'] = stats['current']['sha256'] == stats['reference']['sha256']
    sum_diff=0.0; sum_square=0.0; paired=0
    with current.open() as a, reference.open() as b:
        ha=header(a,label);hb=header(b,label)
        stats['current_header']=ha; stats['reference_header']=hb
        stats['header_context_equal_except_clock_and_spacing']=context(ha)==context(hb)
        for index,(ra,rb) in enumerate(zip_longest(rows(a),rows(b)),1):
            stats['points_current'] += ra is not None
            stats['points_reference'] += rb is not None
            if ra is None or rb is None:
                stats['unpaired_points']+=1
                continue
            wa,ya,ta=ra;wb,yb,tb=rb
            stats['grid_mismatches']+=wa!=wb
            stats['value_mismatches']+=ya!=yb
            stats['current_negative_values']+=ya<0
            d=float(ya-yb);paired+=1;sum_diff+=d;sum_square+=d*d
            stats['max_abs_difference']=max(stats['max_abs_difference'],abs(d))
            if yb!=0:
                stats['max_relative_difference']=max(stats['max_relative_difference'],float(abs((ya-yb)/yb)))
            if (wa!=wb or ya!=yb) and len(stats['difference_examples'])<3:
                stats['difference_examples'].append({'point_1based':index,'current_tokens':ta,'reference_tokens':tb})
    if not paired:
        raise ValueError('Empty spectrum')
    stats['mean_difference']=sum_diff/paired
    stats['RMS_difference']=math.sqrt(sum_square/paired)
    stats['finite_monotonic_parse']='PASS'
    stats['printed_numeric_resolution_gate']='PASS' if not any(stats[k] for k in
          ['grid_mismatches','value_mismatches','unpaired_points','current_negative_values']) else 'FAIL'
    stats['header_context_gate']='PASS' if stats['header_context_equal_except_clock_and_spacing'] else 'FAIL'
    return stats

def main():
    # Mandatory terminal execution evidence must be read before spectra.
    terminal=json.loads((RUN/'terminal.json').read_text())
    assert terminal['status']=='TERMINAL_RC0_COMPARISON_PENDING'
    for name in ['LNFL','LBLRTM']:
        assert terminal[name]['actual_child_RC']==0 and not terminal[name]['timeout']
        assert terminal[name]['status']=='TERMINAL' and terminal[name]['exception'] is None
    output=RUN/'comparison.json'
    assert not output.exists(), 'One-use comparison output already exists'
    inventory=json.loads((RUN/'lblrtm/output-inventory.json').read_text())
    plan=json.loads((PREP/'plan-v3.json').read_text())
    for n in ['TAPE27','TAPE28']:
        p=RUN/'lblrtm'/n;assert p.stat().st_size==inventory[n]['bytes']
        assert digest(p)==inventory[n]['sha256']
    for n in ['TAPE27_ex','TAPE28_ex']:
        p=ROOT/plan['inputs'][n]['path'];assert digest(p)==plan['inputs'][n]['sha256']
    series={n:compare(RUN/'lblrtm'/n,ROOT/plan['inputs'][n+'_ex']['path'],label)
            for n,label in [('TAPE27','RADIANCE'),('TAPE28','TEMPERATURE')]}
    passed=all(r['printed_numeric_resolution_gate']=='PASS' and
               r['header_context_gate']=='PASS' for r in series.values())
    report={'schema':'UDM37_OFFICIAL_LBLRTM_EXAMPLE_COMPARISON_V1',
         'status':'PASS_SCOPED_OFFICIAL_SERIALIZED_EXAMPLE' if passed else 'FAIL_SCOPED_OFFICIAL_SERIALIZED_EXAMPLE',
         'series':series,'terminal_execution':pin(RUN/'terminal.json'),
         'plan':pin(PREP/'plan-v3.json'),'reader':pin(Path(__file__)),
         'acceptance_scope':'Complete owner-bundled radiance/temperature tabulations at original printed precision. No extra atol/rtol. GNU run vs incompletely identified reference compiler.',
         'negative_OD_reference_accepted':False,'WRF4_37_residual_attributed':False,
         'existing_physical_failures_changed':False,'new_model_or_solver_calls_in_reader':0}
    with output.open('x') as f:
        json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({'status':report['status'],'report_sha256':digest(output),
          'series':{k:{a:v[a] for a in ['points_current','points_reference','grid_mismatches','value_mismatches','max_abs_difference','RMS_difference','header_context_gate']} for k,v in series.items()}}))
    return 0 if passed else 1

if __name__=='__main__':
    sys.exit(main())
