# Independent completed RFMIP residual diagnostic readback

The original v5 campaign compiled/linked one diagnostic driver and ran two standalone SW calls. This independent review launched no numerical executable. The original receipt's `model_invocations=2` counts these two reference calls: it adds zero WRF forecasts and zero REAL calls. The root-provided cumulative forecast count is 86, independent of these calls.

Both outputs match their own retained stage-v7 baseline in full float32 arrays and whole-file hashes. Each arm passes all 16,470 captured storage conversions. All 135 gas-optics records are bitwise identical across the solar-only intervention; sources and fluxes differ.

The old-solar output still fails the published threshold at 155 cells (116 down, 39 up). Every retained stored residual is one float32 ULP; every prewrite value lies outside the published target's nearest-float32 interval. Of these, 99 prewrite differences exceed 1e-5 and 56 do not although their stored differences do. Rounding therefore changes strict-threshold classification for those 56; this does not supply a strict PASS or prove a historical generator. These results are clear-sky diagnostics, not WRF physical accuracy or observational skill.

`review.py` independently parses exact stream keys/values and recomputes residuals from retained outputs. It uses the frozen runner's pure pin/library functions only. Large arrays, binary and coefficients remain external with original hashes. Original execution and earlier unrun failures remain untouched.
