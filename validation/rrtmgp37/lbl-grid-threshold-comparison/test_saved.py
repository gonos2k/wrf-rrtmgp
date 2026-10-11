"""Six boundary-specific negative controls on the actual executed evidence."""
from pathlib import Path
import gzip,importlib.util,json,struct,unittest
from unittest.mock import patch
B=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('saved_grid',B/'verify_saved.py');v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
c=v.c
class Rejections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        meta=v.loadj('TAPE3-readback.json')
        cls.blocks={str(n):v.raw(f'TAPE3/{n}.bin.gz') for n in meta['data_records']}
        cls.trace=v.raw('traces/h.layer.gz').decode();cls.minimum=v.raw('traces/h.min.gz').decode()
    def mutated(self,field,value):
        lines=self.trace.splitlines();a=lines[0].split();a[10+field]=str(value);lines[0]=' '.join(a)
        return '\n'.join(lines)+'\n'
    def test_actual_DV_ratio(self):
        with self.assertRaisesRegex(ValueError,'DV'):
            c.analyze_arm(self.mutated(3,c.H/2),self.minimum,self.blocks,'h')
    def test_wrong_physical_sample(self):
        r=v.loadj('samples.json')['h'][40]
        with self.assertRaisesRegex(ValueError,'physical coordinate'):
            c.sample_od(v.raw(f"OD/h.{r['panel']}.header.gz"),v.raw(f"OD/h.{r['panel']}.payload.gz"),r['nu']+.0001)
    def test_zero_threshold_claim(self):
        lines=v.raw('traces/weak0.layer.gz').decode().splitlines();a=lines[0].split();a[21]=str(2e-4/2250);lines[0]=' '.join(a)
        with self.assertRaisesRegex(ValueError,'threshold'):
            c.analyze_arm('\n'.join(lines)+'\n',v.raw('traces/weak0.min.gz').decode(),self.blocks,'weak0')
    def test_missing_target_write(self):
        lines=self.trace.splitlines();k=next(i for i,x in enumerate(lines) if x.startswith('WRITE '));del lines[k]
        for i in range(k,len(lines)):
            a=lines[i].split();a[1]=str(i+1);lines[i]=' '.join(a)
        with self.assertRaisesRegex(ValueError,'all actual target CN writes'):
            c.analyze_arm('\n'.join(lines)+'\n',self.minimum,self.blocks,'h')
    def test_actual_OD_payload_changed(self):
        r=v.loadj('samples.json')['h'][40];path=f"OD/h.{r['panel']}.payload.gz";header=v.raw(f"OD/h.{r['panel']}.header.gz")
        lo,hi,dv,n,pad=struct.unpack('<dddii',header);j=round((r['nu']-lo)/dv);payload=bytearray(v.raw(path))
        x=struct.unpack_from('<Q',payload,8*j)[0];struct.pack_into('<Q',payload,8*j,x+1);original=v.raw
        def corrupt(p):return bytes(payload) if p==path else original(p)
        with patch.object(v,'raw',side_effect=corrupt),self.assertRaisesRegex(ValueError,'computed result'):
            v.replay()
    def test_false_physical_promotion(self):
        original=v.loadj
        def promote(p):
            x=original(p)
            if p=='result.json':x['physical_reference_accepted']=True
            return x
        with patch.object(v,'loadj',side_effect=promote),self.assertRaisesRegex(ValueError,'physical promotion'):
            v.replay()
if __name__=='__main__':unittest.main(verbosity=2)
