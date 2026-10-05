# Normal-carrier LW gas-opacity reconstruction

This package records one saved, source-ordered reconstruction for the ordinary BON-night LW V10 carrier. It is distinct from the earlier matched-45 dry-column counterfactual: this V10 input supplies 32 native dry-mass values and derives the upper 13 solver layers from interface pressure and H2O. The only authenticated direct-library target is the historical N2-absent replay. The package does not establish normal-carrier N2=0 or positive-N2 results.

The reconstruction contains one 45-layer dry column and two 45×128 arrays (`GAS_TAU_RAW` and `GAS_TAU`). Both arrays match the captured direct-library target exactly in the saved comparison (zero residual and zero ordered-binary64 ULP difference). This is an observed same-table implementation diagnostic for one carrier, not a strict arithmetic-bound pass, coefficient-generation proof, spectroscopic or physical-accuracy result, full-port validation, or explanation of the full broadband residual. No tolerance verdict is used.

A separate saved join compares the reconstruction with the actual WRF same-call capture. On the 32 supplied native layers, both tau arrays differ by at most 5.4569682106375694e-12, relative 7.223528191333665e-16, and 6 ordered binary64 ULP; all 13 pressure/H2O extension layers match exactly. The WRF production source uses the factored dry-mass expression `mass * (Avogadro / (MOL_WEIGHT_DRY * 10000))`; the independent source audit found that grouping matches the 32 saved native dry values bitwise. The direct left-associated grouping matches 23/32 and differs by at most 1 ULP. The actual WRF dry-column join has a maximum relative difference of 2.174905586287653e-16. These are separate arithmetic observations; they do not attribute the tau residual or establish a tolerance or accuracy result.

The runner persisted the complete construction before opening the direct target opacity arrays. The package preserves the actual input, raw capture, direct result, parent return-code receipt, invocation, authorization, construction receipt, plans, source files, source/runtime provenance, and independent direct-target and actual-WRF join audits. Large construction/comparison/result data and original Fortran sources are losslessly gzip-compressed; manifest entries bind stored and inflated hashes and sizes.

The pfrac result is reused from the already tracked `bon-night-independent-pfrac` evidence. It is checked after construction only for identical shared input sections, state-derived pressure/temperature/atmosphere indices, semantic gas-key and flavor identity, and gas roster after removing N2. It supplies no dry-column, gas-column, coefficient, or tau values. Its matched input is a 45-mass counterfactual, not the normal carrier; fraction differences remain descriptive.

The build receipt's source-pin manifest has a documented generation discrepancy: its driver file differs from the selected historical source in one sidecar-guard hunk. The selected invocation passed an empty sidecar argument, so that branch was not taken. The audited gas roster, input/constants reads, dry-column expression, and selected call path are scoped compatibility evidence, not proof of complete executable source-to-object identity. The authorization retains 138 recursive pin records, including 44 absolute historical environment paths; these preserve provenance and do not imply those paths are available to CI.

The saved-artifact verifier uses only the Python standard library. It checks the closed package roster, stored/inflated hashes, tracked external pins, plan/authorization/execution ancestry, 32+13 dry-column ledger, construction-to-result and target joins, both tau arrays, pfrac shared-state/semantic context, and the separately pinned actual-WRF join. It does not recompute opacity or invoke a solver, compiler, RTE, WRF, or REAL.

Run from any working directory:

```sh
python3 -I -S /path/to/bon-night-normal-opacity-reconstruction/verify.py
```

An independent terminal review reparsed the direct-reference target and the saved arithmetic arrays. A separate independent saved-source audit checked the actual-WRF same-call result, runtime/source-manifest pins, production dry-mass grouping, and native-versus-extension tau summaries. Those reviews remain scoped to the saved inputs and outputs described above.

The dedicated workflow runs this saved-evidence verifier only; it does not build or run WRF or the radiative-transfer engine.
