#!/usr/bin/env python3
"""Validate high-order quadrature and explicit nonfinite-weight rejection."""
import argparse
import json
import math
from pathlib import Path
import warnings
import numpy as np
from scipy.special import roots_laguerre
import laguerre
import generate as gen


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    if args.output_dir.exists():parser.error('Use a new output directory')
    args.output_dir.mkdir(parents=True)
    source_hash=gen.sha(Path(laguerre.__file__))
    cases=[]
    for order in (4,16,32,64,128,256,512,1024):
        nodes,weights=laguerre.rule(order)
        error=max(abs(float(np.sum(weights*nodes**p))/math.factorial(p)-1) for p in range(7))
        row=dict(order=order,max_polynomial_moment_relative_error=error,finite=True)
        if order<=256:
            other,other_weights=roots_laguerre(order)
            ndiff=float(np.max(abs(nodes-other)));wdiff=float(np.max(abs(weights-other_weights)))
            if ndiff>1e-8 or wdiff>1e-12:raise AssertionError('Independent Laguerre construction differs')
            row.update(scipy_special_node_max_absolute_difference=ndiff,scipy_special_weight_max_absolute_difference=wdiff)
        cases.append(row)
    rejected=[]
    n,w=laguerre.rule(16)
    for label,nodes,weights in [('nan-node',np.full(16,np.nan),w),('nan-weight',n,np.full(16,np.nan)),
                              ('zero-rule',n,np.zeros(16)),('bad-mass',n,w*.5),
                              ('negative-weight',n,-w),('shape',n,w[:15])]:
        try:laguerre.validate_rule(nodes,weights)
        except ValueError as exc:rejected.append(dict(case=label,reason=str(exc)))
        else:raise AssertionError('Invalid quadrature accepted')
    # Retain whether this installed SciPy reproduces the old high-order failure;
    # a future fixed SciPy need not fail for our explicit guarded rule to work.
    with warnings.catch_warnings(record=True) as observed:
        warnings.simplefilter('always'); old_nodes,old_weights=roots_laguerre(512)
    old_finite=bool(np.all(np.isfinite(old_nodes)) and np.all(np.isfinite(old_weights)))
    if not old_finite:
        try:laguerre.validate_rule(old_nodes,old_weights)
        except ValueError:pass
        else:raise AssertionError('Actual high-order nonfinite rule accepted')
    if gen.sha(Path(laguerre.__file__))!=source_hash:raise RuntimeError('Quadrature source changed')
    result=dict(status='PASS_NUMERICAL_ONLY',quadrature_sha256=source_hash,test_sha256=gen.sha(Path(__file__)),
                rule='Golub-Welsch, alpha=0, fixed LAPACK STEV',cases=cases,rejected_rules=rejected,
                old_scipy_special_512_finite=old_finite,old_scipy_warnings=[str(x.message) for x in observed],
                scope='Polynomial quadrature moments and independent rule agreement, not convergence of oscillatory Mie integrands')
    (args.output_dir/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'cases':len(cases),'rejected_rules':len(rejected),'old512_finite':old_finite}))


if __name__=='__main__':main()
