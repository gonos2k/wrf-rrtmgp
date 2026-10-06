#!/usr/bin/env python3
"""Offline bundled-semantic failure controls; no numerical engine calls."""
import csv,importlib.util,json,shutil,sys,tempfile,unittest
from pathlib import Path
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('bon_verifier_control',P/'verify.py');v=importlib.util.module_from_spec(s);sys.modules[s.name]=v;s.loader.exec_module(v)
class Controls(unittest.TestCase):
 def test_actual_csv_pass(self):self.assertEqual(len(v.csv_rows(P/'csv/ON_native4_0-same_state.csv',0)),840)
 def check_csv_change(self,mutate):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'changed.csv'
   with (P/'csv/ON_native4_0-same_state.csv').open() as f:rows=list(csv.DictReader(f))
   mutate(rows)
   with p.open('w') as f:w=csv.DictWriter(f,v.CSV_HEADER,lineterminator='\n');w.writeheader();w.writerows(rows)
   with self.assertRaises(ValueError):v.csv_rows(p,0)
 def test_wrong_sample_count(self):self.check_csv_change(lambda rs:rs[0].update(sample_count='127'))
 def test_wrong_clock(self):self.check_csv_change(lambda rs:rs[0].update(source_seconds='43201'))
 def test_missing_metric(self):self.check_csv_change(lambda rs:rs.pop())
 def test_negative_sd(self):self.check_csv_change(lambda rs:rs[0].update(sd4='-1'))
 def test_roster_extra_rejected(self):
  old=v.PKG
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'pkg';shutil.copytree(P,p);v.PKG=p
   try:
    (p/'unexpected').mkdir();(p/'unexpected/artifact-manifest.json').write_bytes(b'extra')
    with self.assertRaises(ValueError):v.closed_manifest()
   finally:v.PKG=old
 def test_hash_tamper_rejected(self):
  old=v.PKG
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'pkg';shutil.copytree(P,p);v.PKG=p
   try:
    q=p/'csv/ON_native4_0-same_state.csv';q.write_bytes(q.read_bytes()+b'changed')
    with self.assertRaises(ValueError):v.closed_manifest()
   finally:v.PKG=old
if __name__=='__main__':unittest.main()
