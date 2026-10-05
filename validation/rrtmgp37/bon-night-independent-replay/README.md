# Six BON night direct-library reference replays

All six retained OFF LW inputs from the [BON night same-state campaign](../bon-night-same-state/README.md) were replayed once through an existing standalone reference executable. Six distinct PIDs completed RC 0; no input mutation, retry, new build, REAL or forecast occurred. These calls are separate from the original three forecasts and from the portable verifier, which launches no numerical engine.

The executable is 353333cc96bce44d26c02ca7585c0ddef8996fc74a05904220fba83db76cd97f. Its actual compiled `reference_column.f90` fingerprint is 6e82effd7d25242656858a8242c7e6941fced6aec0ec4d906762ef3ccb1b4ff0, byte-identical to the current f731 reference source. The original isolated build used a historically dirty source tree: a pristine Git commit is not substituted for that recorded build identity. Source/module/data and 46-library closure attestations, including the additional ELF interpreter pin, are retained in inventory/execution/build receipts. Runtime uses the original 8cb00850 frozen table and current recorded coefficient bytes, without rebuilding or claiming an independent physical oracle.

## Fixed comparison contract

Each production result has 27 sections, while each standalone result has 24 engine sections. The unchanged tracked `compare_column_replay.py` compares those 24 sections using:

- MASK: exact values.
- Optical sections: `2e-13 absolute + 2e-12 × abs(reference)`.
- UP/DN/HR and their clear counterparts: `4 float32 ULP(reference) + 1e-6`.

No threshold was widened. The portable standard-library implementation recomputes every section's maximum difference/tolerance and matches the six original comparison JSONs. Maximum downward-flux difference is 7.520191701e−6 W/m²; upward-flux difference is 1.512607366e−5 W/m²; heating difference is 2.290885197e−7 K/day. Clear counterparts have the same maxima. These are numerical consistency residuals against the same-code reference, not observational or physical accuracy errors. Full outputs are not asserted bitwise identical.

## Three separate WRF mapping fields

`WRF_GLW`, `WRF_OLR` and `WRF_THETA_HR` are production-only mapping fields, not additional engine comparison sections. The verifier independently checks:

- `WRF_GLW = float32(DN[0])`, surface downward LW.
- `WRF_OLR = float32(UP[-1])`, TOA upward LW.
- All 32 native layers: `WRF_THETA_HR[k] = float32(float32(HR[k] / float32(86400)) / PI[k])`, with captured default-REAL32 HR and PI. Both divisions round to REAL32. This is the captured LW potential-temperature tendency in K/s; no extension-layer or total LW+SW tendency is inferred.

The executed wrapper computes `tten1d = hr/86400.` then `rthratenlw = tten1d/pi3d` before tracing these fields. Exact REAL32 bits match for all six native profiles. The three mappings are reported separately so they cannot be mistaken for standalone reference output.

## Package and verification scope

Six reference outputs are deterministically compressed; six original comparison JSONs and original inventory/plan/runner/preflight/authorization/execution/build and independent terminal-review artifacts are copied verbatim. [original-payload-roster.json](original-payload-roster.json) retains exact original hashes and locations. [The independent terminal report](receipts/independent-terminal-review.json) also records the original closure and comparison readback.

Run from this checkout:

```sh
python3 -I -S validation/rrtmgp37/bon-night-independent-replay/verify.py \
  --output build/bon-night-reference-verification.json
python3 -I -S validation/rrtmgp37/bon-night-independent-replay/test_verify.py
```

The verifier checks the closed roster, decompresses exact original bytes, imports the pinned existing standard-library trace parser, reads the six sibling production capture triples, and enforces the original thresholds and exact WRF mapping contracts. The original NumPy comparator source is hash-pinned from this repository; the portable implementation does not execute that CLI or any solver. New output must be outside immutable evidence and refuses overwrite.

Unbundled executable, installed libraries, module objects, source/data inventories and NetCDF forecast files are archived attestations, not reopened by this verifier. Frozen runner artifacts retain workspace paths and are provenance snapshots. This demonstrates direct-library numerical consistency at six held inactive-cloud night states. It does not resolve the common observed LW bias, separate gas-input construction from spectral/engine effects, prove optical truth, establish active-cloud behavior or approve experimental frozen optics/roughness.
