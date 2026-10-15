"""Prepare three explicit final-PSD public-column inputs; no production radius change."""
from pathlib import Path
import argparse,json,importlib.util,math,numpy as np,netCDF4,shutil
ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--capture',type=Path,required=True);ap.add_argument('--workdir',type=Path,required=True);ap.add_argument('--netcdf-prefix',type=Path,required=True);a=ap.parse_args();r=a.root.resolve();out=a.workdir.resolve();out.mkdir();(out/'src').mkdir()
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v=load(r/'validation/rrtmgp37/radiation-occurrence-runtime/verify_saved.py','parser');capture=a.capture.resolve();records=[]
x,w=np.polynomial.laguerre.laggauss(64);kshape=8.;effective_variance=.1
for phase in ('lw','sw'):
 header,inp=v.trace((capture/(phase+'.input')).read_bytes(),'input');_,raw=v.trace((capture/(phase+'.raw')).read_bytes(),'raw');nl=header[2];cf=inp['CF']['values'];native=inp['REL']['values'];volume=list(native);gamma=list(native);rows=[]
 qc=raw['SOURCE_QC']['values'];eta=raw['SOURCE_QNC']['values'];rho=raw['SOURCE_DRY_RHO']['values']
 for k,(q,n,d) in enumerate(zip(qc,eta,rho)):
  row={'native_level':k+1,'qc_grid_kg_kg':q,'eta_grid_kg_dry_inverse':n,'rho_d_kg_m3':d,'native_input_rel_um':native[k]}
  if k==len(qc)-1:
   row.update(status='EXCLUDED_NONADVANCED_UDM_TOP',native_radius_retained_for_unrepresented_state=True)
  elif q>0. and n>0. and d>0.:
   M0=d*n;M3=3*d*q/(4*math.pi*1000.);lam=(M0*kshape*(kshape+1)*(kshape+2)/M3)**(1/3);M2=M0*kshape*(kshape+1)/lam**2;reff=M3/M2;rv=(M3/M0)**(1/3)
   quadM2=M0*float(np.sum(w*x**(kshape+1)))/math.gamma(kshape)/lam**2
   quadM3=M0*float(np.sum(w*x**(kshape+2)))/math.gamma(kshape)/lam**3
   assert math.isclose(M2,quadM2,rel_tol=5e-12) and math.isclose(M3,quadM3,rel_tol=5e-12)
   volume[k]=rv*1e6;gamma[k]=reff*1e6
   row.update(status='APPLICABLE_EXPLICIT_GAMMA',M0_grid_m_minus3=M0,M2_grid_m_minus1=M2,M3_grid=M3,lambda_m_minus1=lam,rv_um=rv*1e6,reff_um=reff*1e6,M2_independent_quadrature=quadM2,M3_independent_quadrature=quadM3,geometric_mass_extinction_m2_g=3/(2*1000*reff)/1000)
  else:row.update(status='ABSENT' if q==0. else 'UNSUPPORTED_NONPOSITIVE_M0_OR_M3',native_radius_retained_for_unrepresented_state=True)
  rows.append(row)
 # Independent geometric-optics limit comparison in visible SW bands only.
 if phase=='sw':
  with netCDF4.Dataset(r/'WRF/run/rrtmgp-clouds-sw-bnd.nc') as d:
   grid=np.linspace(float(d['radliq_lwr'][:]),float(d['radliq_upr'][:]),d['extliq'].shape[-1]);bands=d['bnd_limits_wavenumber'][:];ext=d['extliq'][:]
   for row in rows:
    if row['status']!='APPLICABLE_EXPLICIT_GAMMA':continue
    re=row['reff_um'];row['LUT_coordinate_clipped']=not(grid[0]<=re<=grid[-1]);row['visible_geometric_limit_comparison']=[]
    for ib,bnd in enumerate(bands):
     if float(bnd[0])>=12850:
      lut=float(np.interp(re,grid,ext[ib]));geo=row['geometric_mass_extinction_m2_g'];row['visible_geometric_limit_comparison'].append({'band':ib+1,'fixed_LUT_ext_m2_g':lut,'geometric_limit_ext_m2_g':geo,'relative_difference':(geo-lut)/lut})
 records.append({'phase':phase.upper(),'source_time_seconds':raw['SOURCE_TIME_SECONDS']['values'][0],'records':rows})
 for mode,rel in [('native',native),('volume_sync',volume),('gamma_v01',gamma)]:
  d=out/(phase+'-'+mode);d.mkdir();modified={name:dict(val) for name,val in inp.items()};modified['REL']={'shape':inp['REL']['shape'],'values':rel}
  for key,new in [('UNIFORM_LWP','UNIFORM_CF0_LWP'),('UNIFORM_RWP','UNIFORM_CF0_RWP')]:modified[key]={'shape':(1,nl),'values':raw[new]['values']+[0.]*(nl-len(qc))}
  text='RRTMGP_REPLAY_V12\n'+' '.join(map(str,header))+'\n'
  for name,row in modified.items():text+=name+' '+' '.join(map(str,row['shape']))+'\n'+''.join(f'{z:.17e}\n' for z in row['values'])
  (d/'input').write_text(text)
