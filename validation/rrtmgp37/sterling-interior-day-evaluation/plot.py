"""Standalone hourly comparison of two configurations and the unchanged observations."""
from pathlib import Path
import json,csv
P=Path(__file__).resolve().parent

def main():
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 r=json.loads((P/'result.json').read_text());old=json.loads((P.parent/'real-output-independent-comparison/result.json').read_text());rows=r['hourly']
 with (P/'hourly-comparison.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
 fig,(ax,err)=plt.subplots(2,1,figsize=(10,6.5),sharex=True,gridspec_kw={'height_ratios':[2,1]},layout='constrained');edges=list(range(25))
 ax.stairs([x['model_W_m2'] for x in rows],edges,label='New interior configuration (accumulator)',color='#b73f2e',linewidth=1.8)
 ax.stairs([x['model_W_m2'] for x in old['hourly']],edges,label='Original boundary configuration (retained)',color='#777777',linestyle='--')
 ax.stairs([x['model_clear_W_m2'] for x in rows],edges,label='New configuration clear sky (model only)',color='#cc9d21',linewidth=1)
 ax.stairs([x['primary_W_m2'] for x in rows],edges,label='NOAA SOLRAD DNI projection + diffuse',color='#164f83',linewidth=1.8)
 ax.stairs([x['secondary_W_m2'] for x in rows],edges,label='NOAA PSP (separate channel)',color='#43866c',linestyle=':',linewidth=1)
 ax.set_ylabel('Hourly mean downward SW (W m$^{-2}$)');ax.legend(fontsize=8);ax.grid(alpha=.2)
 err.stairs([x['primary_error_W_m2'] for x in rows],edges,color='#b73f2e',label='New - primary');err.stairs([x['primary_error_W_m2'] for x in old['hourly']],edges,color='#777777',ls='--',label='Original - primary');err.axhline(0,color='black',lw=.7);err.set_ylabel('Model - primary\n(W m$^{-2}$)');err.set_xlabel('UTC hour, 6 October 2016; all intervals (start, end]');err.set_xlim(0,24);err.set_xticks(range(0,25,3));err.grid(alpha=.2)
 ax.set_title('Sterling: separate interior-domain research configuration, fixed physics\nDomain, WPS version and geography change together; no pure-boundary or optics attribution',fontsize=10)
 fig.savefig(P/'sterling-interior-day-sw.png',dpi=180);plt.close(fig)
if __name__=='__main__':main()
