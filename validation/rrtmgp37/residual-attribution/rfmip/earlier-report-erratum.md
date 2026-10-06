# Corrected source interpretation for the RFMIP SW residual note

This additive erratum corrects the normalization description in `build/udm37-rfmip-residual-next-diagnostic-v1/REPORT.md`. Version 1 is preserved unchanged. No tests, executable calls, builds, downloads, or model runs were performed.

## Correction

The loop variable `b` in `rrtmgp_rfmip_sw.F90` indexes a **block of columns / RFMIP experiment records**, not a spectral band. The array comments identify `total_solar_irradiance` as `(block_size, nblocks)` and `toa_flux` as `(block_size, ngpt)`. Before normalization, `def_tsi(icol)` is the sum of `toa_flux(icol, igpt)` over **all g-points** (`igpt=1..ngpt`, lines 249–264). The subsequent operation at lines 270–273 is therefore broadband, per-column normalization:

`toa_flux(icol, :) *= total_solar_irradiance(icol, b) / sum_g(toa_flux(icol, g))`.

It does not prescribe per-band solar irradiance. `mo_rfmip_io.F90` lines 122–152 reads `total_solar_irradiance` as one value per RFMIP column, repeats it across experiment records, and reshapes it to `(block_size, nblocks)`. The previous report's phrase “for each band” and implication that the band-integrated g-point sum is held fixed were wrong. The supported inference is narrower: the counterfactual changes the g-point distribution of the supplied incoming solar source; afterward the driver scales the entire g-point vector for each column/experiment to the same RFMIP broadband TSI. The spectral shape changes can affect transport even though the broadband sum is normalized.

## Corrected next diagnostic

Use the exact set of `(experiment, column, level)` coordinates whose retained published-output residuals exceed `1e-5` (RSD 116 points; RSU 39 points), rather than referring to “surface/interior/TOA columns.” In the existing RFMIP output dimensions, these are profile/experiment records, horizontal column samples, and vertical levels; levels are not separate columns.

For those points and their corresponding input columns, a future authorized instrumented comparison should record:

1. current and old-solar `gas_optics` source `toa_flux` before driver scaling, plus the all-g-point broadband sum;
2. the post-scaling vector and verify its all-g-point sum against the single supplied TSI for that column and experiment (not per-band values);
3. gas optical properties and solver fluxes before output conversion, keeping profiles and all non-solar coefficient arrays fixed;
4. full zero-change replay equality and the unchanged strict output threshold.

This separates source-vector construction/scaling from gas optics, transport, and output conversion. It still cannot identify the historical `RTE-RRTMGP-181204` generator without source/data provenance for that published source ID. Current-upstream bitwise reproduction remains an independent check and does not authenticate the historical run.

## Scope and unchanged results

The numerical evidence in v1 remains valid: stage-v7 control reproduces pinned current upstream RSD/RSU bitwise; the old-solar counterfactual changes only the three solar source arrays, sharply reduces the published-output residual, and still exceeds unchanged `atol=1e-5, rtol=0` at 116 RSD and 39 RSU points. It is not a strict pass and does not by itself establish a port error or historical source mismatch.

## Source pins

- Pinned source commit: `41c5fcd950fed09b8afe186dede266824eca7fd3`.
- `rrtmgp_rfmip_sw.F90` SHA256: `ec874da7f2891f12b389d03243d58211a66bcee331a0618a0d7ae46c1a835821`.
- `mo_rfmip_io.F90` SHA256: `a51e3d0c851836e770a262b5e9b5f70f068adb8d27e74d54a5ee446a227acb23`.
- `mo_gas_optics_rrtmgp.F90` SHA256: `661a6b7aaec09c46b62a8e2c27c25cdfba5f52c695fcd7ec30701fc4f2a8349c`.
- Preserved v1 report SHA256: `ab2679b55b8244464e4efb8c3a4aeb4a8c343673635570790f9004ebc02d0cf0`.
- Preserved v1 JSON SHA256: `7516abf3857c38c66cd4c9a82611e4bfb0fee0e641d7d79c77a2613b23b88b52`.
- Strict metrics and execution pins: see v1 report/JSON; neither was recomputed for this correction.
