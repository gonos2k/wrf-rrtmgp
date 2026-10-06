# Common-angle longwave attribution for one held BON column

This archive packages the completed Python-only angular attribution for one clear nighttime BON column. It evaluates legacy RRTMG’s own spectrum and RRTMGP’s own spectrum at a common angular integration, comparing only physical bands 3–13. The two engines’ correlated-k g-points are not paired. No RTE, compiled replay, WRF, forecast, or new build was run for this result.

The common-bands-3–13 captured engine difference is `+0.595897146305 W m⁻²`. The frozen decomposition is:

- GP native-angle minus GP common-angle integral: `+0.043201984875 W m⁻²`.
- Own-spectrum common-angle residual (GP integral minus legacy integral): `+0.680771953682 W m⁻²`.
- Legacy integral minus exact legacy native-angle calculation: `−0.128746650279 W m⁻²`.
- Exact legacy result minus captured legacy approximation: `+0.000669858028 W m⁻²`.

The last term groups legacy lookup, thin-layer polynomial, and REAL32 approximations; this analysis does not split those contributions further. The common-angle residual still combines optical coefficients, k-discretization, and source-fraction interpolation. It is not pure opacity causality and does not identify a physical-accuracy winner. Source fractions are not renormalized, no across-engine g-point pairing is attempted, and all-engine totals retain unpaired spectral edges.

The case uses 45 diagnostic layers (32 native WRF layers plus 13 upper extensions). The archived plan records the held packet, matched input, N2 result/transport, prior source calculations and optical-scope gate. The legacy source file is resolved from the tracked checkout by hash. Inputs and helper parsers are reused byte-for-byte from the verified common-band and independent-pfrac archives; no coefficient or executable binary is duplicated.

The standard-library verifier checks the closed archive roster, both sibling package manifests, source and input hashes, result/plan/execution/review links, and performs no integration. From the repository root:

```sh
python3 -I -S validation/rrtmgp37/bon-night-common-angle/verify.py --output build/bon-night-common-angle-verification.json
```

Optional Python-only reproduction requires NumPy and SciPy. The frozen plan contains absolute workstation paths. The reproducer creates a derived temporary plan that changes only those pin paths to the fresh staging root; it verifies every staged pin’s bytes and SHA-256, then runs the archived analyzer. Before comparing results it confirms the generated plan hash and complete pin roster match that derived plan, with all original pin hashes and sizes unchanged. It canonicalizes only the plan hash and pin path strings back to the archived values; all other result fields are compared (floating values within absolute `1e-9`, booleans and integers exactly). The generated JSON bytes therefore need not match the archived JSON byte-for-byte. The child has a 30-second timeout and is reaped on failure.

```sh
python3 -B validation/rrtmgp37/bon-night-common-angle/reproduce.py --run \
  --output-dir build/bon-night-common-angle-reproduction
```

The output directory must be new. The standard-library verifier does not run the analysis.
