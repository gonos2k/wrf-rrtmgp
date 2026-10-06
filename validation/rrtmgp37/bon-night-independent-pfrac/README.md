# Independent pfrac reconstruction for one held BON column

This evidence package reconstructs RRTMGP longwave Planck fractions for one captured nighttime diagnostic column (45 layers: 32 native WRF layers plus 13 upper extensions) from the pinned gas coefficient table and the held atmospheric input. It compares the reconstructed fractions and mapped Planck source against the saved output and transport sidecar. It is a source-and-table reconstruction, not a new RTE or forecast run.

The frozen result reports layer-source and level-source maximum absolute differences of `1.3322676295501878e-15`, surface-source difference `0`, and fraction-vs-inferred difference `2.220446049250313e-16`. Fraction sums range from `0.9998725506731506` to `1.0000030044109705`; the script does not renormalize them. The reconstruction maps the supported reduced gas set and uses the specified N2 value `0.7808`. Although other input gas profiles are retained, the reconstructed key-species pairs only exercise H2O, CO2, O3, CH4, N2O and dry air. This is not an independent absorption check of O2, N2 or CFC opacity.

This result does not validate pfrac interpolation as used by RRTMGP independently of the translated source algorithm, gas absorption coefficients, optical-depth interpolation, RTE flux accuracy, observations, or whole-port physical accuracy. It makes no compiled Fortran bitwise-equivalence claim and does not pair correlated-k g-points across engines. The separate static review records the source/indexing correspondence and its limits; the independent result readback checks the saved arrays and error metrics.

The package includes the exact N2 result compressed, plus the matched input and transport sidecar copied byte-for-byte from the verified `bon-night-common-band-source` package. The parser helper is also byte-identical to that package. The production adapter, frontend, kernel, constants and coefficient file are referenced by hashes against tracked repository files; the 11.7 MB coefficient file is not duplicated. The historical replay executable is recorded as provenance only and is not shipped or launched.

Run the standard-library integrity check from the repository root:

```sh
python3 -I -S validation/rrtmgp37/bon-night-independent-pfrac/verify.py --output build/bon-independent-pfrac-verification.json
```

An optional Python-only reproduction requires NumPy, SciPy, and netCDF4. It stages the frozen plan in a fresh directory, resolves tracked production files by hash, runs the archived analyzer once, and compares the complete result JSON with absolute tolerance `1e-12`. It launches no compiler, RTE, WRF, or forecast executable.

```sh
python3 -B validation/rrtmgp37/bon-night-independent-pfrac/reproduce.py --run \
  --output-dir build/bon-independent-pfrac-reproduction
```

The output directory must not already exist. No reproduction is run by the verifier.
