#!/usr/bin/env python3
"""Replay the first real divergence in the retained native calc_ww_cp kernel."""
from pathlib import Path
import json,struct,importlib.util,shlex,os
import numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-restart-first-ww-v2';O.mkdir(exist_ok=False)
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
def read(p):
 raw=p.read_bytes();pos=0;out={}
 while pos<len(raw):
  key,*sh=struct.unpack_from('<32s3i',raw,pos);pos+=44;count=int(np.prod(sh));out[key.rstrip().decode()]=np.frombuffer(raw,dtype='<f4',count=count,offset=pos).reshape(sh,order='F');pos+=count*4
 return out
seed=B/'udm37-restart-first-probe-run-v1';entry=[read(seed/a/'probe-021540-r0-a00-entry.bin') for a in ['continuous','restart']];after=[read(seed/a/'probe-021540-r1-a00-rk_prep.bin') for a in ['continuous','restart']]
cp=B/'udm37-specified-number-run-v2/continuous/wrfrst_d01_2016-10-06_05:59:00'
with Dataset(cp) as d:
 def mapx(name,stagger=False):
  x=np.asarray(d[name][0]);rows=x[91:100,18:27]
  if rows.shape[0]==8:rows=np.concatenate([rows,rows[-1:]],axis=0)
  assert rows.shape==(9,9);return rows.T
 geometry=[mapx('MAPFAC_MX'),mapx('MAPFAC_MY'),mapx('MAPFAC_UY'),mapx('MF_VX_INV')]
 vertical=[]
 for n in ['C1H','C2H','DNW']:
  x=np.asarray(d[n][0]);assert len(x)==44;vertical.append(np.r_[x,np.float32(0)])
 rdx=np.float32(d['RDX'][0]);rdy=np.float32(d['RDY'][0])
 arrays=[entry[0]['u_2'],entry[0]['v_2'],entry[0]['mu_2'][:,:,0],entry[1]['mu_2'][:,:,0],entry[0]['mub'][:,:,0],*geometry,*vertical,np.asarray([rdx,rdy]),*[x['ww'][4,:,7] for x in after]]
 with (O/'inputs.bin').open('wb') as f:
  for a in arrays:f.write(np.asarray(a,dtype='<f4').tobytes(order='F'))
source='''program native_first_ww
 use module_big_step_utilities_em, only: calc_ww_cp
 use module_bc, only: set_physical_bc2d
 use module_configure, only: grid_config_rec_type
 implicit none
 type(grid_config_rec_type)::cfg
 real::u(19:27,1:45,92:103),v(19:27,1:45,92:103)
 real::mc(19:27,92:103),mr(19:27,92:103),mf(19:27,92:103),mb(19:27,92:103)
 real::mx(19:27,92:103),my(19:27,92:103),uy(19:27,92:103),vi(19:27,92:103)
 real::c1(45),c2(45),dn(45),rdx,rdy,wc(45),wr(45)
 real::w(19:27,1:45,92:103),mass
 integer::n,k,unit
 open(newunit=unit,file='inputs.bin',access='stream',form='unformatted',convert='little_endian')
 read(unit)u(:,:,92:100),v(:,:,92:100),mc(:,92:100),mr(:,92:100),mb(:,92:100), &
 mx(:,92:100),my(:,92:100),uy(:,92:100),vi(:,92:100),c1,c2,dn,rdx,rdy,wc,wr
 close(unit)
 cfg%specified=.true.;cfg%nested=.false.;cfg%periodic_x=.false.;cfg%periodic_y=.false.
 cfg%symmetric_xs=.false.;cfg%symmetric_xe=.false.;cfg%symmetric_ys=.false.;cfg%symmetric_ye=.false.
 cfg%open_xs=.false.;cfg%open_xe=.false.;cfg%open_ys=.false.;cfg%open_ye=.false.;cfg%polar=.false.
 mf=mc
 call set_physical_bc2d(mf,'t',cfg,1,91,1,100,19,27,92,103,19,27,92,100,23,23,99,100)
 if(any(transfer(mc(:,92:99),[0],72)/=transfer(mf(:,92:99),[0],72)))error stop 'physical mass changed'
 do n=1,3
  if(n==1)mf=mc
  if(n==2)mf=mr
  if(n==3)then
   mf=mc
   call set_physical_bc2d(mf,'t',cfg,1,91,1,100,19,27,92,103,19,27,92,100,23,23,99,100)
  endif
  mass=.5*(mf(23,100)+mb(23,100)+mf(23,99)+mb(23,99))
  call calc_ww_cp(u,v,mf,mb,c1,c2,w,rdx,rdy,mx,my,uy,uy,uy,vi,uy,dn, &
                 1,91,1,100,1,45,19,27,92,103,1,45,23,23,99,99,1,45)
  if(n==1.and.any(transfer(w(23,:,99),[0],45)/=transfer(wc,[0],45)))error stop 'continuous WW replay differs'
  if(n>=2.and.any(transfer(w(23,:,99),[0],45)/=transfer(wr,[0],45)))error stop 'restart/repaired WW replay differs'
  write(*,'(A,I1,1X,Z8.8)')'MUV ',n,transfer(mass,0)
  do k=1,45
   write(*,'(A,2I3,1X,Z8.8)')'WW ',n,k,transfer(w(23,k,99),0)
  enddo
 enddo
 print *,'ACTUAL_FIRST_WW_REPLAY_COMPLETE'
end program
''';(O/'replay.f90').write_text(source)
base=B/'udm37-specified-number-build-v1';rec=json.loads((base/'receipt.json').read_text());opts=[x for x in rec['commands'][3]['argv'][1:-4] if not x.startswith('-J')]+['-J'+str(O)]
link=rec['commands'][-1]['argv'];libs=link[link.index('-Wl,--start-group')+1:link.index('-Wl,--end-group')]
r=h.Runner(O,180,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib')},4)
r.run(['gfortran',*opts,'-c',O/'replay.f90','-o',O/'replay.o'],O,'compile_real_stencil_replay');r.run(['gfortran','-o',O/'replay',O/'replay.o','-Wl,--start-group',*libs,'-Wl,--end-group'],O,'link_real_stencil_replay')
log=r.run([O/'replay'],O,'consume_actual_first_difference').read_text();assert 'ACTUAL_FIRST_WW_REPLAY_COMPLETE' in log
h.write_json(O/'receipt.json',{'commands':r.commands,'inputs':h.pin(O/'inputs.bin'),'fixture':h.pin(O/'replay.f90'),'library':h.pin(base/'libWRF_Core.a'),'output':h.pin(O/'command-03.stdout'),'production_accepted':False});print('ACTUAL_FIRST_WW_REPRODUCED_AND_REPAIRED_WITHOUT_CHANGING_PHYSICAL_MU')
