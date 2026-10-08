"""Targeted corruption checks for actual selection-to-write joins."""
import copy,importlib.util,json,unittest
from pathlib import Path
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('saved_use',BASE/'verify_saved.py')
saved=importlib.util.module_from_spec(spec);spec.loader.exec_module(saved)
class Corruption(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.args=saved.load()
    def reject_trace(self,tag,column,value):
        a=list(self.args);rows=a[0].splitlines();i=next(i for i,l in enumerate(rows) if l.startswith(tag+' '));r=rows[i].split();r[column]=value;rows[i]=' '.join(r);a[0]='\n'.join(rows)+'\n'
        with self.assertRaises(ValueError):saved.core.analyze(*a)
    def test_missing_entry(self):
        a=list(self.args);rows=a[0].splitlines();rows.pop(0)
        for i,l in enumerate(rows):r=l.split();r[1]=str(i+1);rows[i]=' '.join(r)
        a[0]='\n'.join(rows)+'\n'
        with self.assertRaises(ValueError):saved.core.analyze(*a)
    def test_wrong_origin(self):self.reject_trace('WRITE',5,'125')
    def test_wrong_clamped_width(self):self.reject_trace('WIDTH',12,'0.1')
    def test_wrong_rejection_reason(self):self.reject_trace('OUTCOME',10,'4')
    def test_changed_actual_TAPE3(self):
        a=list(copy.deepcopy(self.args));key=next(iter(a[2]));raw=bytearray(a[2][key]);raw[0]^=1;a[2][key]=bytes(raw)
        with self.assertRaises(ValueError):saved.core.analyze(*a)
    def test_physical_promotion(self):
        c=json.loads((BASE/'scientific-record-comparison.json').read_text());c['physical_reference_accepted']=True
        with self.assertRaises(ValueError):saved.validate_receipts(c,[])
if __name__=='__main__':unittest.main()
