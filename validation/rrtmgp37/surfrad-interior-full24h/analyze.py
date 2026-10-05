#!/usr/bin/env python3
"""Time-matched SURFRAD SW/LW analysis of the completed winter pair."""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import verify_surfrad as obs


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()


def pin(p):
    p=Path(p);return {'path':str(p.resolve()),'bytes':p.stat().st_size,'sha256':sha(p)}


def extract(pair, root):
    from netCDF4 import Dataset, chartostring
    out={'schema':'winter-model-extract-v1','new_model_solver_build_calls':0,'arms':{}}
    for arm,rad in [('ra4',4),('ra37',37)]:
        base=pair/f'{arm}-24h-v1';case=base/'case'
        receipt=base/'execution-receipt-v1.json';r=json.loads(receipt.read_text())
        assert r['status']==f'PASS_{arm.upper()}_24H'
        assert r['actual_model_invocations']==1 and r['model']['returncode']==0 and r['model']['model_completed']
        history=case/'wrfout_d01_2000-01-24_12:00:00'
        assert sha(history)==r['outputs']['history']['file']['sha256']
        assert sha(case/'wrfinput_d01')=='0cc7e188ef585a93ab52550816c6af236932254820fb1bc6937f464bfed38637'
        stage=base/'stage-receipt-v1.json';s=json.loads(stage.read_text())
        assert sha(case/'namelist.input')==s['case']['snapshot']['namelist']['sha256']
        with Dataset(history) as d:
            d.set_auto_maskandscale(False)
            times=chartostring(d['Times'][:]).astype(str).tolist()
            assert times==[(obs.START+dt.timedelta(hours=h)).strftime('%Y-%m-%d_%H:%M:%S') for h in range(25)]
            assert d.MP_PHYSICS==27 and d.RA_SW_PHYSICS==d.RA_LW_PHYSICS==rad
            lat,lon=np.asarray(d['XLAT'][0],float),np.asarray(d['XLONG'][0],float)
            assert lat.shape==lon.shape==(60,73)
            grids={};values={}
            for station,meta in obs.STATIONS.items():
                p2=math.radians(meta['official_lat']);p1=np.deg2rad(lat)
                aa=np.sin((p1-p2)/2)**2+np.cos(p1)*math.cos(p2)*np.sin(np.deg2rad(lon-meta['official_lon'])/2)**2
                dist=2*6371000*np.arcsin(np.sqrt(np.clip(aa,0,1)))
                j,i=map(int,np.unravel_index(dist.argmin(),dist.shape))
                edges=min(j,i,59-j,72-i)
                assert edges>=5, 'station inside lateral boundary strip'
                assert i+1=={'gwn':11,'psu':41,'bon':13}[station] and j+1=={'gwn':24,'psu':53,'bon':46}[station]
                grids[station]={'i_zero_based':i,'j_zero_based':j,'cells_to_nearest_edge':edges,'spec_bdy_width':5,
                                'inside_boundary_zone':False,'lat':float(lat[j,i]),'lon':float(lon[j,i]),
                                'station':meta,'distance_m':float(dist[j,i]),'HGT_m':float(d['HGT'][0,j,i]),
                                'LANDMASK':float(d['LANDMASK'][0,j,i])}
                values[station]={}
                for name in ['ACSWDNB','ACSWUPB','ACLWDNB','ACSWDNBC','ACLWDNBC']:
                    assert d[name].units=='J m-2'
                    a=np.asarray(d[name][:,j,i],float)
                    assert np.isfinite(a).all() and np.all(np.diff(a)>=0)
                    values[station][name]=a.tolist()
            out['arms'][arm]={'history':pin(history),'execution_receipt':pin(receipt),'stage_receipt':pin(stage),
                             'wrfinput':pin(case/'wrfinput_d01'),'wrfbdy':pin(case/'wrfbdy_d01'),
                             'namelist':(case/'namelist.input').read_text(),'namelist_sha256':sha(case/'namelist.input'),
                             'executable':pin(case/'wrf.exe'),'build_receipt':s['build_receipt'],
                             'runtime':s['runtime'],'Times':times,'grid':grids,'accumulators_J_m2':values,
                             'attributes':{name:float(d.getncattr(name)) for name in ['DX','DY','DT','MP_PHYSICS','RA_LW_PHYSICS','RA_SW_PHYSICS']}}
    assert out['arms']['ra4']['wrfinput']['sha256']==out['arms']['ra37']['wrfinput']['sha256']
    assert out['arms']['ra4']['wrfbdy']['sha256']==out['arms']['ra37']['wrfbdy']['sha256']
    assert out['arms']['ra4']['grid']==out['arms']['ra37']['grid']
    (root/'model-extract.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')


def hourly(rows, start):
    times=[start+dt.timedelta(seconds=180*k) for k in range(1,21)]
    selected=[rows.get(t) for t in times]
    result={'present':sum(r is not None for r in selected)}
    for name in ['sw_components','sw_global','lw_down','net_sw_components','net_sw_global']:
        values=[]
        for r in selected:
            if r is None:continue
            indices={'sw_components':[12,14],'sw_global':[8],'lw_down':[16],
                     'net_sw_components':[12,14,10],'net_sw_global':[8,10]}[name]
            if not all(r[k+1]==0 and math.isfinite(r[k]) and r[k]!=-9999.9 for k in indices):continue
            direct=r[12]*max(0.0,math.cos(math.radians(r[7])))
            values.append({'sw_components':direct+r[14],'sw_global':r[8],'lw_down':r[16],
                           'net_sw_components':direct+r[14]-r[10],'net_sw_global':r[8]-r[10]}[name])
        result[name]=float(sum(values)/20) if len(values)==20 else None
        result[name+'_qc0_samples']=len(values)
    result['daylight_samples']=sum(r[7]<90 for r in selected if r is not None)
    result['daylight_hour']=result['daylight_samples']>=10
    return result


