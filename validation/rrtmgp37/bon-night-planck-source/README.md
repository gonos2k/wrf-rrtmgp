# Independent finite-band Planck analysis

This package archives the private Planck analysis, its frozen plan, the single completed result, selected-column inputs, and both design versions. The archived plan and analyzer are byte-preserved. The result came from one Python-only analysis invocation; the standard-library verifier does not rerun it.

The full gas coefficient file is not duplicated. The frozen plan pins the tracked CI coefficient `WRF/run/rrtmgp-gas-lw-g128.nc` by SHA-256 and size. `WRF/external/rte_rrtmgp/DATA.json` identifies upstream `earth-system-radiation/rrtmgp-data` commit `ea788bb39876948fa8d2c235665ccff19b4686b5` and records the same file hash. CI uses `WRF/run` as `RRTMGP_DATA_DIR`. The reproduction checks the coefficient and four production-source files against the pinned hashes before and after execution.

The three raw inputs (legacy packet, matched GP input, and GP LW transport sidecar) are compressed in the archive and checked against their exact origin hashes. The parser helpers are byte-identical to the sibling `bon-night-common-band-source` archive. Its manifest hash is pinned and the sibling archive’s complete roster and payload hashes are checked. The unused GP broadband result is not duplicated.

The analysis reports finite-band SI Planck integrals and compares them to the captured legacy values and GP `totplnk` table. It does not independently validate pfrac interpolation, optical depth, RTE accuracy, full-spectrum support, or general legacy-versus-GP equivalence. The reported maximum GP-to-SI relative difference is 0.04028%; legacy-to-SI is 0.04010%. The maximum common-band raw GP-minus-legacy radiance difference is 4.47196047357e-5 W m⁻² sr⁻¹. These are numerical comparisons, not accuracy tolerances.

The archive includes the static review, terminal review, environment record, and independent result-array readback. There is no executable or full coefficient copy. A standard-library verifier checks the closed archive manifest, all copied origin hashes, sibling-manifest linkage, tracked source/coefficient hashes, and result/plan/script/execution/review links. It performs no numerical integration.

From the repository root:

```sh
python3 -I -S validation/rrtmgp37/bon-night-planck-source/verify.py --output build/bon-night-planck-package-check.json
```

Optional reproduction requires NumPy, SciPy, and netCDF4. It stages the exact frozen plan under a fresh output directory, reconstructs the relative pin tree, launches the archived analyzer once, and compares the complete result structure with absolute tolerance 1e-9. It does not launch compiled RTE, WRF, or forecast executables.

```sh
python3 -B validation/rrtmgp37/bon-night-planck-source/reproduce.py --run \
  --output-dir build/bon-night-planck-reproduction
```

The output directory must not exist. The execution receipt records PID, return code, logs, result comparison, and before/after source/coefficient hashes.
