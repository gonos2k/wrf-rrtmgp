# Independent gas-opacity reconstruction for one held BON column

This archive contains a Python reconstruction of LW gas optical depth for one held nighttime diagnostic column with 45 layers (32 native WRF layers plus 13 upper extensions), 128 g-points and 16 bands. It rebuilds major/minor absorption optical depth from the held atmospheric state and pinned coefficient table, then compares the total to the captured RRTMGP N2 result. It performs no RTE, compiled replay, WRF or forecast call.

The frozen result reports maximum absolute optical-depth difference `2.000888343900442e-11`, maximum relative nonzero difference `2.5575589802172747e-15`, zero-mask mismatches `0`, and maximum gate-normalized error `0.002441161108222878`. The frozen gates are absolute `1e-11`, relative `1e-12`, and dry-column closure `1e-14`. The 75 minor-identifier rows agree with the independent metadata inventory. Grouped component sums close within `3.637978807091713e-12` in the translated calculation.

The component arrays are reconstructed from translated formulas; no independently captured major/minor component observer is retained. Their agreement is not an independent component oracle. The result does not establish spectroscopy accuracy, RRTMG equivalence, whole-port physical accuracy, observational agreement, or native 32-layer/domain behavior. It does not normalize source fractions, clip/tune opacity, or pair correlated-k points across engines. The captured gas profiles include additional species, but the calculation’s key-species mapping does not constitute an independent validation of each species’ opacity.

The package carries the exact held input and captured N2 result as compressed files, copied byte-for-byte from the verified independent-pfrac package, along with its byte-identical parser helper. The six production adapter, frontend, kernel, loader, constants, and coefficient pins resolve to tracked checkout files by SHA-256 and size; the 11.7 MB coefficient is not duplicated. The N2 execution record and read-only design/minor inventory are retained as provenance. A historical replay executable is not packaged or invoked.

Run the standard-library archive check from the repository root:

```sh
python3 -I -S validation/rrtmgp37/bon-night-independent-opacity/verify.py --output build/bon-independent-opacity-verification.json
```

Optional numerical reproduction requires NumPy, SciPy, and netCDF4. It stages the frozen plan under a new directory, resolves tracked production files by hash, runs the archived Python analyzer once, and compares the full JSON tree with absolute tolerance `1e-11` and relative tolerance `1e-12` (boolean and integer values compare exactly). It does not run a compiler, RTE, compiled replay, WRF, or forecast executable.

```sh
python3 -B validation/rrtmgp37/bon-night-independent-opacity/reproduce.py --run \
  --output-dir build/bon-independent-opacity-reproduction
```

The output directory must not already exist. The standard-library verifier does not run this calculation.
