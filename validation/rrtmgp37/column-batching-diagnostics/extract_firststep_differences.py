#!/usr/bin/env python3
"""Extract sparse first-step B1/B32 field deltas from the original JSON receipt."""
import argparse,csv,json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser();ap.add_argument('execution_json',type=Path);ap.add_argument('csv_out',type=Path);a=ap.parse_args()
    d=json.loads(a.execution_json.read_text(encoding='utf-8'))
    rows=[]
    for key in ('b1-omp1__b32-omp1','b1-omp2__b32-omp2'):
        cmp=d['comparisons'][key]; samples={}
        for x in cmp.get('first_changed_values',[]): samples.setdefault((x['file'],x['field']),x)
        for filename,record in cmp['files'].items():
            for name,s in record.get('fields',{}).items():
                if s.get('equal',False): continue
                q=samples.get((filename,name),{})
                rows.append({'comparison':key,'filename':filename,'variable':name,'dtype':s.get('dtype',''),
                  'shape':json.dumps(s.get('shape',[]),separators=(',',':')),'different_values':s.get('different_values',s.get('different_storage_values','')),
                  'max_abs_difference':s.get('max_abs_difference',s.get('max_abs_numeric_difference','')),'rms_difference':s.get('rms_difference',''),
                  'raw_bytes_equal':s.get('raw_bytes_equal',''),'first_index_c_order':json.dumps(q.get('first_index_c_order',[]),separators=(',',':')),
                  'first_a':q.get('a',''),'first_b':q.get('b','')})
    a.csv_out.parent.mkdir(parents=True,exist_ok=True)
    with a.csv_out.open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(f'wrote {len(rows)} differing comparison rows')
if __name__=='__main__':main()
