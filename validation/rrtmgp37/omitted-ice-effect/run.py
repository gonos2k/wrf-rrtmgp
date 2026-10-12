#!/usr/bin/env python3
import argparse,shutil,gzip,hashlib,importlib.util,json,os,sys
from pathlib import Path


def normalize_seed(original,offset):
    return 1+(original+offset-1)%2147483647


def main():
    ap=argparse.ArgumentParser();ap.add_argument('repository',type=Path);ap.add_argument('components',type=Path);ap.add_argument('data',type=Path);ap.add_argument('output',type=Path);ap.add_argument('--seed-offsets',default='0');ap.add_argument('--phases',default='lw,sw');ap.add_argument('--reuse-from',type=Path);args=ap.parse_args()
    root=args.repository.resolve();out=args.output.absolute();out.mkdir(exist_ok=False)
    sys.path.insert(0,str(root/'WRF/test/rrtmgp'))
    from test_netcdf_zz import Runner,pin,write_json
    parent=root/'validation/rrtmgp37/radiation-occurrence-runtime'
    spec=importlib.util.spec_from_file_location('parent',parent/'verify_saved.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
    env=os.environ.copy()
    for name in list(env):
        if name.startswith(('WRF_','LD_DEBUG')):del env[name]
    env['LD_LIBRARY_PATH']='/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps/netcdf/lib'
    env['WRF_RRTMGP_COLUMN_I']='1';env['WRF_RRTMGP_COLUMN_J']='1'
    offsets=[int(x) for x in args.seed_offsets.split(',')]
    phases=args.phases.split(',')
    runner=Runner(out,60,env,4*len(phases)*(len(offsets)*2+(1 if 0 in offsets else 0)))
    plan={'parent_main':'36301782b2372b28f942920d5ab7997801b16e3a','column_input_origin':'PR168 final actual 60s call capture',
          'source_time_seconds':60,'occurrence':1,'existing_CF_and_mask_unchanged':True,'new_ice_SW_delta_scalings':1,
          'new_WRF_processes':0,'public_column_calls_expected':runner.maximum,'seed_offsets':offsets,'phases':phases,'uncertainty_scope':'held-policy sensitivity, not truth or population approval',
          'executables':{n:pin(args.components/'build'/n) for n in ('baseline','diagnostic')},
          'coefficients':{p.name:pin(p) for p in sorted(args.data.glob('rrtmgp-*.nc'))},'production_accepted':False}
    write_json(out/'plan.json',plan)
    for case in ('on-i1-j1','on-i2-j1','on-i1-j2','on-i2-j2'):
        for phase,offset in [(p,s) for p in phases for s in offsets]:
            prefix=out/(case+'-'+phase+'-s'+str(offset));prefix.mkdir()
            original=parent/'saved'/case/'capture'/(phase+'.input.gz')
            capture=gzip.decompress(original.read_bytes());raw=gzip.decompress((original.with_name(phase+'.raw.gz')).read_bytes())
            (_,rr)=v.trace(raw,'raw');(header,_)=v.trace(capture,'input');nl=header[2]
            if offset:
                lines=capture.decode().splitlines(True);h=lines[1].split();h[4]=str(normalize_seed(int(h[4]),offset));lines[1]=' '.join(h)+'\n';capture=''.join(lines).encode()
            (prefix/'input').write_bytes(capture)
            values=rr['IWP_OMITTED']['values']+[0.]*(nl-59)
            (prefix/'ice.sidecar').write_text('CF0_ICE_DIAGNOSTIC_V1\n'+f'{phase.upper()} 1 {nl} 59 1\n'+''.join(f'{k+1} {x:.17e}\n' for k,x in enumerate(values)))
            write_json(prefix/'provenance.json',{'parent_input_sha256':hashlib.sha256(capture).hexdigest(),'parent_raw_sha256':hashlib.sha256(raw).hexdigest(),'sidecar':pin(prefix/'ice.sidecar'),'positive_ice_layers1':[k+1 for k,x in enumerate(values) if x>0]})
            old=args.reuse_from/prefix.name if args.reuse_from else None
            if old and all((old/m/(phase+'.result')).is_file() for m in ('Z','B')):
                # Completed same-source pairs are reused; partial failed prefixes are excluded.
                for m in ('Z','B'):
                    if (old/'input').read_bytes()!=capture:raise ValueError('reused input changed')
                    shutil.copytree(old/m,prefix/m)
                write_json(prefix/'reused.json',{'runtime':str(old),'qualified_pair_reused':True})
                continue
            for mode,exe in ([('A','baseline'),('Z','diagnostic'),('B','diagnostic')] if offset==0 else [('Z','diagnostic'),('B','diagnostic')]):
                run=prefix/mode;run.mkdir()
                env['WRF_RRTMGP_CAPTURE_DIR']=str(run)
                env.pop('WRF_DIAGNOSTIC_ICE_FILE',None);env.pop('WRF_DIAGNOSTIC_ICE_SCALE',None)
                if mode!='A':
                    env['WRF_DIAGNOSTIC_ICE_FILE']=str(prefix/'ice.sidecar');env['WRF_DIAGNOSTIC_ICE_SCALE']='0' if mode=='Z' else '1'
                write_json(run/'launch.json',{'mode':mode,'executable':pin(args.components/'build'/exe),'environment':{k:x for k,x in env.items() if k.startswith(('WRF_','LD_'))},'input':pin(prefix/'input')})
                runner.run([str(args.components/'build'/exe),str(args.data),str(prefix/'input')],run,case+'-'+phase+'-'+mode)
            print(case,phase,offset,'paired RC0',flush=True)
    write_json(out/'execution.json',{'commands':runner.commands,'solver_processes':runner.confirmed_children,'new_WRF_processes':0,'production_accepted':False})

if __name__=='__main__':main()
