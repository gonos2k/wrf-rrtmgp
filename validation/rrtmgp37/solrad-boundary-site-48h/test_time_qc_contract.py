#!/usr/bin/env python3
"""Small controls for interval inclusion, missing/QC rejection and signed data."""
import datetime as dt
import json
import tempfile
from pathlib import Path
import analyze


def main():
    start = analyze.START
    rows = {start + dt.timedelta(minutes=i): {
        'component_wm2': -2.0, 'global_psp_wm2': -3.0,
        'sun_above_horizon': False} for i in range(61)}
    rows[start]['component_wm2'] = 99999.0
    rows[start+dt.timedelta(hours=1)]['component_wm2'] = 118.0
    # Excluding start and including final yields exactly zero, not 99999/61.
    assert analyze.hourly(rows, start, start+dt.timedelta(hours=1))['component_wm2'] == 0.0
    assert analyze.hourly(rows, start, start+dt.timedelta(hours=1))['global_psp_wm2'] == -3.0
    missing = dict(rows); del missing[start+dt.timedelta(minutes=15)]
    assert analyze.hourly(missing, start, start+dt.timedelta(hours=1))['component_wm2'] is None
    badqc = {t: dict(r) for t, r in rows.items()}; badqc[start+dt.timedelta(minutes=15)]['component_wm2'] = None
    h = analyze.hourly(badqc, start, start+dt.timedelta(hours=1))
    assert h['component_wm2'] is None and h['global_psp_wm2'] == -3.0
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp);(p/'raw').mkdir()
        for day in (280,281,282):
            date=dt.datetime(2016,1,1)+dt.timedelta(days=day-1)
            # Header and free-format 22-field rows; two samples at/below horizon.
            base=[2016,day,10,date.day,0,0,0,60,-3,0,100,0,10,0,0,0,0,0,0,0,0,0]
            second=list(base);second[5]=1;second[7]=120;second[12]=-2
            (p/'raw'/f'ste16{day}.dat').write_text(' Sterling\n38.97203 -77.48690 85 -5 version 1\n'+' '.join(map(str,base))+'\n'+' '.join(map(str,second))+'\n')
        parsed,_=analyze.load_observations(p)
        assert abs(parsed[start]['component_wm2']-60) < 1e-12
        assert parsed[start+dt.timedelta(minutes=1)]['component_wm2'] == -2
        # QC direct failed: no global PSP fallback into primary component.
        file=p/'raw'/'ste16280.dat';lines=file.read_text().splitlines();v=lines[2].split();v[11]='1';lines[2]=' '.join(v);file.write_text('\n'.join(lines)+'\n')
        parsed,_=analyze.load_observations(p)
        assert parsed[start]['component_wm2'] is None and parsed[start]['global_psp_wm2']==-3
    receipt={'status':'PASS','controls':['start excluded / end included','QC0 negative preserved','missing minute rejects full-hour mean','component QC rejects without PSP fallback','DNI projected by supplied SZA','below-horizon direct zero with signed diffuse retained'],'new_model_solver_build_calls':0}
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
