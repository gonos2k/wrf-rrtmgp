#!/usr/bin/env python3
"""Standalone hourly comparison figure from already extracted CSV."""
import csv
import datetime as dt
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

root=Path(__file__).resolve().parent
rows=list(csv.DictReader((root/'hourly-comparison.csv').open()))
t=[dt.datetime.fromisoformat(r['end_utc'])-dt.timedelta(minutes=30) for r in rows]
fig,ax=plt.subplots(figsize=(10,5.2))
for field,label,color,style in [('component_wm2','NOAA SOLRAD (DNI projection + diffuse)','black','-'),('ra4_hourly_W_m2','UDM27 / RRTMG4','#3875bb','--'),('ra37_hourly_W_m2','UDM27 / RRTMGP37 (experimental frozen optics)','#d56520','-')]:
 ax.plot(t,[float(r[field]) for r in rows],label=label,color=color,linestyle=style,linewidth=1.6)
ax.set(title='Sterling, VA: 2016-10-06 to 2016-10-08 UTC',ylabel='Hourly mean downward solar flux (W m$^{-2}$)',xlabel='UTC; plotted at interval midpoints')
ax.xaxis.set_major_locator(mdates.HourLocator(interval=6));ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
ax.grid(alpha=.25);ax.legend(fontsize=8)
fig.subplots_adjust(left=.09,right=.98,top=.90,bottom=.22)
fig.text(.5,.035,'One station in the 27-km lateral boundary zone; coupled forecasts. No interior-skill or causal engine-accuracy claim.',ha='center',fontsize=8)
fig.savefig(root/'sterling-hourly-sw.png',dpi=160)
plt.close(fig)
