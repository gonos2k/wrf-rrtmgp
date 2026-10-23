"""Reconstruct the selection and area check from actual files, never change forcing."""
from pathlib import Path
import json,math,numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;D=B/'udm37-frozen-selected-selection-v1'
rows=[x.split() for x in (D/'host/frozen-selection.txt').read_text().splitlines()]
assert len(rows)==8910 and len({(int(x[0]),int(x[1])) for x in rows})==8910 and all(float(x[3])==3000 for x in rows)
r=max(rows,key=lambda x:(float(x[4]),float(x[5]),-int(x[1]),-int(x[0])))
target=dict(i=int(r[0]),j=int(r[1]),source_time_s=3000,warm_layers=int(r[2]),warm_hail_path_g_m2=float(r[4]),all_hail_path_g_m2=float(r[5]),native_layer=int(float(r[6])),temperature_K=float(r[7]),layer_hail_path_g_m2=float(r[8]),lambda_m_1=float(r[9]),selection='maximum local warm-ambient hail path, then largest actual warm hail layer',observed_physical_columns=len(rows),production_changes=False)
with Dataset(B/'udm37-vapor-corrected-day-v2/host/wrfout_d01_2016-10-06_00:00:00') as d:
 a=float(d.DX)*float(d.DY)/(d['MAPFAC_MX'][0].astype('f8')*d['MAPFAC_MY'][0].astype('f8'));A=a.sum()
 got=math.fsum(a[int(x[1])-1,int(x[0])-1]*float(x[4])*.001 for x in rows)/A
for line in (B/'udm37-vapor-corrected-day-v2/host/real-budget.txt').read_text().splitlines():
 x=line.split()
 if x[:3]==['3000.000','frozen_consumption','2']:expected=float(x[12])/A;break
else:raise ValueError('baseline hail source absent')
target.update(warm_hail_domain_path_kg_m2=got,baseline_domain_path_kg_m2=expected,domain_path_difference_kg_m2=got-expected)
comp=json.loads((D/'history-comparison.json').read_text());assert comp['pairs']==450 and not comp['differences']
assert json.loads((D/'target.json').read_text())==target,'selection reproduction differs'
(D/'area.json').write_text(json.dumps({'axis_order':'j,i, physical mass grid only','area_m2':a.tolist(),'whole_area_m2':float(A),'baseline_frozen_line':line},indent=2)+'\n')
print('ACTUAL_SELECTION_AND_AREA_REPRODUCED')
