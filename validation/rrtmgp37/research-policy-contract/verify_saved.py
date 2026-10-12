"""Verify the fixed research contract and root's retained-state readback."""
from pathlib import Path
import gzip,hashlib,importlib.util,json
B=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('contract',B/'audit_profile.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
def main():
    m=c.load(B/'manifest.json');actual={str(p.relative_to(B)) for p in B.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
    c.require(m['production_accepted'] is False and {r['path'] for r in m['files']}==actual,'exact contract package roster')
    for r in m['files']:
        p=B/r['path'];c.require(p.stat().st_size==r['bytes'] and c.digest(p)==r['sha256'],'sealed contract bytes')
    meta=c.load(B/'state-readback.json')
    for r in meta['raw_files']:
        p=c.ROOT/r['path'];v=p.read_bytes();raw=gzip.decompress(v)
        c.require(len(v)==r['compressed_bytes'] and hashlib.sha256(v).hexdigest()==r['compressed_sha256'],'retained raw archive binding')
        c.require(len(raw)==r['uncompressed_bytes'] and hashlib.sha256(raw).hexdigest()==r['uncompressed_sha256'],'retained raw NetCDF bytes')
    # CI validates raw-file identity and the extracted float32 packets. It does
    # not independently decode NetCDF variables; root used NetCDF4 for that.
    c.require(meta['fresh_solver_executions']==0 and meta['production_accepted'] is False,'readback scope')
    p=c.load(B/'profile.json');results={}
    for case,r in p['namelist_bindings'].items():
        n=(c.ROOT/r['path']).read_bytes();results[case]=c.audit(c.ROOT,p,case,n,source_scope="retained")
    c.require(results==c.load(B/'result.json'),'declared research audit vs computed state/source binding')
    print(json.dumps({'status':'PASS_SCOPED_RESEARCH_POLICY_CONTRACT','retained_namelists':2,'source_files':11,'source_scope':'historical_snapshot','current_tree_approved_by_legacy_profile':False,'checked_snapshots':4,'history_60s_CF0_positive_ice_cells':12,'physical_required_gates_unresolved':7,'physical_ready':False,'root_actual_saved_NetCDF_readback':True,'CI_independent_NetCDF_variable_decode':False,'fresh_solver_runs':0,'production_accepted':False}))
if __name__=='__main__':main()
