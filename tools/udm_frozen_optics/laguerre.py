"""Stable Gauss–Laguerre rule from the symmetric Jacobi eigenproblem.

Golub–Welsch construction for alpha=0, weight exp(-u) on [0,infinity).
The fixed LAPACK STEV driver avoids dependence on SciPy's changing auto choice.
Zero weights in the far tail are permitted; nonfinite values and invalid
normalization/mass moments are rejected before a spectral task is submitted.
"""
import math
import numpy as np
from scipy.linalg import eigh_tridiagonal


def validate_rule(nodes,weights):
    nodes=np.asarray(nodes,dtype=float);weights=np.asarray(weights,dtype=float)
    if nodes.ndim!=1 or weights.shape!=nodes.shape or nodes.size<4:
        raise ValueError('Invalid Laguerre rule shape')
    if not np.all(np.isfinite(nodes)) or not np.all(np.isfinite(weights)):
        raise ValueError('Nonfinite Laguerre nodes or weights')
    if not np.all(nodes>0) or not np.all(np.diff(nodes)>0) or not np.all(weights>=0):
        raise ValueError('Invalid Laguerre node/weight range')
    errors=[abs(float(np.sum(weights*nodes**power))/math.factorial(power)-1.) for power in range(7)]
    if max(errors)>5e-12:
        raise ValueError('Laguerre normalization/area/mass polynomial moments failed')
    return nodes,weights


def rule(order):
    if not isinstance(order,int) or not 4<=order<=1024:
        raise ValueError('Gauss-Laguerre order must be an integer in 4..1024')
    nodes,vectors=eigh_tridiagonal(2.*np.arange(order)+1.,np.arange(1,order,dtype=float),
                                   lapack_driver='stev')
    return validate_rule(nodes,vectors[0,:]**2)
