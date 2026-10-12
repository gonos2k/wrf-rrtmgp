"""Research scope is enforceable, and cannot silently become science approval."""
from pathlib import Path
import copy,hashlib,importlib.util,json,struct,subprocess,sys,unittest
from unittest.mock import patch
B=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('profile_audit',B/'audit_profile.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
class ResearchContract(unittest.TestCase):
    def test_actual_cold_and_restart_profile_with_disclosed_CF0_state(self):
        p=c.load(B/'profile.json')
        for case in p['namelist_bindings']:
            r=c.audit(c.ROOT,p,case,(c.ROOT/p['namelist_bindings'][case]['path']).read_bytes())
            self.assertFalse(r['production_accepted']);self.assertEqual(len(r['unresolved_required_gates']),7)
            by={s['role']:s for s in r['checked_snapshots']}
            self.assertFalse(by['initial_input_before_CF_diagnosis']['CF_diagnostic_stamp_nonnegative'])
            self.assertEqual(by['history_60s_after_step6']['CF0_positive_condensate_cells']['QICE'],12)
            self.assertFalse(by['history_60s_after_step6']['direct_radiation_call_state'])
    def test_external_preservation_and_implicit_unit_approval_refused(self):
        p=c.load(B/'profile.json');n=(c.ROOT/p['namelist_bindings']['warm-cloud-on']['path']).read_bytes()
        with self.assertRaisesRegex(ValueError,'external preservation'):c.audit(c.ROOT,p,'warm-cloud-on',n,number_policy='preserve_external')
        p=copy.deepcopy(p);p['number_policy']['encoding']='kg_d-1'
        with self.assertRaisesRegex(ValueError,'number relabeling'):c.audit(c.ROOT,p,'warm-cloud-on',n)
    def test_other_transport_configuration_requires_its_own_binding(self):
        p=c.load(B/'profile.json');n=(c.ROOT/p['namelist_bindings']['warm-cloud-on']['path']).read_bytes()
        changed=n.replace(b'scalar_adv_opt = 0',b'scalar_adv_opt = 1');self.assertNotEqual(n,changed)
        with self.assertRaisesRegex(ValueError,'configuration outside'):c.audit(c.ROOT,p,'warm-cloud-on',changed)
    def test_positive_graupel_cannot_hide_in_zero_species_profile(self):
        m=copy.deepcopy(c.load(B/'state-readback.json')['states'][2]);raw=bytearray((B/m['extracted_path']).read_bytes());struct.pack_into('<f',raw,7*236*4,1e-6)
        m['extracted_sha256']=hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError,'positive G/H'):c.decode_state(m,raw)
    def test_physical_request_refused_even_after_documentary_retagging(self):
        p=c.load(B/'profile.json');n=(c.ROOT/p['namelist_bindings']['warm-cloud-on']['path']).read_bytes();old=c.load
        def retag(path):
            x=old(path)
            if path.name=='review-resolution-checklist.json':
                for i in x['items']:
                    if i['id'] in c.GATES:i['integrated_validation']='PASS_PHYSICAL'
            return x
        with patch.object(c,'load',side_effect=retag):r=c.audit(c.ROOT,p,'warm-cloud-on',n,purpose='physical')
        self.assertEqual(r['status'],'REJECT_PHYSICAL_ACCEPTANCE');self.assertFalse(r['production_accepted'])
        proc=subprocess.run([sys.executable,'-I','-S',str(B/'audit_profile.py'),'--purpose','physical'],capture_output=True,text=True,timeout=60)
        self.assertEqual(proc.returncode,2);self.assertEqual(json.loads(proc.stdout)['status'],'REJECT_PHYSICAL_ACCEPTANCE')
if __name__=='__main__':unittest.main(verbosity=2)
