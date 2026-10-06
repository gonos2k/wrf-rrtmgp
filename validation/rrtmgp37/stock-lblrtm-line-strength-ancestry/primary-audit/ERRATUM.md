# Additive correction

Preserve `audit.json` unchanged. Its first local source-interpretation entry labels the assignments at `oprop.f90:1262–1264` as HIRAC1. They are in **LNCOR1**; LNCOR1 initializes the per-line `YI`/`GI` accumulators at lines 1065–1069. The exact pinned source and locations are recorded in `erratum-v1.json`.

Also keep the public AER compatibility table separate from local executed-asset proof: it lists LBLRTM v12.17 / MT_CKD 4.3 / AER line file v3.8.1, while the local generation plan pins its own line-list/TAPE3. The compatibility table alone does not attest the exact code/data loaded by a local executable. Neither that provenance nor the source’s signed coupling terms establish physical validity of the negative samples.
