#!/usr/bin/env python3
"""Offline V10/V11 CU-held input and CF0-sidecar pairing controls; no solver calls."""
from __future__ import annotations
import hashlib
import tempfile
import unittest
from pathlib import Path

from cf0_precip_sidecar import (SidecarError, encode, parse_raw, validate_against_raw,
                                validate_replay_context, parse_input_matrix)


def write_input(path: Path, version: str, phase: str) -> None:
    n=3
    records={
        'CF': [[0.0,0.5,0.0]],
        'RES': [[25.0,26.0,27.0]],
        'NATIVE_DRY_LAYER_MASS_KG_M2': [[1.0,2.0,3.0]],
        'CU_POPULATION_POLICY': [[1.0]], 'CU_RADIUS_POLICY': [[1.0]],
        'CU_OCCURRENCE_POLICY': [[1.0]], 'CU_LWP': [[0.2,0.0,0.3]],
        'CU_IWP': [[0.0,0.1,0.0]], 'CU_REL': [[10.0,10.0,11.0]],
        'CU_REI': [[25.0,26.0,27.0]],
    }
    if phase == 'LW': records['VMR_CFC11']=[[1e-10,1e-10,1e-10]]
    else:
        # Names and scalar are the V11 direct-diagnostic provenance contract.
        records['SW_DIRECT_PREDELTA_POLICY']=[[1.0]]
        for name in ('TOA_GPOINT','RAW_GAS_TAU','MCICA_MASK','RAW_CLOUD_TAU',
                     'RAW_NATIVE_CLOUD_TAU','RAW_CU_CLOUD_TAU','RAW_PRECIP_TAU',
                     'RAW_GRAUPEL_TAU_EXT','RAW_HAIL_TAU_EXT','BAND_LIMS_GPOINT',
                     'BAND_LIMS_WAVENUMBER','VISIBLE_WEIGHT'):
            # Header presence is validated here; matrix shapes are compact fixture placeholders.
            records[name]=[[0.0,1.0,0.0]]
    lines=[version,f'{phase} 1 {n} 0 12345 4']
    for name,rows in records.items():
        flat=[v for row in rows for v in row]
        lines += [f'{name} 1 {len(flat)}',' '.join(f'{v:.17e}' for v in flat)]
    path.write_text('\n'.join(lines)+'\n',encoding='ascii')


def write_raw(path: Path, phase: str):
    records={'CF':[0.0,0.5,0.0], 'RWP_OMITTED':[5.0,0.0,0.0],
             'SWP_OMITTED':[0.0,0.0,2.0], 'RES':[25.0,26.0,27.0],
             'SOURCE_RE_SNOW':[25e-6,26e-6,27e-6], 'HAS_REQS':[1.0],
             'CU_POPULATION_POLICY':[1.0], 'CU_RADIUS_POLICY':[1.0],
             'CU_OCCURRENCE_POLICY':[1.0]}
    lines=['RRTMGP_RAW_V1',f'{phase} 24 55 3']
    for name,values in records.items(): lines += [f'{name} {len(values)}',' '.join(map(str,values))]
    path.write_text('\n'.join(lines)+'\n',encoding='ascii')


