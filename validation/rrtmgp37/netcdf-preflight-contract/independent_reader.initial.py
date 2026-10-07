from pathlib import Path
import hashlib,json
import numpy as np
from scipy.io import netcdf_file
prep=Path(__file__).parent
plan=json.loads((prep/'independent-reader-plan.json').read_text())
root=Path(plan['input_root']);results=[]
expected=np.array([[1000*j+17*i for i in range(1,4)] for j in range(1,6)],dtype=np.int32)
for optimization in plan['optimization_modes']:
    for path in sorted((root/optimization/'ranks-1').glob('*.nc')):
        with netcdf_file(path,'r',mmap=False) as ds:
            if path.name.startswith('preflight-'):
                follow=int(path.stem.split('-')[-1])
                times=[b''.join(row).decode() for row in ds.variables['Times'].data]
                assert times==['2026-10-06_00:00:00',f'2026-10-06_0{follow}:00:00'],(path,times)
                values=ds.variables['FIELD'].data.copy()
                assert values.shape==(2,5,3)
                assert np.array_equal(values[0],expected) and np.array_equal(values[1],expected)
                claim={'kind':'rejected_write_recovery','Times':times,'field_values_exact':30,'no_empty_intermediate_record':True}
            elif path.name=='zz.nc':
                times=[b''.join(row).decode() for row in ds.variables['Times'].data]
                assert times==['2026-10-06_00:00:00','2026-10-06_01:00:00']
                for name,offset in [('INT_UPPER',0),('INT_LOWER',0),('FLOAT_REAL',.25),('FLOAT_LOWER',.5)]:
                    v=ds.variables[name];values=v.data.copy()
                    assert v.dimensions==('Time','independent_n','vertical_k')
                    assert getattr(v,'MemoryOrder')==b'ZZ'
                    for record in range(2):
                        assert np.array_equal(values[record],expected+100000*record+offset)
                claim={'kind':'ordered_ZZ','Times':times,'four_fields_values_exact':120,'dimension_order_exact':True}
            else:
                assert path.name.startswith('bad-order-attribute-')
                idx=int(path.stem.split('-')[-1]);wanted={1:b'xyzq',2:b'qq',3:b''}[idx]
                assert ds.variables['FIELD'].MemoryOrder==wanted
                claim={'kind':'malformed_attribute_fixture','attribute_hex':wanted.hex()}
        results.append({'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'size_bytes':path.stat().st_size,**claim})
assert len(results)==plan['expected_files']
(prep/'independent-reader-result.json').write_text(json.dumps({'status':'PASS_SCOPED_INDEPENDENT_READER','reader_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'results':results,'production_accepted':False},indent=2)+'\n')
print('PASS_SCOPED_INDEPENDENT_READER',len(results))
