"""Finite parser/selector/CSV/cleanup controls. No compiler or model subprocesses."""
import csv,importlib.util,json,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('bon_runtime_tests',HERE/'run_bon_once.py');r=importlib.util.module_from_spec(s);sys.modules[s.name]=r;s.loader.exec_module(r)
class Controls(unittest.TestCase):
 def test_raw_actual_context(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'a.raw';p.write_text('RRTMGP_RAW_V1\nLW 13 46 32\nRADIATION_STEP 1\n721\nSOURCE_TIME_SECONDS 1\n43200\n')
   phase,x=r.parse_capture(p,'raw');self.assertEqual(phase,'LW');self.assertEqual(x['RADIATION_STEP']['values'],[721.])
 def test_wrong_point_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'a.raw';p.write_text('RRTMGP_RAW_V1\nLW 24 55 32\nA 1\n0\n')
   with self.assertRaises(RuntimeError):r.parse_capture(p,'raw')
 def test_nonfinite_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'a.raw';p.write_text('RRTMGP_RAW_V1\nLW 13 46 32\nA 1\nNaN\n')
   with self.assertRaises(RuntimeError):r.parse_capture(p,'raw')
 def test_duplicate_record_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'a.raw';p.write_text('RRTMGP_RAW_V1\nLW 13 46 32\nA 1\n0\nA 1\n0\n')
   with self.assertRaises(RuntimeError):r.parse_capture(p,'raw')
 def test_selector_is_observed_not_guessed(self):
  gs=[{'phase':'SW','step':721,'source_seconds':43200.,'files':{}},{'phase':'LW','step':731,'source_seconds':43800.,'files':{'raw':{'sha256':'observed'}}}]
  x=r.selector_from_off(gs);self.assertEqual(x['selector']['step'],731);self.assertEqual(len(x['environment']),5);self.assertEqual(x['environment'][r.SEL_PREFIX+'SECONDS'],'43800')
 def test_selector_missing_LW_rejected(self):
  with self.assertRaises(StopIteration):r.selector_from_off([{'phase':'SW'}])
 def test_auth_environment_only_ON1(self):
  p={'arms':{a:{'environment_overrides_pending_runtime_closure':{}} for a in r.ARMS}}
  sel=r.selector_from_off([{'phase':'LW','step':731,'source_seconds':43800.,'files':{'raw':{}}}])
  self.assertNotIn(r.SEL_PREFIX+'DIR',r.clean_env('OFF',p,{},None));self.assertNotIn(r.SEL_PREFIX+'DIR',r.clean_env('ON_native4_0',p,{},sel));self.assertIn(r.SEL_PREFIX+'DIR',r.clean_env('ON_native4_1',p,{},sel))
 def test_selector_required_before_ON1(self):
  p={'arms':{a:{'environment_overrides_pending_runtime_closure':{}} for a in r.ARMS}}
  with self.assertRaises(RuntimeError):r.clean_env('ON_native4_1',p,{},None)
 def test_atomic_oneuse_and_json(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'r.json';r.atomic(p,{'call_keys':[['LW',721,43200.]],'returncode':0},exclusive=True);self.assertEqual(json.loads(p.read_text())['returncode'],0)
   with self.assertRaises(FileExistsError):r.atomic(p,{'bad':True},exclusive=True)
 def test_csv_samplecount_sd_and_roster(self):
  def rows():
   out=[]
   for phase in ['LW','SW']:
    for point in [(13,46),(0,0)]:
     for m in ['SURFACE_DOWN','TOA_UP']+['HEAT_'+str(k) for k in range(1,33)]+(['SW_NET','SW_DIRECT'] if phase=='SW' else []):
      x=dict.fromkeys(r.CSV_HEADER,'0');x.update(phase=phase,domain='1',step='721',source_seconds='43200',i=str(point[0]),j=str(point[1]),metric=m,sample_count='128',radius_mode='0',scope='selected_column');out.append(x)
   return out
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);(p/'audit').mkdir();f=p/'audit/same_state.csv';gs=[{'phase':'LW','step':721,'source_seconds':43200.}]
   def write(rs):
    with f.open('w') as ff:w=csv.DictWriter(ff,r.CSV_HEADER,lineterminator='\n');w.writeheader();w.writerows(rs)
   rs=rows();write(rs);q,_=r.audit_rows(p,'ON_native4_0',gs);self.assertEqual(q['night_SW_zero_calls_without_capture'],[['SW',721,43200.]])
   rs[0]['sample_count']='127';write(rs)
   with self.assertRaises(RuntimeError):r.audit_rows(p,'ON_native4_0',gs)
   rs=rows();rs[0]['sd37']='-1';write(rs)
   with self.assertRaises(RuntimeError):r.audit_rows(p,'ON_native4_0',gs)
   rs=rows()[:-1];write(rs)
   with self.assertRaises(RuntimeError):r.audit_rows(p,'ON_native4_0',gs)
 def test_export_context_reader_matches_new_selector(self):
  e=r.load_module('bon_test_export_reader',HERE/'read_export_context.py')
  donor=r.ROOT/'build/udm37-export-selection-pr-work/validation/rrtmgp37/rrtmg4-optics-export/fixture/rrtmg4_d01_i24_j55_step2161_lw.txt'
  text=donor.read_text().replace('step 2161','step 721').replace('i 24\n','i 13\n').replace('j 55\n','j 46\n').replace('1.2960000000000000E+005','4.3200000000000000E+004')
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'e.txt';p.write_text(text)
   x=e.read_export(p,expected_phase='LW',expected_context={'domain':1,'i':13,'j':46,'step':721,'source_seconds':43200.});self.assertEqual(x['metadata']['i'],13)
   with self.assertRaises(ValueError):e.read_export(p,expected_phase='LW')
 def test_completed_output_tamper_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'out';p.write_bytes(b'completed');rec={'arms':{'OFF':{'outputs':{'out':r.pin(p)}}}}
   self.assertEqual(r.completed_pins(rec)['pin_count'],1);p.write_bytes(b'changed')
   with self.assertRaises(RuntimeError):r.completed_pins(rec)
 def test_actual_retained_production_capture_schema(self):
  # Original bytes, no solver: raw point/native-depth parameter differs from BON only in this smoke.
  folder=r.ROOT/'build/udm37-current-matthew-serial-audit-v1/OFF/trace'
  for phase in ['lw','sw']:
   for suffix in ['raw','input','result']:
    p=folder/(phase+'_000001.'+suffix);a,x=r.parse_capture(p,suffix,raw_context=(24,55,44))
    self.assertEqual(a,phase.upper());self.assertGreater(len(x),10)
if __name__=='__main__':unittest.main()
