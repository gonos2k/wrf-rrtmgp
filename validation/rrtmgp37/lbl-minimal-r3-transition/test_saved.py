import gzip,importlib.util,json,unittest
from pathlib import Path
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('minimal_r3_reader',BASE/'verify_saved.py');reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
class Counterexamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lines=gzip.decompress((BASE/'trace.txt.gz').read_bytes()).decode().splitlines()
        cls.write=next(i for i,x in enumerate(cls.lines) if x.startswith('CN_WRITE '))
    def rejected(self,lines):
        with self.assertRaises(ValueError):reader.analyze('\n'.join(lines))
    def test_missing_actual_write(self):
        self.rejected(self.lines[:self.write]+self.lines[self.write+1:])
    def test_broken_before_state(self):
        lines=list(self.lines);a=lines[self.write].split();a[14]='1.0';lines[self.write]=' '.join(a);self.rejected(lines)
    def test_wrong_physical_frequency(self):
        lines=list(self.lines);a=lines[self.write].split();a[12]=str(float(a[12])+0.1);lines[self.write]=' '.join(a);self.rejected(lines)
    def test_missing_zero_initialization(self):
        lines=list(self.lines);idx=next(i for i,x in enumerate(lines) if x.startswith('CLEAR '));a=lines[idx].split();a[15]='1.0';lines[idx]=' '.join(a);self.rejected(lines)
    def test_false_scientific_equality_receipt(self):
        comparison=json.loads((BASE/'scientific-record-comparison.json').read_text())
        comparison['files'][0]['all_scientific_records_equal']=False
        with self.assertRaises(ValueError):reader.verify_comparison(comparison)
    def test_wrong_scientific_record_total(self):
        comparison=json.loads((BASE/'scientific-record-comparison.json').read_text())
        comparison['scientific_records_total']+=1
        with self.assertRaises(ValueError):reader.verify_comparison(comparison)
if __name__=='__main__':unittest.main()
