#!/usr/bin/env python3
"""Export a figure from the recorded hourly estimates, no model calls."""
import csv
import datetime as dt
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

root=Path(__file__).resolve().parent
rows=list(csv.DictReader((root/'hourly-comparison.csv').open()))
fig,axes=plt.subplots(3,2,figsize=(12,9),sharex=True)
for j,site in enumerate(['gwn','psu','bon']):
 data=[r for r in rows if r['station']==site]
 t=[dt.datetime.fromisoformat(r['end_utc'])-dt.timedelta(minutes=30) for r in data]
 for k,(field,model,label) in enumerate([('sw_components','down_sw','Downward shortwave'),('lw_down','down_lw','Downward longwave')]):
  ax=axes[j,k]
  for name,title,color,style in [(field,'NOAA SURFRAD','black','-'),('ra4_'+model,'UDM27 / RRTMG4','#3875bb','--'),('ra37_'+model,'UDM27 / RRTMGP37 frozen1','#d56520','-')]:
   ax.plot(t,[float(r[name]) for r in data],label=title,color=color,linestyle=style,linewidth=1.5)
  ax.set_title(site.upper()+': '+label);ax.set_ylabel('Hourly mean (W m$^{-2}$)');ax.grid(alpha=.25)
  ax.xaxis.set_major_locator(mdates.HourLocator(interval=6));ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H'))
axes[0,0].legend(fontsize=8)
for ax in axes[-1]:ax.set_xlabel('UTC; values plotted at interval midpoints')
fig.suptitle('Winter UDM27 forecasts versus three interior SURFRAD sites: 2000-01-24 12 to 01-25 12 UTC',fontsize=12)
fig.subplots_adjust(left=.08,right=.98,top=.91,bottom=.11,hspace=.34,wspace=.24)
fig.text(.5,.025,'One day, 30-km grid, coupled trajectories, experimental frozen optics; no general forecast-accuracy or causal engine claim.',ha='center',fontsize=9)
fig.savefig(root/'surfrad-hourly-sw-lw.png',dpi=150)
plt.close(fig)
