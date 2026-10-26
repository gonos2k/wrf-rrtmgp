"""One fixed-cell scientific figure; export independently of CI replay."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
P=Path(__file__).resolve().parent

def main():
 r=json.loads((P/'result.json').read_text());hours=[x['start_hour_UTC'] for x in r['hourly']];a=[x['layers'][1] for x in r['hourly']];x=np.arange(5);fig,ax=plt.subplots(2,2,figsize=(12,8),layout='constrained')
 pairs=[('dry_theta_paired_horizontal_K','dry_theta_paired_vertical_K','Paired dry-theta transport [K]'),('qv_horizontal_g_kg','qv_vertical_g_kg','Vapor transport [g/kg dry]')]
 for panel,(h,v,title) in zip(ax[0],pairs):
  panel.bar(x-.17,[z['sums'][h] for z in a],.34,label='Horizontal');panel.bar(x+.17,[z['sums'][v] for z in a],.34,label='Vertical');panel.axhline(0,color='k',lw=.6);panel.set_title(title);panel.legend()
 panel=ax[1,0];panel.bar(x-.2,[z['sums']['qv_center_relative_face_g_kg'] for z in a],.4,label='Center-relative face term');panel.bar(x+.2,[z['sums']['qv_center_mass_convergence_g_kg'] for z in a],.4,label='Center x mass-flux difference');panel.plot(x,[z['sums']['qv_vertical_g_kg'] for z in a],'ko-',label='Actual vertical total');panel.axhline(0,color='k',lw=.6);panel.set_title('Declared reference split [g/kg dry]');panel.legend(fontsize=8)
 panel=ax[1,1];panel.plot(x,[z['means']['qv_eta_mass_flux_lower_native_Pa_s'] for z in a],'o-',label='PD native eta flux: lower');panel.plot(x,[z['means']['qv_eta_mass_flux_upper_native_Pa_s'] for z in a],'s-',label='PD native eta flux: upper');panel.axhline(0,color='k',lw=.6);panel.set_title('Consumed eta mass flux [native Pa/s]');panel.legend(fontsize=8)
 for panel in ax.flat:panel.set_xticks(x,[f'{h}–{h+1}' for h in hours]);panel.set_xlabel('UTC hour on 2016-10-06');panel.grid(axis='y',alpha=.2)
 fig.suptitle('Sterling fixed cell (37,119), native layer 8: same-case state/face diagnosis\nConservative operator contributions; not parcel heating or vertical-motion validation',fontsize=12);fig.savefig(P/'transport-state.png',dpi=150);plt.close(fig)
if __name__=='__main__':main()
