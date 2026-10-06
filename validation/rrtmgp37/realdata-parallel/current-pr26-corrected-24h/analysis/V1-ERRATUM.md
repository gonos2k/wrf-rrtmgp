# Erratum to analysis-v1 area-weighting label

`analysis-v1/analysis.json`, its CSV, plots, and V1 report are preserved as
originally generated. The metrics are numerically valid for the weights used,
but the report's generic phrase “physical domain” overstates what `AREA2D`
represents in this WRF source.

The RA4/RA37 history has `AREA2D=400,000,000 m²` at every cell, while
`DX=DY=20,000 m` and `MAPFAC_MX/MY` vary (each between about 0.991435 and
1.048567). In `WRF/phys/module_physics_init.F`, `compute_2d_dx_area` retains the
map-factor expression `DX/MAPFAC_MX * DY/MAPFAC_MY` under `#if 0`; the active
`#else` assigns `AREA2D=DX*DY`. Thus V1 accurately reports WRF-model-AREA2D-
weighted metrics, which equal nominal projected-grid weights here; its
`domain_integrated_difference_j` is a nominal projected-grid integral, not a
physical Earth-area integral.

V1 calculations are not changed. Use the separately prepared V2 analyzer for
physical-map-area-weighted results from `DX*DY/(MAPFAC_MX*MAPFAC_MY)`. V2 also
reports the original model-AREA2D weighted values side-by-side. V2 forecast
analysis must remain separate and requires its own review/approval.
