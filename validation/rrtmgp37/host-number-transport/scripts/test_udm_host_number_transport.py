#!/usr/bin/env python3
"""Verbatim native advection/RK slices, manufactured periodic FV ledger.

This is not a full-module build, WRF host trajectory or UDM unit authority.
No production number, density, cloud fraction or radius policy is changed.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import sys
sys.dont_write_bytecode=True
HELPER=Path(__file__).with_name('test_netcdf_zz.py')
spec=importlib.util.spec_from_file_location('host_durable_runner',HELPER)
runner_module=importlib.util.module_from_spec(spec); spec.loader.exec_module(runner_module)
pin,write_json,Runner=runner_module.pin,runner_module.write_json,runner_module.Runner

def require(condition,message):
    if not condition: raise ValueError(message)

def r32(value):
    return struct.unpack('!f',struct.pack('!f',value))[0]

def extract(source,name):
    text=source.read_text()
    start=list(re.finditer(r'^[ \t]*SUBROUTINE\s+'+name+r'\s*\(',text,re.M|re.I))
    end=list(re.finditer(r'^[ \t]*END SUBROUTINE\s+'+name+r'[ \t]*$',text,re.M|re.I))
    require(len(start)==len(end)==1 and start[0].start()<end[0].start(),'ambiguous native procedure: '+name)
    a,b=start[0].start(),end[0].end()
    data=text[a:b]+'\n'
    return data,{'source':pin(source),'procedure':name,'first_line':text[:a].count('\n')+1,
                 'last_line':text[:b].count('\n')+1,'slice_sha256':hashlib.sha256(data.encode()).hexdigest()}

ADAPTER='''module host_scalar_procedures
implicit none
type grid_config_rec_type
 logical::nested=.false.,specified=.false.,periodic_x=.false.,periodic_y=.false.
 logical::symmetric_xs=.false.,symmetric_xe=.false.,symmetric_ys=.false.,symmetric_ye=.false.
 logical::open_xs=.false.,open_xe=.false.,open_ys=.false.,open_ye=.false.,polar=.false.
 integer::rk_ord=3,h_sca_adv_order=2,v_sca_adv_order=2
end type
character(1024)::wrf_err_message
contains
subroutine wrf_error_fatal(message)
character(*),intent(in)::message
print *,message
error stop 1
end subroutine
'''

def parse(text):
    lines=iter(text.splitlines()); cells={}; boundaries={}; counts=None
    for line in lines:
        words=line.split()
        if not words:continue
        if words[0]=='CALLS':
            require(counts is None and len(words)==5,'invalid call count');counts=list(map(int,words[1:]));continue
        require((words[0]=='CELL' and len(words)==7) or (words[0]=='BOUNDARY' and len(words)==5),'unexpected output')
        key=tuple(map(int,words[1:]));bits=next(lines).split()
        records=cells if words[0]=='CELL' else boundaries
        require(key not in records and len(bits)==(23 if words[0]=='CELL' else 6) and all(re.fullmatch('[0-9A-F]{8}',v) for v in bits),'invalid cell record')
        values=[struct.unpack('!f',bytes.fromhex(v))[0] for v in bits]
        require(all(map(math.isfinite,values)),'nonfinite cell')
        records[key]=values
    require(counts==[32,32,32,6],'procedure call roster differs')
    return {'cells':cells,'boundaries':boundaries,'counts':counts}

def check(data):
    cells=data['cells']
    roster={(c,s,n,i,k,j) for c in range(1,9) for s in (1,3) for n in (1,2)
            for i in range(1,5) for k in range(1,3) for j in range(1,4)}
    require(set(cells)==roster,'cell roster differs')
    broster={(b,i,k,j) for b in range(1,7) for i in range(0,6) for k in range(0,4) for j in range(0,5)}
    require(set(data['boundaries'])==broster,'boundary storage roster differs')
    initial=lambda i,k,j:r32(1.e6*(i+8*k+32*j))
    for (b,i,k,j),v in data['boundaries'].items():
        before,u,velocity,ccn,out,periodic=v;mode=(b-1)%3-1;px=(b-1)//3
        require(before==initial(i,k,j) and u==velocity==mode and ccn==1.e8 and periodic==px,'boundary input arm differs')
        expected=before
        if 1<=k<=2 and 1<=i<=4 and 1<=j<=3:
            inner=i if px else min(max(i,2),3)
            if j==1:expected=initial(inner,k,2) if mode<0 else ccn
            elif j==3:expected=initial(inner,k,2) if mode>0 else ccn
            elif not px and i==1:expected=initial(2,k,2) if mode<0 else ccn
            elif not px and i==4:expected=initial(3,k,2) if mode>0 else ccn
        require(out==expected,'boundary direct inflow/copy/untouched contract differs')
    budgets=[]
    def close(a,b,label):
        require(math.isclose(a,b,rel_tol=3e-7,abs_tol=.1),label)
    for (c,s,n,i,k,j),v in cells.items():
        dt,dnw,g,c1,c2,mx,my,mu0,mub,mu1,left,right,qleft,q,qright,adv,out,time_t,ah,az,source,pd,cleared=v
        arm=(c-1)//4;pattern=((c-1)//2)%2;geometry=(c-1)%2
        require(dt==.25 and dnw==-.5 and math.isclose(g,9.81,rel_tol=1e-7),'ledger constants differ')
        require(c1==(.5 if geometry and k==2 else 1.) and c2==(4096. if geometry and k==2 else 0.),'hybrid arm differs')
        require(mx==(1.+.125*(i-1) if geometry else 1.) and my==(.75+.0625*j if geometry else 1.),'map arm differs')
        require(mu0==0. and mub==65536.+32768.*arm,'mass arm differs')
        faces=[1024.,2304.,768.,1536.,1024.]
        require(left==c1*faces[i-1]+c2*.125 and right==c1*faces[i]+c2*.125,'mass face differs')
        close(mu1,-dt*mx*my*(faces[i]-faces[i-1]),'dry mass continuity differs')
        target=lambda ii:r32((1.e8/n)*(1.+.125*ii+.0625*j+.03125*k if pattern else 1.))
        require(q==target(i) and qleft==target((i-2)%4+1) and qright==target(i%4+1),'periodic input differs')
        # Independent FV face ledger, not the source statement functions.
        inflow=left*(qleft+q)/2.;outflow=right*(q+qright)/2.
        close(adv,-mx*(outflow-inflow),'advection flux differs')
        m0=c1*(mu0+mub)+c2;m1=c1*(mu1+mub)+c2
        close(out,(m0*q+dt*my*adv)/m1,'RK mass-coupled update differs')
        require(time_t==q,'time-t buffer differs')
        close(ah,dt*my*adv/m1 if s==3 else 0.,'RK diagnostic differs')
        require(az==0. and cleared==0.,'vertical diagnostic or consumed source differs')
        close(source,.01*m1*q,'prescribed source differs')
        close(pd,out+dt*source/m1,'source update differs')
    for c in range(1,9):
      for s in (1,3):
       for n in (1,2):
        before=after=allowed=post=raw0=raw1=0.
        for key,v in cells.items():
            if key[:3]!=(c,s,n):continue
            dt,dnw,g,c1,c2,mx,my,mu0,mub,mu1,_,_,_,q,_,_,out,_,_,_,source,pd,_=v
            area=1./(mx*my);coefficient=area*(-dnw)/g
            before+=coefficient*(c1*(mu0+mub)+c2)*q
            after+=coefficient*(c1*(mu1+mub)+c2)*out
            allowed+=coefficient*dt*source
            post+=coefficient*(c1*(mu1+mub)+c2)*pd
            raw0+=q;raw1+=out
        require(abs(after-before)/before<1.5e-7,'periodic mass-weighted conservation differs')
        require(abs(post-after-allowed)/before<1.5e-7,'prescribed source ledger differs')
        if ((c-1)//2)%2:
            require(abs(raw1-raw0)/raw0>1.e-6,'patterned raw-sum discriminator missing')
        else:
            require(all(math.isclose(v[16],v[13],rel_tol=2e-7) for key,v in cells.items() if key[:3]==(c,s,n)),
                    'uniform scalar not preserved')
        budgets.append({'case':c,'rk_stage':s,'population_slot':n,'weighted_before':before,'weighted_after':after,
                        'relative_closure':abs(after-before)/before,'raw_sum_relative_change':(raw1-raw0)/raw0,
                        'prescribed_source_total':allowed,'post_source_total':post})
    return budgets

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('wrf_root',type=Path)
    ap.add_argument('--workdir',required=True,type=Path);ap.add_argument('--compiler',default='gfortran');args=ap.parse_args()
    wrf=args.wrf_root.resolve(strict=True);work=args.workdir.resolve();work.mkdir(parents=True,exist_ok=False)
    compiler=Path(shutil.which(args.compiler) or args.compiler).resolve(strict=True)
    fixture=Path(__file__).with_suffix('.f90').resolve()
    sources=[wrf/'dyn_em/module_advect_em.F',wrf/'dyn_em/module_em.F',wrf/'dyn_em/solve_em.F',
             wrf/'share/module_bc.F',wrf/'phys/module_microphysics_driver.F',wrf/'Registry/Registry.EM_COMMON',
             wrf/'phys/module_mp_udm.F',wrf/'dyn_em/start_em.F',wrf/'dyn_em/module_initialize_real.F',
             wrf/'dyn_em/module_first_rk_step_part1.F',
             Path(__file__).resolve(),fixture,HELPER.resolve()]
    before=[pin(p) for p in sources];result=work/'receipt.json'
    report={'schema':'HOST_NUMBER_TRANSPORT_V1','status':'PREPARED','source_pins_before':before,
            'scientific_acceptance':False,'remaining_physical_gates':7,'full_WRF_builds':0,'WRF_host_runs':0,
            'full_module_builds':0,'UDM_calls':0,'RTE_runs':0,'compiler':pin(compiler)}
    write_json(result,report);runner=Runner(work,120,{**os.environ,'LC_ALL':'C','OMP_NUM_THREADS':'1'},8)
    try:
        pieces=[];slices=[]
        for path,name in ((sources[0],'advect_scalar'),(sources[1],'rk_update_scalar'),(sources[1],'rk_update_scalar_pd'),
                          (sources[3],'flow_dep_bdy_qnn')):
            data,record=extract(path,name);pieces.append(data);slices.append(record)
        generated=work/'native-scalar-slices.f90';generated.write_text(ADAPTER+'\n'.join(pieces)+'\nend module\n')
        report['native_slices']=slices;report['generated_source']=pin(generated)
        report['compiler_version']=runner.run([compiler,'--version'],work,'compiler_version').read_text()
        results={};exe_pins=[]
        for opt in ('O0','O2'):
            directory=work/opt;directory.mkdir();exe=directory/'fixture'
            runner.run([compiler,'-'+opt,'-g','-ffree-form','-ffree-line-length-none','-fcheck=all',
                        '-finit-real=snan','-ffpe-trap=invalid,zero,overflow','-J',directory,generated,fixture,'-o',exe],directory,'compile_link')
            exe_pins.append(pin(exe));output=runner.run([exe],directory,'native_scalar_fixture')
            parsed=parse(output.read_text());budgets=check(parsed);negatives={}
            for label in ('missing-cell','wrong-map','wrong-mass','wrong-number','uncleared-source','wrong-inflow'):
                changed=copy.deepcopy(parsed);key=(8,3,2,2,2,2)
                if label=='missing-cell':del changed['cells'][key]
                elif label=='wrong-inflow':changed['boundaries'][(2,1,1,1)][4]*=.7
                else:changed['cells'][key][{'wrong-map':6,'wrong-mass':9,'wrong-number':16,'uncleared-source':22}[label]]+=12345.
                try:check(changed)
                except ValueError as error:negatives[label]=str(error)
                else:raise ValueError('negative control accepted: '+label)
            results[opt]={'cell_records':len(parsed['cells']),'boundary_storage_records':len(parsed['boundaries']),
                          'procedure_calls':parsed['counts'],
                          'budgets':budgets,'negative_controls_rejected':negatives}
        require([pin(p) for p in sources]==before,'native inputs changed')
        report.update(status='PASS_SCOPED_NATIVE_SCALAR_TRANSPORT',source_pins_after=before,results=results,
                      processes=runner.commands,executable_pins=exe_pins,
                      limits=['Four verbatim procedures with minimal config/type/shape adapter; not full modules or a WRF host run.',
                              'Order-2 horizontal periodic manufactured fluxes; vertical flux zero, manual periodic halos.',
                              'Two generic scalar slots, not Registry-managed QNN/QNC initialization or UDM routing.',
                              'Stages 1/3 checked separately with identical prescribed input, not a full RK trajectory.',
                              'Source update consumes prescribed mass-coupled tendency; PD advection limiter not executed.',
                              'Boundary inflow/outflow/zero velocity and periodic-x suppression are isolated; no complete lateral boundary host trajectory.',
                              'Mass-coupled transport behavior does not decide intended UDM stored units or population.',
                              'No microphysics, radius, optics, forecast, EOS/balanced atmospheric column or MPI.'])
        write_json(result,report);print(json.dumps({'status':report['status'],'receipt':pin(result)}));return 0
    except BaseException as error:
        report.update(status='FAIL_PRESERVED_STOPPED',error=f'{type(error).__name__}: {error}',processes=runner.commands)
        write_json(result,report);print(json.dumps({'status':report['status'],'error':report['error']}));return 1

if __name__=='__main__':sys.exit(main())
