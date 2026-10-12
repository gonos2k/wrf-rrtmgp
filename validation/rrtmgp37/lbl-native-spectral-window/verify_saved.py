"""Replay PR165 payloads into the complete native window; no new solver."""
from pathlib import Path
import gzip,hashlib,importlib.util,json
B=Path(__file__).resolve().parent
P=B.parent/'lbl-grid-threshold-comparison'
s=importlib.util.spec_from_file_location('native_core',B/'analyze_core.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
def data(p):return p.read_bytes()
def loadj(p):return json.loads(data(p))
def gz(p):return gzip.decompress(data(p))
def replay():
    ps=loadj(P/'samples.json');parent=loadj(P/'result.json');native={}
    source=gz(P/'source/oprop.f90.official.gz').decode()
    c.require('DXFF1 / 0.002 /' in source and 'DXFF2 / 0.008 /' in source and 'DXFF3 / 0.032 /' in source,'pinned source geometric spacing')
    c.require('DVR2 = (DXF2/DXF1)*DV' in source and 'DVR3 = (DXF3/DXF1)*DV' in source,'source ratio definitions')
    for a in c.RATIOS:
        k=ps[a][40]['panel']
        native[a]=c.extract(gz(P/f'OD/{a}.{k}.header.gz'),gz(P/f'OD/{a}.{k}.payload.gz'),gz(P/f'traces/{a}.min.gz').decode(),a)
        c.require(c.csv_bytes(native[a])==data(B/f'{a}.native.csv'),'complete native CSV vs actual OD payload')
    result,shared=c.analyze(native,parent,ps)
    c.require(c.csv_bytes(shared)==data(B/'half-quarter.shared161.csv'),'complete shared161 CSV')
    c.require(result==loadj(B/'result.json'),'computed result and no physical promotion')
    return result

def main():
    manifest=loadj(B/'manifest.json');actual={str(p.relative_to(B)) for p in B.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
    c.require(manifest['production_accepted'] is False and {r['path'] for r in manifest['files']}==actual,'exact new package roster')
    for r in manifest['files']:
        b=data(B/r['path']);c.require(len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'],'sealed new bytes')
    pins=loadj(B/'parent-pins.json');c.require(pins['parent_main_commit']=='3e577a5bacc5d189cd2528675255da1c1b3641b6' and pins['parent_main_tree']=='a63510836516da367aaabda461eacbad6327b047' and pins['parent_merged_PR']==165,'merged parent snapshot')
    for r in pins['files']:
        p=B.parent/r['path'];c.require(p.resolve().is_relative_to(P.resolve()),'parent pin scope')
        b=data(p);c.require(len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'],'unchanged parent data/source')
    old=loadj(P/'manifest.json')
    for r in old['files']:
        b=data(P/r['path']);c.require(len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'],'sealed PR165 bytes')
    receipt=loadj(B/'root-readback-receipt.json')
    c.require(receipt['returncode']==0 and receipt['native_rows']=={'h':81,'half':161,'quarter':321} and receipt['shared_rows']==161 and receipt['fresh_model_or_compiler_processes']==0 and receipt['production_accepted'] is False,'readback execution scope')
    result=replay()
    print(json.dumps({'status':result['status'],'native_sign_counts':{a:(r['negative_samples'],r['native_samples']) for a,r in result['native'].items()},
      'shared161_max_difference':result['shared161_half_to_quarter']['maximum_abs_OD_difference'],
      'half_R3_nodes_max_difference':result['alignment_group_diagnostics']['half_R3_nodes']['maximum_abs_OD_difference'],
      'fresh_solver_executions':0,'physical_reference_accepted':False}))
if __name__=='__main__':main()
