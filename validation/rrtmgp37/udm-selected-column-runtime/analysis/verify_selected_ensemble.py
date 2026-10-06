#!/usr/bin/env python3
"""Check the selected-column ensemble summary against its source audit CSV.

The original summary was a postprocessing of the audit CSV; this retained
verifier independently recomputes its scalar differences, MCSE, covariance
bounds, correlations, and selection counts. It does not run WRF or regenerate
all presentation formatting in the archived JSON/Markdown.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, math
from pathlib import Path

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def near(a, b):
    return math.isclose(float(a), float(b), rel_tol=2e-14, abs_tol=2e-14)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('csv',type=Path)
    ap.add_argument('analysis_json',type=Path)
    args=ap.parse_args()
    report=json.loads(args.analysis_json.read_text())
    rows=list(csv.DictReader(args.csv.open(newline='')))
    if sha(args.csv)!=report['source_csv']['sha256']:
        raise SystemExit('FAIL: CSV digest does not match archived analysis')
    chosen=[r for r in rows if (int(r['domain']),int(r['i']),int(r['j']),r['scope'])==(1,169,80,'selected_column')]
    if len(rows)!=336 or len(chosen)!=168 or len(rows)-len(chosen)!=168:
        raise SystemExit('FAIL: unexpected total/selected/aggregate row counts')
    if any(r['i']=='0' and r['j']=='0' for r in chosen):
        raise SystemExit('FAIL: aggregate row entered selected data')
    groups={}
    for r in chosen:
        key=(r['phase'],str(int(r['step'])))
        groups.setdefault(key,[]).append(r)
        if int(r['sample_count'])!=32 or int(r['radius_mode'])!=0:
            raise SystemExit('FAIL: sample count or radius mode changed')
        vals=[float(r[k]) for k in ('value37','value4','mean37','sd37','mean4','sd4','sd_delta')]
        if not all(math.isfinite(x) for x in vals):
            raise SystemExit('FAIL: nonfinite audit summary field')
    expected_counts={('lw','721'):41,('lw','731'):41,('sw','721'):43,('sw','731'):43}
    if {k:len(v) for k,v in groups.items()}!=expected_counts:
        raise SystemExit('FAIL: phase/time metric counts differ')
    checks=0
    for (phase,step), items in groups.items():
        expected=report['results'][phase][step]
        heats=[]
        for r in items:
            metric=r['metric']; n=int(r['sample_count'])
            m37,s37,m4,s4,sd=[float(r[k]) for k in ('mean37','sd37','mean4','sd4','sd_delta')]
            mean_delta=m37-m4
            op=float(r['value37'])-float(r['value4'])
            resid=op-mean_delta
            lo,hi=abs(s37-s4),s37+s4
            if sd<lo-1e-12 or sd>hi+1e-12:
                raise SystemExit(f'FAIL: covariance bounds {phase}/{step}/{metric}')
            corr=None if s37==0 or s4==0 else ((s37*s37+s4*s4-sd*sd)/2)/(s37*s4)
            if corr is not None and (not math.isfinite(corr) or abs(corr)>1+2e-12):
                raise SystemExit(f'FAIL: correlation {phase}/{step}/{metric}')
            key={'SURFACE_DOWN':'surface_down','TOA_UP':'toa_up','SW_NET':'sw_net','SW_DIRECT':'sw_direct'}.get(metric)
            record={'metric':metric,'mean37_minus_mean4':mean_delta,
                    'paired_sd_difference':sd,'mcse_sd_difference_over_sqrt32':sd/math.sqrt(n),
                    'operational_value37_minus_value4':op,
                    'operational_minus_ensemble_mean_difference':resid,
                    'implied_pair_correlation':corr}
            saved=(expected['heating_profile_39_layers'] if metric.startswith('HEAT_') else [])
            if metric.startswith('HEAT_'):
                ix=int(metric.split('_')[1])-1
                if ix<0 or ix>=39: raise SystemExit('FAIL: unexpected heating layer')
                stored=saved[ix]
                if stored['metric']!=metric: raise SystemExit('FAIL: heat layer ordering')
            else:
                if key is None or key not in expected: raise SystemExit(f'FAIL: missing expected {key}')
                stored=expected[key]
            for field,value in record.items():
                if field=='metric':
                    if stored[field]!=value: raise SystemExit('FAIL: metric naming mismatch')
                elif value is None:
                    if stored[field] is not None: raise SystemExit(f'FAIL: expected undefined {phase}/{step}/{metric}/{field}')
                elif not near(stored[field],value):
                    raise SystemExit(f'FAIL: summary mismatch {phase}/{step}/{metric}/{field}: {stored[field]} != {value}')
            checks+=1
    print(json.dumps({'status':'PASS','csv_sha256':sha(args.csv),'rows_total':len(rows),
                      'selected_rows':len(chosen),'groups':len(groups),'summary_metrics_verified':checks,
                      'scope':'domain 1, WRF column (169,80), selected_column rows only; aggregates excluded'},indent=2))
if __name__=='__main__': main()
