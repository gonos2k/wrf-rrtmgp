"""Time/units/missing-data counterexamples for this actual observational comparison."""
from pathlib import Path
import sys,unittest,json,copy,csv,io
sys.path.insert(0,str(Path(__file__).resolve().parent))
from parse import sounding,metars,elapsed_seconds,interpolate
from analyze import evaluate
import verify_saved as V
P=Path(__file__).resolve().parent
class IndependentAtmosphere(unittest.TestCase):
 def test_IGRA_MMMSS_is_not_integer_seconds_and_missing_is_not_zero(self):
  self.assertEqual(elapsed_seconds(121),81);self.assertEqual(elapsed_seconds(200),120);self.assertIsNone(elapsed_seconds(-8888));self.assertIsNone(elapsed_seconds(-9999))
  with self.assertRaises(ValueError):elapsed_seconds(160)
 def test_nominal18_is_not_actual_launch18(self):
  s=sounding((P/'raw/sounding-2016100618.txt').read_bytes());self.assertEqual(s['release_UTC'],'2016-10-06T17:34:00+00:00');r=next(x for x in s['levels'] if x['original_integer_fields']['elapsed']==121);self.assertEqual(r['actual_UTC'],'2016-10-06T17:35:21+00:00');self.assertEqual(r['reported_RH_ratio'],.944)
 def test_VRB_is_not_north_or_calm_and_missing_cloud_is_not_clear(self):
  rows=list(csv.DictReader(io.StringIO((P/'raw/asos.csv').read_text())));row=next(x for x in rows if x['station']=='IAD' and x['valid']=='2016-10-06 17:52');buf=io.StringIO();w=csv.DictWriter(buf,fieldnames=list(row));w.writeheader();w.writerow(row);r=metars(buf.getvalue().encode())[0];self.assertIsNone(r['wind_from_deg']);self.assertGreater(r['wind_speed_m_s'],0);self.assertTrue(r['wind_variable'])
  row['metar']='KIAD 061752Z VRB03KT 10SM 19/13 A3030';buf=io.StringIO();w=csv.DictWriter(buf,fieldnames=list(row));w.writeheader();w.writerow(row);r=metars(buf.getvalue().encode())[0];self.assertIsNone(r['ceiling_agl_m']);self.assertFalse(r['low_level_clear_reported'])
 def test_profile_is_not_extrapolated_above_or_below_observations(self):
  s=sounding((P/'raw/sounding-2016100618.txt').read_bytes());self.assertIsNone(interpolate(s['levels'],110000,'T_K'));self.assertIsNotNone(interpolate(s['levels'],95000,'T_K'))
 def test_false_release_relabelling_is_rejected(self):
  d=V.load();ex=json.loads(d['derived/enriched.json']);prior=json.loads((P.parent/'sterling-cloud-loss-operation/result.json').read_text());next(x for x in ex['soundings'] if '2016-10-06T18:' in x['nominal_UTC'])['release_UTC']='2016-10-06T18:00:00+00:00'
  with self.assertRaisesRegex(ValueError,'release'):evaluate(ex,prior)
 def test_unsupported_inversion_ruling_is_rejected(self):
  d=V.load();ex=json.loads(d['derived/enriched.json']);prior=json.loads((P.parent/'sterling-cloud-loss-operation/result.json').read_text());rows=[x for x in prior['selected_native_saturation_states'] if x['source_seconds']==63300 and x['stage']=='before'];next(x for x in rows if x['k']==7)['actual_T_from_native_product_K']=next(x for x in rows if x['k']==6)['actual_T_from_native_product_K']-1
  with self.assertRaisesRegex(ValueError,'inversion-sign'):evaluate(ex,prior)
 def test_actual_saved_data_replay_keeps_scientific_approval_withheld(self):
  r=V.verify();self.assertFalse(r['physical_accuracy_approved']);self.assertFalse(r['PBL_parameter_fault_confirmed']);self.assertEqual(r['new_model_runs'],0)
if __name__=='__main__':unittest.main()
