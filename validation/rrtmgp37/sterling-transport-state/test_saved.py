"""Counterexamples on actual consumed faces, coordinate conventions and time support."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_saved import *
from analyze import split_faces
import unittest

def change(text,tag,k,offset,value):
 lines=text.splitlines();found=0
 for i,l in enumerate(lines):
  x=l.split()
  if x[1]==tag and int(x[4])==k:x[5+offset]=str(value);lines[i]=' '.join(x);found+=1
 require(found==1,'counterexample selection');return '\n'.join(lines)+'\n'
class NativeTransportBoundaries(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.data=load();cls.raw=cls.data['native/transport_faces.txt'].decode();cls.first='\n'.join(l for l in cls.raw.splitlines() if int(float(l.split()[0]))==43200)+'\n';cls.prior=json.loads(cls.data['prior/prior-state-and-coordinate.json']);cls.oldtext,cls.oldcsv,cls.oldresult,*_=inputs(cls.data);cls.result=verify()
 def run_first(self,text):return analyze(text,self.prior,self.oldtext,self.oldcsv,self.oldresult,partial=True)
 def test_geometric_W_cannot_replace_native_eta_mass_flux(self):
  d=parse_for_test(self.first);wrong=d['geometry',8][6];bad=change(self.first,'theta_before',8,2,wrong)
  with self.assertRaisesRegex(ValueError,'theta face'):self.run_first(bad)
 def test_dry_theta_cannot_replace_transported_moist_perturbation(self):
  d=parse_for_test(self.first);v=d['theta_stencil',8][3];q=d['q_stencil',8][3];bad=change(self.first,'theta_stencil',8,3,(v+300)/(1+1.60836*q))
  with self.assertRaisesRegex(ValueError,'theta face'):self.run_first(bad)
 def test_low_order_PD_flux_is_part_of_the_actual_face(self):
  bad=change(self.first,'q_before',8,7,0)
  with self.assertRaisesRegex(ValueError,'PD vertical divergence'):self.run_first(bad)
 def test_source_updated_old_q_is_not_the_predictor_field(self):
  d=parse_for_test(self.first);self.assertNotEqual(d['q_stencil',8],d['q_old_stencil',8]);bad=change(self.first,'q_stencil',8,3,d['q_old_stencil',8][3])
  with self.assertRaisesRegex(ValueError,'consumed state'):self.run_first(bad)
 def test_hourly_sign_reversal_must_survive_five_hour_summary(self):
  h={x['start_hour_UTC']:x['layers'][1]['sums'] for x in self.result['hourly']};self.assertGreater(h[15]['qv_vertical_g_kg'],0);self.assertLess(h[15]['qv_horizontal_g_kg'],0);self.assertLess(self.result['five_hour_layers'][1]['sums']['qv_vertical_g_kg'],0)
  with self.assertRaisesRegex(ValueError,'time roster'):analyze(self.first,self.prior,self.oldtext,self.oldcsv,self.oldresult)
 def test_reference_split_changes_parts_not_total_and_handles_zero_mass_flux(self):
  d=parse_for_test(self.first);v=d['q_before',8];fb,ft=v[4]+v[6],v[5]+v[7];a,b=split_faces(fb,ft,v[2],v[3],d['q_stencil',8][3]);c,e=split_faces(fb,ft,v[2],v[3],0);self.assertNotEqual(a,c);self.assertAlmostEqual(a+b,c+e,places=15);self.assertEqual(split_faces(0,0,0,0,0.01),(0,0))
 def test_conservative_contribution_is_not_unique_parcel_motion_or_approval(self):
  r=self.result;self.assertFalse(r['physical_accuracy_approved']);self.assertFalse(r['decision']['vertical_motion_accuracy_approved']);self.assertFalse(r['decision']['production_defect_confirmed']);self.assertEqual(r['original_daily_SOLRAD_statistics_unchanged'],self.oldresult['original_daily_SOLRAD_statistics_unchanged']);self.assertEqual(r['new_cold24h_WRF_processes'],0);self.assertFalse(r['original_seven_conditions_changed'])

def parse_for_test(text):return {(l.split()[1],int(l.split()[4])):list(map(float,l.split()[5:])) for l in text.splitlines()}
if __name__=='__main__':unittest.main()
