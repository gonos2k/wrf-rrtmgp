import importlib.util,unittest
from pathlib import Path
B=Path(__file__).resolve().parent;s=importlib.util.spec_from_file_location('v',B/'verify_saved.py');v=importlib.util.module_from_spec(s);s.loader.exec_module(v);a=v.load(B/'analyze_saved.py','energy_analysis')

def mutate(data,prefix,field,transform):
 lines=data.decode().splitlines();done=False
 for k,line in enumerate(lines):
  if line.startswith(prefix):
   w=line.split();w[field]=str(transform(float(w[field])));lines[k]=' '.join(w);done=True;break
 if not done:raise AssertionError(prefix)
 return ('\n'.join(lines)+'\n').encode()

class ApplicationBoundaries(unittest.TestCase):
 def test_saved_runs_keep_energy_and_physics_nonapproval(self):
  self.assertFalse(v.verify()['dry_energy_closed'])
 def test_native_top_cannot_be_replaced_by_extended_TOA(self):
  data=v.read('host/command-02.stdout');rows=a.records(data)['EI_LW'];ext=next(z for k,z in rows if k==(1,1,121))
  lines=data.decode().splitlines()
  for idx,line in enumerate(lines):
   if line.startswith('EI_LW 1 1 59 '):
    w=line.split();w[7]=str(ext[3]);w[9]=str(ext[5]);lines[idx]=' '.join(w);break
  else:self.fail('native boundary absent')
  with self.assertRaisesRegex(ValueError,'native flux heat closure'):a.analyze_host(('\n'.join(lines)+'\n').encode())
 def test_time_ledger_cannot_change_actual_acoustic_interval(self):
  data=mutate(v.read('host/command-02.stdout'),'EA_APPLY ',11,lambda x:x*2)
  with self.assertRaisesRegex(ValueError,'source add ledger alignment'):a.analyze_host(data)
 def test_wrong_YSU_lower_diagonal_breaks_actual_solve_replay(self):
  data=mutate(v.read('host/command-02.stdout'),'YS_MATRIX ',4,lambda x:x*2)
  with self.assertRaisesRegex(ValueError,'YSU REAL32 solve replay'):a.analyze_host(data)
if __name__=='__main__':unittest.main(verbosity=2)
