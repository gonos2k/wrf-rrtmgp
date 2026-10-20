#!/usr/bin/env python3
"""Actual small controls of the matched external integration interface."""
from pathlib import Path
import importlib.util,json,math,hashlib
P=Path(__file__).resolve().parent;s=importlib.util.spec_from_file_location('matched_ref_run',P/'run_reference.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
import numpy as np
optics,mie_coeff,average=a.load_external();x,w=a.roots(128);x=(x+1)*40;w=w*40;reff=12.;r=x*reff/10;d=2*r;dw=2*reff/10*w
area=np.pi*r*r;vol=4*np.pi*r**3/3;nu=np.array([10000/1.3]);m=1.33-.01j
e,sc,g=mie_coeff(np.full(128,nu[0]),r,area,np.full(128,m));hi=a.mie.efficiencies(np.full(128,m),2*r,np.full(128,1.3),n_env=1)
assert np.allclose(e/area,hi[0],rtol=1e-12,atol=1e-12) and np.allclose(sc/area,hi[1],rtol=1e-12,atol=1e-12)
z=[]
for rho in [1000.,996.]:z.append(optics.gamma_int(nu,np.array([8.]),d,vol,area,np.array([1.6*reff]),dw,e[None,:],sc[None,:],g[None,:],rho*1000))
rat=float(z[1].ext[0,0]/z[0].ext[0,0]);assert abs(rat-1000/996)<1e-13
# Same spectral moments must use scattering-weighted g, not mean(g).
source=np.array([1.,2.,3.]);sca=np.array([[1.,4.,2.]]);gg=np.array([[.2,.8,.5]])
weighted=float(average(source,sca*gg,(np.arange(3),))[0]/average(source,sca,(np.arange(3),))[0]);direct=float(average(source,gg,(np.arange(3),))[0]);assert abs(weighted-direct)>1e-3
result={'status':'PASS_MATCHED_DEFINITION_CONTROLS','external_functions_actually_called':['mie_coefficients (matched medium/API)','optics_var.gamma_int (unchanged)','convert_lblOD_to_band (unchanged)'],'density_only_actual_ratio_996_over1000':rat,'density_exact_ratio':1000/996,'matched_reconstructed_reff_um':float(z[0].r[0]),'high_level_medium_API_matches_cross_sections':True,'moment_g_control':{'sca_weighted':weighted,'mean_g':direct,'mean_g_is_used_in_reference':False},'no_constructor_projection':True,'source_sha256':hashlib.sha256((P/'run_reference.py').read_bytes()).hexdigest(),'scope':'definition and normalization controls, not an additional independent kernel or atmospheric validation'}
(a.OUT/'definition-controls.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
