#!/usr/bin/env python3
"""Semantic boundaries of retained clipping-contribution and source analysis."""
from pathlib import Path
from functools import lru_cache
import gzip,importlib.util,json,unittest
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
s=importlib.util.spec_from_file_location('exposure_analysis',B/'analyze_saved.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
@lru_cache(None)
def read(n):return gzip.decompress((B/'saved'/(n+'.gz')).read_bytes())
refs=json.loads((B/'prior-evidence.json').read_text())
@lru_cache(None)
def prior(n):return gzip.decompress((ROOT/refs[n]['path']).read_bytes())
def replace_field(data,kind,name,index,value):
    _,fields=m.parser.trace(data,kind);fields[name]['values'][index]=value
    lines=data.decode().splitlines()[:2]
    for key,row in fields.items():
        lines.append(key+' '+' '.join(map(str,row['shape'])))
        lines.extend(format(x,'.17e') for x in row['values'])
    return ('\n'.join(lines)+'\n').encode()
class Boundaries(unittest.TestCase):
    def test_retained_contributions_and_source_window(self):
        r=m.analyze(read,prior)
        self.assertFalse(r['production_accepted'])
        self.assertGreater(r['exposure']['day_11']['categories']['high']['path_time_fraction'],0.08)
        self.assertFalse(r['bounded_source_windows']['window_11']['daily_residual_approved_or_corrected'])
    def test_selected_source_clock(self):
        target='capture/day_peak/lw.raw'
        def altered(n):
            data=read(n)
            if n==target:data=data.replace(b'6.5100000000000000E+004',b'6.5070000000000000E+004',1)
            return data
        self.assertNotEqual(altered(target),read(target))
        with self.assertRaisesRegex(ValueError,'selected capture clock differs'):m.analyze(altered,prior)
    def test_removal_cannot_change_unselected_liquid_layer(self):
        target='attribution/day_peak_sw_omit_high/sw.input'
        def altered(n):
            return replace_field(read(n),'input','LWP',3,1.) if n==target else read(n)
        with self.assertRaisesRegex(ValueError,'liquid removal scope differs'):m.analyze(altered,prior)
    def test_mass_bridge_cannot_hide_a_mixing_ratio_change(self):
        target='water/window_11.stdout'
        def altered(n):
            if n!=target:return read(n)
            lines=read(n).decode().splitlines()
            for i,l in enumerate(lines):
                words=l.split()
                if words and words[0]=='MB_POST':
                    words[9]=str(float(words[9])+1.e-4);lines[i]=' '.join(words);break
            return ('\n'.join(lines)+'\n').encode()
        with self.assertRaisesRegex(ValueError,'inventory bridge unexpectedly changes mixing ratio'):m.analyze(altered,prior)
if __name__=='__main__':unittest.main()
