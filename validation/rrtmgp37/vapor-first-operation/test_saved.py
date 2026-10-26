"""Reject causal substitutions and false nonnegative/conservative claims."""
from pathlib import Path
import importlib.util,copy,json,unittest,runpy,sys,io,contextlib
from unittest import mock
P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('vapor_saved',P/'verify_saved.py');V=importlib.util.module_from_spec(s);s.loader.exec_module(V);A=V.E.A
class ActualVaporBoundaries(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.d=V.data()
 def test_write_preserves_sealed_result_and_scopes_only_console(self):
  saved=json.loads((P/'result.json').read_text());writes=[];console=io.StringIO()
  def capture(path,text,*args,**kwargs):writes.append((path,text));return len(text)
  with mock.patch.object(sys,'argv',[str(P/'verify_saved.py'),'--write']), \
       mock.patch.object(Path,'write_text',autospec=True,side_effect=capture), \
       contextlib.redirect_stdout(console):
   runpy.run_path(str(P/'verify_saved.py'),run_name='__main__')
  self.assertEqual(len(writes),1);self.assertEqual(writes[0][0],P/'result.json')
  self.assertEqual(json.loads(writes[0][1]),saved)
  summary=json.loads(console.getvalue());self.assertFalse(summary['current_runtime_source_matches'])
  self.assertEqual(summary['source_scope'],'historical_PR209_snapshot')
 def test_reject_substituting_CU_for_actual_relaxation(self):
  x=self.d['components/host/vapor-components.txt'].decode();x=x.replace('relax_after','false_relax_after')
  with self.assertRaises((KeyError,ValueError)):A.causes(self.d['original/host/vapor-first.txt'].decode(),x)
 def test_first_native_result_must_match_replay(self):
  x=self.d['original/host/vapor-first.txt'].decode().replace('-3.8907008311720587E-014','0.0000000000000000E+000',1)
  with self.assertRaises(ValueError):A.causes(x,self.d['components/host/vapor-components.txt'].decode())
 def test_native_source_does_not_hide_prior_invalid_input(self):
  x=self.d['public/command-08.stdout'].decode().splitlines();row=x[2].split();row[3]='0';x[2]=' '.join(row)
  with self.assertRaises(ValueError):A.native_source('\n'.join(x))
 def test_predictor_undershoot_is_not_a_final_state(self):
  x=A.vapor('0 summary_rk 1 2 -1\n0 summary_rk 2 3 -2\n0 summary_pd 3 0 0\n0 summary_rk 3 0 0\n0 summary_micro 0 0 0\n0 summary_final_bdy 4 0 0\n')
  self.assertEqual(x['final_stage_negative_samples'],0);self.assertEqual(x['predictor_negative_samples'],5)
 def test_shared_flux_conservation_cannot_be_assumed(self):
  x=self.d['native_transport/command-03.stdout'].decode().splitlines();row=x[2].split();row[3]='1';x[2]=' '.join(row)
  with self.assertRaises(ValueError):A.native_transport('\n'.join(x))
 def test_restart_cannot_omit_a_variable(self):
  names={'original_first':'original/history-comparison.json','original_components':'components/history-comparison.json','corrected_observer':'short_observed/history-comparison.json','corrected_restart':'restart/history-comparison.json'};c={n:json.loads(self.d[p]) for n,p in names.items()};row=next(iter(c['corrected_restart']['inventory'].values()));row.pop(next(iter(row)))
  with self.assertRaises(ValueError):A.comparisons(c)
 def test_new_final_negative_is_preserved_as_failure(self):
  x=A.vapor('0 summary_rk 3 1 -1e-12\n0 summary_final_bdy 4 0 -1e-12\n');self.assertEqual(x['final_stage_negative_samples'],1);self.assertLess(x['final_stage_minimum'],0)
if __name__=='__main__':unittest.main(verbosity=2)
