"""Four controls for the newly read native/interstitial evidence boundary."""
from pathlib import Path
import csv,io,importlib.util,json,struct,unittest
from unittest.mock import patch
B=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('native_saved',B/'verify_saved.py');v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
class NativeBoundary(unittest.TestCase):
    def test_quarter_only_point_changed_parent81_preserved(self):
        path=B/'quarter.native.csv';original=v.data;rows=list(csv.DictReader(io.StringIO(original(path).decode())))
        # Row117 is among the240 points never represented by the parent81 subset.
        before=[dict(r) for r in rows[::4]];rows[117]['OD']='0.0';self.assertEqual(before,rows[::4])
        altered=v.c.csv_bytes(rows)
        with patch.object(v,'data',side_effect=lambda p:altered if p==path else original(p)),self.assertRaisesRegex(ValueError,'native CSV'):
            v.replay()
    def test_new_shared_point_missing_old81_preserved(self):
        path=B/'half-quarter.shared161.csv';original=v.data;rows=list(csv.DictReader(io.StringIO(original(path).decode())))
        # Remove an odd row, which was absent from all original81 comparisons.
        before=rows[::2];altered=v.c.csv_bytes([r for i,r in enumerate(rows) if i!=41])
        self.assertEqual(len(before),81)
        with patch.object(v,'data',side_effect=lambda p:altered if p==path else original(p)),self.assertRaisesRegex(ValueError,'shared161 CSV'):
            v.replay()
    def test_nearest_point_on_wrong_grid_is_rejected(self):
        k=v.loadj(v.P/'samples.json')['quarter'][40]['panel'];header=v.gz(v.P/f'OD/quarter.{k}.header.gz');lo,hi,dv,n,pad=struct.unpack('<dddii',header)
        wrong=struct.pack('<dddii',lo+dv/2,hi+dv/2,dv,n,pad)
        with self.assertRaisesRegex(ValueError,'physical native coordinate'):
            v.c.extract(wrong,v.gz(v.P/f'OD/quarter.{k}.payload.gz'),v.gz(v.P/'traces/quarter.min.gz').decode(),'quarter')
    def test_result_cannot_promote_physical_acceptance(self):
        original=v.loadj
        def promote(p):
            x=original(p)
            if p==B/'result.json':x['physical_reference_accepted']=True
            return x
        with patch.object(v,'loadj',side_effect=promote),self.assertRaisesRegex(ValueError,'physical promotion'):
            v.replay()
if __name__=='__main__':unittest.main(verbosity=2)
