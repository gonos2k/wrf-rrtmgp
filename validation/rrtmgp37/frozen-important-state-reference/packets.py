"""Strict numeric parser for the actual selected LW V13 packets."""
import math

def read(data,kind):
 lines=data.decode('ascii').splitlines();magic,header=lines[:2]
 if magic!={'input':'RRTMGP_REPLAY_V13','raw':'RRTMGP_RAW_V1','result':'RRTMGP_RESULT_V1'}[kind]:raise ValueError('unexpected packet version')
 h=header.split();head=[h[0],*map(int,h[1:])]
 if head[0]!='LW':raise ValueError('only selected LW state is in scope')
 records={};pos=2
 while pos<len(lines):
  if not lines[pos].strip():pos+=1;continue
  fields=lines[pos].split();pos+=1;name=fields[0];shape=list(map(int,fields[1:]));n=math.prod(shape)
  if not 1<=len(shape)<=3 or min(shape)<=0 or name in records:raise ValueError('invalid/duplicate section')
  values=[]
  while len(values)<n and pos<len(lines):
   values.extend(float(s.replace('D','E')) for s in lines[pos].split());pos+=1
  if len(values)!=n or not all(math.isfinite(x) for x in values):raise ValueError('invalid value count/nonfinite')
  records[name]={'shape':shape,'values':values}
 return head,records
