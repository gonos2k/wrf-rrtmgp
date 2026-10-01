#!/usr/bin/env python3
"""Synthetic NetCDF IO/schema fixtures. NOT RRTMGP spectroscopy or validation data."""
from pathlib import Path
import sys
import numpy as np
from scipy.io import netcdf_file

def gas_table(path:Path,kind:str,corrupt:str=''):
    # Array descriptions are in Fortran order; NetCDF-C storage reverses axes.
    dims={'gpt':4,'bnd':2,'pair':2,'atmos_layer':2,'absorber':2,'absorber_ext':3,
          'temperature':3,'pressure':2,'pressure_interp':3,'mixing_fraction':2,
          'minor_absorber':1,'minor_absorber_intervals_lower':1,'minor_absorber_intervals_upper':1,
          'contributors_lower':4,'contributors_upper':4,'string_len':40,
          'temperature_Planck':4,'fit_coeffs':2}
    fields={}
    def add(n,d,v,typ='d'):fields[n]=(d,np.asarray(v),typ)
    def names(n,d,values):
        a=np.full((40,len(values)),b' ',dtype='S1')
        for j,s in enumerate(values):a[:len(s),j]=np.frombuffer(s.encode(),dtype='S1')
        add(n,('string_len',d),a,'c')
    names('gas_names','absorber',['h2o','co2'])
    for n,dd,val in [('gas_minor','minor_absorber','h2o'),('identifier_minor','minor_absorber','h2o_self'),
                      ('minor_gases_lower','minor_absorber_intervals_lower','h2o_self'),
                      ('minor_gases_upper','minor_absorber_intervals_upper','h2o_self'),
                      ('scaling_gas_lower','minor_absorber_intervals_lower',''),
                      ('scaling_gas_upper','minor_absorber_intervals_upper','')]:names(n,dd,[val])
    add('bnd_limits_wavenumber',('pair','bnd'),[[10.,500.],[500.,1000.]])
    add('bnd_limits_gpt',('pair','bnd'),[[1,3],[2,4]],'i')
    key=np.ones((2,2,2),dtype=np.int32);key[1,:,:]=2
    add('key_species',('pair','atmos_layer','bnd'),key,'i')
    add('press_ref',('pressure',),[100000.,10000.]);add('temp_ref',('temperature',),[200.,250.,300.])
    for n,v in [('press_ref_trop',30000.),('absorption_coefficient_ref_P',101325.),('absorption_coefficient_ref_T',296.)]:add(n,(),v)
    add('vmr_ref',('atmos_layer','absorber_ext','temperature'),np.ones((2,3,3)))
    km=np.empty((4,2,3,3))
    for g in range(4):
      for m in range(2):
       for p in range(3):
        for t in range(3):km[g,m,p,t]=1.+g+10*m+100*p+1000*t
    add('kmajor',('gpt','mixing_fraction','pressure_interp','temperature'),km)
    for side in ['lower','upper']:
        di='minor_absorber_intervals_'+side
        add('kminor_'+side,('contributors_'+side,'mixing_fraction','temperature'),np.ones((4,2,3))*0.01)
        add('minor_limits_gpt_'+side,('pair',di),[[1],[4]],'i')
        for name,value in [('kminor_start_',1),('minor_scales_with_density_',0),('scale_by_complement_',1)]:add(name+side,(di,),[value],'i')
        add('rayl_'+side,('gpt','mixing_fraction','temperature'),np.ones((4,2,3))*1.e-8)
    if kind=='lw':
        add('totplnk',('temperature_Planck','bnd'),np.arange(8).reshape((4,2))+1.)
        add('plank_fraction',('gpt','mixing_fraction','pressure_interp','temperature'),np.ones((4,2,3,3))*.25)
        add('optimal_angle_fit',('fit_coeffs','bnd'),np.ones((2,2)))
    else:
        for n,v in [('solar_source_quiet',[200.,300.,400.,461.]),('solar_source_facular',[0.,0.,0.,0.]),('solar_source_sunspot',[0.,0.,0.,0.])]:add(n,('gpt',),v)
        for n,v in [('tsi_default',1361.),('mg_default',0.1495954),('sb_default',0.00066696)]:add(n,(),v)
    if corrupt=='missing':del fields['kmajor']
    if corrupt=='negative':fields['kmajor'][1][0,0,0,0]=-1.
    if corrupt=='default_fill':fields['kmajor'][1][0,0,0,0]=np.float64(9.969209968386869e36)
    if corrupt in ['explicit_fill','missing_attr']:fields['kmajor'][1][0,0,0,0]=123456.
    if corrupt=='nan':fields['kmajor'][1][0,0,0,0]=np.nan
    if corrupt=='pressure':fields['press_ref'][1][:]=[10000.,100000.]
    if corrupt=='bandgap':fields['bnd_limits_gpt'][1][0,1]=4
    if corrupt=='fractional':add('key_species',('pair','atmos_layer','bnd'),np.ones((2,2,2))*1.5)
    if corrupt=='flag':fields['scale_by_complement_lower'][1][0]=2
    if corrupt=='minor_bounds':fields['kminor_start_lower'][1][0]=2
    if corrupt=='rayleigh':del fields['rayl_upper']
    if corrupt=='longname':names('gas_names','absorber',['x'*33,'co2'])
    if corrupt=='rank':add('kmajor',('gpt','mixing_fraction','temperature'),np.ones((4,2,3)))
    with netcdf_file(path,'w',version=2) as f:
        f.fixture_only=np.int32(1);f.history=b'SYNTHETIC IO TEST - NOT REAL RRTMGP COEFFICIENTS'
        for d,n in dims.items():f.createDimension(d,n)
        for n,(ds,a,typ) in fields.items():
            v=f.createVariable(n,typ,tuple(reversed(ds)))
            if n=='kmajor' and corrupt=='explicit_fill':v._FillValue=np.float64(123456.)
            if n=='kmajor' and corrupt=='missing_attr':v.missing_value=np.array([123456.,789.],dtype=np.float64)
            if ds:v[:]=a.transpose(tuple(reversed(range(a.ndim))))
            else:v[...]=a

def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
    for kind in ['lw','sw']:gas_table(out/f'{kind}.nc',kind)
    cases=['missing','negative','nan','pressure','bandgap','fractional','flag','minor_bounds','rayleigh','longname','rank','default_fill','explicit_fill','missing_attr']
    for c in cases:gas_table(out/f'bad_{c}.nc','lw',c)
    (out/'NOTICE.txt').write_text('All files are SYNTHETIC IO/schema fixtures, NOT usable spectroscopy.\n')
if __name__=='__main__':main()
