"""Export support-matched hourly data and a standalone scientific figure."""
from pathlib import Path
import json,csv
P=Path(__file__).resolve().parent

def main():
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 r=json.loads((P/'result.json').read_text());rows=r['hourly']
 with (P/'hourly-comparison.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
 fig,(ax,err)=plt.subplots(2,1,figsize=(10,6.3),sharex=True,gridspec_kw={'height_ratios':[2,1]},layout='constrained')
 edges=list(range(25))
 ax.stairs([x['model_W_m2'] for x in rows],edges,label='Corrected serial WRF37 (accumulator difference)',color='#c04432',linewidth=1.8)
 ax.stairs([x['primary_W_m2'] for x in rows],edges,label='NOAA SOLRAD DNI projection + diffuse',color='#164f83',linewidth=1.8)
 ax.stairs([x['secondary_W_m2'] for x in rows],edges,label='NOAA global PSP (separate secondary)',color='#43866c',linestyle='--',linewidth=1)
 ax.set_ylabel('Hourly mean downward SW (W m$^{-2}$)');ax.legend(fontsize=9,loc='upper left');ax.grid(alpha=.2)
 err.stairs([x['primary_error_W_m2'] for x in rows],edges,color='#963729');err.axhline(0,color='black',linewidth=.7);err.set_ylabel('Model - primary\n(W m$^{-2}$)');err.grid(alpha=.2);err.set_xlabel('UTC hour, 6 October 2016; all intervals (start, end]');err.set_xlim(0,24);err.set_xticks(range(0,25,3))
 ax.set_title('Sterling boundary site: corrected real-data output vs actual observations\nOne station-day; no interior forecast or physical-optics accuracy approval',fontsize=11)
 fig.savefig(P/'sterling-corrected-day-sw.png',dpi=180);plt.close(fig)
if __name__=='__main__':main()
