"""Portable same-support comparison of actual retained fields and PR191 sources."""
import hashlib,math,struct

def require(x,m):
 if not x:raise ValueError(m)
def analyze(raw,meta,prior):
 require(hashlib.sha256(raw).hexdigest()==meta['sha256'],'spatial payload hash')
 nx=meta['nx'];ny=meta['ny'];n=nx*ny;require((nx,ny)==(90,99),'native physical precipitation grid')
 a=struct.unpack_from('<'+str(n)+'d',raw);pos=8*n;require(all(math.isfinite(x) and x>0 for x in a),'area data')
 area=prior['area_m2'];fields={}
 # Native Fortran sequential SUM and Python fsum need not accumulate the 8910
 # positive cell areas identically. This is an arithmetic check, not a budget tolerance.
 require(abs(math.fsum(a)-area)<=n*math.ulp(area),'whole physical area normalization')
 require(meta['times']==['2016-10-06_05:59:00','2016-10-06_06:00:00','2016-10-06_06:01:00','2016-10-06_06:02:00'],'original precipitation times')
 require(meta['fields']==['RAINC','RAINNC','RAINSH'],'precipitation counter inventory')
 for t in meta['times']:
  fields[t]={}
  for name in meta['fields']:
   b=raw[pos:pos+4*n];pos+=4*n;require(hashlib.sha256(b).hexdigest()==meta['field_sha256'][t][name],'precipitation field hash')
   values=struct.unpack('<'+str(n)+'f',b);require(all(math.isfinite(v) for v in values),'nonfinite precipitation')
   fields[t][name]=values
 require(pos==len(raw),'unindexed precipitation bytes')
 inner=[j*nx+i for j in range(1,ny-1) for i in range(1,nx-1)];inner_set=set(inner);outer=[i for i in range(n) if i not in inner_set]
 rows=[]
 for it,old in enumerate(prior['water_steps']):
  t0,t1=meta['times'][it:it+2];out={}
  for name in meta['fields']:
   x=[a[i]*(fields[t1][name][i]-fields[t0][name][i]) for i in range(n)]
   allv=math.fsum(x)/area;ins=math.fsum(x[i] for i in inner)/area;outs=math.fsum(x[i] for i in outer)/area
   require(math.isclose(ins+outs,allv,rel_tol=2e-14,abs_tol=1e-18),'whole-area normalization identity')
   out[name]={'all_domain_mean_kg_m2':allv,'interior_contribution_kg_m2':ins,'outer_contribution_kg_m2':outs}
  pc=out['RAINC'];pn=out['RAINNC'];ps=out['RAINSH']
  f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
  rc0=fields[t0]['RAINC'];rc1=fields[t1]['RAINC'];rn0=fields[t0]['RAINNC'];rn1=fields[t1]['RAINNC']
  # PR191 reduced REAL32(RAINC+RAINNC) at each operator boundary.
  before=math.fsum(a[i]*(f32(rc1[i]+rn0[i])-f32(rc0[i]+rn0[i])) for i in range(n))/area
  during=math.fsum(a[i]*(f32(rc1[i]+rn1[i])-f32(rc1[i]+rn0[i])) for i in range(n))/area
  require(abs(before-old['P_before_microphysics'])<1e-12,'pre-microphysics counter cannot be reconstructed from native sum')
  require(abs(during-old['P_during_microphysics'])<1e-12,'microphysics counter cannot be reconstructed from native sum')
  evaluation_difference=old['P_before_microphysics']-pc['all_domain_mean_kg_m2']
  require(ps['all_domain_mean_kg_m2']==0,'unexpected shallow precipitation')
  cu=old['cumulus_applied_tendency_integral'];res=cu+pc['interior_contribution_kg_m2'];outerp=pc['outer_contribution_kg_m2']
  require(abs(res+outerp+evaluation_difference-old['cumulus_plus_its_P'])<1e-12,'CU spatial decomposition identity')
  rows.append({'source_time_s':old['source_time_s'],'start':t0,'end':t1,'precipitation':out,'actual_CU_moisture_increment_kg_m2':cu,'CU_plus_full_precipitation_kg_m2':old['cumulus_plus_its_P'],'CU_plus_interior_precipitation_kg_m2':res,'outer_precipitation_kept_separately_kg_m2':outerp,'native_sum_evaluation_difference_kg_m2':evaluation_difference,'native_before_microphysics_counter_reconstructed_kg_m2':before,'native_during_microphysics_counter_reconstructed_kg_m2':during})
 return {'status':'SAME_SUPPORT_CU_COMPARISON_COMPLETE','normalization':'every component uses the same original whole physical-domain area, including interior/outer contributions','area_m2':area,'steps':rows,'sum_interior_CU_residual_kg_m2':math.fsum(r['CU_plus_interior_precipitation_kg_m2'] for r in rows),'sum_outer_precipitation_kg_m2':math.fsum(r['outer_precipitation_kept_separately_kg_m2'] for r in rows),'finding':'Outer precipitation explains only part of the old CU residual. Increasing interior residual requires the actual tendency/precipitation time contract; not a production defect declaration.','water_conservation_approved':False,'new_model_runs':0}
if __name__=='__main__':
 from pathlib import Path
 import json
 p=Path(__file__).resolve();R=p.parents[3];B=R.parent;O=B/'udm37-convective-support-analysis-v1'
 d=analyze((O/'rain-spatial.bin').read_bytes(),json.loads((O/'rain-spatial.json').read_text()),json.loads((R/'validation/rrtmgp37/real-case-budget/result.json').read_text()))
 (O/'spatial-result.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
