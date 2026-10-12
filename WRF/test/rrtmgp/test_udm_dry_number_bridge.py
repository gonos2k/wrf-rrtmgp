#!/usr/bin/env python3
"""Execute the full UDM wrapper with dry-mass storage and native-volume control."""
import argparse,hashlib,importlib.util,json,os,shutil,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True

def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def f32(x):return struct.unpack('!f',struct.pack('!f',x))[0]
def bits(x):return struct.pack('!f',x)
def require(ok,msg):
    if not ok:raise ValueError(msg)

def fixture(raw,case):
    s=raw.decode()
    s=s.replace('integer::step(1,1),top(1,1),a,b,k,iteration','integer::step(1,1),top(1,1),a,b,k,iteration,policy,timestep')
    s=s.replace('character(8)::mode','character(8)::mode,arg')
    s=s.replace('  call get_command_argument(1,mode)','  call get_command_argument(1,mode)\n  call get_command_argument(2,arg)\n  read(arg,*) policy\n  timestep=2')
    # The two runs start from the same eta, and the native control receives the
    # exactly rounded volume value which the policy-1 wrapper will construct.
    s=s.replace('      nn=2.e8; nc=5.e7; nr=0.',
        '      nn=2.e8/den; nc=5.e7/den; nr=0.\n      if(policy==0) then\n        nn=nn*den; nc=nc*den; nr=nr*den\n      endif')
    s=s.replace('itimestep=2,has_reqc=1','itimestep=timestep,has_reqc=1')
    s=s.replace('input_density_is_dry=.true.)','input_density_is_dry=.true.,number_policy=policy)')
    if case in ('dry','cold'):
        s=s.replace('rh=1.+.0048*exp(log(target_alpha)/.6)','rh=.8')
        s=s.replace('qc=1.e-4; qi=0.; qr=0.; qs=0.; qg=0.; qh=0.','qc=0.; qi=0.; qr=0.; qs=0.; qg=0.; qh=0.')
        s=s.replace('nn=2.e8/den; nc=5.e7/den; nr=0.','nn=2.e8/den; nc=0.; nr=0.')
    if case=='cold':
        s=s.replace('timestep=2','timestep=1').replace('ccn_preinitialized=.true.','ccn_preinitialized=.false.')
        s=s.replace('nn=2.e8/den; nc=0.; nr=0.','nn=123.; nc=0.; nr=0.')
    if case=='bounds':
        s=s.replace('rh=1.+.0048*exp(log(target_alpha)/.6)','rh=.8')
        s=s.replace('qc=1.e-4; qi=0.; qr=0.; qs=0.; qg=0.; qh=0.','qc=0.; qi=0.; qr=0.; qs=0.; qg=0.; qh=0.')
        s=s.replace('nn=2.e8/den; nc=5.e7/den; nr=0.','nn=1.e7/den; nc=0.; nr=0.\n      if(b==2) nn=3.e10/den')
    return s.encode()

