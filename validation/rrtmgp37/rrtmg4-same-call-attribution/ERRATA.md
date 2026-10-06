# Interpretive errata for frozen analyses

This file supplements, but does not alter, the frozen source reports and JSON.

- The observer comparison is a first-call LW V10 / SW V11 trace at step 2161 and `(24,55)`. Its CSV summarizes 128 observer seeds; that summary is not the realization represented by the one captured GP trace.
- The layer-31 analysis maps physical bands using the coefficient-based joins. Generic `TOTAL_*` `values_by_band` vectors in its frozen JSON are g-point vectors. Review found 11 LW and 12 SW physical-band joins, but does not support flux attribution or forecast-accuracy claims.
- CF=1 in the inspected native layers 30–32 rules out missed-cloud samples in those layers only. It does not rule out McICA sampling elsewhere in the column affecting boundary fluxes or heating.
- The dry-column v2 formula-only REAL64 table and the actual exported-column ratio are separate quantities. For actual exports, native-normalized mean/max absolute relative differences are 0.1651868890% / 0.2891570627%; the maximum normalized by legacy is 0.2883233554%. The exact REAL32 reconstruction result (0 ULP on the 102 legacy values) is an arithmetic check, not proof that all other conversion paths or columns behave identically.
- The original v3/v2 files remain unchanged and include absolute workspace paths. Use `reproduce.py` for the portable package-relative integrity and same-call checks.
