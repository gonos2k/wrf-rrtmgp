import gzip,importlib.util,json,struct,unittest
from pathlib import Path
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('coeff_core',BASE/'verify_core.py');core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
class TargetedCounterexamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trace=gzip.decompress((BASE/'coeff-trace.txt.gz').read_bytes()).decode()
        cls.data=[gzip.decompress((BASE/'excerpts'/f'{n}.bin.gz').read_bytes()) for n in ('file_header','line_block_header','line_data')]
        cls.first=json.loads((BASE.parent/'lbl-minimal-r3-transition/result.json').read_text())['first_negative']
    def reject(self,trace=None,data=None):
        with self.assertRaises(ValueError):core.analyze(trace or self.trace,*(data or self.data),self.first)
    def test_wrong_species_in_actual_excerpt(self):
        data=list(self.data);b=bytearray(data[2]);struct.pack_into('<i',b,5000+123*4,101);data[2]=bytes(b);self.reject(data=data)
    def test_one_ULP_coupling_sidecar_change(self):
        data=list(self.data);b=bytearray(data[2]);at=8*124;n=struct.unpack_from('<Q',b,at)[0];struct.pack_into('<Q',b,at,n+1);data[2]=bytes(b);self.reject(data=data)
    def test_wrong_coefficient_record_join(self):
        lines=self.trace.splitlines();a=lines[4].split();a[3]='523';lines[4]=' '.join(a);self.reject(trace='\n'.join(lines))
    def test_changed_coupling_STRF3(self):
        lines=self.trace.splitlines();a=lines[4].split();a[9+11]=str(float(a[9+11])*0.99);lines[4]=' '.join(a);self.reject(trace='\n'.join(lines))
    def test_missing_LNC_generation(self):
        self.reject(trace='\n'.join(self.trace.splitlines()[:3]+self.trace.splitlines()[4:]))
if __name__=='__main__':unittest.main()
