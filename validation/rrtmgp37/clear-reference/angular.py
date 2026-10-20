#!/usr/bin/env python3
"""Execute independent Python angular quadrature on exact upstream LW gas/source arrays."""
from pathlib import Path
import importlib.util,json,math,hashlib
import numpy as np
from scipy.special import roots_jacobi
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-clear-reference-run-v4'
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ana=load('ana',R/'validation/rrtmgp37/same-state-engines/analyze_saved.py')
a=load('angular',R/'validation/rrtmgp37/bon-night-common-angle/analysis/angular_reference.py')
plan=json.loads((P/'plan.json').read_text());report={'scope':plan['scope'],'port':{},'self_test':a.self_test(),'production_accepted':False}
for ph in ['lw','sw']:
 up,dn,col=[np.fromstring(x,sep=' ') for x in (O/ph/'flux.dat').read_text().splitlines()]
 _,res=ana.parse37((B/'udm37-same-state-run-v1'/f'{ph}_clear/capture/{ph}.result').read_bytes(),'result')
 err=max(float(np.max(abs(up-res['UP_WP']['values']))),float(np.max(abs(dn-res['DN_WP']['values']))))
 ce=float(np.max(abs(col/np.asarray(res['GAS_COL_DRY']['values'])-1)))
 report['port'][ph]={'max_flux_abs_W_m2':err,'max_molecule_relative_difference':ce,'pass':bool(err<=plan['port_screen_absolute_W_m2'] and ce<=64*np.finfo(float).eps)}
 assert report['port'][ph]['pass'],report['port'][ph]
ls=(O/'lw/source.dat').read_text().splitlines();nl,ng=map(int,ls[0].split());assert (nl,ng)==(121,128)
tau=np.fromstring(ls[1],sep=' ').reshape(nl,ng,order='F');lay=np.fromstring(ls[2],sep=' ').reshape(nl,ng,order='F');lev=np.fromstring(ls[3],sep=' ').reshape(nl+1,ng,order='F');surf=np.fromstring(ls[4],sep=' ')
i=(O/'lw/input.dat').read_text().splitlines();pe=np.asarray(list(map(float,i[3].split())),dtype=np.float32).astype(float);grav,cp=map(float,i[1].split()[:2]);grav=float(np.float32(grav));cp=float(np.float32(cp));emis=np.full(ng,float(np.float32(i[7].split()[0])))
u,d,_=[np.fromstring(x,sep=' ') for x in (O/'lw/flux.dat').read_text().splitlines()]
# Tau/source must also reproduce saved adapter optics (not just broadband flux).
_,res=ana.parse37((B/'udm37-same-state-run-v1/lw_clear/capture/lw.result').read_bytes(),'result')
tau_error=float(np.max(abs(tau.ravel(order='F')-res['GAS_TAU']['values'])))
assert np.allclose(tau.ravel(order='F'),res['GAS_TAU']['values'],rtol=64*np.finfo(float).eps,atol=0)
one=a.angular_result([.6096748751],[1.],tau,lay,lev,surf,emis,pe,grav,cp)
err=max(float(np.max(abs(one[0]-u))),float(np.max(abs(one[1]-d))))
assert err<=plan['angular_reconstruction_absolute_W_m2'],err
report['one_angle_reconstruction_max_W_m2']=err
trace=[];history=[];prev=None;final=None
for n in plan['angular_orders']:
 x,w=roots_jacobi(n,0,1);out=a.angular_result((x+1)/2,w/2,tau,lay,lev,surf,emis,pe,grav,cp)
 changes=None if prev is None else [float(np.max(abs(x-y))) for x,y in zip(out,prev)]
 history.append({'order':n,'up':out[0].tolist(),'dn':out[1].tolist(),'pressure_heat_K_day':out[2].tolist()})
 trace.append({'order':n,'successive_up_down_W_m2_heat_K_day':changes})
 if changes is not None and max(changes)<=plan['angular_successive_flux_screen_W_m2']:
  final=out;break
 prev=out
assert final is not None,'angular screen not reached'
# Preserve signed full-grid arrays, common-capacity native heating and same-location diagnostics.
_,v4=ana.native4((O/'lw/native4.txt').read_bytes());c=np.asarray(v4['Cstar'])
def targets(up,dn):
 net=dn-up;q=np.diff(net)
 return {'surface_up_down_net':[float(up[0]),float(dn[0]),float(net[0])],'native_top_up_down_net':[float(up[59]),float(dn[59]),float(net[59])],'native_column_convergence':float(net[59]-net[0]),'native_common_heat_K_day':(q[:59]/c*86400).tolist()}
ref=targets(*final[:2]);native=targets(u,d);legacy=targets(np.asarray(v4['UP']),np.asarray(v4['DN']))
report.update(angular_trace=trace,conditional_reference=ref,upstream_one_angle=native,legacy4=legacy,source_tau_matches_adapter_within_float64_arithmetic=True, max_tau_abs_difference=tau_error)
arrays={'one_up':u.tolist(),'one_dn':d.tolist(),'reference_up':final[0].tolist(),'reference_dn':final[1].tolist(),'reference_pressure_heat_K_day':final[2].tolist(),'one_pressure_heat_K_day':one[2].tolist()}
(O/'angular-history.json').write_text(json.dumps(history,indent=2)+'\n')
(O/'angular-arrays.json').write_text(json.dumps(arrays,indent=2)+'\n');(O/'analysis.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ['conditional_reference','upstream_one_angle','legacy4']},indent=2))
print('native top DN: 37-one, angular, 4',d[59],final[1][59],v4['DN'][59])
