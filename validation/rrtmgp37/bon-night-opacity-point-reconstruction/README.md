# Saved point reconstruction for BON-night LW gas opacity

This additive evidence package extends the earlier one-case translated tau check at `../bon-night-independent-opacity/`. That earlier archive and its result/gates remain unchanged. This package records a separate source-ordered point reconstruction for the same held BON nighttime diagnostic carrier, with three gas-roster states: N2 absent, explicit N2=0, and N2=0.7808.

The saved reconstruction agrees exactly with the captured `GAS_TAU_RAW` and `GAS_TAU` values in all three 45×128 cases, and its 45 dry-column values agree exactly with each saved `GAS_COL_DRY`. These are observed binary64 equalities for this held column and this pinned table. They do not constitute a strict forward-error/gamma-bound pass: the v3 plan explicitly withdraws the provisional v2 gamma-256 bound, and no tolerance-based verdict is applied. This is a same-table implementation diagnostic, not independent spectroscopy, coefficient-generation, physical-accuracy, full-port, or broadband-residual attribution evidence.

The V10 input used here is a matched dry-column counterfactual. The original trace has a 32-value dry-mass section; the retained carrier plan changed only that section to 45 values, and the replay reader uses the section width to override all 45 solver layers. The reconstructed 45-layer carrier therefore does not represent the ordinary production 32 native levels plus 13 upper extensions. Its exact input and transformation receipts are included.

The package includes the point source, locked runner, authorization, parent execution receipt, source/runner reviews, original construction JSON (losslessly gzip-compressed), diagnostic output, three saved reference results, input, source excerpts, and context receipts. The five archived Fortran source excerpts are also losslessly gzip-compressed to keep repository whitespace checks clean; their manifest entries bind both compressed bytes and original uncompressed SHA/size. The frozen plan carries 51 historical artifact-pin records; those pins document the original rooted execution context and do not promise that this archive alone can rerun that execution. The exact LW coefficient file is not duplicated: it is already tracked as `WRF/run/rrtmgp-gas-lw-g128.nc` in this repository checkout and is checked by the verifier against the pinned SHA and size.

The prior pfrac result is used only for a post-construction cross-check of the positive-N2 gas roster and discrete temperature, pressure, atmosphere, key-species and flavor mappings. The new point construction is durably written before pfrac and target-result parsing; pfrac values are not fed into the tau reconstruction. The included verifier reads saved artifacts only. It does not rerun the reconstruction or invoke a solver, compiler, RTE, WRF, REAL, or forecast.

From any working directory, run the standard-library verifier with:

```sh
python3 -I -S /path/to/bon-night-opacity-point-reconstruction/verify.py
```

The retained review records include an initial read-only lookup attempt that stopped before its final report because repeated interval identifiers were keyed too coarsely. The corrected audit keyed intervals by identifier, atmosphere, gas, g-point bounds and raw/packed offsets; it checked 44,947 saved minor terms without changing the construction or targets. The final terminal review and its erratum are both included.
