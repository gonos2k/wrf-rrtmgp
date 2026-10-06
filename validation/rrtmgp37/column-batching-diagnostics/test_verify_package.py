import json,shutil,subprocess,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
REFS=json.loads((HERE/'source_references.json').read_text())
EXTERNAL_AVAILABLE=Path(REFS['evidence_root']).is_dir()
class VerifyPackageTests(unittest.TestCase):
 def clone(self,d):
  out=Path(d)/'pkg';shutil.copytree(HERE,out,ignore=shutil.ignore_patterns('__pycache__'));return out
 def runver(self,p): return subprocess.run(['python3',str(p/'verify_package.py'),str(p)],capture_output=True,text=True)
 def test_clean_package(self):
  r=self.runver(HERE);self.assertEqual(r.returncode,0,r.stderr)
 @unittest.skipUnless(EXTERNAL_AVAILABLE, 'external evidence workspace is not present in this checkout')
 def test_external_receipt_pins_when_workspace_available(self):
  r=subprocess.run(['python3',str(HERE/'verify_package.py'),str(HERE),'--external'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
 def test_payload_tamper_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.clone(d);(p/'README.md').write_text((p/'README.md').read_text()+'tamper\n');r=self.runver(p);self.assertNotEqual(r.returncode,0)
 def test_manifest_path_traversal_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.clone(d);m=json.loads((p/'manifest.json').read_text());m['files'][0]['path']='../escape';(p/'manifest.json').write_text(json.dumps(m));r=self.runver(p);self.assertNotEqual(r.returncode,0)
 def test_manifest_digest_tamper_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=self.clone(d);m=json.loads((p/'manifest.json').read_text());m['files'][0]['sha256']='0'*64;(p/'manifest.json').write_text(json.dumps(m));r=self.runver(p);self.assertNotEqual(r.returncode,0)
if __name__=='__main__': unittest.main()
