"""Scientific misinterpretation counterexamples, not new physical gates."""
import copy,gzip,importlib.util,json,unittest
from pathlib import Path
B=Path(__file__).resolve().parent
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v=load(B/'verify_saved.py','verify');a=load(B/'analyze_saved.py','analysis')
class StudyBoundaries(unittest.TestCase):
 def test_study_integrity_does_not_approve_physics(self):self.assertFalse(v.verify()['host_water_budget_approved'])
 def test_relabelling_rhoDz_as_native_mass_rejected(self):
  row=next(iter(a.micro_records(v.read('host/command-02.stdout')).values()));wrong=list(row);wrong[0]=row[1]*row[2]
  with self.assertRaisesRegex(ValueError,'pressure dry mass'):a.check_native_mass(wrong)
 def test_changed_Mie_state_rejected(self):
  def altered(n):
   data=v.read(n)
   if n=='flux/sw-mie_band6/input':
    lines=data.decode().splitlines();i=next(k for k,x in enumerate(lines) if x.startswith('CF '));lines[i+1]='0.25';data=('\n'.join(lines)+'\n').encode()
   return data
  with self.assertRaisesRegex(ValueError,'changed state'):a.analyze(altered)
if __name__=='__main__':unittest.main(verbosity=2)
