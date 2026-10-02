#!/usr/bin/env python3
"""Reject invalid numerical controls before creating artifacts or fetching data."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import generate as gen


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    if args.output_dir.exists():parser.error('Use a new output directory')
    args.output_dir.mkdir(parents=True)
    cases=[]
    fixtures=[('lambda-nan',['--lambda-grid','nan']),('lambda-zero',['--lambda-grid','0']),
              ('lambda-order',['--lambda-grid','2000','300']),('lambda-duplicate',['--lambda-grid','300','300']),
              ('temperature-inf',['--temperatures','233','inf']),('temperature-zero',['--temperatures','0']),
              ('order-low',['--order','3']),('order-high',['--order','513']),('workers-zero',['--workers','0']),
              ('recurrence-low',['--max-terms','15']),('recurrence-c-int-wrap',['--max-terms','4294967296']),
              ('chunk-zero',['--spectral-chunk-size','0']),
              ('spectral-zero',['--spectral-step','0']),('spectral-nan',['--spectral-step','nan'])]
    generator=gen.HERE/'generate.py'; source_hash=gen.sha(generator)
    for name,options in fixtures:
        destination=args.output_dir/name
        command=[sys.executable,str(generator),'--input-dir',str(args.output_dir/'no-input'),
                 '--output-dir',str(destination)]
        if options[0]!='--lambda-grid':command+=['--lambda-grid','300']
        result=subprocess.run(command+options,text=True,capture_output=True)
        (args.output_dir/(name+'.log')).write_text(result.stdout+result.stderr)
        if result.returncode!=2 or destination.exists() or (args.output_dir/'no-input').exists():
            raise AssertionError(f'Invalid controls reached artifact creation: {name}, status {result.returncode}')
        cases.append(dict(name=name,options=options,status='EXPECTED_ARGUMENT_REJECTION'))
    if gen.sha(generator)!=source_hash:raise RuntimeError('Generator changed during tests')
    receipt=dict(status='PASS',cases=cases,generator_sha256=source_hash,test_sha256=gen.sha(Path(__file__)),
                 scope='Numerical control range/ordering, including c_int wrapping; no model validation')
    (args.output_dir/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':'PASS','cases':len(cases)}))


if __name__=='__main__':main()