(out/'moments.json').write_text(json.dumps({'candidate':'final-liquid-gamma-veff-0p1-v1','effective_variance':effective_variance,'number_gamma_shape_k':kshape,'density_water_kg_m3':1000,'shape_is_declared_research_assumption':True,'fixed_LUT_generation_PSD_certified':False,'production_radius_changed':False,'independent_geometric_comparator':'Qext=2 large-size spherical visible limit; not Mie/absorption/flux truth','comparisons':'native vs volume_sync separates consumed radius timing/clipping; volume_sync vs gamma_v01 isolates this explicit final PSD closure','cases':records,'production_accepted':False},indent=2)+'\n')
# Current public column, with explicit uniform residual inputs; no science source patch.
for name in ('module_ra_rrtmgp','module_ra_rrtmgp_input','module_ra_rrtmgp_trace','module_ra_rrtmgp_precip','module_ra_rrtmgp_hash','module_ra_rrtmgp_frozen'):shutil.copyfile(r/'WRF/phys'/(name+'.F'),out/'src'/(name+'.F'))
shutil.copyfile(r/'WRF/test/rrtmgp/standalone_wrf_error.f90',out/'src/standalone_wrf_error.f90')
s=(r/'validation/rrtmgp37/omitted-ice-effect/driver.f90').read_text();s=s.replace('  REAL :: gravity,cp,mw,solar','  REAL,ALLOCATABLE :: ulwp(:,:),urwp(:,:)\n  REAL :: gravity,cp,mw,solar');s=s.replace('  gravity=9.81;','  ALLOCATE(ulwp(1,nl),urwp(1,nl));ulwp=0.;urwp=0.\n  gravity=9.81;');s=s.replace("    CASE('PLAY')", "    CASE('UNIFORM_LWP');ulwp=RESHAPE(values,SHAPE(ulwp))\n    CASE('UNIFORM_RWP');urwp=RESHAPE(values,SHAPE(urwp))\n    CASE('PLAY')");s=s.replace('frozen_optics=0)','frozen_optics=0,uniform_clear_warm=.true.)');s=s.replace('ccl4vmr=ccl4)','ccl4vmr=ccl4,uniform_lwp=ulwp,uniform_rwp=urwp)')
# SW call ends with nir diagnostics rather than CFC arguments.
a='nirdir_unscaled=pn)';assert a in s;s=s.replace(a,'nirdir_unscaled=pn,uniform_lwp=ulwp,uniform_rwp=urwp)')
(out/'src/driver.f90').write_text(s)
cmake=f'''cmake_minimum_required(VERSION 3.20)
project(CF0_FINAL_PSD LANGUAGES Fortran)
add_compile_options(-ffree-form -ffree-line-length-none)
add_subdirectory("{r}/WRF/external/rte_rrtmgp" rte)
add_library(helpers STATIC src/standalone_wrf_error.f90 src/module_ra_rrtmgp_trace.F src/module_ra_rrtmgp_input.F src/module_ra_rrtmgp_precip.F src/module_ra_rrtmgp_hash.F src/module_ra_rrtmgp_frozen.F)
set_target_properties(helpers PROPERTIES Fortran_MODULE_DIRECTORY "${{CMAKE_BINARY_DIR}}/helper-modules")
file(MAKE_DIRECTORY "${{CMAKE_BINARY_DIR}}/helper-modules")
target_include_directories(helpers PUBLIC "${{CMAKE_BINARY_DIR}}/helper-modules" "{a.netcdf_prefix.resolve()}/include")
target_link_libraries(helpers PUBLIC wrf_rrtmgp)
add_library(adapter STATIC src/module_ra_rrtmgp.F)
set_target_properties(adapter PROPERTIES Fortran_MODULE_DIRECTORY "${{CMAKE_BINARY_DIR}}/adapter-modules")
file(MAKE_DIRECTORY "${{CMAKE_BINARY_DIR}}/adapter-modules")
target_include_directories(adapter PUBLIC "${{CMAKE_BINARY_DIR}}/adapter-modules")
target_link_libraries(adapter PUBLIC helpers)
add_executable(column src/driver.f90)
target_link_libraries(column PRIVATE adapter)
'''
(out/'CMakeLists.txt').write_text(cmake);print(out)
