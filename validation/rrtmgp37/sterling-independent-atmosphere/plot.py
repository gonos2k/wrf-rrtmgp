"""Scientific plot of retrieved observations and the unchanged forecast states."""
from pathlib import Path
import json,datetime as dt
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent

def main():
 ex=json.loads((B/'udm37-sterling-independent-atmosphere-analysis-v1/enriched.json').read_text());r=json.loads((P/'result.json').read_text());ob=next(x for x in ex['soundings'] if '2016-10-06T18:' in x['nominal_UTC']);model={x['hour_UTC']:x for x in ex['model']['profiles']}
 fig,ax=plt.subplots(3,2,figsize=(12,13),constrained_layout=True)
 def filtered(rows,field):return sorted([x for x in rows if x.get(field) is not None and x.get('z_agl_m') is not None and x.get('p_Pa') is not None and 0<=x['z_agl_m']<=2500],key=lambda x:x['z_agl_m'])
 for axis,of,mf,label,scale in [(ax[0,0],'T_K','T_K','Temperature (C)',1),(ax[0,1],'qv_from_dewpoint_kg_kg','qv_kg_kg','Water vapor (g kg$^{-1}$ dry)',1000),(ax[1,0],'RH_water_from_dewpoint_ratio','RH_water_ratio','RH relative to water (%)',100)]:
  o=filtered(ob['levels'],of);axis.plot([(x[of]-273.15 if of=='T_K' else x[of]*scale) for x in o],[x['z_agl_m'] for x in o],'k.-',label='IGRA nominal18; release17:34')
  for h,c in [(17,'C0'),(18,'C1')]:
   m=filtered(model[h]['profiles'],mf);axis.plot([(x[mf]-273.15 if mf=='T_K' else x[mf]*scale) for x in m],[x['z_agl_m'] for x in m],'.-',color=c,label=f'Model {h}:00')
  axis.set(xlabel=label,ylabel='Height above local ground (m)');axis.legend(fontsize=8)
 a=ax[1,1]
 for field,col,lab in [('wind_u_east_m_s','C2','eastward u'),('wind_v_north_m_s','C3','northward v')]:
  o=filtered(ob['levels'],field);m=filtered(model[18]['profiles'],field);a.plot([x[field] for x in o],[x['z_agl_m'] for x in o],color=col,label='IGRA '+lab);a.plot([x[field] for x in m],[x['z_agl_m'] for x in m],'--',color=col,label='Model18 '+lab)
 a.set(xlabel='Pressure-level wind components (m s$^{-1}$)',ylabel='Height above local ground (m)');a.legend(fontsize=8)
 a=ax[2,0]
 for st,marker in [('IAD','o'),('DCA','s'),('BWI','^')]:
  rows=next(x['records'] for x in r['surface_station_context'] if x['station']==st);rows=[x for x in rows if x['ceiling_agl_m'] is not None]
  a.scatter([dt.datetime.fromisoformat(x['time_UTC']).hour+dt.datetime.fromisoformat(x['time_UTC']).minute/60 for x in rows],[x['ceiling_agl_m'] for x in rows],marker=marker,label=st+' lowest BKN/OVC')
 a.axvline(17.6,color='k',ls='--',label='Model cloud lost17:36');a.set(xlabel='UTC hour (actual report instants)',ylabel='Reported ceiling AGL (m)',xlim=(17,20));a.legend(fontsize=8)
 a=ax[2,1];s=r['existing_same_period_radiation_components'][1];mm=s['model_native_period_end_means_W_m2'];oo=s['observed_same_period_end_means_W_m2'];a.bar([-.2,.8],[mm['SWDDIR'],mm['SWDDIF']],width=.4,label='Model');a.bar([.2,1.2],[oo['horizontal_direct_W_m2'],oo['DHI_W_m2']],width=.4,label='SOLRAD');a.set(xticks=[0,1],xticklabels=['Horizontal direct','Diffuse'],ylabel='18–19 UTC surface SW (W m$^{-2}$)');a.legend(fontsize=8)
 for a in ax.flat:a.grid(alpha=.2)
 fig.suptitle('Independent atmosphere constraints: Sterling 2016-10-06, fixed PR202/203 forecast\nPoint/balloon profiles differ in time and footprint; no coefficient tuning or new forecast',fontsize=12)
 fig.savefig(P/'independent-atmosphere.png',dpi=150);plt.close(fig)
if __name__=='__main__':main()
