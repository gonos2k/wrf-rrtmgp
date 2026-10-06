# Shared-source Planck and face-policy attribution

This archive records one Python-only attribution for a held, clear longwave BON column: 45 layers (32 native plus 13 upper extensions), restricted to common physical bands 3–13. It keeps each engine’s own optical depth and within-band fractions; the 140 legacy and 128 RRTMGP g-points are never paired. No production policy was changed, no source fractions were normalized, and no new SI integration, RTE call, compiled replay, build, or forecast was run for this calculation.

Under the shared angular integral, the common-band engine difference is **+0.680771953682 W m⁻²**. The saved ordered path is:

| Step | Contribution (W m⁻²) |
|---|---:|
| Native Planck envelope → shared SI Planck source | +0.000083100951 |
| Native face policy → both-layer-local face policy | +0.000050386072 |
| Remaining shared-SI / both-layer-local residual | +0.680638466659 |
| Total | +0.680771953682 |

The residual is 99.9804% of the native common-angle difference. The lowest layer contributes 0.506137 W m⁻² (74.36% of the total); native 32-layer emitters contribute 0.649248 W m⁻² and the 13 upper extensions 0.031390 W m⁻². A **hypothetical** unit-sum rescaling has a triangle upper bound of 0.002304985 W m⁻² (0.3387% of the residual); no rescaling was performed. The additional isothermal counterfactual is +0.682508783 W m⁻² and is not part of the three-term decomposition.

This is a scoped source attribution, not a physical-accuracy verdict. The remaining term combines the engines’ own absorption coefficients, correlated-k discretization, and within-band Planck-fraction structure. It does not isolate optical depth or identify an accuracy winner. The face-policy comparison is an algorithmic sensitivity, not proof that either implementation is wrong. The separate independent p-fraction, Planck-source, and common-angle archives are pinned as dependencies; their payloads and manifests are checked by the verifier.

`verify.py` checks the closed archive roster, input/source/result hashes, all three sibling package manifests, and execution/review links using only the Python standard library. It does not recalculate the result:

```sh
python3 -I -S validation/rrtmgp37/bon-night-shared-source/verify.py --output build/bon-night-shared-source-verification.json
```

Optional reproduction uses NumPy and SciPy. The reproducer stages a derived plan in a new output directory, verifies all rebased paths against original hashes and sizes, runs the archived analyzer, and compares the full result after canonicalizing only the derived plan hash and pin path strings. Floating values use absolute tolerance `1e-9`; integers and booleans must match exactly. It does not modify the archived plan or result:

```sh
python3 -B validation/rrtmgp37/bon-night-shared-source/reproduce.py --run \
  --output-dir build/bon-night-shared-source-reproduction
```

The output directory must be new. No numerical reproduction was run while preparing this package.
