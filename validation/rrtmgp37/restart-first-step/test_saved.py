#!/usr/bin/env python3
"""Semantic rejection of false restarts, stale records and false kernel repair."""
from pathlib import Path
import importlib.util,json,unittest
P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('restart_verifier',P/'verify_saved.py');V=importlib.util.module_from_spec(s);s.loader.exec_module(V)
class RestartEvidence(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.saved=V.data();cls.plan=json.loads((P/'plan.json').read_text())
 def reject(self,name,change,message):
  data=dict(self.saved);obj=json.loads(data[name]);change(obj);data[name]=json.dumps(obj).encode()
  with self.assertRaisesRegex(ValueError,message):V.A.analyze(data.__getitem__,self.plan)
 def test_flag_cannot_hide_a_differing_history_array(self):
  def mutate(a):
   row=next(iter(next(iter(a['fixed_restart']['inventory'].values())).values()));row['right_sha256']='0'*64
  self.reject('analysis.json',mutate,'false bitwise inventory flag')
 def test_variable_exclusion_cannot_pass(self):
  self.reject('analysis.json',lambda a:a['fixed_restart'].__setitem__('array_pairs',672),'225-variable criterion')
 def test_original_failure_is_not_rewritten(self):
  self.reject('analysis.json',lambda a:a['original_restart'].__setitem__('differences',[]),'history mismatch inventory')
 def test_stale_kernel_profile_is_not_a_repair(self):
  data=dict(self.saved);text=data['native/command-03.stdout'].decode();text=text.replace('WW   3  2 BB512892','WW   3  2 BB5128A4')
  # Format-independent edit of the repaired second level.
  rows=text.splitlines()
  for i,line in enumerate(rows):
   part=line.split()
   if len(part)==4 and part[:3]==['WW','3','2']:rows[i]='WW 3 2 BB5128A4'
  data['native/command-03.stdout']=('\n'.join(rows)+'\n').encode()
  with self.assertRaisesRegex(ValueError,'native halo repair'):V.A.analyze(data.__getitem__,self.plan)
 def test_second_record_cannot_be_replaced_by_first(self):
  def mutate(a):a['boundary']['restart'][-1]['south_MU'][23]+=1
  self.reject('analysis.json',mutate,'next actual boundary record')
 def test_nonzero_tendency_cannot_be_replaced_by_zero(self):
  self.reject('nonzero/receipt.json',lambda a:a['fields']['QNCLOUD'].__setitem__('slope_record1',0),'nonzero stored S interpolation')
if __name__=='__main__':unittest.main()
