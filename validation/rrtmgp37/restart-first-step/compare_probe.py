#!/usr/bin/env python3
from pathlib import Path
import numpy as np,struct,json
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-restart-first-probe-run-v1'
def read(p):
 b=p.read_bytes();at=0;out={}
 while at<len(b):
  n,*shape=struct.unpack_from('<32s3i',b,at);at+=44;n=n.rstrip(b' ').decode();count=int(np.prod(shape));out[n]=np.frombuffer(b,dtype='<f4',count=count,offset=at).reshape(shape,order='F').copy();at+=count*4
 assert at==len(b)
 return out
def valid(n,x):
 if n.endswith(('_bye','_btye')):return x[:,:45 if n.startswith(('ph_','w_')) else 44,:]
 if x.shape[2]==1:return x[:,:8 if n not in ['muv','muvs'] else 9,:]
 kk=45 if n in ['w_1','w_2','ph_1','ph_2','phb','rw','ww','ww_m','rw_tend','rw_tendf','ph_tend','ph_tendf','w_save','ph_save'] else 44
 jj=9 if n in ['v_1','v_2','rv','rv_tend','rv_tendf'] else 8
 return x[:,:kk,:jj]
def main():
 stage=['entry','rk_prep','pre_physics','physics_part1','physics_part2','rk_tend','dry_boundaries','small_prep','acoustic_end','small_finish','rk_end'];rows=[]
 files=list((O/'restart').glob('probe-*.bin'))
 files.sort(key=lambda p:(int(p.name.split('-')[1]),int(p.name.split('-')[2][1:]),stage.index(p.stem.split('-',4)[4]),int(p.name.split('-')[3][1:])))
 for a in files:
  b=O/'continuous'/a.name
  if not b.exists():continue
  x=read(b);y=read(a);assert x.keys()==y.keys();diffs={}
  for n in x:
   xx=valid(n,x[n]);yy=valid(n,y[n]);mask=xx.view('u4')!=yy.view('u4')
   if mask.any():
    ii=tuple(map(int,np.argwhere(mask)[0]));finite=np.isfinite(xx)&np.isfinite(yy)
    delta=np.where(finite,np.abs(xx.astype('f8')-yy.astype('f8')),0.);im=tuple(map(int,np.unravel_index(np.argmax(delta),xx.shape)))
    diffs[n]={'count':int(mask.sum()),'first_index':ii,'first_continuous':float(xx[ii]),'first_restart':float(yy[ii]),'continuous_bits':hex(int(xx.view('u4')[ii])),'restart_bits':hex(int(yy.view('u4')[ii])),'max_abs':float(delta[im]),'max_index':im}
  rows.append({'file':a.name,'differences':diffs})
  print(a.stem,','.join(diffs))
 (O/'stage-differences.json').write_text(json.dumps(rows,indent=2)+'\n')
if __name__=='__main__':main()
