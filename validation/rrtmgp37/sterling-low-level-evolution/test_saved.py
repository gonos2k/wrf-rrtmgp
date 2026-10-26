"""Scientific convention and support boundaries, with deliberate wrong alternatives."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_saved import *
import unittest
class StateSupport(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.result=verify()
 def test_near_release_hours_preserve_nominal_pairs_and_actual_offsets(self):
  rows=self.result['release_near_and_nominal_observation_pairs'];r={x['model_hour_UTC']:x for x in rows if x['pressure_Pa']==90000}
  self.assertEqual(set(r),{11,12,17,18,23,24});self.assertLess(abs(r[11]['model_minus_observation_time_s']),600);self.assertGreater(r[12]['model_minus_observation_time_s'],3000);self.assertLess(r[23]['model_minus_observation_time_s'],0)
 def test_temperature_lapse_is_not_dry_static_instability(self):
  T0,T1,p0,p1=285.6426,284.6932,95350.25,93308.09
  self.assertLess(T1-T0,0);self.assertGreater(theta(T1,p1)-theta(T0,p0),0)
  self.assertTrue(self.result['development_ruling']['all_11_18_dry_theta_925_minus_950_positive'])
 def test_RH_scales_vapor_pressure_not_saturated_mixing_ratio(self):
  T,p,rh=290.,90000.,50.;e=611.2*math.exp(17.67*(T-273.15)/(T-29.65));expected=.622*.5*e/(p-.5*e)
  self.assertAlmostEqual(real_qv(T,p,rh),expected,places=16);self.assertNotEqual(real_qv(T,p,rh),.5*.622*e/(p-e))
 def test_pressure_coupled_moist_theta_is_not_dry_output_theta(self):
  dry,q,a=300.,.012,90000.;thm=dry*(1+(461.6/287)*q);raw={'MU':a,'QVAPOR':[q*a],'T':[(thm-300)*a]};d=decode_boundary(raw,0,[1],[0])[0]
  self.assertAlmostEqual(d['dry_theta_K'],dry);self.assertNotEqual(d['moist_theta_K'],dry)
  with self.assertRaises(ValueError):decode_boundary(raw,0,[-1],[0])
 def test_spatial_stencil_is_not_best_neighbor_or_extrapolation(self):
  c=[{'lat':y,'lon':x,'value':x+2*y} for y in [38.,39.] for x in [282.,283.]]
  self.assertEqual(bilinear(c,38.5,-77.5),359.5)
  with self.assertRaises(ValueError):bilinear(c,40,-77.5)
  self.assertIsNone(interpolate([{'p_Pa':90000,'T':280},{'p_Pa':85000,'T':None}],80000,'T'))
 def test_state_difference_not_prescribed_interior_or_boundary_causality(self):
  r=self.result;self.assertTrue(r['limitations']['local_later_met_em_is_not_direct_interior_forcing']);self.assertTrue(r['limitations']['decoded_boundary_has_no_interior_pressure_or_station_error_assigned']);self.assertFalse(r['decision']['direct_boundary_causality_proven']);self.assertGreater(r['development_ruling']['900hPa_met_em_12_18_qv_diagnostic_change_g_kg'],0)
 def test_no_score_substitution_or_scientific_approval(self):
  r=self.result;prior=json.loads((P.parent/'sterling-independent-atmosphere/result.json').read_text());self.assertEqual(r['original_daily_SOLRAD_statistics_unchanged'],prior['original_daily_SOLRAD_statistics_unchanged']);self.assertFalse(r['physical_accuracy_approved']);self.assertFalse(r['decision']['unique_PBL_fault_confirmed']);self.assertEqual(r['new_model_runs'],0);self.assertFalse(r['original_seven_conditions_changed'])
if __name__=='__main__':unittest.main()
