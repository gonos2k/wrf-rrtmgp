# Prepared exact-band SW cloud-optics swap (offline only)

This directory contains two `WRF_SW_OPTICS_OVERRIDE_V1` inputs prepared from the retained selected-column capture. No executable was launched. `sw-optics-control-full-prepared.optics` is a full baseline PREPARED_TAU/SSA/G identity control. `sw-optics-legacy-exact-band-k30-32.optics` changes only those arrays at native layers 30–32 and 12 physical band bounds shared exactly by the legacy export and the pinned RRTMGP SW coefficient table. The first two GP bands retain the baseline values; their legacy 820–2600/2600–3250 split does not match the GP 820–2680/2680–3250 split.

The capture is domain 1, i=24, j=55, radiation step 2161 (129600 s), SW V11. Its pressure interfaces are strictly decreasing bottom-first: native raw DP_HPA matches the first 44 PLEV intervals exactly; the replay/core arrays have 45 layers, including one upper extension. Input and raw cloud fraction equal one at all three selected native layers. At each selected layer all 112 legacy MCICA and GP masks are one. The 12 common bands yield 36 band-layer cells and 108 TAU/SSA/ASYM values. For every cell, each legacy property is exactly constant across all legacy g points in that physical band. The writer uses that one verified band value for each GP g point in its own coefficient-defined range. It does not average or pair g points by index; quadrature counts can differ.

The legacy CLDPRMC values are emitted after the legacy `cldprmc_sw` delta-M transform. The independent replay applies the override after constructing its combined prepared native-cloud/CU/precipitation optics and before its mask-generation/MCICA path. Raw state and component diagnostic records remain baseline, but the selected combined PREPARED optical tuple is replaced; therefore this is not a test with CU optics still present in the RTE at the swapped cells, nor a pure engine or PSD comparison. The direct-beam/raw-cloud bookkeeping is a separate path, so this prepared-optics change is not a complete direct-beam attribution.

Recreate the files into a new, absent output directory with Python 3, NumPy, and netCDF4:

```sh
python3 -B generate.py --workspace /path/to/RRTMGP --output-dir /path/to/new-output
```

`plan-inputs.json` records hashes/sizes for the export, V11 input/raw, baseline execution and result, exact coefficient copies, parser sources, executed reference source/executable, all 36 band-layer records, both generated override pins, and six offline rejection controls. The generator refuses to overwrite an existing directory and does not call a solver.
