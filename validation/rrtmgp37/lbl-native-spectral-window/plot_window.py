"""Optional standalone scientific plot; core replay uses only the stdlib."""
from pathlib import Path
import csv,json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
B=Path(__file__).resolve().parent
result=json.loads((B/'result.json').read_text())
fig,axes=plt.subplots(2,1,figsize=(8.5,6),sharex=True,constrained_layout=True)
for arm,label,color in [('h','h (81 native samples)','#4878b5'),('half','h/2 (161 native samples)','#d97d26'),('quarter','h/4 (321 native samples)','#202020')]:
 rows=list(csv.DictReader((B/f'{arm}.native.csv').open()))
 axes[0].plot([float(r['actual_nu_cm1']) for r in rows],[float(r['OD']) for r in rows],label=label,color=color,linewidth=1,marker='.',markersize=2)
rows=list(csv.DictReader((B/'half-quarter.shared161.csv').open()))
x=[float(r['half_actual_nu_cm1']) for r in rows];y=[float(r['signed_OD_difference']) for r in rows]
axes[1].plot(x,y,'.-',color='#b44d4d',linewidth=.8,markersize=2,label='h/4 minus h/2, all 161 shared samples')
nodes=[r for r in rows if r['half_R3_node']=='True']
axes[1].scatter([float(r['half_actual_nu_cm1']) for r in nodes],[float(r['signed_OD_difference']) for r in nodes],s=20,color='#202020',zorder=3,label='11 nodes aligned with both R3 grids')
maxloc=result['shared161_half_to_quarter']['maximum_location'];nu=maxloc['half_actual_nu_cm1']
for ax in axes:
 ax.axhline(0,color='#777777',linewidth=.6);ax.axvline(618.6133629315808,color='#777777',linestyle=':',linewidth=.8)
 ax.axvline(nu,color='#41865a',linestyle='--',linewidth=.8);ax.grid(alpha=.15);ax.legend(fontsize=8)
axes[0].set_ylabel('Optical depth (dimensionless)')
axes[0].set_title('PR165 saved layer 21: native window, IOD=2\nNegative OD retained; grid differences are not truth errors',fontsize=10)
axes[1].set_ylabel('OD difference (h/4 - h/2)');axes[1].set_xlabel('Wavenumber (cm$^{-1}$)')
axes[1].ticklabel_format(axis='y',style='sci',scilimits=(0,0));axes[1].ticklabel_format(axis='x',style='plain',useOffset=False)
axes[1].annotate(f'Max: {abs(maxloc["signed_OD_difference"]):.4g}\nat {nu:.6f} cm$^{{-1}}$',xy=(nu,maxloc['signed_OD_difference']),xytext=(20,-45),textcoords='offset points',fontsize=8,arrowprops={'arrowstyle':'->','lw':.6})
fig.savefig(B/'native-window.png',dpi=180)
fig.savefig(B/'native-window.pdf',metadata={'CreationDate':None,'ModDate':None})
plt.close(fig)
