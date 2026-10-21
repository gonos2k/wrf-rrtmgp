#!/usr/bin/env python3
"""Meaningful counterexamples against actual source and final operands."""
from pathlib import Path
import importlib.util,json,unittest
P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('closeout_verifier',P/'verify_saved.py');V=importlib.util.module_from_spec(s);s.loader.exec_module(V)
class CloseoutEvidence(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.saved=V.data();cls.plan=json.loads((P/'plan.json').read_text())
 def analyze(self,data):return V.A.analyze(data.__getitem__,self.plan)
 def reject_trace(self,change,message):
  data=dict(self.saved);lines=data['host/boundary-closeout.txt'].decode().splitlines();change(lines);raw=('\n'.join(lines)+'\n').encode();data['host/boundary-closeout.txt']=raw
  a=json.loads(data['analysis.json']);a['trace_records']=V.A.rows(raw);data['analysis.json']=json.dumps(a).encode()
  with self.assertRaisesRegex(ValueError,message):self.analyze(data)
 def test_positive_tendency_cannot_be_zeroed(self):
  def change(lines):
   for i,line in enumerate(lines):
    p=line.split()
    if p[0] in ['relax-after','wrapper-after'] and p[1]=='1' and p[3]=='21600.000':p[4]='00000000';lines[i]=' '.join(p)
  self.reject_trace(change,'native relaxation arithmetic')
 def test_target_interpolation_cannot_use_stale_time(self):
  def change(lines):
   for i,line in enumerate(lines):
    p=line.split()
    if p[0]=='relax-before' and p[1]=='2' and p[3]=='21600.000':p[8]='00000000';lines[i]=' '.join(p)
  self.reject_trace(change,'actual target/model mismatch')
 def test_history_mass_cannot_replace_native_call_mass(self):
  def change(lines):
   for i,line in enumerate(lines):
    p=line.split()
    if p[0]=='final' and p[1]=='1' and p[3]=='21600.000':p[8]='47ba5106';lines[i]=' '.join(p)
  self.reject_trace(change,'call-time native mass factor')
 def test_differing_observer_array_cannot_be_hidden(self):
  data=dict(self.saved);a=json.loads(data['host/receipt.json']);row=next(iter(next(iter(a['observer_inventory'].values())).values()));row['observed_sha256']='0'*64;data['host/receipt.json']=json.dumps(a).encode()
  with self.assertRaisesRegex(ValueError,'observer changes history'):self.analyze(data)
 def test_common_number0_case_cannot_be_omitted(self):
  data=dict(self.saved);data['halo/command-03.stdout']=b'\n'.join(line for line in data['halo/command-03.stdout'].splitlines() if not line.startswith(b'HALO_POLICY_METHOD_PASS  0  1'))+b'\n'
  with self.assertRaisesRegex(ValueError,'common specified halo coverage'):self.analyze(data)
 def test_physical_cell_preservation_assertion_is_required(self):
  data=dict(self.saved);data['halo/common_halo.f90']=data['halo/common_halo.f90'].replace(b'physical MU modified',b'other unused assertion')
  with self.assertRaisesRegex(ValueError,'native property assertion missing'):self.analyze(data)
if __name__=='__main__':unittest.main()
