# Winter QI one-point observational hook (scratch only)

The observer lives only in `source/WRF` copied from staged commit `e7c97ed661403b3922fcf752300c052611ef89cd`. It is opt-in through `WRF_UDM_WINTER_CAPTURE_DIR`, cached once under an OpenMP critical region, and only emits for global `(i,j)=(17,58)`, levels 6–8, and timestep 168–170. It only reads state. The output directory must already exist. Each MPI rank appends to its own `rankNNNN.csv`; the row layout is stage, rank/domain/step/i/j/k, seconds, 16 observed reals (QC,QI,QR,QS,QG,QH, three radii, radiation CF, UDM CF, QNN/QNC/QNR, native dry mass, T), then memory and active bounds. `-999` denotes a field unavailable at that capture point.

Capture stages are `PRE_MICROPHYSICS`; `UDM_PRE`/`UDM_POST`; `POST_PHYSICAL_BC`; `POST_SPEC_BDY`; and `RAD_PRE_BUILDER`. The latter records builder inputs and native layer mass immediately before `rrtmgp_build_udm_inputs`, before the expected negative-QI fatal. UDM stages capture all six hydro q and number fields at levels 6–8. Solve stages capture the middle level (k=7) around microphysics and boundary updates.

## Static source bounds

The frozen Jan case has `e_sn=61`, `spec_bdy_width=5`, and `spec_zone=1` (Registry default). In `solve_em.F` the UDM call uses `sz=grid%spec_zone`; for specified boundaries it sets `jts=max(tile_jts,jds+sz)` and `jte=min(tile_jte,jde-1-sz)`. With `jds=1,jde=61`, active global rows are 2 through 59. `module_mp_udm.F` processes `jts:jte`, so j=58 is within UDM's physical update interval when owned by a tile. The later final specified-boundary operation in `module_bc.F` uses `spec_zone=1` and selects the outer row j=60; j=58 is not overwritten by that final row operation, despite being inside the wider five-row specified relaxation zone. Capture remains necessary to establish actual per-rank/tile ownership and values.

`solve_em.F` order is: RK advection/update; radiation in `module_first_rk_step_part1.F`; microphysics in `solve_em.F`; then `set_physical_bc3d` and later `spec_bdy_final`. This ordering does not alone identify which earlier update generated the fatal value.

## Bounded replay proposal (not executed)

Use a fresh case copy from `build/udm-alternate-jan2000-data/paired-forecast-v2/ra37`, same frozen namelist, wrfinput, wrfbdy, table, runtime assets, executable configuration and 4-rank layout; only point the opt-in capture environment variable at a new empty existing directory. Run from 12:00 to 14:50 (170 minutes) with the strict input policy unchanged; expect the run to stop at the original fatal. Compare output partial-history records at 12:00, 13:00, and 14:00 bytewise with the original RA37 partial history before attributing captured values to the original trajectory. If they differ, report the captured replay trajectory as divergent and do not claim it proves original fatal provenance. Preserve the original run and all artifacts.
