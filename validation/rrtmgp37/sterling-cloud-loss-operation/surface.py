"""Re-use native hour support and the original independent observation convention."""
import importlib.util,datetime as dt,math
from pathlib import Path
from analyze import require,f32
P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('interior_analysis',P.parent/'sterling-interior-day-evaluation/analyze.py');A=importlib.util.module_from_spec(s);s.loader.exec_module(A)
def evaluate(ex,blobs,old):
 sf=ex['surface'];v=sf['values'];orig=ex['original'];require(sf['selected_j_i_zero_based']==[118,36],'wrong new grid point')
 expected=[(dt.datetime(2016,10,6,17)+dt.timedelta(minutes=m)).strftime('%Y-%m-%d_%H:%M:%S') for m in range(121)]
 require(sf['times_utc']==expected and all(len(x)==121 and all(math.isfinite(y) for y in x) for x in v.values()),'native surface time/finite support')
 for m in range(1,121):
  for flux,acc in [('SWDNB','ACSWDNB'),('SWDNBC','ACSWDNBC')]:require(f32(v[acc][m-1]+f32(60*v[flux][m]))==v[acc][m],'native applied accumulator replay')
  require(v['SWDDIF'][m]==f32(v['SWDNB'][m]-v['SWDDIR'][m]),'native unscaled horizontal direct/diffuse definition')
 result=[]
 for h,start in [(17,0),(18,60)]:
  end=start+60
  for name in ['ACSWDNB','ACSWDNBC']:require(v[name][start]==orig[name+'_J_m2'][h] and v[name][end]==orig[name+'_J_m2'][h+1],'different cold/hour endpoint')
  mean=lambda n:math.fsum(v[n][start+1:end+1])/60
  model={n:mean(n) for n in ['SWDNB','SWDNBC','SWDDIR','SWDDIRC','SWDDIF','SWDDNI']}
  model['diffuse_fraction']=model['SWDDIF']/model['SWDNB'];model['all_minus_clear']=model['SWDNB']-model['SWDNBC']
  model['accumulator_allsky_W_m2']=(v['ACSWDNB'][end]-v['ACSWDNB'][start])/3600
  model['accumulator_clearsky_W_m2']=(v['ACSWDNBC'][end]-v['ACSWDNBC'][start])/3600
  obs=A.observed_components(blobs,dt.datetime(2016,10,6,h));row=old['hourly'][h]
  require(model['accumulator_allsky_W_m2']==row['model_W_m2'] and obs['primary_W_m2']==row['primary_W_m2'],'old whole-day score changed')
  result.append({'UTC':f'{h:02d}:00/{h+1:02d}:00','model_native_period_end_means_W_m2':model,'observed_same_period_end_means_W_m2':obs})
 return {'hours':result,'native_accumulator_updates_replayed':240,'native_direct_diffuse_definitions_replayed':120,'instantaneous_fluxes_not_substituted_for_hour_means':True,'old_whole_day_statistics_unchanged':old['statistics'],'scope':'surface held actual end-of-step fluxes independently replay accumulators; SWDDIR is horizontal physical direct, SWDDNI is native normal direct; not meanDNI*meanCos; cloudy observations do not validate model clear-sky accuracy'}
