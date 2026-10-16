import importlib.util,unittest
from pathlib import Path
B=Path(__file__).resolve().parent;s=importlib.util.spec_from_file_location('v',B/'verify_saved.py');v=importlib.util.module_from_spec(s);s.loader.exec_module(v);a=v.load(B/'analyze_saved.py','capacity_analysis')
class NativeCapacityBoundaries(unittest.TestCase):
 def test_actual_candidate_keeps_physics_nonapproval(self):
  self.assertFalse(v.verify()['whole_energy_approved'])
 def test_dry_cp_substitution_does_not_satisfy_selected_completion(self):
  data=v.read('host/command-02.stdout');lines=data.decode().splitlines()
  for i,line in enumerate(lines):
   if line.startswith('EC LW '):
    w=line.split();w[4]=str(float(w[6])*1004.5);lines[i]=' '.join(w);break
  else:self.fail('EC missing')
  with self.assertRaisesRegex(ValueError,'constant kappa capacity'):a.host_energy(('\n'.join(lines)+'\n').encode(),1,True)
 def test_modified_native_heat_breaks_layer_closure(self):
  data=v.read('host/command-02.stdout');lines=data.decode().splitlines()
  for i,line in enumerate(lines):
   if line.startswith('EI_LW '):
    w=line.split();w[10]=str(float(w[10])*1.01);lines[i]=' '.join(w);break
  else:self.fail('heat record missing')
  with self.assertRaisesRegex(ValueError,'layer flux capacity'):a.host_energy(('\n'.join(lines)+'\n').encode(),1,True)
 def test_previous_radius_cannot_pass_as_Gamma8_consumption(self):
  def changed(n):
   data=v.read(n)
   if n=='host/cloud_gamma8/capture/sw.input':
    lines=data.decode().splitlines();j=next(i for i,z in enumerate(lines) if z.startswith('REL '));lines[j+1]=str(float(lines[j+1])/1.11572);return ('\n'.join(lines)+'\n').encode()
   return data
  with self.assertRaisesRegex(ValueError,'Gamma8 consumed radius'):a.analyze(changed)
if __name__=='__main__':unittest.main(verbosity=2)
