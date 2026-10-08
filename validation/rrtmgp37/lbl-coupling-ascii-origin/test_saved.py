#!/usr/bin/env python3
from pathlib import Path
import unittest,json,gzip,copy,importlib.util
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('upstream_test_core',BASE/'verify_core.py');core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
class SourceJoins(unittest.TestCase):
    def setUp(self):
        self.fields=json.loads((BASE/'source-fields.json').read_text());self.readback=json.loads((BASE/'readback.json').read_text());self.data=gzip.decompress((BASE.parent/'lbl-coupling-generation/excerpts/line_data.bin.gz').read_bytes())
    def reject(self):
        with self.assertRaises(ValueError):core.verify(self.fields,self.readback,self.data)
    def test_source_coefficient(self):self.fields['Y_decimals'][0]='0.0';self.reject()
    def test_source_temperature_exponent(self):self.fields['TDEP_decimal']='0.22';self.reject()
    def test_wrong_sidecar_record(self):self.readback['files'][0]['matches'][0]['sidecar']['offset0']+=101;self.reject()
    def test_F160_claim(self):self.readback['LNFL_TAPE5']['F160']=True;self.reject()
    def test_publisher_checksum(self):self.readback['archive']['md5']='0'*32;self.reject()
    def test_physical_promotion(self):self.readback['upstream_original_generator_authenticated']=True;self.reject()
if __name__=='__main__':unittest.main()
