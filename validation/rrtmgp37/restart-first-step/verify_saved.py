#!/usr/bin/env python3
"""Replay bounded saved evidence. This command runs no model or compiler."""
from pathlib import Path
import argparse,gzip,hashlib,importlib.util,io,json,tarfile
P=Path(__file__).resolve().parent;R=P.parents[2]
s=importlib.util.spec_from_file_location('restart_evidence_analysis',P/'analyze_saved.py');A=importlib.util.module_from_spec(s);s.loader.exec_module(A)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def data():
 identity=json.loads((P/'identity.json').read_text());archive=(P/'saved/evidence.tar.gz').read_bytes()
 A.require(sha(archive)==identity['archive']['sha256'],'evidence archive hash')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(archive)),mode='r:') as tar:
  A.require(set(tar.getnames())==set(identity['files']),'unindexed evidence')
  saved={n:tar.extractfile(n).read() for n in identity['files']}
 for n,row in identity['files'].items():A.require(len(saved[n])==row['bytes'] and sha(saved[n])==row['sha256'],'evidence payload '+n)
 for n,row in identity['current_sources'].items():A.require(sha((R/n).read_bytes())==row['sha256'],'current source '+n)
 A.require(saved['build/compiled_solve.F']==(R/'WRF/dyn_em/solve_em.F').read_bytes(),'tested public source differs')
 build=json.loads(saved['build/receipt.json']);A.require(build['source']['sha256']==sha(saved['build/compiled_solve.F']),'build source receipt')
 fixed=json.loads(saved['fixed/receipt.json']);A.require(build['executable']['sha256']==fixed['executable']['sha256'],'fixed run used other executable')
 # A source identity pins the complete change, including barrier placement.
 old=json.loads((P.parent/'historical-source/snapshot-3ad2efd1.json').read_text())['files']['WRF/dyn_em/solve_em.F']
 prior=gzip.decompress((P.parent/'historical-source'/old['archive']).read_bytes());A.require(sha(prior)==old['sha256'],'old source binding')
 new=saved['build/compiled_solve.F'];anchor=b'   DO ij = 1 , grid%num_tiles\n      ! Final specified MU changed'
 A.require(new.count(anchor)==1,'mass halo refresh missing or duplicated')
 begin=new.index(anchor)+len(b'   DO ij = 1 , grid%num_tiles\n');end=new.index(b'      CALL set_w_surface',begin)
 block=new[begin:end];A.require(b'IF ( config_flags%specified )' in block and b'CALL set_physical_bc2d( grid%mu_2' in block,'wrong halo repair')
 A.require(new[:begin]+new[end:]==prior,'production changes exceed the isolated halo refresh')
 return saved
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');args=parser.parse_args()
 result=A.analyze(data().__getitem__,json.loads((P/'plan.json').read_text()))
 if args.write:(P/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 else:A.require(result==json.loads((P/'result.json').read_text()),'saved result differs')
 print(json.dumps({**result,'current_runtime_source_matches':True}))
if __name__=='__main__':main()