def compare(native,dry,case):
    require(native['tags']==dry['tags'],'CF/top epoch changed')
    rows=[]
    for c in range(1,5):
        rho=dry['inputs'][(c,1)][12]
        a=native['returns'][c];b=dry['returns'][c]
        require(len(a)==len(b),'return shape')
        for n,(x,y) in enumerate(zip(a,b)):
            expected=f32(x/rho) if 32<=n<44 else x
            require(bits(y)==bits(expected),f'{case} return mismatch case={c} slot={n}')
        for k in range(1,5):
            eta=dry['inputs'][(c,k)][0];nout=b[32+k-1]
            if case=='dry':
                require(abs(nout-eta)<=abs(eta)*2**-23,'no-process eta roundtrip drift')
            if case=='cold':
                require(bits(nout)==bits(f32(2.e8/rho)),'cold constant is not physical-volume constant')
            if case=='bounds' and k<4:
                expected=f32((5.e7 if c%2 else 2.e10)/rho)
                require(bits(nout)==bits(expected),'native-volume entry bound not reflected in eta')
        rows.append({'case':c,'dry_density':rho,'host_NN_return':b[32:36],'host_NC_return':b[36:40],
                     'native_NN_return':a[32:36],'native_NC_return':a[36:40],'native_radius':b[57:61]})
    require(native['observations']==dry['observations'],'bridge changed native process/radius operands')
    return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument('wrf_root',type=Path);ap.add_argument('--workdir',required=True,type=Path);args=ap.parse_args()
    root=args.wrf_root.resolve();work=args.workdir.resolve();work.mkdir(parents=True,exist_ok=False)
    tests=root/'test/rrtmgp';partial=load(tests/'test_udm_partial_activation.py','partial');helper=load(tests/'test_netcdf_zz.py','runner')
    runner=helper.Runner(work,120,{**os.environ,'LC_ALL':'C','OMP_NUM_THREADS':'1'},100)
    compiler=Path(shutil.which('gfortran')).resolve();source=root/'phys/module_mp_udm.F';template=tests/'test_udm_partial_activation.f90'
    raw=source.read_bytes();observed,anchors=partial.observer_snapshot(raw);(work/'observed.F').write_bytes(observed)
    report={'schema':'DRY_NUMBER_GRID_V1_CANDIDATE_TEST','status':'PREPARED','production_accepted':False,
            'source_sha256':hashlib.sha256(raw).hexdigest(),'full_WRF_runs':0,'processes':[],'results':{}}
    def save():report['processes']=runner.commands;helper.write_json(work/'receipt.json',report)
    save()
    try:
        runner.run([compiler,'--version'],work,'compiler_version')
        for opt in ('O0','O2'):
            d=work/opt;d.mkdir();flags=['-'+opt,'-g','-ffree-form','-ffree-line-length-none','-fcheck=all','-finit-real=snan','-ffpe-trap=invalid,zero,overflow','-J',str(d),'-I',str(d)]
            stub=d/'errors.f90';stub.write_text('module module_wrf_error\ncontains\nsubroutine wrf_debug(level,text)\ninteger,intent(in)::level\ncharacter(*),intent(in)::text\nend subroutine\nend module\nsubroutine wrf_error_fatal(text)\ncharacter(*),intent(in)::text\nprint *,text\nerror stop 2\nend subroutine\n')
            fixtures={}
            for case in ('wet','dry','cold','bounds'):
                p=d/(case+'.f90');p.write_bytes(fixture(template.read_bytes(),case));fixtures[case]=p
            objects=[]
            for path,extra in [(root/'phys/module_gfs_machine.F',['-ffixed-form']),(stub,[]),(root/'phys/module_mp_radar.F',[]),(fixtures['wet'],['-cpp','-DOBSERVER_ONLY']),(work/'observed.F',[])]:
                obj=d/(path.stem+'.o');runner.run([compiler,*flags,*extra,'-c',path,'-o',obj],d,'compile');objects.append(obj)
            results={}
            for case,fixturepath in fixtures.items():
                exe=d/case;runner.run([compiler,*flags,'-cpp',fixturepath,*objects,'-o',exe],d,'link')
                data={}
                for policy in (0,1):
                    output=runner.run([exe,'on',str(policy)],d,'actual_UDM_'+case+'_policy'+str(policy));data[policy]=partial.parse(output.read_text())
                    data[policy]['returns']={c:[struct.unpack('!f',bytes.fromhex(x))[0] for x in values] for c,values in data[policy]['outputs'].items()}
                rows=compare(data[0],data[1],case)
                if case=='wet':
                    evidence=partial.check(data[0]);require(len(evidence)==12,'partial CF/activation row count')
                results[case]={'paired_control_exact':True,'rows':rows,'process_evidence':'same native stage/CF/activation/radius observations',
                               'partial_CF_partial_activation_caps_inactive':case=='wet'}
            report['results'][opt]=results;save()
        require(source.read_bytes()==raw,'source changed during test')
        report.update(status='PASS_SCOPED_DRY_NUMBER_BRIDGE',manufactured_pairs=32,UDM_calls=64,
                      limits=['Manufactured module calls, not independently observed atmospheric PSD/population.',
                              'Two dry densities, partial CF/activation, dry no-process, cold physical background, entry bounds.',
                              'Native-volume control demonstrates boundary/process/radius equivalence; optical physics remains open.'])
        save();print(json.dumps({'status':report['status'],'receipt':str(work/'receipt.json')}));return 0
    except BaseException as e:
        report.update(status='FAIL_PRESERVED',error=repr(e));save();raise
if __name__=='__main__':raise SystemExit(main())
