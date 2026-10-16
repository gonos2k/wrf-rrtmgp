import copy,importlib.util,json,unittest
from pathlib import Path
B=Path(__file__).resolve().parent;s=importlib.util.spec_from_file_location('v',B/'verify_saved.py');v=importlib.util.module_from_spec(s);s.loader.exec_module(v);a=v.load(B/'analyze_saved.py','a')
class ScientificBoundaries(unittest.TestCase):
 def test_integrity_preserves_physical_nonapproval(self):
  result=v.verify();self.assertFalse(result['full_host_water_approved']);self.assertFalse(result['PSD_observationally_approved'])
 def test_fixed_reff_shape_substitution_is_not_fixed_mass_number(self):
  def changed(n):
   data=v.read(n)
   if n=='psd/moments-optics.json':
    x=json.loads(data);x['PSDs'][1]['reff_um']=x['PSDs'][0]['reff_um'];return json.dumps(x).encode()
   return data
  with self.assertRaisesRegex(ValueError,'PSD shape'):a.analyze(changed)
 def test_surface_QFX_cannot_be_relabelled_as_applied_PBL_source(self):
  def changed(n):
   data=v.read(n)
   if n=='host/command-02.stdout':
    lines=data.decode().splitlines()
    for i,line in enumerate(lines):
     if line.startswith('WQ_PBL '):
      w=line.split();w[14]=str(float(w[14])*1.1);lines[i]=' '.join(w)
    return ('\n'.join(lines)+'\n').encode()
   return data
  with self.assertRaisesRegex(ValueError,'surface time integral'):a.analyze(changed)
if __name__=='__main__':unittest.main(verbosity=2)
