#!/usr/bin/env python3
import unittest,gzip,struct,importlib.util
from pathlib import Path
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('final_core_test',BASE/'verify_core.py');core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
class Corruption(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace=gzip.decompress((BASE/'trace.txt.gz').read_bytes()).decode();cls.header=gzip.decompress((BASE/'excerpts/panel14_header.bin.gz').read_bytes());cls.data=gzip.decompress((BASE/'excerpts/panel14_OD.bin.gz').read_bytes())
    def mutate(self,tag,index,value):
        rows=self.trace.splitlines();n=next(i for i,r in enumerate(rows) if r.split()[0]==tag);a=rows[n].split();a[5+index]=repr(value);rows[n]=' '.join(a);return '\n'.join(rows)+'\n'
    def reject(self,trace=None,header=None,data=None):
        with self.assertRaises(ValueError):core.analyze(trace or self.trace,header or self.header,data or self.data)
    def test_missing_mutation(self):
        self.reject(trace='\n'.join(x for x in self.trace.splitlines() if not x.startswith('RAD_MULT 18 '))+'\n')
    def test_continuum_stencil(self):self.reject(trace=self.mutate('XINT_EXTRA',14,1.0))
    def test_wrong_physical_grid(self):self.reject(trace=self.mutate('PRE_PANEL',0,618.0))
    def test_wrong_R2_deposit(self):self.reject(trace=self.mutate('POST_R2',40,0.0))
    def test_wrong_radiation_multiplier(self):self.reject(trace=self.mutate('RAD_MULT',3,1.0))
    def test_actual_OD_payload(self):
        data=bytearray(self.data);x=struct.unpack_from('<d',data,272*8)[0];import math
        struct.pack_into('<d',data,272*8,math.nextafter(x,math.inf));self.reject(data=bytes(data))
if __name__=='__main__':unittest.main()
