"""Meaningful mutations of the newly connected source, size and restart boundaries."""
import unittest
from pathlib import Path
import importlib.util
B=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('verify',B/'verify_saved.py');v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
a=v.load(B/'analyze_saved.py','analysis')

def changed(name,kind,field,index,value):
    x=v.read(name);head=x.decode().splitlines()[:2];_,records=a.parser.trace(x,kind)
    records[field]['values'][index]=value
    lines=head[:]
    for n,z in records.items():
        lines.append(n+' '+' '.join(map(str,z['shape'])))
        lines += [' '.join(format(y,'.17e') for y in z['values'][i:i+6]) for i in range(0,len(z['values']),6)]
    altered=('\n'.join(lines)+'\n').encode()
    return lambda n:altered if n==name else v.read(n)

class Boundaries(unittest.TestCase):
    def test_retained_integration(self):self.assertEqual(v.verify()['status'],'PASS_SCOPED_INTEGRATED_RESEARCH')
    def test_wrong_capacity(self):
        n='host/cloud_11/capture/lw.result';_,z=a.parser.trace(v.read(n),'result')
        with self.assertRaisesRegex(ValueError,'capacity mismatch'):a.analyze(changed(n,'result','NATIVE_CAPACITY_J_M2_K',0,z['NATIVE_CAPACITY_J_M2_K']['values'][0]*1.01))
    def test_wrong_optical_radius(self):
        raw='host/cloud_01/capture/sw.raw';_,z=a.parser.trace(v.read(raw),'raw');k=next(i for i,q in enumerate(z['SOURCE_QC']['values']) if q>0)
        n='host/cloud_01/capture/sw.input';_,z=a.parser.trace(v.read(n),'input')
        with self.assertRaisesRegex(ValueError,'Gamma8 optical radius'):a.analyze(changed(n,'input','REL',k,z['REL']['values'][k]*1.01))
    def test_restart_recalculates_at_checkpoint(self):
        with self.assertRaisesRegex(ValueError,'radiation call phase'):a.analyze(changed('host/resumed_11/capture/lw.raw','raw','SOURCE_TIME_SECONDS',0,20.))
if __name__=='__main__':unittest.main()
