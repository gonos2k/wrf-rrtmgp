#!/usr/bin/env python3
"""Exercise every output filename, daylight selection, missing-SW outcomes and default pins. No engines."""
import ast, hashlib, importlib.util, json, subprocess, sys, tempfile, unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent.parent
RUNNER=HERE/'capture_runner.py'
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('proposed_executor',RUNNER);runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
PLAN=json.loads((HERE/'plan.json').read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def filename_expressions(source):
 return [n.args[0] for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='write']

def evaluate_names(source,phase,root):
 results=[]
 for e in filename_expressions(source):
  for node in ast.walk(e):
   if isinstance(node,ast.Name):assert node.id in {'out','phase','preflight_path'},node.id
   if isinstance(node,ast.Call):assert isinstance(node.func,ast.Attribute) and node.func.attr=='lower' and isinstance(node.func.value,ast.Name) and node.func.value.id=='phase' and not node.args and not node.keywords
  value=eval(compile(ast.Expression(e),'<offline-filename>','eval'),{'__builtins__':{}},dict(out=root,phase=phase,preflight_path=root/'preflight.json'))
  assert isinstance(value,Path) and value.is_relative_to(root);results.append(value.name)
 return results

class OfflineChecks(unittest.TestCase):
 def test_all_write_paths_both_phases(self):
  with tempfile.TemporaryDirectory() as d:
   for phase in ['LW','SW']:
    names=evaluate_names(RUNNER.read_text(),phase,Path(d));self.assertIn('strict-'+phase.lower()+'.json',names);self.assertGreater(len(names),8)
   self.assertFalse(list(Path(d).iterdir()))
 def test_nighttime_absence_is_expected_gate(self):
  with tempfile.TemporaryDirectory() as d:
   status,presence=runner.classify_sw_capture(Path(d),-.25774246)
   self.assertEqual(status,'SW_NOT_RUN_AT_NIGHT_EXPECTED_PRODUCTION_GATE');self.assertFalse(any(presence.values()))
   self.assertEqual(runner.classify_sw_capture(Path(d),0.)[0],status)
 def test_daylight_missing_or_partial_is_failure(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)
   with self.assertRaisesRegex(AssertionError,'MISSING_SW_CAPTURE'):runner.classify_sw_capture(p,.1)
   (p/'sw.raw').write_text('offline dummy')
   for mu in [-.1,.1]:
    with self.assertRaisesRegex(AssertionError,'INCOMPLETE_CAPTURE'):runner.classify_sw_capture(p,mu)
   for suffix in ['input','result']:(p/('sw.'+suffix)).write_text('offline dummy')
   self.assertEqual(runner.classify_sw_capture(p,.1)[0],'SW_CAPTURE_COMPLETE')
 def test_daylight_pins_and_original_night_point(self):
  for point in PLAN['points']:
   info=runner.verify_daylight_selection(PLAN,point);self.assertTrue(info['production_SW_daylight']);self.assertTrue(info['selection_daylight_margin'])
  from netCDF4 import Dataset
  import numpy as np
  h=PLAN['selection_radiation_field_provenance']['history']['path']
  with Dataset(h) as n:
   n.set_auto_maskandscale(False);cf=np.asarray(n['CLDFRA'][0,:,36,21],float).tolist();mu=float(n['COSZEN'][0,36,21])
  night=dict(i=22,j=37,profiles=dict(selection_radiation_CF=cf),eligibility=dict(retained_history_coszen=mu))
  info=runner.verify_daylight_selection(PLAN,night);self.assertFalse(info['production_SW_daylight']);self.assertFalse(info['selection_daylight_margin'])
 def test_two_preflights_repeat_and_fresh_guard(self):
  results=[]
  cases=[p['name'] for p in PLAN['points']]
  for case in cases+[cases[0]]:
   command=[sys.executable,str(RUNNER),'--case',case]
   p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
   self.assertEqual(p.returncode,0,p.stdout);receipt=HERE/'preflight'/(case+'.json');r=json.loads(receipt.read_text())
   self.assertEqual(r['status'],'PIN_PREFLIGHT_PASS_NO_RUNTIME');self.assertEqual(r['runner_sha256'],sha(RUNNER));self.assertEqual(r['maximum_fresh_wrf_runs'],2);self.assertEqual(r['maximum_strict_reference_calls'],4)
   self.assertFalse(Path(r['fixed_output_dir']).exists());results.append(dict(case=case,command=command,stdout=p.stdout,preflight_sha256=sha(receipt)))
  self.assertEqual(results[0]['preflight_sha256'],results[-1]['preflight_sha256'])
  text=RUNNER.read_text();self.assertIn("if out.exists():raise RuntimeError('fresh fixed case directory required; no retry or overwrite')",text);self.assertNotIn('shutil.rmtree',text)
  (HERE/'offline-test-receipt.json').write_text(json.dumps(dict(status='TWO_DEFAULT_PREFLIGHTS_REPEAT_AND_OFFLINE_GATE_TESTS_PASS',results=results,model_calls=0,reference_calls=0,runner_sha256=sha(RUNNER),plan_sha256=sha(HERE/'plan.json')),indent=2,sort_keys=True)+'\n')
 def test_reject_original_case_names(self):
  original=json.loads(Path(PLAN['historical_plan']['path']).read_text())
  self.assertEqual(len(runner.REMAINING),2)
  self.assertTrue({p['name'] for p in original['points']}.isdisjoint(runner.REMAINING))
  self.assertEqual({(p['i'],p['j']) for p in PLAN['points']} & {(p['i'],p['j']) for p in original['points']},set())

if __name__=='__main__':unittest.main(verbosity=2)
