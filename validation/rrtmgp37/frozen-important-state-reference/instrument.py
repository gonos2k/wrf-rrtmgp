"""Rebuild the actual private selection observer from current public source."""
from pathlib import Path
import importlib.util
P=Path(__file__).resolve().parent

def transform(root):
 s=importlib.util.spec_from_file_location('frozen_baseline_observer',P.parent/'convective-support/instrument.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
 text=m.transform(root)['module_ra_rrtmg_lw.F']
 text=text.replace(' USE module_real_budget_probe,ONLY:column,frozen',' USE module_real_budget_probe,ONLY:column,frozen\n USE module_frozen_selection_probe,ONLY:select_column',1)
 needle='         IF(gp_batch_enabled) THEN';pos=text.index(needle,text.index('gp_seed=rrtmgp_column_seed'))
 return text[:pos]+'''         IF(run_rrtmgp.AND.gp_frozen)CALL select_column(i,j,audit_time,tlay(1,kts:kte), &
          gp_hwp(1,kts:kte),gp_lambda_h(1,kts:kte))
'''+text[pos:]
