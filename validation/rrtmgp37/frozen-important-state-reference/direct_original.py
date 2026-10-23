"""Separate table interpolation from its original integration method at actual state."""
from pathlib import Path
import sys,json,importlib.util,hashlib
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-frozen-important-original-v1';O.mkdir(exist_ok=False)
sys.path.insert(0,str(R/'tools/udm_frozen_optics'))
s=importlib.util.spec_from_file_location('original_frozen_generator',R/'tools/udm_frozen_optics/generate.py');g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
base=B/'udm37-frozen-planck-coverage-v1';lib=base/'runs/frozen-planck-150-330-step5-plus233-v1/kernel/libmie_dynamic.so';inputs=g.inputs_at(base/'inputs',False)
target=json.loads((B/'udm37-frozen-selected-selection-v1/target.json').read_text());g.initialize(str(lib),str(inputs['IOP_2008_ASCIItable.dat']),str(inputs['tsi-ssi_v03r00_reference-spectra_c20240830.txt']),128,32000000)
rows=[]
for i,(lo,hi) in enumerate(g.EXPECTED_BOUNDS['LW']):
 row=g.integrate(('LW',i,lo,hi,target['lambda_m_1'],[target['temperature_K']],50.));rows.append(row);(O/('band-%02d.json'%(i+1))).write_text(json.dumps(row,indent=2)+'\n');print('ORIGINAL_DIRECT',i+1,flush=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r={'completed':True,'state':target,'order':128,'spectral_max_step_cm_1':50.,'bands':rows,'library_sha256':sha(lib),'generator_sha256':sha(R/'tools/udm_frozen_optics/generate.py'),'laguerre_sha256':sha(R/'tools/udm_frozen_optics/laguerre.py'),'source_adaptation':json.loads((lib.parent/'source-adaptation.json').read_text()),'ice_sha256':sha(inputs['IOP_2008_ASCIItable.dat']),'density_kg_m3':912.,'physical_accuracy_approved':False};(O/'result.json').write_text(json.dumps(r,indent=2)+'\n')
