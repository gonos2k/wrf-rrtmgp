"""Static figure of actual hourly thermodynamic support; not a causal attribution."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parent;B=P.parents[2].parent
d=json.loads((B/'udm37-sterling-thermodynamics-v2/thermodynamics.json').read_text());fig,axes=plt.subplots(1,2,figsize=(9,4),sharey=True)
for j in [95,96,97,98]:
 r=[x for x in d['profiles'] if x['hour_UTC']==16 and x['j']==j];axes[0].plot([100*x['RH_water_ratio'] for x in r],[x['pressure_Pa']/100 for x in r],label=f'j={j}'+(' (original site)' if j==97 else ''));axes[1].plot([1e3*sum(x['condensate'].values()) for x in r],[x['pressure_Pa']/100 for x in r])
axes[0].axvline(100,color='gray',ls=':');axes[0].set(xlabel='Native UDM RH over water (%)',ylabel='Native pressure (hPa)',ylim=(1000,50));axes[1].set(xlabel='Six condensate sum (g/kg dry)');axes[0].legend(fontsize=8);fig.suptitle('Original i=37 transect, 2016-10-06 16:00 UTC history snapshot\nHourly state description; no substep or boundary causality inferred',fontsize=10)
for ax in axes:ax.grid(alpha=.2)
fig.tight_layout();fig.savefig(P/'hourly-state-transect.png',dpi=160);plt.close(fig)