def stats(rows, field, subset):
    chosen=[r for r in rows if r[field] is not None and (subset=='all' or r['daylight_hour'])]
    out={'n_hours':len(chosen)}
    modelname={'sw_components':'down_sw','sw_global':'down_sw','lw_down':'down_lw',
               'net_sw_components':'net_sw','net_sw_global':'net_sw'}[field]
    y=np.array([r[field] for r in chosen]);assert len(y)>0
    for arm in ['ra4','ra37']:
        x=np.array([r[arm+'_'+modelname] for r in chosen]);e=x-y
        out[arm]={'observation_mean_W_m2':float(y.mean()),'model_mean_W_m2':float(x.mean()),
                  'bias_W_m2':float(e.mean()),'MAE_W_m2':float(np.abs(e).mean()),
                  'RMSE_W_m2':float(np.sqrt(np.mean(e**2))),'max_abs_error_W_m2':float(np.abs(e).max())}
    out['ra37_minus_ra4_mean_W_m2']=out['ra37']['model_mean_W_m2']-out['ra4']['model_mean_W_m2']
    return out


def analyze(root):
    obs.verify_pins(root)
    model=json.loads((root/'model-extract.json').read_text())
    allrows=[];summary={}
    for station in obs.STATIONS:
        rows={}
        for day in [24,25]:
            _,daily=obs.parse_daily_text((root/'raw'/f'{station}000{day}.dat').read_text(),station,dt.datetime(2000,1,day))
            for row in daily:
                assert row['time'] not in rows
                assert math.isfinite(row['values'][7]) and 0<=row['values'][7]<=180
                rows[row['time']]=row['values']
        assert sum(obs.START<t<=obs.END for t in rows)==480
        items=[]
        for h in range(24):
            start=obs.START+dt.timedelta(hours=h)
            item={'station':station,'start_utc':start.isoformat(),'end_utc':(start+dt.timedelta(hours=1)).isoformat(),**hourly(rows,start)}
            for arm in ['ra4','ra37']:
                ac=model['arms'][arm]['accumulators_J_m2'][station]
                assert all(len(v)==25 for v in ac.values())
                delta={name:(v[h+1]-v[h])/3600 for name,v in ac.items()}
                item[arm+'_down_sw']=delta['ACSWDNB'];item[arm+'_down_lw']=delta['ACLWDNB']
                item[arm+'_net_sw']=delta['ACSWDNB']-delta['ACSWUPB']
                item[arm+'_clear_down_sw']=delta['ACSWDNBC'];item[arm+'_clear_down_lw']=delta['ACLWDNBC']
                item[arm+'_model_sw_cloud_effect']=delta['ACSWDNB']-delta['ACSWDNBC']
                item[arm+'_model_lw_cloud_effect']=delta['ACLWDNB']-delta['ACLWDNBC']
            items.append(item)
        summary[station]={field:{subset:stats(items,field,subset) for subset in ['all','daylight']}
                          for field in ['sw_components','sw_global','lw_down','net_sw_components','net_sw_global']}
        allrows+=items
    with (root/'hourly-comparison.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(allrows[0]),lineterminator='\n');w.writeheader();w.writerows(allrows)
    cloud_effects={s:{arm:{name:float(np.mean([r[arm+'_model_'+name+'_cloud_effect'] for r in allrows if r['station']==s]))
                          for name in ['sw','lw']} for arm in ['ra4','ra37']} for s in obs.STATIONS}
    result={'schema':'winter-surfrad-full24h-v1','status':'DESCRIPTIVE_INTERIOR_THREE_STATIONS_ONE_EVENT',
            'new_model_solver_build_calls':0,'window':[obs.START.isoformat(),obs.END.isoformat()],
            'model_extract_sha256':sha(root/'model-extract.json'),'station_periods':3*480,
            'station_hour_bins':3*24,'metrics':summary,
            'model_all_minus_clear_mean_W_m2':cloud_effects,
            'limits':['One winter day and three point-to-30km-grid sites; all outside specified boundary strip but no independence from domain forcing.',
                      'Existing experimental frozen1 paired coupled trajectories; no same-state causal engine attribution or general winner claim.',
                      'Primary SW = projected DNI + diffuse; signed QC0 values preserved, no missing/QC fallback or interpolation.',
                      'Measured PSP and its corresponding net-SW reference are separate secondary diagnostics.',
                      'Three-minute-period central SZA projection is an estimate; not an exact integral of instantaneous DNI.',
                      'Float32 native accumulators have storage quantization; differences computed in float64.',
                      'Model, gas/LUT, frozen PSD, radius and occurrence assumptions are not validated just by observation scores.',
                      'Model all-minus-clear fluxes diagnose its own cloud-radiative contribution, not observed clouds or the cause of an observation bias.',
                      'Metrics have no significance/confidence claims from temporally/spatially correlated samples.']}
    (root/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);p.add_argument('--extract-from-pair',type=Path)
    a=p.parse_args()
    if a.extract_from_pair:extract(a.extract_from_pair,a.root)
    r=analyze(a.root)
    print(json.dumps({'status':r['status'],'metrics':{s:{f:r['metrics'][s][f]['all'] for f in ['sw_components','lw_down']} for s in r['metrics']}},indent=2))


if __name__=='__main__':main()
