import gzip,importlib.util,json,unittest
from pathlib import Path
B=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('v',B/'verify_saved.py');v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
a=v.load(B/'analyze_saved.py','a')
class InputBoundaries(unittest.TestCase):
 def history(self):return a.old.History(json.loads(v.read('host/final-input.json')),v.read('host/final-input.bin'))
 def test_actual_evidence_does_not_approve_whole_budget(self):
  result=v.verify();self.assertFalse(result['whole_host_budget_approved']);self.assertFalse(result['production_accepted'])
 def test_inconsistent_alpha_is_rejected(self):
  h=self.history();orig=h.at
  h.at=lambda n,*i:orig(n,*i)*1.1 if n in ('AL','ALB') else orig(n,*i)
  with self.assertRaisesRegex(ValueError,'geometry'):a.audit_input(h,True)
 def test_dry_theta_damper_reference_cannot_pass_as_theta_m(self):
  h=self.history();orig=h.at
  h.at=lambda n,*i:orig('T',i[0],i[1],0,0) if n=='T_BASE' else orig(n,*i)
  with self.assertRaisesRegex(ValueError,'reference'):a.audit_input(h,True)
if __name__=='__main__':unittest.main(verbosity=2)
