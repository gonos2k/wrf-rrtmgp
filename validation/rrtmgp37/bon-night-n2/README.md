# BON night: held-input N2 sensitivity

Three standalone longwave reference calls reuse the first BON night input from [PR85's dry-column diagnostic](../bon-night-dry-column-attribution/README.md). They hold its matched legacy dry columns and the default angular transport policy fixed. The N2 argument is absent, explicitly zero, or a constant dry-air VMR of 0.7808. This packet records a private reference-driver experiment; it changes no production physics, coefficients, forecast state, or repository reference driver.

The absent and explicit-zero main result files are byte-identical to each other and to the retained matched-dry baseline. All three calls succeeded with distinct PIDs and return code 0, without retries. Two private compiler attempts preceded these calls: the first failed on an internal `READ(TRIM(...),...)`; the corrected CHARACTER-variable read compiled successfully. The original failed source, log, authorization, and receipt remain in this packet. The successful source snapshot is SHA256 `77e2bdf233139771209dffd6efa00616960d3e609f8bd90691877f1ed8806678`. Neither compile attempt launched WRF, REAL, or a solver.

| Dry N2 VMR | Surface downward LW (W/m²) | Change from absent N2 (W/m²) | TOA upward LW (W/m²) | TOA change (W/m²) | Largest native-32 heating change (K/day) |
|---|---:|---:|---:|---:|---:|
| Absent | 189.087514736734 | 0 | 205.716777342270 | 0 | 0 |
| 0 | 189.087514736734 | 0 | 205.716777342270 | 0 | 0 |
| 0.7808 | 189.111523643557 | +0.024008906823 | 205.679317443577 | −0.037459898693 | 0.012535850468 |

The full 45-layer engine heating maximum is also 0.012535850468 K/day; clear-sky heating changes have the same maximum in this inactive-cloud input. The actual legacy surface downward LW is 187.837631225586 W/m². Its residual is **+1.249883511148 W/m²** for the absent/zero calls and **+1.273892417971 W/m²** for the positive N2 call. The positive TOA residual versus legacy is +0.117015807834 W/m²; that residual differs from the −0.037459898693 W/m² response to adding N2.

The [historical background-gas audit](../bon-night-lw-transport/audits/background-gases/README.md) identifies a real input-closure omission: the ten-gas host/reference list did not supply N2, and unavailable N2 minor absorbers were removed. This held-state measurement quantifies one response to restoring a declared N2 abundance. Its size does not justify leaving the omission unresolved. The value 0.7808 comes from a pinned primary all-sky example, not a measured BON composition or an exact reconstruction of legacy `colbrd` continuum conventions. CO was not changed.

## Held fields and optical support

Each main result has 24 sections. Fifteen sections are held bitwise: native/CU/cloud/precipitation/frozen component optics, prepared optics, mask, dry gas columns, and radii. Five source/band sections plus `TRANSPORT_POLICY=1` are also held bitwise. Only gas optical depths, assembled total optical depth, fluxes, and heating respond. The explicit N2 declaration appears in the two corresponding sidecars.

The positive call changes **1,136 gas cells**, all inside **1,226 allowed cells**: g-points 1–26 through all 45 layers, plus g-points 123–124 only where layer pressure exceeds the pinned 9,948.431564193395 Pa tropopause reference (28 layers). No cell outside that support changes. Gas τ increments range from zero to 0.028245591211316423. `GAS_TAU` and `GAS_TAU_RAW` are bitwise identical in these LW outputs, and the total-τ increment equals the gas increment exactly in this archive. Total τ also equals gas τ plus the band-mapped frozen τ bitwise for each call.

This is one nighttime BON column (domain 1, i=13, j=46, step 721, source seconds 43200). Its cloud paths/prepared cloud optics are inactive; frozen τ is tiny but nonzero under experimental frozen mode 1 and roughness 1. The 45-layer carrier includes 32 native layers and upper extensions. The [source-contract audit](../bon-night-lw-transport/audits/source-contract/README.md) documents remaining gas/Planck/engine and spectral limits. This is not exact RRTMG parity, observed physical accuracy, an attribution of the full observational LW bias, or evidence that the remaining residual is purely spectral. N2 and angular sensitivities were measured in separate experiments; their combined response has not been measured.

## Retained evidence and verification

[summary.json](summary.json) contains full-precision metrics. [receipts/terminal-review.json](receipts/terminal-review.json) is the verbatim independent terminal readback. The packet includes three compressed main outputs, three compressed source sidecars, original logs, both compile receipts and source generations, frozen plans/runners/authorizations, and a closed artifact manifest. [original-payload-roster.json](original-payload-roster.json) joins every retained copy to its original hash. Large libraries, coefficient files, executable binaries, and forecast NetCDF files are externally pinned rather than copied.

From this directory:

```sh
python3 -I -S verify.py --output /absolute/new/path/n2-verification.json
python3 -I -S test_verify.py
```

The stdlib verifier checks the closed roster, original compressed/raw hashes, archived source/build/authorization joins, three PIDs and return codes, absent/zero baseline bytes, exact held arrays and shapes, N2 support/locality, total optics, and flux/heating metrics. It reads hashed relative PR85/PR86 inputs, export, parsers, and historical audits. It uses frozen source snapshots and does not pin a subsequently mutable production/reference driver. It runs no compiler, WRF, REAL, or radiation solver and writes only a new report outside this packet.

The ten offline controls comprise three positive contracts and seven rejection controls for signed-zero drift, missing held fields, out-of-support gas changes, wrong pressure regime, wrong total response, wrong VMR, and extra sidecar sections. These Python evidence-contract controls do not prove compiled Fortran parser error paths. Archived build/runtime snapshots attest the external source/data/library closure; the portable verifier does not reopen those external libraries or forecast arrays. The original runner scripts retain workspace paths and are provenance snapshots, not portable execution launchers.
