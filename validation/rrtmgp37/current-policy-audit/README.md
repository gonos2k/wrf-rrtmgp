# UDM27 current policy audit

This package analyzes existing records from the PR57 review base
`9b6c09332e1b0cb3c919882646070443472754ac`. It adds no model invocation,
compilation, or production Fortran change. The [publication manifest](publication-manifest.json)
maps the copied audit artifacts to their original paths and byte hashes.

## Cloud-ice attribution

The [derived arithmetic](ice-attribution-derived.json) uses five overcast,
ice-only captures from the existing [optical-swap experiment](../runtime-contracts/ice-optics-attribution.json).
It is a historical serial experiment, not a new calculation with the latest
MPI executable. Within each optical swap, gas optical properties, McICA mask,
clear-sky flux/heating and clear direct flux remain exactly fixed.

| Surface-down SW quantity | Five-case range, W/m² |
|---|---:|
| Actual RRTMGP37 minus native-radius RRTMG4 | +61.8589 to +61.8788 |
| Native-wrapper optical swap minus RRTMGP baseline | −65.0173 to −64.9813 |
| Swapped RRTMGP minus actual RRTMG4 | −3.1493 to −3.1094 |
| Physical Fu size variant minus actual RRTMG4 | +2.2237 to +2.2670 |
| Generic RRTMG radius variant minus actual RRTMG4 | +3.8120 to +4.5439 |

This substantially narrows the large cloudy difference to cloud optical model
and size conventions in these cases. The native-radius counterfactual above
and the earlier generic-radius approximately +54 W/m² result are different
comparisons. They must not be combined as one unexplained residual.

The swapped case still uses RRTMGP gases and RTE. Ordered-band correspondence
is approximate at the 2600/2680 cm⁻¹ edge. Consequently its residual is neither
a pure solver-error measurement nor proof of observational accuracy. This
does not establish that every 4/37 difference is correct or benign. The
recomputed −3.1493 to −3.1094 range corrects the former approximate text
−3.16 to −3.12 in `RUNTIME_CONTRACTS.md`; the original numerical record remains
unchanged.

## Existing 24-hour occurrence and clipping samples

[phase-summary.json](phase-summary.json) extracts 7,149 diagnostic rows from
the four `rsl.out` files of the already completed `long-b32` run. The matching
four `rsl.error` policy sequences are duplicates and are excluded. This run
used source commit `d05c97b4f26be0ca21867051b50d6fca00261d51`, executable SHA256
`6088620a5a27020bba4454d8380ecc149bbbea78ef1c82b37df15e719163fca5`, MPI4/OMP2,
overlap 2, and experimental frozen G/H optics.

| Quantity over logged samples | LW | Daytime SW |
|---|---:|---:|
| Native ice clipped / eligible grid-path sums | 25.8327% | 22.0776% |
| CU ice clipped / accepted grid-path sums | 47.9399% | 49.8952% |
| Native liquid clipped / eligible grid-path sums | 0.119589% | 0.0858843% |
| CU liquid clipping rows | none | none |
| Maximum reported CF=0 rain layer path, g/m² | 250.7207 | 241.6300 |
| Maximum reported CF=0 snow layer path, g/m² | 4.304008 | 4.304008 |

These are sums of grid-mean layer paths repeated across logged radiation
samples, not area-integrated domain mass, unique atmospheric events or flux
error percentages. LW and SW must remain separate. Native printed sums have
finite precision. No complete-call-coverage claim is made.

Native rain/snow CF=0 rows lack total rain/snow path denominators, so omission
fractions cannot be calculated. CU clipping rows lack tile/call identifiers
and appear only when clipping is positive; they cannot be paired by adjacency
to population rows under concurrent tile execution. The CU ratios above use
all logged accepted CU population paths as the denominator, including samples
with no clipping line, with the actual overlap-2 output echo checked. Main-step
timestamp context is not an authenticated radiation-call timestamp.

[Source cross-checks](source-crosscheck.json) verify the six audited Fortran
files against the original source manifest and PR57. [Log provenance](raw-log-provenance.json)
is narrower: the eight rank logs are pinned at audit time and unchanged during
parsing. The terminal execution receipt pins the executable launch and quality
result, but an independent historical eight-rank-log inventory was not located.
These are not claimed to be pre-run cryptographic log pins.

Native and CU populations use separate radius inputs and a shared combined CF
and McICA mask. Native ice uses twice the UDM radius; CU ice uses twice the WRF
fallback radius. Native rain/snow retain the documented cloud-occurrence
policy; frozen G/H use their separate occurrence policy. The observed clamps
and exclusions agree with those policies. Their radiative impact and physical
validity remain open. The sizable clipped-path participation does not support
calling the clamp harmless.

One source-level diagnostic issue remains outside this overlap-2 experiment:
native clipping counters are overlap-0 gated, while CU clipping counters are
not. Such CU counts would concern prepared sizes, not participating cloud
optics. Missing CU tile/call identifiers and CF=0 precipitation denominators
also remain diagnostic gaps. None is silently marked fixed by this audit.

## Reproduction and verification

`parse_existing_logs.py`, `test_parser.py`, and `derive_attribution.py` are
verbatim snapshots of the executed scratch helpers. Their path defaults
assume the original workspace and scratch directory layout recorded in the
manifest; these are evidence snapshots, not portable model launch tools.
The original parser's seven controls pass, covering malformed/missing/duplicate
fields, duplicate record identity, repeated legitimate calls and LW/SW
separation. The original input-only overlap preflight failure is preserved in
scratch; the final parser checks the actual output echo instead.

Raw rank logs and 7,149 line-indexed JSONL rows stay in the recorded scratch
tree. No new optical replay or forecast was performed for this package.
Hourly history lacks native/CU radius and CU state fields needed to reconstruct
actual radiation-call inputs. Future impact comparisons must capture those
inputs rather than treat hourly states as exact call replay.
