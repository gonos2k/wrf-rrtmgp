from pathlib import Path
import importlib.util,json,unittest
P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('kf_v',P/'verify_saved.py');V=importlib.util.module_from_spec(s);s.loader.exec_module(V)
class Lifetimes(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.d=V.data()
 def native_change(self,step,index,value):
  d=dict(self.d);rows=[]
  for l in d['native/command-08.stdout'].decode().splitlines():
   a=l.split()
   if a and a[:3]==['NATIVE','1',str(step)]:a[3+index]=str(value);l=' '.join(a)
   rows.append(l)
  d['native/command-08.stdout']='\n'.join(rows).encode();return d
 def test_last_valid_accumulation_cannot_be_erased(self):
  with self.assertRaisesRegex(ValueError,'last valid precipitation'):V.A.analyze(self.native_change(2,0,25))
 def test_surface_interval_cannot_be_cleared_at_rate_expiry(self):
  with self.assertRaisesRegex(ValueError,'RAINCV must outlive'):V.A.analyze(self.native_change(2,1,0))
 def test_inactive_rate_cannot_keep_accumulating(self):
  with self.assertRaisesRegex(ValueError,'inactive rate reused'):V.A.analyze(self.native_change(3,0,55))
 def test_other_grouped_schemes_cannot_be_changed(self):
  d=dict(self.d);d['native/after/scheme-11.bin']=b'changed'
  with self.assertRaisesRegex(ValueError,'non-KF scheme changed'):V.A.analyze(d)
 def test_observer_differences_cannot_be_ignored(self):
  d=dict(self.d);h=json.loads(d['host/history-comparison.json']);next(iter(next(iter(h['inventory'].values())).values()))['equal']=False;d['host/history-comparison.json']=json.dumps(h).encode()
  with self.assertRaisesRegex(ValueError,'observer array changed'):V.A.analyze(d)
if __name__=='__main__':unittest.main()
