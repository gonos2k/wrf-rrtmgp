# RFMIP reference lineage and historical SW coefficient provenance

The retained RFMIP reference set has different LW and SW histories despite a
common `RTE-RRTMGP-181204` filename/source label. This read-only investigation
authenticates the published SW bytes and the old solar vector used in the
completed sensitivity experiment. It does **not** identify the exact historical
flux-generating executable, compiler, flags, or complete generation inputs.
No model, build, radiation solver, or numerical transport was run for this audit.
No production source, coefficient file, reference output, or tolerance changed.

## What was established

| Object | Independent evidence | Result |
| --- | --- | --- |
| Retained RSD reference | Actual HTTPS CMIP6 replica, plus dataset PID version `20191007` | All 485,284 bytes equal the retained RSD file; SHA256 `f9b0313fdf74598859a7caf27a5d1395b7fe1e445c9620a66856cc19eaf5e5b9` |
| Retained RSU reference | Public FILE PID's `FILE_NAME`, size, SHA256 method and checksum | Retained RSU checksum equals `0ea3f4272d9ef088db6ffd07153587863a052e3cf8b3bf04bfb7c9288ed8b324` |
| Retained SW Git history | June 2023 reference replacement and pinned data tree | Both SW Git blobs equal the retained files and June 2023 replacements |
| Retained LW Git history | May 17, 2024 single-level source update, then Hogan 2023 quadrature update | Current RLD/RLU blobs match the second update and pinned data tree, not the June 2023 LW blobs |
| Historical SW coefficients | Official v1.0/v1.0.0 tree at `ed5b0113109fcd23a010a90c61f21bad551146ef` and raw file | Full file matches Git blob `63bc19ec5388da186a582cd69224711fe14d30fa`; SHA256 `b9f4b15796d132880fffb49ac45c29753c1ee70a8ee3fed733899cb315c75e9b` |
| Old-solar sensitivity vector | Historical `solar_source` versus constructed file's `solar_source_quiet` | All 224 values exactly equal after float32-to-float64 promotion; band/g-point coordinates also equal |
| Historical/current common non-solar payload | Variable intersection comparison | All 29 common non-solar variables have equal values; six current-only variables remain outside this assertion |

The public FILE PID is reused in more than one reference's `tracking_id`.
Its **own checksum identifies RSU only**. RSD authentication uses the independently
downloaded replica, not the RSU checksum. A dataset PID identifies a dataset and
version; it does not by itself authenticate each file's bytes.

The June 2023 commit is a reference replacement/import event. It is not proof
that SW fluxes were calculated in 2023: the retained SW metadata and independently
retrieved CMIP6 replica retain the 2019 publication lineage. Likewise, the LW
`creation_date` metadata predates the May 2024 array updates and cannot identify
the final generating executable. The `181204` source label is a model identifier,
not a verified source commit. A chronologically nearby Git commit is only a
candidate until the generation record explicitly connects it to the outputs.

## Consequence for the port comparison

The existing completed comparison found bitwise-equal upstream and WRF-vendored
CPU RFMIP arrays on the **g256/g224** path. The stored-reference strict SW gate
still fails at `atol=1e-5`, `rtol=0`: the current coefficient arm has 104,071
failures (52,972 RSD + 51,099 RSU). The completed old-solar sensitivity retains
155 failures (116 RSD + 39 RSU). Those counts are inherited results, not reruns
or recounts in this audit. All 155 selected old-solar outputs are one float32 ULP
from reference; the prior prewrite analysis excludes output casting as the sole
cause. The corresponding prior inventory/report hashes are recorded separately.

This audit strengthens the solar-input attribution: the sensitivity vector is
now authenticated against an official historical release. The **constructed
whole coefficient file remains a counterfactual**. It is not byte-identical to
the historical file, nor proof of the exact RFMIP generation input. Equal values
in the 29-variable intersection do not certify the full file or all loader paths.

The mixed reference history prevents interpreting the common `181204` label as
one uniform historical experiment. It supports checking source/data lineage
before blaming a WRF port, but does not establish that every remaining difference
is physically normal. The 155 strict failures remain open. This clear-sky
g256/g224 result also cannot approve UDM cloud/precipitation optics, the production
WRF g128/g112 path, or forecast accuracy.

## Primary records and reproduction scope

- [Official v1.0 coefficient tree](https://github.com/earth-system-radiation/rte-rrtmgp/tree/ed5b0113109fcd23a010a90c61f21bad551146ef/rrtmgp/data)
- [June 2023 reference replacement](https://github.com/earth-system-radiation/rrtmgp-data/commit/162f494ed3950009c465372018cb6286b7d441c9)
- [May 2024 LW single-level source update](https://github.com/earth-system-radiation/rrtmgp-data/commit/41d3fa4fd1c363a084d311015fabcf60c9745708)
- [May 2024 LW quadrature update](https://github.com/earth-system-radiation/rrtmgp-data/commit/8695c5c0184023daaaed51a24c7ab1ab0891a1f2)
- [Pinned reference snapshot](https://github.com/earth-system-radiation/rrtmgp-data/tree/ea788bb39876948fa8d2c235665ccff19b4686b5/examples/rfmip-clear-sky/reference)
- [Public RSU FILE PID](https://hdl.handle.net/api/handles/21.14100/43a44dc8-ea58-40a6-b26a-bbbeca786640)
- [Public RSD dataset PID](https://hdl.handle.net/api/handles/21.14100/1ec63348-53e0-3d31-9504-3c6a0f5eaa28)

The archived API responses, retrieval receipts and comparison receipts preserve
the actual observations. A portable verifier should check archive integrity and
these Git/PID joins without network or numerical work. An optional local NetCDF
check can recompute byte hashes, the 224-value vector equality and the 29-variable
intersection using explicitly supplied retained files. It must not fetch or
substitute files implicitly, invoke a solver, or promote the strict accuracy gate.
The large coefficient and reference NetCDFs remain external, with immutable
source URLs and hashes recorded in receipts.

Next discriminating evidence is an authoritative generation record (source,
compiler/flags and inputs) or a separately planned historical-release experiment.
The pinned ice LUT's PSD/habit/size-definition provenance remains a separate open
physical contract; the AER SVN import origin alone does not resolve that contract.
