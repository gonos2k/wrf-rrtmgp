"""Small regressions for the candidate replay; no new physical gates."""
import copy,importlib.util,json,struct,unittest,gzip
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v=load(B/'verify_saved.py','saved');bridge=load(ROOT/'WRF/test/rrtmgp/test_udm_dry_number_bridge.py','bridge');partial=load(ROOT/'WRF/test/rrtmgp/test_udm_partial_activation.py','partial')
class CandidateBoundaries(unittest.TestCase):
 def test_saved_replay_does_not_approve_physics(self):
  r=v.verify();self.assertEqual(r['manufactured_module_pairs'],32);self.assertFalse(r['production_accepted'])
 def test_wrong_host_return_rejected(self):
  cmds=json.loads((B/'saved/module/receipt.json').read_text())['processes'];data={}
  for policy in (0,1):
   n=next(n for n,c in enumerate(cmds,1) if c['kind']=='actual_UDM_wet_policy'+str(policy) and '/O0/' in c['argv'][0])
   d=partial.parse(v.read(f'saved/module/command-{n:02d}.stdout.gz').decode());d['returns']={c:[struct.unpack('!f',bytes.fromhex(x))[0] for x in values] for c,values in d['outputs'].items()};data[policy]=d
  data[1]['returns'][1][36]*=1.01
  with self.assertRaisesRegex(ValueError,'return mismatch'):bridge.compare(data[0],data[1],'wet')
 def test_missing_density_arm_rejected(self):
  n=next(n for n,c in enumerate(json.loads((B/'saved/module/receipt.json').read_text())['processes'],1) if c['kind']=='actual_UDM_wet_policy1' and '/O0/' in c['argv'][0])
  lines=v.read(f'saved/module/command-{n:02d}.stdout.gz').decode().splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('INPUT 3 1 '));del lines[i:i+2]
  with self.assertRaisesRegex(ValueError,'input roster'):partial.parse('\n'.join(lines))
 def test_unmarked_capture_rejected(self):
  raw=v.read('saved/live/capture/udm_radius_d1_i1_j1_step1.raw.gz').replace(b'HOST_NUMBER_POLICY 1\n  1.0000000000000000E+000',b'HOST_NUMBER_POLICY 1\n  0.0000000000000000E+000')
  # Avoid depending on the compiler's numeric text width.
  lines=raw.decode().splitlines();i=next(i for i,l in enumerate(lines) if l.startswith('HOST_NUMBER_POLICY '));lines[i+1]='0.0'
  with self.assertRaisesRegex(ValueError,'encoding'):v.raw_capture('\n'.join(lines).encode())
if __name__=='__main__':unittest.main(verbosity=2)
