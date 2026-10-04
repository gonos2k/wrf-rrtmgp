from pathlib import Path
import sys, json, hashlib, subprocess, os
import numpy as np
HERE=Path(__file__).resolve().parent
PLAN=json.loads((HERE/'plan.json').read_text())
TOOL=Path(PLAN['source_checkout'])/'tools/udm_frozen_optics'
sys.path.insert(0,str(TOOL))
import test_fortran_lookup as t
from lookup import FrozenTable

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
out=HERE/'fortran-nominal-v1'
assert not out.exists(), 'Preserve prior lookup artifacts'
out.mkdir()
generation=Path(PLAN['generation_runs'][0]['output_dir'])
table=FrozenTable(generation)
exe=Path(PLAN['workspace'])/'build/udm37-fatal-message-components-v1/test_rrtmgp_frozen_lookup'
lam=np.tile(table.axes['lambda'],5)
temp=np.repeat(np.asarray([150.,179.996,180.,233.,330.]),len(table.axes['lambda']))
path=np.full(lam.shape,6.054224e-4)
query=out/'query.txt';csv=out/'fortran-output.csv'
nc,nl=t.write_query(query,lam,path,lam,temp,path)
rec={'status':'NOT_RUN','exe_sha256':sha(exe),'table_sha256':table.table_sha256,'generation_receipt_sha256':table.receipt_sha256,'query_sha256':sha(query),'query_count_unpadded':len(lam),'matrix_shape':[nc,nl],'temperatures_K':[150.,179.996,180.,233.,330.],'tolerances':{'rtol':t.RTOL,'atol':t.ATOL},'scope':'Python/Fortran interpolation implementation parity and fixture rejection checks only.179.996 is the nominal formatted log temperature. No RTE or forecast.'}
try:
 env=os.environ.copy();env['LD_LIBRARY_PATH']=str(Path(PLAN['workspace'])/'build/deps/netcdf/lib')+os.pathsep+env.get('LD_LIBRARY_PATH','')
 proc=subprocess.run([str(exe),str(generation/'frozen-ice-psd-moments.nc'),str(query),str(csv)],env=env,text=True,capture_output=True,timeout=30)
 rec['returncode']=proc.returncode
 (out/'stdout.log').write_text(proc.stdout);(out/'stderr.log').write_text(proc.stderr)
 if proc.returncode!=0: raise RuntimeError('Fortran fixture failed')
 rec['comparison']=t.compare_output(table,csv,lam,path,lam,temp,path,nc,nl)
 rec['status']='PASS_SCOPED_IMPLEMENTATION_PARITY'
except BaseException as exc:
 rec['status']='FAIL_PRESERVED';rec['exception']=repr(exc)
finally:
 rec['artifact_sha256']={x.name:sha(x) for x in out.iterdir() if x.is_file()}
 (out/'receipt.json').write_text(json.dumps(rec,indent=2)+'\n')
 print(json.dumps({'status':rec['status'],'returncode':rec.get('returncode'),'comparison':rec.get('comparison')}))
if rec['status']!='PASS_SCOPED_IMPLEMENTATION_PARITY': raise SystemExit(1)
