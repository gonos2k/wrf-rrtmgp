import json, shutil, tempfile, unittest, sys
sys.dont_write_bytecode = True
from pathlib import Path
import verify

class PackageTests(unittest.TestCase):
    def setUp(self): self.root=Path(__file__).parent.resolve()
    def test_pristine(self):
        r=verify.verify(self.root); self.assertEqual(r['status'],'PASS_NESTED_RUNTIME_PACKAGE_INTEGRITY_AND_SCOPE'); self.assertEqual(r['restart_raw_variable_hash_rows'],3783)
    def copied(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); dst=Path(td.name)/'pkg'; shutil.copytree(self.root,dst); return dst
    def recalc_manifest(self,root):
        p=root/'artifact-manifest.json'; d=json.loads(p.read_text())
        for e in d['files']:
            b=(root/e['path']).read_bytes(); import hashlib; e['size_bytes']=len(b); e['sha256']=hashlib.sha256(b).hexdigest()
        p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
    def test_payload_tamper_rejected(self):
        p=self.copied(); (p/'README.md').write_text('tampered\n')
        with self.assertRaisesRegex(ValueError,'payload hash/size'): verify.verify(p)
    def test_semantic_status_tamper_rejected_after_manifest_refresh(self):
        p=self.copied(); q=p/'receipts/restart-execution.json'; d=json.loads(q.read_text()); d['status']='PASS'; q.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n'); self.recalc_manifest(p)
        with self.assertRaisesRegex(ValueError,'restart original execution status'): verify.verify(p)
    def test_hash_csv_mutation_rejected_after_manifest_refresh(self):
        p=self.copied(); q=p/'reports/restart-variable-raw-hashes.csv'; s=q.read_text(); q.write_text(s.replace('221439efc46c9df044058aa110e0fd3f37d7a45b56726e02c4062bb359ac3f8f','0000000000000000000000000000000000000000000000000000000000000000',1)); self.recalc_manifest(p)
        with self.assertRaisesRegex(ValueError,'raw variable hash CSV does not match report'): verify.verify(p)

if __name__=='__main__': unittest.main()
