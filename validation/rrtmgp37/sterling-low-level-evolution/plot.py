"""Standalone scientific state-development figure, no interpolation across time."""
from common import *
from report import dependencies
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
def main():
 r=json.loads((P/'result.json').read_text());obs,_=dependencies();fig,ax=plt.subplots(2,3,figsize=(13,8));hs=[x for x in r['hourly_profiles'] if 11<=x['hour_UTC']<=18]
 for p,col in [(95000,'C0'),(92500,'C1'),(90000,'C2'),(85000,'C3')]:
  rows=[next(z for z in h['pressure_rows'] if z['pressure_Pa']==p) for h in hs]
  ax[0,0].plot([h['hour_UTC'] for h in hs],[z['T_K']-273.15 for z in rows],'.-',color=col,label=f'{p/100:g} hPa')
  ax[0,1].plot([h['hour_UTC'] for h in hs],[z['qv_kg_kg']*1000 for z in rows],'.-',color=col)
 inv=r['fixed_pressure_and_native_inversion_development'];ax[0,2].plot([z['hour_UTC'] for z in inv],[z['T925_minus_T950_K'] for z in inv],'.-',label='T925-T950');ax[0,2].plot([z['hour_UTC'] for z in inv],[z['theta925_minus_theta950_K'] for z in inv],'.-',label='theta925-theta950');ax[0,2].axhline(0,color='gray',lw=.5)
 for n,(s,c) in enumerate([('2016-10-06T12:00:00+00:00','C0'),('2016-10-06T18:00:00+00:00','C1')]):
  sound=next(x for x in obs['soundings'] if x['nominal_UTC']==s);lev=[x for x in sound['levels'] if x['p_Pa'] and 80000<=x['p_Pa']<=97500 and x.get('qv_from_dewpoint_kg_kg') is not None];lev.sort(key=lambda x:-x['p_Pa'])
  label=f"IGRA release {sound['release_HHMM']} (ascent times differ)"
  ax[1,0].plot([z['T_K']-273.15 for z in lev],[z['p_Pa']/100 for z in lev],color=c,label=label)
  ax[1,1].plot([z['qv_from_dewpoint_kg_kg']*1000 for z in lev],[z['p_Pa']/100 for z in lev],color=c)
 for h,c in [(11,'C0'),(18,'C1')]:
  z=next(x for x in r['hourly_profiles'] if x['hour_UTC']==h)['pressure_rows'];ax[1,0].plot([a['T_K']-273.15 for a in z],[a['pressure_Pa']/100 for a in z],'--',color=c,label=f'model {h:02d}:00')
  ax[1,1].plot([a['qv_kg_kg']*1000 for a in z],[a['pressure_Pa']/100 for a in z],'--',color=c)
 sr=[next(z for z in s['pressure_rows'] if z['pressure_Pa']==90000) for s in r['source_to_met_em_chain']];hours=[s['hour_UTC'] for s in r['source_to_met_em_chain']]
 ax[1,2].plot(hours,[z['GRIB_bilinear_qv_REAL_method1_diagnostic']*1000 for z in sr],'o-',label='FNL bilinear, RH diagnostic')
 ax[1,2].plot(hours,[z['met_em_qv_REAL_method1_diagnostic']*1000 for z in sr],'s--',label='met_em, RH diagnostic')
 chain=[x for x in r['local_met_em_initial_history_chain'] if x['pressure_Pa']==90000];ax[1,2].plot([x['hour_UTC'] for x in chain],[x['history_qv']*1000 for x in chain],'x-',label='actual history')
 titles=['Actual model temperature','Actual model vapor','Same pressure interval: lapse vs dry stability','Temperature profiles: no time interpolation','Vapor profiles: same native water diagnostic','900 hPa source / forecast states']
 for a,title in zip(ax.flat,titles):a.set_title(title,fontsize=10);a.grid(alpha=.25)
 for a in ax[0]:a.set_xlabel('UTC hour, 2016-10-06')
 ax[0,0].set_ylabel('deg C');ax[0,1].set_ylabel('g/kg dry');ax[0,2].set_ylabel('K')
 for a in ax[1,:2]:a.invert_yaxis();a.set_ylim(980,795);a.set_ylabel('hPa')
 ax[1,0].set_xlabel('deg C');ax[1,1].set_xlabel('g/kg dry');ax[1,2].set_xlabel('UTC hour (24 = next 00)');ax[1,2].set_ylabel('g/kg dry')
 for a in [ax[0,0],ax[0,2],ax[1,0],ax[1,2]]:a.legend(fontsize=6)
 fig.suptitle('Fixed Sterling cell (37,119): existing forcing and forecast, unchanged physics',fontsize=13);fig.tight_layout();fig.savefig(P/'state-development.png',dpi=160);plt.close(fig)
if __name__=='__main__':main()
