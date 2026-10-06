#!/usr/bin/env python3
"""Focused saved-RAW bootstrap mapping controls; no models or replay calls."""
import sys
sys.dont_write_bytecode = True
import unittest
import numpy as np
from test_column_replay import ReplayError, startup_snow_radius_mapping


def records():
    native=np.array([25.e-6,999.e-6,0.,0.],dtype=np.float32).astype(np.float64)
    selected=(native.astype(np.float32)*np.float32(1.e6)).astype(np.float64)
    selected[2:]=np.array([80.e-6,9.99e-6],dtype=np.float32).astype(np.float64)*1.e6
    return {'HOST_REAL_BITS':np.array([32.]),'SOURCE_DRY_RHO':np.array([1.,.7,.5,1.]),
            'STARTUP_SNOW_BOOTSTRAP':np.array([1.,1.,0.,0.]),
            'STARTUP_SNOW_RADIUS_M':native,
            'SOURCE_RE_SNOW':np.array([9.99e-6,9.99e-6,80.e-6,9.99e-6],dtype=np.float32).astype(np.float64),
            'QS':np.array([1.e-30,.1,.001,0.]),'CF':np.ones(4),
            'HAS_REQS':np.array([1.]),'ICLOUD':np.array([1.]),'MP_PHYSICS':np.array([27.]),'RES':selected}


class Mapping(unittest.TestCase):
    def test_valid_native_origin_and_float32_units(self):
        raw=records();result=startup_snow_radius_mapping(raw,4,'LW')
        self.assertTrue(np.array_equal(result[1],np.array([True,True,False,False])))
        self.assertTrue(np.array_equal(result[0][:2],raw['RES'][:2]))

    def test_real64_host_mapping(self):
        raw=records();raw['HOST_REAL_BITS'][0]=64.
        raw['STARTUP_SNOW_RADIUS_M']=np.array([25.e-6,999.e-6,0.,0.])
        raw['SOURCE_RE_SNOW']=np.array([9.99e-6,9.99e-6,80.e-6,9.99e-6])
        raw['RES'][:2]=raw['STARTUP_SNOW_RADIUS_M'][:2]*1.e6
        result=startup_snow_radius_mapping(raw,4,'SW')
        self.assertTrue(np.array_equal(result[0][:2],raw['RES'][:2]))
        # A REAL64 near-background value must not become a REAL32 sentinel.
        raw['SOURCE_RE_SNOW'][0]=np.nextafter(9.99e-6,np.inf)
        raw['STARTUP_SNOW_BOOTSTRAP'][0]=0.
        raw['STARTUP_SNOW_RADIUS_M'][0]=0.
        raw['RES'][0]=raw['SOURCE_RE_SNOW'][0]*1.e6
        self.assertFalse(startup_snow_radius_mapping(raw,4,'SW')[1][0])

    def test_invalid_host_kind(self):
        for value in [16.,np.nan,32.5]:
            raw=records();raw['HOST_REAL_BITS'][0]=value
            with self.assertRaises(ReplayError):startup_snow_radius_mapping(raw,4,'LW')

    def test_historical_absent_bundle(self):
        self.assertIsNone(startup_snow_radius_mapping({'RES':np.array([10.])},1,'SW'))

    def test_partial_bundle(self):
        raw=records();del raw['SOURCE_DRY_RHO']
        with self.assertRaises(ReplayError):startup_snow_radius_mapping(raw,4,'LW')

    def test_bad_mask(self):
        for value in [0.,.5,2.]:
            raw=records();raw['STARTUP_SNOW_BOOTSTRAP'][0]=value
            with self.assertRaises(ReplayError):startup_snow_radius_mapping(raw,4,'LW')

    def test_clear_mask_cannot_claim_bootstrap(self):
        for field in ['CF','ICLOUD']:
            raw=records();raw[field][:]=0.
            with self.assertRaises(ReplayError):startup_snow_radius_mapping(raw,4,'SW')

    def test_invalid_dryrho(self):
        for value in [0.,-1.,np.nan,np.inf]:
            raw=records();raw['SOURCE_DRY_RHO'][0]=value
            with self.assertRaises(ReplayError):startup_snow_radius_mapping(raw,4,'LW')

    def test_wrong_native_radius_or_shape(self):
        for value in [10.e-6,1000.e-6,np.nan]:
            raw=records();raw['STARTUP_SNOW_RADIUS_M'][0]=value
            with self.assertRaises(ReplayError):startup_snow_radius_mapping(raw,4,'SW')
        raw=records();raw['STARTUP_SNOW_RADIUS_M']=np.zeros(3)
        with self.assertRaises(ReplayError):startup_snow_radius_mapping(raw,4,'SW')

    def test_inactive_diagnostic_must_be_zero(self):
        raw=records();raw['STARTUP_SNOW_RADIUS_M'][2]=50.e-6
        with self.assertRaises(ReplayError):startup_snow_radius_mapping(raw,4,'SW')

    def test_native_mapping_not_selected_res_echo(self):
        raw=records();raw['RES'][0]=10.
        with self.assertRaises(ReplayError):startup_snow_radius_mapping(raw,4,'LW')
        raw=records();raw['STARTUP_SNOW_RADIUS_M'][0]=float(np.float32(30.e-6))
        with self.assertRaises(ReplayError):startup_snow_radius_mapping(raw,4,'LW')

    def test_wrong_native_scheme(self):
        raw=records();raw['MP_PHYSICS'][0]=4.
        with self.assertRaises(ReplayError):startup_snow_radius_mapping(raw,4,'LW')

if __name__=='__main__':unittest.main()
