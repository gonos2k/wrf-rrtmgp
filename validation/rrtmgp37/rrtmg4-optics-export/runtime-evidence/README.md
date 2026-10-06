# One-minute RRTMG4 optics-export runtime evidence

This package records a bounded runtime check of the optional selected-column
RRTMG4 optics export. The exact 55-field LW and 69-field SW text exports are
stored as deterministic gzip files; `export-index.json` records each original
byte count and SHA-256. Decompression reproduces the model output exactly.

The fresh GNU serial run used the observer source head `b7b5f6f9` (based on PR70 `1cb6920a`) and a one-minute restart
from the completed 48-hour production-37 case. Three arms ran once: the older
binary with export off, the fresh binary with export off, and the fresh binary
with export on. All three returned zero and produced the expected successful
WRF completion markers. The two off arms and the off/on arms each had two
history files and one restart compared exactly (six whole-file comparisons).
The selected production capture records also matched the retained capture for
both phases (18 files across the three arms; six phase/suffix hash comparisons).
The audit receipt reports 188 matched rows. Runtime review is
`receipts/runtime/independent-runtime-review.json`.

The observer exported the actual RRTMG4 LW and SW inputs/intermediate optics
and results at domain 1, global column `(i,j)=(24,55)`, step 2161,
source time 129600 seconds. Each file has `INPUT`, `CLOUD`, `GAS`, and `RESULT`
stages. This is one selected call per phase; the separate deterministic-seed
audit does not turn the export into a 128-seed optics ensemble.

This evidence establishes scoped runtime preservation and successful export
serialization. It does not establish radiative accuracy, observational skill,
production-37 physical accuracy, or domain-wide behavior. The run lasted one
minute and uses the specified experimental frozen-optics configuration. The
export observes the legacy RRTMG4 call; it does not change solver inputs or
outputs.

## Reproduction and verification

From the repository root, the standalone writer checks remain available via
the parent directory README. Verify this packaged runtime evidence with:

```sh
python3 validation/rrtmgp37/rrtmg4-optics-export/runtime-evidence/verify_runtime_evidence.py
```

The verifier checks the exact package roster and file hashes, both decompressed
export hashes and metadata, receipt status/arm roster, all six exact NetCDF
comparisons, and six recorded phase/suffix capture-comparison entries. The large NetCDF
outputs, executable binaries, and full model logs are intentionally referenced
by SHA-256 in `external-pins.json` rather than copied into this package. The
external-reference pins and build/source receipts are provenance evidence;
the portable verifier does not fetch or independently reopen those omitted
files.
