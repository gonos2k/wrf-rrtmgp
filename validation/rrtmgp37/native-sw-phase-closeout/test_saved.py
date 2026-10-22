"""Reject missing/filled returns and incorrect hold-phase interpretations."""
from pathlib import Path
import importlib.util,unittest,json
P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('sw_saved',P/'verify_saved.py');V=importlib.util.module_from_spec(s);s.loader.exec_module(V)
class SWReturnSemantics(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.d=V.data();cls.text=cls.d['day/host/sw-phase.txt'].decode()
 def change(self,tag,field,value):
  rows=self.text.splitlines()
  for i,row in enumerate(rows):
   x=row.split()
   if x[1]==tag:
    x[2+field]=str(value);rows[i]=' '.join(x);return '\n'.join(rows)
  raise AssertionError(tag)
 def test_missing_return_is_not_a_valid_zero(self):
  rows=self.text.splitlines();rows.pop(next(i for i,x in enumerate(rows) if x.split()[1]=='coverage'))
  with self.assertRaises(ValueError):V.A.analyze('\n'.join(rows))
 def test_nonzero_night_return_is_rejected(self):
  with self.assertRaises(ValueError):V.A.analyze(self.change('coverage',7,1e-15))
 def test_partial_column_count_is_rejected(self):
  with self.assertRaises(ValueError):V.A.analyze(self.change('coverage',4,8909))
 def test_night_flux_cannot_be_guessed_or_backfilled(self):
  with self.assertRaises(ValueError):V.A.analyze(self.change('phase_flux',1,1.0))
 def test_no_call_step_is_not_a_new_call(self):
  rows=self.text.splitlines()
  for i,row in enumerate(rows):
   x=row.split()
   if x[1]=='held' and float(x[0])==60:
    x[5]='1';rows[i]=' '.join(x);break
  with self.assertRaises(ValueError):V.A.analyze('\n'.join(rows))
 def test_stale_held_phase_is_rejected(self):
  with self.assertRaises(ValueError):V.A.analyze(self.change('held',0,-600))
 def test_history_variable_cannot_be_omitted(self):
  x=json.loads(self.d['day/history-comparison.json']);rows=next(iter(x['inventory'].values()));rows.pop(next(iter(rows)))
  with self.assertRaises(ValueError):V.compare_inventory(x,5625)
if __name__=='__main__':unittest.main(verbosity=2)
