# BON nocturnal same-state LW evidence

Three serial one-hour restart forecasts at BON global i=13, j=46 completed successfully for 2000-01-25 00:00–01:00 UTC: audit OFF, ON with generic legacy radii (native4=0), and ON with native legacy radii (native4=1). Executed source is f731bb993a86a1836a64152d9b936edb7c315c19; the package parent cc1ff2f changes registration hashes only. DT=60 s, RADT=10 min, CU=1 with feedback, mp=27, frozen optics=1, roughness=1, OMP1/B1 and the original 8cb00850 frozen table were retained. No REAL, standalone replay or retry belongs to this campaign.

The surface downward LW engine37−engine4 contrast is **+1.2424 to +1.2473 W/m²** across the six captured calls. Both radius arms have identical engine37 and engine4 statistics, with 128 seeds and exactly zero sample SD. This is a selected same-state contrast, not an observational accuracy error or an explanation of the common BON/PSU daily LW bias.

| Actual step | Source seconds | Engine37 surface LW | Engine4 surface LW | Difference (W/m²) |
| --- | --- | --- | --- | --- |
| 721 | 43200 | 189.0800171 | 187.8376312 | +1.2423859 |
| 731 | 43800 | 189.3886108 | 188.1446991 | +1.2439117 |
| 741 | 44400 | 189.6951294 | 188.4478607 | +1.2472687 |
| 751 | 45000 | 189.9772949 | 188.7304230 | +1.2468719 |
| 761 | 45600 | 190.2626495 | 189.0184479 | +1.2442017 |
| 771 | 46200 | 190.5495605 | 189.3048096 | +1.2447510 |

The first actual OFF LW capture selected step 721 / source seconds 43200 for the one legacy LW export. This clock was observed, not imposed. At night there is no SW solver capture or export; zero SW audit rows are clock-joined bookkeeping, not daytime validation. CSV is allsky only, without a paired clear-sky CSV.

Native/extended CF, native and CU liquid/ice paths, rain/snow radiative paths, sampled cloud masks and cloud optical depths are exactly zero at all six calls. Tiny frozen graupel/hail optical depths remain nonzero (maximum 5.6602135279e−21). Captured engine37 allsky and clear DN/UP/HR are bitwise equal; this does not prove exactly zero physical frozen effect. Changing legacy radius mapping or cloud seeds therefore does not explain the contrast in these inactive-cloud calls; no conclusion follows for active-cloud columns or a full day.

At the first call, 16 thermodynamic/gas/emissivity input joins are IEEE64-equal between the GP capture and legacy export. Molecular dry-column amounts differ despite the same molecule/cm² units: legacy/GP is 1.00034308–1.00035063 in 32 native layers and 1.00034701 in 13 extensions. Host gravity and native dry-mass versus legacy pressure/humidity construction contribute different conventions; there was no dry-mass-only intervention here. The +1.24 W/m² contrast retains combined input-construction, gas/spectral and engine effects. It is not attributed solely to gravity, and it does not settle optical truth, observational accuracy or thermodynamic/surface/observation mismatch.

The maximum absolute native-layer heating contrast is 0.0788683891 K/day. TOA upward LW contrast is +0.05055 to +0.15814 W/m². The 128 seed summaries are descriptive; no IID confidence interval or domain/time average is claimed. A separate [six-call direct-library replay](../bon-night-independent-replay/README.md) subsequently passed on these immutable inputs. The maximum replay flux residual is 1.513e−5 W/m² and heating residual 2.291e−7 K/day under the unchanged comparison contract; all 24 engine sections per call passed and the three WRF mapping fields were checked separately. Those six standalone calls belong to the additive replay campaign, not the original three-forecast campaign. Both calculations share the pinned library/data; this consistency check does not establish physical accuracy.

## Retained evidence and external attestations

The closed manifest retains six OFF raw/input/result triples, one legacy LW export, both audit CSVs, three identical namelists, original build/runtime/authorization/identity receipts, and the independent terminal report/README. Gzip payloads decompress to the exact immutable originals. [original-payload-roster.json](original-payload-roster.json) joins each retained file to its original path/SHA and records source/parser dependencies.

The [terminal report](attestations/independent-terminal-review.json) independently reopened all nine native NetCDF files. Each arm has two 225-variable histories and a 667-variable final checkpoint. Both ON arms matched OFF in raw arrays, variable sets, dtypes, dimensions/unlimited flags, data_model and all variable/global attributes, plus whole-file SHA. All six production raw/input/result triples per arm matched bitwise. These are archived independent external-file attestations: NetCDF outputs, full source inventories, ELF, coefficients and 48 libraries are **not bundled** and are not reopened by the portable verifier.

The historical checkpoint lacks three UDM cloud diagnostics. The explicit missing-diagnostic warnings and documented sentinel fallback remain part of this run; exact restoration of those old diagnostics is not claimed. The private terminal prototype's incorrect exactly-zero frozen-opacity assertion was corrected without touching original runs or outputs. Original failures and the earlier v1 staging limitation remain external, preserved evidence.

## Portable verification

From this repository checkout:

```sh
python3 -I -S validation/rrtmgp37/bon-night-same-state/verify.py \
  --output build/bon-night-bundled-verification.json
python3 -I -S validation/rrtmgp37/bon-night-same-state/test_verify.py
```

The standard-library verifier checks the closed expected roster, original/decompressed digests, source/build/runtime receipt joins and exact recorded forecast counts. It imports the pinned existing [trace parser](../rrtmg4-same-call-attribution/reproduce.py), parses all 18 traces, and uses the strict export parser with only an explicit selected-context adapter. It recomputes the six-call CSV contrasts, complete metric/aggregate/time/radius joins, 128 sample/SD checks, inactive-cloud state, first-call atmospheric/VMR joins and molecular dry-column ratios. Its output must be outside the immutable package and refuses overwrite.

This verifies bundled content and archived attestation joins. It does not numerically rerun WRF/RRTMGP, reconstruct external forecast-array parity, inspect installed libraries, prove current physical accuracy or resolve the observational bias. Frozen launcher/reviewer scripts retain workspace paths and are provenance snapshots, not portable forecast launchers. No binary, coefficient dataset, full diagnostic log or NetCDF file is copied.
