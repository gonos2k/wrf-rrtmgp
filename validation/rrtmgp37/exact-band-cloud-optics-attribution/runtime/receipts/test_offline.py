#!/usr/bin/env python3
"""Offline controls for the two-call exact-band swap runner; no executable is launched."""
import importlib.util
import sys
from pathlib import Path
import numpy as np
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
RUNNER=ROOT/'build/udm37-exact-band-cloud-swap-runtime-v2/run_two.py'
spec=importlib.util.spec_from_file_location('cloud_swap_runner',RUNNER)
runner=importlib.util.module_from_spec(spec); sys.modules[spec.name]=runner; spec.loader.exec_module(runner)
prep=runner.load_json(runner.PREP_PLAN)

def must_fail(fn,label):
    try: fn()
    except (ValueError,RuntimeError): return
    raise AssertionError(f'negative control accepted: {label}')

runner.verify_prepared(prep)
control=runner.read_override(runner.resolve_root_path(prep['generated_overrides']['full_baseline_prepared_control']['path']))
variant=runner.read_override(runner.resolve_root_path(prep['generated_overrides']['legacy_exact_common_band_swap']['path']))
assert runner.validate_override_pair(control,variant)=={'TAU':36,'SSA':36,'ASYM':36}
# The retained baseline is an offline control: complete bytes and all 54 fields must agree.
case={'output':str(runner.BASE_RESULT)}
check=runner.validate_control(case,prep,runner.load_json(runner.PLAN)['fixed_pins']['result_parser']['path'])
assert check['whole_file_baseline_identity'] and check['section_count']==54
# An extra edit outside the selected k=30..32, GP-band 3..14 rectangle must be rejected.
bad={k:np.array(v,copy=True) if isinstance(v,np.ndarray) else v for k,v in variant.items()}
bad['TAU'][0,0,0]=np.nextafter(bad['TAU'][0,0,0],np.inf)
must_fail(lambda: runner.validate_override_pair(control,bad),'outside-scope optical edit')
# A selected-cell omission is also rejected; every prepared property has the 36-cell contract.
bad2={k:np.array(v,copy=True) if isinstance(v,np.ndarray) else v for k,v in variant.items()}
bad2['SSA'][0,29,2]=control['SSA'][0,29,2]
must_fail(lambda: runner.validate_override_pair(control,bad2),'missing selected-cell replacement')
# Nonfinite values and wrong dimensions cannot enter the offline override contract.
bad3={k:np.array(v,copy=True) if isinstance(v,np.ndarray) else v for k,v in variant.items()}
bad3['ASYM'][0,29,2]=np.nan
must_fail(lambda: runner.validate_override_pair(control,bad3),'nonfinite prepared property')
bad4={k:np.array(v,copy=True) if isinstance(v,np.ndarray) else v for k,v in variant.items()}
bad4['TAU']=bad4['TAU'][:,:,:13]
must_fail(lambda: runner.validate_override_pair(control,bad4),'wrong band dimension')
print('PASS offline exact-scope/finite/shape controls; 0 executable invocations')
