#!/usr/bin/env python3
"""Failure tests for generated table/receipt consistency; preserve each case."""
import argparse
import copy
import json
from pathlib import Path
import shutil

from netCDF4 import Dataset
import compare
import generate as gen


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    if args.output_dir.exists():parser.error('Use a new output directory')
    args.output_dir.mkdir(parents=True)
    compare.load(args.generation)
    original=json.loads((args.generation/'result.json').read_text())
    cases=[]
    for name in ('table-hash','status','lambda-axis','temperature-axis','missing-row','duplicate-row',
                 'task-index','task-values','negative-moment','nonfinite-moment','wrong-units',
                 'closure','workspace','pruning','bounds','generator-source','kernel-source','input-source','adaptation-source',
                 'local-library','local-adaptation','order-control','order-bool','step-control','workspace-control',
                 'workers-control','chunk-control','flags-control','quadrature-control','pruning-control'):
        directory=args.output_dir/name; directory.mkdir()
        table=directory/'frozen-ice-psd-moments.nc'
        shutil.copyfile(args.generation/'frozen-ice-psd-moments.nc',table)
        receipt=copy.deepcopy(original)
        if name=='table-hash': receipt['table_sha256']='0'*64
        elif name=='generator-source':receipt['generator_sha256']='0'*64
        elif name=='kernel-source':receipt['kernel_source_sha256'][next(iter(receipt['kernel_source_sha256']))]='0'*64
        elif name=='input-source':receipt['input_sources'][next(iter(receipt['input_sources']))]['sha256']='0'*64
        elif name=='adaptation-source':receipt['kernel_source_adaptation']['compiled_mie_sha256']='0'*64
        elif name=='order-control':receipt['order']=513
        elif name=='order-bool':receipt['order']=True
        elif name=='step-control':receipt['max_spectral_step_cm_inv']=float('nan')
        elif name=='workspace-control':receipt['max_terms']=2**32
        elif name=='workers-control':receipt['workers']=0
        elif name=='chunk-control':receipt['spectral_chunk_size']=0
        elif name=='flags-control':receipt['kernel_flags']=['-ffast-math']
        elif name=='quadrature-control':receipt['quadrature_algorithm']='unknown'
        elif name=='pruning-control':receipt['quadrature_area_weight_pruning_threshold']=.01
        elif name=='local-library':
            (directory/'kernel').mkdir();(directory/'kernel/libmie_dynamic.so').write_bytes(b'corrupted library')
        elif name=='local-adaptation':
            (directory/'kernel').mkdir();(directory/'kernel/source-adaptation.json').write_text('{}\n')
        elif name=='status':receipt['status']='PARTIAL'
        elif name=='lambda-axis':receipt['lambda_grid_m_inv'][0]*=2
        elif name=='temperature-axis':receipt['temperatures_K'][0]+=1
        elif name=='missing-row':receipt['rows'].pop()
        elif name=='duplicate-row':receipt['rows'].append(receipt['rows'][0])
        elif name=='task-index':receipt['rows'][0]['band']=999
        elif name=='task-values':receipt['rows'][0]['moments'][0][0]+=1
        elif name=='workspace':receipt['rows'][0]['needed_terms_max']=receipt['max_terms']+1
        elif name=='pruning':receipt['rows'][0]['dropped_mass_weight_fraction']=.01
        else:
            with Dataset(table,'a') as nc:
                if name=='wrong-units': nc['lambda'].units='micron'
                elif name=='bounds': nc['sw_bounds'][0,0]+=1
                elif name=='negative-moment':nc['sw_absorption_times_density'][0,0]=-1
                elif name=='nonfinite-moment':nc['lw_scattering_times_density'][0,0,0]=float('nan')
                elif name=='closure':nc['sw_extinction_times_density'][0,0]*=2
            receipt['table_sha256']=gen.sha(table)
        (directory/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
        try: compare.load(directory)
        except (ValueError,KeyError,IndexError,TypeError) as exc:
            cases.append(dict(name=name,status='EXPECTED_REJECTION',reason=str(exc)))
        else:raise AssertionError(f'Accepted invalid table/receipt: {name}')
    result=dict(status='PASS',valid_generation_receipt_sha256=gen.sha(args.generation/'result.json'),
                validator_sha256=gen.sha(gen.HERE/'compare.py'),test_sha256=gen.sha(Path(__file__)),cases=cases,
                scope='Artifact schema and receipt identities, not material/optical model accuracy')
    (args.output_dir/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':'PASS','expected_rejections':len(cases)}))


if __name__=='__main__':main()
