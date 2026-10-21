#!/usr/bin/env python3
"""Counterexamples: timing, native support, boundary omission, and evidence binding."""
from pathlib import Path
import importlib.util,json,unittest
P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('real_budget_verifier',P/'verify_saved.py');V=importlib.util.module_from_spec(s);s.loader.exec_module(V)
class BudgetEvidence(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.d=V.data();cls.sd=json.loads(cls.d['surface_domains.json'])
 def mutated_trace(self,predicate,mutate):
  rows=[]
  for line in self.d['host/real-budget.txt'].decode().splitlines():
   a=line.split()
   if predicate(a):mutate(a)
   rows.append(' '.join(a))
  return '\n'.join(rows)+'\n'
 def test_cannot_sum_three_predictors_as_physical_time(self):
  raw=self.mutated_trace(lambda a:a[1]=='pd_tendency',lambda a:a.__setitem__(4,'180'))
  with self.assertRaisesRegex(ValueError,'final PD dt'):V.A.analyze(raw,self.sd)
 def test_cannot_omit_boundary_tendency_in_applied_source(self):
  raw=self.mutated_trace(lambda a:a[1]=='pd_tendency',lambda a:a.__setitem__(3,'0'))
  with self.assertRaisesRegex(ValueError,'tendency changed'):V.A.analyze(raw,self.sd)
 def test_TOA_cannot_replace_native_top(self):
  def change(a):
   v=list(map(float,a[3:]));v[7]=v[9];a[3:]=list(map(str,v))
  raw=self.mutated_trace(lambda a:a[1]=='rad_raw' and a[0]=='21600.000',change)
  with self.assertRaisesRegex(ValueError,'native top substituted'):V.A.analyze(raw,self.sd)
 def test_history_surface_must_match_actual_source_time(self):
  sd=json.loads(json.dumps(self.sd));sd[0]['QFX_full_kg_s']=sd[1]['QFX_full_kg_s']
  with self.assertRaisesRegex(ValueError,'actual call-time QFX'):V.A.analyze(self.d['host/real-budget.txt'].decode(),sd)
 def test_changed_observer_field_is_not_accepted(self):
  d=dict(self.d);h=json.loads(d['host/receipt.json']);next(iter(next(iter(h['observer_inventory'].values())).values()))['observed_sha256']='0'*64;d['host/receipt.json']=json.dumps(h).encode()
  with self.assertRaisesRegex(ValueError,'observer changed history'):V.evaluate(d)
 def test_inserting_between_native_IF_and_CALL_is_rejected(self):
  old=' if(x) &\n CALL physics(x)\n';new=' if(x) &\n CALL observer(x)\n CALL physics(x)\n'
  with self.assertRaisesRegex(ValueError,'native continuation'):V.readonly(old,new)
 def test_missing_frozen_water_species_is_rejected(self):
  raw='\n'.join(x for x in self.d['host/real-budget.txt'].decode().splitlines() if not(x.split()[1]=='micro_after' and x.split()[2]=='7'))+'\n'
  with self.assertRaises(KeyError):V.A.analyze(raw,self.sd)
if __name__=='__main__':unittest.main()
