# Frozen-optics inter-knot sampling plan (not executed)

This package prepares a bounded numerical interpolation diagnostic for the proposed 38-knot LW temperature axis in `../udm37-frozen-planck-coverage-v1/plan.json`. It generates direct LW coefficients at the 37 temperatures halfway between adjacent lookup knots, including both sides of the retained 233 K knot (231.5 and 234 K). Across 9 size slopes and 16 LW bands, this yields 5,328 direct cells per moment (21,312 moment values total).

**No generator, compiler, lookup comparison, reference calculation, or model was run for this package.** The existing plan and current frozen table are left untouched. `plan.json` records exact source/input/gas/numerical pins and the expected expanded-table location. The runner refuses to proceed until that first-stage generation is complete and passes the pinned artifact loader with the exact expected axes and controls. It records the realized table/receipt hashes instead of assuming them.

`run_midpoints.py` is single-use and protected by an exclusive lock. Root should run it only after reviewing the completed first-stage generation and authorizing this second stage. It stages only verified links to the cached material and solar inputs, uses the same generator checkout, gas band data, nine lambdas, order 128, 50 cm⁻¹ maximum spectral spacing, 12 workers, chunk size 32, and 32,000,000 Mie workspace. It does not fetch inputs or modify production sources. Any failure preserves partial outputs and a receipt; it does not retry.

After the direct generation completes, `validate_midpoints.py` compares all four LW moments at every lambda, band, and midpoint against interpolation from the expanded table. The output contains each per-cell absolute and extinction-normalized difference, plus maxima. It deliberately has no numerical acceptance threshold. These samples test interpolation behavior under the selected fixed material/kernel/numerics only; they do not establish ice-material validity, forecast accuracy, or a global interpolation error bound.

```bash
python3 build/udm37-frozen-planck-interknots-v1/validate_midpoints.py \
  --expanded build/udm37-frozen-planck-coverage-v1/runs/frozen-planck-150-330-step5-plus233-v1 \
  --direct build/udm37-frozen-planck-interknots-v1/runs/frozen-direct-interknots-v1 \
  --output build/udm37-frozen-planck-interknots-v1/interpolation-diagnostic.json
```

Each generated kernel binary is validated against its own generation receipt. Binary hashes are reported for both output directories, but cross-directory byte identity is not a gate: the embedded build path can make separately compiled binaries differ even when their source and numerical controls match. Source files, static adaptation, compiler, flags, material/solar/gas data, quadrature, and generation controls remain required to match exactly.
