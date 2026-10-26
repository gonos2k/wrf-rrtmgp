"""Standalone scientific process plot with signed contributions and actual net states."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parent
def main():
 r=json.loads((P/'result.json').read_text());layers=r['five_hour_layers'];ks=[x['k'] for x in layers];fig,ax=plt.subplots(1,3,figsize=(14,6))
 names=['horizontal_transport','vertical_transport','radiation','PBL','microphysics'];colors=['C0','C1','C2','C3','C4']
 for n,c in zip(names,colors):ax[0].plot([x['dry_theta_paired_processes_K'][n] for x in layers],ks,'o-',label=n.replace('_',' '),color=c)
 ax[0].plot([x['dry_theta_change_K'] for x in layers],ks,'k--',lw=2,label='actual diagnostic delta')
 for n,c in [('transport_horizontal','C0'),('transport_vertical','C1'),('PBL','C3'),('microphysics','C4')]:ax[1].plot([x['qv_components_g_kg'][n] for x in layers],ks,'o-',label=n.replace('_',' '),color=c)
 ax[1].plot([x['qv_change_g_kg'] for x in layers],ks,'k--',lw=2,label='actual delta')
 hours=[x['start_seconds']/3600 for x in r['hourly_layers']]
 for k,c in [(6,'C0'),(7,'C1'),(8,'C2')]:
  rows=[next(z for z in h['layers'] if z['k']==k) for h in r['hourly_layers']];ax[2].plot(hours,[x['dry_theta_change_K'] for x in rows],'o-',label=f'layer {k}',color=c)
 for a in ax:a.grid(alpha=.2);a.legend(fontsize=7)
 for a in ax[:2]:a.axvline(0,color='gray',lw=.6)
 ax[0].set_title('12–17 UTC: dry-theta attribution');ax[0].set_xlabel('K, finite-change diagnostic');ax[0].set_ylabel('Native layer (not fixed pressure)');ax[1].set_title('12–17 UTC: vapor attribution');ax[1].set_xlabel('g/kg dry');ax[1].set_ylabel('Native layer');ax[2].set_title('Actual hourly dry-theta change');ax[2].set_xlabel('UTC interval start');ax[2].set_ylabel('K per actual hour');ax[2].axhline(0,color='gray',lw=.6);ax[2].set_xlim(11.8,16.2);ax[2].set_xticks(hours)
 fig.suptitle('Sterling (37,119): actual bounded operators, unchanged physics',fontsize=13);fig.tight_layout();fig.savefig(P/'thermodynamic-processes.png',dpi=160);plt.close(fig)
if __name__=='__main__':main()
