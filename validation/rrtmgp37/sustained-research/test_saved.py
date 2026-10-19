#!/usr/bin/env python3
"""Meaningful evidence-boundary checks; no new WRF, RTE or optical solver run."""
import gzip
import importlib.util
from functools import lru_cache
from pathlib import Path
import unittest
B=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('sustained',B/'analyze_saved.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
@lru_cache(None)
def read(name):return gzip.decompress((B/'saved'/(name+'.gz')).read_bytes())
class Boundaries(unittest.TestCase):
    def test_retained(self):
        r=m.analyze(read)
        self.assertEqual(r['restart']['overlap_times'],216)
        self.assertFalse(r['preregistered_full_validation_passed'])
    def test_actual_resume_phase(self):
        target='logs/resumed_11.stdout'
        def changed(name):
            b=read(name)
            if name==target:
                b=b.replace(b'source_time_seconds=2.1630000000000000E+004',b'source_time_seconds=2.1620000000000000E+004',1)
                self.assertNotEqual(b,read(name))
            return b
        with self.assertRaisesRegex(ValueError,'restart call phase changed'):m.analyze(changed)
    def test_same_call_capacity(self):
        target='capture/day_11/lw.result'
        def changed(name):
            b=read(name)
            if name==target:
                lines=b.decode().splitlines();begin=next(i for i,l in enumerate(lines) if 'NATIVE_CAPACITY_J_M2_K' in l)
                # Trace values start on the next line; change one physically positive capacity.
                for i in range(begin+1,len(lines)):
                    words=lines[i].split()
                    if words:
                        try:value=float(words[0])
                        except ValueError:continue
                        words[0]=str(value*1.01);lines[i]=' '.join(words);break
                b=('\n'.join(lines)+'\n').encode()
            return b
        with self.assertRaisesRegex(ValueError,'capacity inputs changed'):m.analyze(changed)
if __name__=='__main__':unittest.main()
