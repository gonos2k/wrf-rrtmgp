#!/usr/bin/env python3
"""Controls for new component-based SW/LW reduction using 3-minute ends."""
import datetime as dt
import json
import analyze


def main():
    start=analyze.obs.START
    row=[0.0]*48
    row[7]=60;row[8]=-3;row[10]=7;row[12]=100;row[14]=10;row[16]=200
    rows={start+dt.timedelta(minutes=3*k):list(row) for k in range(21)}
    rows[start][12]=999999
    h=analyze.hourly(rows,start)
    assert abs(h['sw_components']-60)<1e-12 and h['net_sw_components']==h['sw_components']-7
    assert h['sw_global']==-3 and h['lw_down']==200
    rows[start+dt.timedelta(hours=1)][14]=30
    assert abs(analyze.hourly(rows,start)['sw_components']-61)<1e-12
    missing=dict(rows);del missing[start+dt.timedelta(minutes=9)]
    assert analyze.hourly(missing,start)['sw_components'] is None
    bad={t:list(r) for t,r in rows.items()};bad[start+dt.timedelta(minutes=9)][13]=1
    h=analyze.hourly(bad,start);assert h['sw_components'] is None and h['sw_global']==-3 and h['lw_down']==200
    bad={t:list(r) for t,r in rows.items()};bad[start+dt.timedelta(minutes=9)][16]=-9999.9
    assert analyze.hourly(bad,start)['lw_down'] is None
    below={t:list(r) for t,r in rows.items()}
    for r in below.values():r[7]=120;r[14]=-2
    h=analyze.hourly(below,start);assert h['sw_components']==-2 and not h['daylight_hour']
    print(json.dumps({'status':'PASS','new_model_solver_build_calls':0,
                      'controls':['start excluded','final endpoint included','20 samples required','component QC failure without global fallback','LW fill rejection','signed QC0 global/diffuse preserved','SZA projection and below-horizon direct','component-based net SW']},indent=2))


if __name__=='__main__':main()