class V10V11SidecarTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def fixture(self, phase):
        version='RRTMGP_REPLAY_V10' if phase=='LW' else 'RRTMGP_REPLAY_V11'
        inp=self.root/f'{phase.lower()}.input';raw=self.root/f'{phase.lower()}.raw'
        write_input(inp,version,phase);write_raw(raw,phase)
        return inp,raw
    def test_v10_cu_retained_absent_sidecar_parse(self):
        inp,raw=self.fixture('LW');before=inp.read_bytes(); rawh,records=parse_raw(raw)
        ctx=validate_replay_context(inp,rawh,records,3)
        self.assertEqual(ctx['version'],'RRTMGP_REPLAY_V10')
        self.assertEqual(len(ctx['cu_records_preserved']),7)
        self.assertEqual(inp.read_bytes(),before)
    def test_v11_direct_and_cu_context_accepts_paired_sidecar(self):
        inp,raw=self.fixture('SW');before=inp.read_bytes()
        side=encode('SW',1,3,1,1.0,[[5.0,0.0,0.0]],[[0.0,0.0,0.0]],[[0.0,0.5,0.0]],3)
        result=validate_against_raw(side,raw,'rain',3,inp)
        self.assertEqual(result['replay_context']['version'],'RRTMGP_REPLAY_V11')
        self.assertEqual(result['replay_context']['cu_records_preserved'],[
            'CU_POPULATION_POLICY','CU_RADIUS_POLICY','CU_OCCURRENCE_POLICY','CU_LWP','CU_IWP','CU_REL','CU_REI'])
        self.assertEqual(inp.read_bytes(),before)
    def test_v11_cu_and_direct_parse_without_sidecar(self):
        inp,raw=self.fixture('SW');before=inp.read_bytes();rawh,records=parse_raw(raw)
        ctx=validate_replay_context(inp,rawh,records,3)
        self.assertEqual(ctx['version'],'RRTMGP_REPLAY_V11')
        self.assertEqual(ctx['cu_records_preserved'],[
            'CU_POPULATION_POLICY','CU_RADIUS_POLICY','CU_OCCURRENCE_POLICY',
            'CU_LWP','CU_IWP','CU_REL','CU_REI'])
        self.assertEqual(parse_input_matrix(inp,'SW_DIRECT_PREDELTA_POLICY'),(1,1,[1.0]))
        self.assertEqual(inp.read_bytes(),before)
    def test_v10_rain_matches_raw_and_cu_bytes_remain(self):
        inp,raw=self.fixture('LW');before=hashlib.sha256(inp.read_bytes()).hexdigest()
        side=encode('LW',1,3,1,1.0,[[5.0,0.0,0.0]],[[0.0,0.0,0.0]],[[0.0,0.5,0.0]],3)
        got=validate_against_raw(side,raw,'rain',3,inp)
        self.assertEqual(got['omitted_path_sum_g_m2'],5.0)
        self.assertEqual(hashlib.sha256(inp.read_bytes()).hexdigest(),before)
    def test_reject_wrong_native_prefix(self):
        inp,raw=self.fixture('LW')
        side=encode('LW',1,2,1,1.0,[[5.0,0.0]],[[0.0,0.0]],[[0.0,0.5]],3)
        with self.assertRaises(SidecarError): validate_against_raw(side,raw,'rain',3,inp)
    def test_reject_cf_positive_sidecar_path(self):
        inp,raw=self.fixture('SW')
        with self.assertRaises(SidecarError):
            encode('SW',1,3,1,1.0,[[0.0,4.0,0.0]],[[0.0,0.0,0.0]],[[0.0,0.5,0.0]],3)
    def test_reject_species_mismatch(self):
        inp,raw=self.fixture('LW')
        side=encode('LW',1,3,2,1.0,[[0.0,0.0,0.0]],[[0.0,0.0,2.0]],[[0.0,0.5,0.0]],3)
        with self.assertRaises(SidecarError): validate_against_raw(side,raw,'rain',3,inp)
    def test_reject_wrong_raw_path_pair(self):
        inp,raw=self.fixture('SW')
        side=encode('SW',1,3,1,1.0,[[6.0,0.0,0.0]],[[0.0,0.0,0.0]],[[0.0,0.5,0.0]],3)
        with self.assertRaises(SidecarError): validate_against_raw(side,raw,'rain',3,inp)
    def test_reject_v11_missing_direct_metadata(self):
        inp,raw=self.fixture('SW')
        text=inp.read_text().replace('SW_DIRECT_PREDELTA_POLICY 1 1\n1.00000000000000000e+00\n','')
        inp.write_text(text)
        from cf0_precip_sidecar import parse_raw
        rawh,raw_records=parse_raw(raw)
        with self.assertRaises(SidecarError): validate_replay_context(inp,rawh,raw_records,3)

if __name__=='__main__': unittest.main(verbosity=2)
