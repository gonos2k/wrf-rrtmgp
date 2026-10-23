"""Same-position signed optical and transport contrasts for one actual state."""
import math

def require(ok,message):
 if not ok:raise ValueError(message)

def coefficient_record(table_tau,path,original,reference):
 records=[]
 for j,row in enumerate(reference['records']):
  level=row['levels'][-1];fine=level['fine'];rh=level['radius_half'];vh=level['spectral_half'];a=table_tau[j]/(path*.001);b=original['bands'][j]['moments'][3][0]/912.;c=fine['moments_m2_kg']['abs']
  require(level['qualified_numerical_axes'] and level['absorption_radius_relative_change']<=.01 and level['absorption_spectral_relative_change']<=.01,'unqualified independent absorption')
  require(c>0 and a>=0 and b>=0,'invalid absorption')
  records.append({'band':j+1,'A_current_kappa_m2_kg':a,'B_original_direct_kappa_m2_kg':b,'C_independent_kappa_m2_kg':c,'B_minus_A':b-a,'C_minus_B':c-b,'C_minus_A':c-a,'current_minus_reference_relative':(a-c)/c,'radius_axis_relative_change':level['absorption_radius_relative_change'],'spectral_axis_relative_change':level['absorption_spectral_relative_change'],'axis_absolute_change_sum_m2_kg':abs(c-rh['moments_m2_kg']['abs'])+abs(c-vh['moments_m2_kg']['abs'])})
 return records

def quantities(records,native,working):
 names=['UP_WP','DN_WP','HEAT_WP_K_S'] if working else ['UP','DN','HR']
 u,d,h=[records[n]['values'] for n in names]
 if working:h=[x*86400 for x in h]
 u=u[:native+1];d=d[:native+1];h=h[:native];net=[y-x for x,y in zip(u,d)]
 return {'UP':u,'DN':d,'NET_DOWN':net,'HEATING_K_day':h,'surface_UP':u[0],'surface_DN':d[0],'surface_NET_DOWN':net[0],'native_top_UP':u[-1],'native_top_DN':d[-1],'native_top_NET_DOWN':net[-1],'native_column_convergence':net[-1]-net[0]}

def difference(x,y):
 out={}
 for k,v in x.items():out[k]=[a-b for a,b in zip(v,y[k])] if isinstance(v,list) else v-y[k]
 out['max_abs_native_flux_W_m2']=max(map(abs,out['UP']+out['DN']))
 out['max_abs_native_heating_K_day']=max(map(abs,out['HEATING_K_day']))
 out['max_heating_native_layer_1based']=max(range(len(out['HEATING_K_day'])),key=lambda k:abs(out['HEATING_K_day'][k]))+1
 return out

def transport(results,native):
 answer={}
 for working,label in [(False,'native_consumed_REAL32'),(True,'working_precision')]:
  q={mode:quantities(r,native,working) for mode,r in results.items()}
  for name in q['public_A']:
   require(q['public_A'][name]==q['diagnostic_A'][name],'inactive optical hook changed baseline')
  diffs={name:difference(q[x],q[y]) for name,x,y in [('B_minus_A','original_direct','public_A'),('C_minus_B','fine','original_direct'),('C_minus_A','fine','public_A'),('radius_change','fine','radius_half'),('spectral_change','fine','spectral_half')]}
  for key in ['UP','DN','NET_DOWN','HEATING_K_day']:
   for a,b,c in zip(diffs['B_minus_A'][key],diffs['C_minus_B'][key],diffs['C_minus_A'][key]):
    require(abs(a+b-c)<=16*math.ulp(max(1,abs(a),abs(b),abs(c))),'signed same-location decomposition')
  answer[label]={'baseline':q['public_A'],'contrasts':diffs,'empirical_axis_change_sum':{'native_flux_W_m2':diffs['radius_change']['max_abs_native_flux_W_m2']+diffs['spectral_change']['max_abs_native_flux_W_m2'],'native_heating_K_day':diffs['radius_change']['max_abs_native_heating_K_day']+diffs['spectral_change']['max_abs_native_heating_K_day']},'is_certified_error_bound':False}
 return answer
