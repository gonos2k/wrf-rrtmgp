"""Scientific diagnostic figure and fixed-transect CSV; no neighbor scoring."""
from pathlib import Path
import json,csv,importlib.util
P=Path(__file__).resolve().parent

def main():
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 s=importlib.util.spec_from_file_location('sterling_plot_data',P/'verify_saved.py');v=importlib.util.module_from_spec(s);s.loader.exec_module(v);d,_,_=v.data();rec=v.A.parse(d['host/sterling-cloud.txt']);r=json.loads((P/'result.json').read_text());hour=r['observed_minutes'];h=[rec['held'][t,97] for t in range(57600,61200,60)]
 table=[]
 for x in r['fixed_north_transect']:
  table.append({k:z for k,z in x.items() if k!='actual_call_inputs'})
 with (P/'transect.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(table[0]),lineterminator='\n');w.writeheader();w.writerows(table)
 fig,(ax,bx)=plt.subplots(2,1,figsize=(10,7.3),layout='constrained');edges=list(range(61))
 ax.stairs([x[4] for x in h],edges,label='Model all sky = clear sky',color='#bd3b32',linewidth=1.8)
 ax.stairs([x[8] for x in h],edges,label='Model physical horizontal direct',color='#cb8d24',linewidth=1.2)
 ax.stairs([x[7] for x in h],edges,label='Model diffuse',color='#70398b',linewidth=1.2)
 ax.stairs([x['primary_W_m2'] for x in hour],edges,label='Observed horizontal direct + diffuse',color='#204f88',linewidth=1.5)
 ax.stairs([x['DHI_W_m2'] for x in hour],edges,label='Observed diffuse',color='#3e9771',linestyle='--',linewidth=1)
 ax.set(xlim=(0,60),xlabel='Minutes after 16:00 UTC on 6 October 2016; intervals end at minute label',ylabel='Downward SW (W m$^{-2}$)',title='Original Sterling cell (37,97): actual returned/held components and minute observations');ax.legend(fontsize=8,ncol=2);ax.grid(alpha=.2)
 x=[z['cells_from_north_edge'] for z in table];bx.axvspan(-.5,4.5,color='#efcb8c',alpha=.25,label='Five-row specified boundary zone');bx.axvline(2,color='#555',linestyle=':',label='Original station cell (no score replacement)')
 for key,label,color in [('model_allsky_held_W_m2','All sky','#bd3b32'),('model_clearsky_held_W_m2','Clear sky','#777'),('physical_horizontal_direct_held_W_m2','Physical horizontal direct','#cb8d24')]:bx.plot(x,[z[key] for z in table],marker='o',markersize=3,label=label,color=color)
 bx.set(xlim=(-.5,10.5),xticks=range(11),xlabel='Rows inward from northern physical edge, fixed i=37 (j=99 minus x)',ylabel='Model one-hour mean (W m$^{-2}$)',title='Model-only fixed transect: cloud attenuation appears inward; boundary causality remains unproven');bx.legend(fontsize=8,ncol=2);bx.grid(alpha=.2)
 fig.savefig(P/'sterling-components-transect.png',dpi=170);plt.close(fig)
if __name__=='__main__':main()
