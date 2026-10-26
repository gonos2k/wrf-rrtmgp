"""Standalone scientific plot of actual local processes and observed surface flux."""
from pathlib import Path
import json,csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parent;B=P.parents[3]
def main():
 a=json.loads((B/'udm37-sterling-cloud-loss-analysis-v1/analysis.json').read_text());r=json.loads((P/'result.json').read_text());steps=[x for x in a['steps'] if 61200<=x['source_seconds']<64800]
 t=np.array([x['end_seconds']/3600 for x in steps]);cloud=[x['species'][1]['layers'][5] for x in steps];vap=[x['species'][0]['layers'][5] for x in steps]
 fig,ax=plt.subplots(2,2,figsize=(12,8),constrained_layout=True)
 ax[0,0].plot(np.r_[17,t],np.r_[cloud[0]['start_kg_m2'],[x['end_kg_m2'] for x in cloud]]*1000,'k-',label='End-of-step cloud')
 ax[0,0].set(ylabel='Layer 6 cloud water (g m$^{-2}$)',xlabel='UTC hour',title='Fixed station cell (37,119): actual cloud loss')
 colors={'PD_source_actual_kg_m2':'C0','RK_advection_actual_kg_m2':'C1','microphysics_actual_kg_m2':'C2'}
 labels={'PD_source_actual_kg_m2':'PD source (PBL/CU/mixing)','RK_advection_actual_kg_m2':'Final RK transport','microphysics_actual_kg_m2':'Microphysics'}
 for key,col in colors.items():
  ax[0,1].plot(t,np.cumsum([x[key] for x in cloud])*1000,color=col,label=labels[key])
  ax[1,0].plot(t,np.cumsum([x[key] for x in vap])*1000,color=col,label=labels[key])
 ax[0,1].plot(t,np.cumsum([x['delta_kg_m2'] for x in cloud])*1000,'k--',label='Actual cloud change')
 ax[1,0].plot(t,np.cumsum([x['delta_kg_m2'] for x in vap])*1000,'k--',label='Actual vapor change')
 ax[0,1].set(ylabel='Cumulative cloud change (g m$^{-2}$)',xlabel='UTC hour',title='Applied processes, one physical interval per step')
 ax[1,0].set(ylabel='Cumulative vapor change (g m$^{-2}$)',xlabel='UTC hour',title='Vapor receiver and transport/source exchange')
 ex=json.loads((B/'udm37-sterling-cloud-loss-analysis-v1/extracted.json').read_text());sf=ex['surface'];tm=np.arange(1,121)/60+17
 for n,label in [('SWDNB','Model all sky'),('SWDDIR','Model horizontal direct'),('SWDDIF','Model diffuse')]:ax[1,1].step(tm,sf['values'][n][1:],where='pre',label=label)
 for h,row in zip([17,18],r['surface_components']['hours']):ax[1,1].hlines(row['observed_same_period_end_means_W_m2']['primary_W_m2'],h,h+1,color='k',lw=2)
 ax[1,1].plot([],[],color='k',lw=2,label='SOLRAD hourly all sky');ax[1,1].set(ylabel='Surface downwelling SW (W m$^{-2}$)',xlabel='UTC hour',title='Same period-end support; original day score preserved')
 for x in ax.flat:x.grid(alpha=.2);x.legend(fontsize=8,loc='best')
 fig.suptitle('PR202 trajectory diagnosis: fixed physics and optics; no parameter calibration',fontsize=12)
 fig.savefig(P/'cloud-loss-processes.png',dpi=170);plt.close(fig)
if __name__=='__main__':main()
