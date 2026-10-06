from __future__ import annotations
import hashlib,importlib.util,json,shutil,sys,tempfile,unittest
from pathlib import Path

sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('verify',Path(__file__).with_name('verify.py'))
verify=importlib.util.module_from_spec(spec)
sys.modules['verify']=verify
spec.loader.exec_module(verify)

ROOT=Path(__file__).resolve().parent

class PackageControls(unittest.TestCase):
    def test_package_passes(self):
        self.assertEqual(verify.verify_tree(ROOT)['status'],'PASS_PACKAGE_AND_STORED_PROFILE_CONTRACTS')

    def copied(self):
        td=tempfile.TemporaryDirectory(prefix='bon-package-control-')
        dest=Path(td.name)/'copy'; shutil.copytree(ROOT,dest,ignore=shutil.ignore_patterns('manifest.json'))
        shutil.copyfile(ROOT/'manifest.json',dest/'manifest.json')
        self.addCleanup(td.cleanup)
        return dest

    def repin(self,root,rel):
        m=json.loads((root/'manifest.json').read_text()); b=(root/rel).read_bytes()
        digest=hashlib.sha256(b).hexdigest()
        for row in m['payloads']:
            if row['path']==rel: row['sha256']=digest; row['size_bytes']=len(b); break
        else: raise AssertionError(rel)
        for origin in m['origins'].values():
            if origin['package_path']==rel:
                origin['origin_sha256']=digest; origin['origin_size_bytes']=len(b); break
        (root/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')

    def test_unlisted_file_rejected(self):
        root=self.copied(); (root/'unexpected.txt').write_text('extra\n')
        with self.assertRaisesRegex(ValueError,'closed roster'): verify.verify_tree(root)

    def test_bad_asset_hash_rejected(self):
        root=self.copied(); p=root/'analysis/result.json'; p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'package hash mismatch'): verify.verify_tree(root)

    def test_surface_sum_tamper_rejected(self):
        root=self.copied(); p=root/'summary.json'; d=json.loads(p.read_text()); d['common_bands_3_13']['legacy_surface_DN_Wm2']+=1
        p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n'); self.repin(root,'summary.json')
        with self.assertRaisesRegex(ValueError,'stored broadband sum mismatch'): verify.verify_tree(root)

    def test_band_relabel_rejected(self):
        root=self.copied(); p=root/'analysis/result.json'; d=json.loads(p.read_text()); d['bands'][2]['band']=12
        p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n'); self.repin(root,'analysis/result.json')
        with self.assertRaisesRegex(ValueError,'band labels/order'): verify.verify_tree(root)

    def test_emissivity_source_mismatch_rejected(self):
        root=self.copied(); p=root/'analysis/result.json'; d=json.loads(p.read_text()); d['bands'][0]['gp_emitted_surface_source_Wm2sr']+=0.01
        p.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n'); self.repin(root,'analysis/result.json')
        with self.assertRaisesRegex(ValueError,'emissivity application mismatch'): verify.verify_tree(root)

if __name__=='__main__': unittest.main()
