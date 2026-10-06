#!/usr/bin/env python3
"""Optional exact local-file joins; this opens NetCDF but runs no solver."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--historical-coefficient',type=Path,required=True)
 ap.add_argument('--current-coefficient',type=Path,required=True)
 ap.add_argument('--counterfactual-coefficient',type=Path,required=True)
 ap.add_argument('--reference-dir',type=Path,required=True)
 ap.add_argument('--package',type=Path,default=Path(__file__).resolve().parent)
 ap.add_argument('--output',type=Path)
 a=ap.parse_args();package=a.package.resolve()
 try:
  import numpy as np
  from netCDF4 import Dataset
 except ImportError as exc: raise SystemExit('requires NumPy and netCDF4; no package installation attempted') from exc
 expected={'historical-coefficient':'b9f4b15796d132880fffb49ac45c29753c1ee70a8ee3fed733899cb315c75e9b',
           'current-coefficient':'584f1dd41ea9fc07d4ee3754eb1dafbd46ad3161cd6fd20fa06b6922b6f0702e',
           'counterfactual-coefficient':'02d4cd320696b9b8a3006a373855a3b4b95fdb6495251fe5f5692d6a9fddfaa4'}
 paths={'historical-coefficient':a.historical_coefficient,'current-coefficient':a.current_coefficient,'counterfactual-coefficient':a.counterfactual_coefficient}
 hashes={k:sha(p) for k,p in paths.items()}
 for k,v in expected.items():
  if hashes[k]!=v:raise ValueError(f'{k} hash mismatch')
 join=json.loads((package/'joins/reference-byte-join-v1.json').read_text());refhash={r['variable']:r['sha256'] for r in join['rows']}
 names={'rld':'rld_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc','rlu':'rlu_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc','rsd':'rsd_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc','rsu':'rsu_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc'}
 refpaths={k:a.reference_dir/v for k,v in names.items()};refactual={k:sha(p) for k,p in refpaths.items()}
 for k,v in refhash.items():
  if refactual[k]!=v:raise ValueError(f'reference {k} hash mismatch')
 with Dataset(a.historical_coefficient) as old,Dataset(a.current_coefficient) as current,Dataset(a.counterfactual_coefficient) as cf:
  names_common=sorted((set(old.variables)&set(current.variables))-{'solar_source','solar_source_quiet','solar_source_facular','solar_source_sunspot'})
  if len(names_common)!=29:raise ValueError(f'expected 29 common non-solar variables, found {len(names_common)}')
  compared=[]
  for name in names_common:
   x=np.asarray(old.variables[name][:]);y=np.asarray(current.variables[name][:])
   if x.shape!=y.shape or x.dtype!=y.dtype or not np.array_equal(x,y):raise ValueError(f'coefficient variable differs: {name}')
   compared.append(name)
  oldsolar=np.asarray(old.variables['solar_source'][:],dtype=np.float64)
  quiet=np.asarray(cf.variables['solar_source_quiet'][:],dtype=np.float64)
  if oldsolar.shape!=(224,) or quiet.shape!=(224,) or not np.array_equal(oldsolar,quiet):raise ValueError('224-element old solar / counterfactual quiet vector mismatch')
 result={'status':'PASS_SCOPED_LOCAL_LINEAGE_JOINS','external_file_sha256':{**hashes,**{'reference_'+k:v for k,v in refactual.items()}},'common_non_solar_variables_exact':len(compared),'historical_solar_vs_counterfactual_quiet_elements_exact':224,'solver_or_network_used':False,'scope':'Local byte hashes, coefficient variable intersection, historical solar vector and four retained reference files only.'}
 text=json.dumps(result,indent=2,sort_keys=True)+'\n'
 if a.output:
  if a.output.exists():raise FileExistsError('refusing output overwrite')
  a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text)
 print(json.dumps(result,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
