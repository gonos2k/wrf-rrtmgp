from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
base=Path(__file__).resolve().parent
x=json.loads((base/'causal-decomposition.json').read_text());v=json.loads((base/'radius-counterfactual.json').read_text())
names=['mp4-mixed','mp4-liquid-only','mp4-ice-only','mp4-snow-only','mp5-mixed'];labels=['WSM5 mixed','WSM5 liquid','WSM5 ice','WSM5 snow','Ferrier mixed'];a=[];b=[];c=[]
for name in names:
 row=x['scenarios'][name]['SW'];m=row['metrics']['surface_down'];a.append(m['delta_observed_37_minus4']);b.append(m['delta_ica_mean_37_minus4']);r=v[name]['SW'];c.append(b[-1]+row['cloud_fraction']*(r['allcloud_background_fallback']['surface_down']-r['allcloud_actual']['surface_down']))
fig,ax=plt.subplots(figsize=(10,4.8),layout='constrained');p=np.arange(len(names));w=.24
ax.bar(p-w,a,w,label='Actual first-call samples',color='#da6a58');ax.bar(p,b,w,label='Exact single-layer ICA mean',color='#4d77b1');ax.bar(p+w,c,w,label='ICA mean with host BG fallback',color='#3e9973')
ax.axhline(0,color='#555',linewidth=.8);ax.set_xticks(p,labels);ax.set_ylabel('RRTMGP 37 - RRTMG 4 SW surface down (W m$^{-2}$)');ax.set_title('Same initial WRF column: sampling versus input/optics effects');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);ax.legend(fontsize=9)
fig.savefig(base/'causal-decomposition.png',dpi=180)
