#!/usr/bin/env python3
import gzip,json,unittest,importlib.util,sys
from pathlib import Path
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P))
from analyze_saved import analyze
identity=json.loads((P/'identity.json').read_text());plan=json.loads((P/'plan.json').read_text())
data={n:gzip.decompress((P/z['gzip']).read_bytes()) for n,z in identity['saved'].items()}
class Meaning(unittest.TestCase):
 def modified(self,key,edit):
  def read(n):return json.dumps(edit(json.loads(data[n]))).encode() if n==key else data[n]
  return read
 def test_physical_reference_promotion_rejected(self):
  def edit(v):v['production_accepted']=True;return v
  with self.assertRaisesRegex(ValueError,'physical approval'):analyze(self.modified('analysis.json',edit),plan)
 def test_native_boundary_cannot_be_extended_TOA(self):
  def edit(v):v['conditional_reference']['native_top_up_down_net']=[0,0,0];return v
  with self.assertRaisesRegex(ValueError,'target conditional_reference'):analyze(self.modified('analysis.json',edit),plan)
 def test_different_spectral_intervals_cannot_be_paired_by_index(self):
  def edit(v):v['common_physical_band_upper_DN'][0]['bands4_one_based']=[1];return v
  with self.assertRaisesRegex(ValueError,'common physical bands'):analyze(self.modified('analysis.json',edit),plan)
 def test_zero_input_producer_does_not_enable_boundaries(self):
  def edit(v):v['boundary_runtime_support']=True;return v
  with self.assertRaisesRegex(ValueError,'producer/support'):analyze(self.modified('real/number1_input/producer.json',edit),plan)
 def test_transport_refinement_failure_not_silently_promoted(self):
  def edit(v):v[-1]['dn'][59]+=1e-4;return v
  with self.assertRaisesRegex(ValueError,'angular numerical screen'):analyze(self.modified('angular-history.json',edit),plan)
if __name__=='__main__':unittest.main()
