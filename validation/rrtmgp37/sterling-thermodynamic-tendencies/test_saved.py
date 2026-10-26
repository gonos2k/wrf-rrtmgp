"""Actual-operand counterexamples for integration/variable/attribution boundaries."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_saved import *
from analyze import native_rhs,acoustic_flux,f32
import unittest
def block(text,t):return '\n'.join(l for l in text.splitlines() if int(float(l.split()[0]))==t)+'\n'
def change(text,tag,rk,s,k,offset,value):
 rows=text.splitlines();found=0
 for i,l in enumerate(rows):
  x=l.split()
  if x[1]==tag and list(map(int,x[2:5]))==[rk,s,k]:x[5+offset]=str(value);rows[i]=' '.join(x);found+=1
 require(found==1,'counterexample selection');return '\n'.join(rows)+'\n'
class ThermodynamicBoundaries(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.data=load();cls.text=cls.data['native/thermodynamic_operations.txt'].decode();cls.first=block(cls.text,43200);cls.result=verify()
 def test_predictors_are_not_added_as_independent_sixty_second_intervals(self):
  r=analyze(self.first,partial=True);self.assertEqual(r['replay_counts']['native_PD'],8);self.assertEqual(r['replay_counts']['native_acoustic_RHS'],32)
  bad=change(self.first,'q_rk_factors',3,2,8,0,20)
  with self.assertRaisesRegex(ValueError,'source time'):analyze(bad,partial=True)
 def test_native_source_update_cannot_be_replaced_by_post_update_floor(self):
  bad=change(self.first,'q_pd_after',3,2,8,0,0)
  with self.assertRaisesRegex(ValueError,'native PD'):analyze(bad,partial=True)
 def test_dry_rhs_cannot_substitute_for_actual_moist_theta_conversion(self):
  line=next(l.split() for l in self.first.splitlines() if l.split()[1]=='convert_before_theta' and l.split()[4]=='8');bad=change(self.first,'convert_after_theta',1,1,8,0,float(line[5]))
  with self.assertRaisesRegex(ValueError,'moist theta'):analyze(bad,partial=True)
 def test_acoustic_mapfactor_or_vertical_flux_change_is_rejected(self):
  bad=change(self.first,'ac_flux_operands',3,1,8,15,0)
  with self.assertRaisesRegex(ValueError,'acoustic flux'):analyze(bad,partial=True)
 def test_held_microphysics_heating_must_be_removed_at_final_finish(self):
  record=next(l.split() for l in self.text.splitlines() if l.split()[1]=='smallfinish_before' and l.split()[2]=='3' and float(l.split()[9])!=0)
  t=int(float(record[0]));k=int(record[4]);v=list(map(float,record[5:]));b0,save,ap,af,h,dt,n=v;single=block(self.text,t);actual=next(float(l.split()[5]) for l in single.splitlines() if l.split()[1]=='after_smallfinish' and l.split()[2]=='3' and int(l.split()[4])==k)
  wrong=f32(f32(b0+f32(save*ap))/af);self.assertNotEqual(wrong,actual)
 def test_distinct_moisture_layers_and_supported_ruling(self):
  layers={x['k']:x for x in self.result['five_hour_layers']};self.assertGreater(layers[9]['qv_components_g_kg']['transport_vertical'],0)
  for k in [10,11]:self.assertLess(layers[k]['qv_components_g_kg']['transport_vertical'],0);self.assertGreater(layers[k]['qv_components_g_kg']['transport_horizontal'],0)
  self.assertFalse(self.result['decision']['PBL_coefficient_fault_confirmed']);self.assertFalse(self.result['physical_accuracy_approved'])
 def test_original_scores_and_exact_historical_document_are_preserved(self):
  old=json.loads((P.parent/'sterling-low-level-evolution/result.json').read_text());self.assertEqual(self.result['original_daily_SOLRAD_statistics_unchanged'],old['original_daily_SOLRAD_statistics_unchanged']);documents(self.data);self.assertFalse(self.result['original_seven_conditions_changed']);self.assertEqual(self.result['new_cold24h_WRF_processes'],0)
if __name__=='__main__':unittest.main()
