# Physical map-area comparison, V2

`analyze_pair_v2.py` preserves the V1 code and results and adds a separate
analysis using projected ground-cell area
`DX*DY/(MAPFAC_MX*MAPFAC_MY)`. It validates the exact `MAPFAC_MX` and
`MAPFAC_MY` time/latitude/longitude dimensions, dimensionless units, positive
finite values, and exact static equality through both histories and between
arms. It also requires stable positive DX/DY. The WRF `AREA2D` weighting is
reported separately in every hourly field result and for each daily energy
accumulator.

The source behavior is visible in `WRF/phys/module_physics_init.F`'s
`compute_2d_dx_area`: the map-factor formula is inside `#if 0`; the active
`#else` sets `AREA2D=DX*DY`. Hence the V1 results are model-AREA2D weighted,
while V2's primary weights estimate physical grid-cell area from map factors.
This distinction is a source implementation choice, not a data-port defect.

Run only after reviewing the script and receiving approval for the forecast
analysis. The command requires a fresh output directory and will refuse to
overwrite an existing one:

```sh
python3 build/udm-current-24h-analysis/analyze_pair_v2.py --self-test
python3 build/udm-current-24h-analysis/analyze_pair_v2.py \
  --output-dir build/udm-current-24h-analysis/analysis-v2
```

No forecast output has been read by V2 yet. V1 remains the executed and
reviewed run; see `V1-ERRATUM.md` for its area-weight interpretation.
