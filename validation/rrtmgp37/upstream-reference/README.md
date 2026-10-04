# Independent RFMIP clear-sky validation

This validation record compares the official RFMIP clear-sky driver run in two builds: (1) the pinned upstream RTE+RRTMGP library and (2) the WRF-vendored CPU-only library. Both use the same official driver, input and gas coefficients. Each run is also checked against the pinned published reference files. This does not use the WRF adapter and does not directly validate WRF's g128/g112 configuration.

Pins: `earth-system-radiation/rte-rrtmgp@41c5fcd950fed09b8afe186dede266824eca7fd3` and `earth-system-radiation/rrtmgp-data@ea788bb39876948fa8d2c235665ccff19b4686b5`. The input has 1800 profiles. GNU Fortran 13.3.0 was used serially with `-O0 -ffree-line-length-none`; `RTE_USE_SP` was not defined, so `wp=c_double`. Output NetCDF flux variables are `float32`. The preserved high-resolution run's input, coefficients, sources, libraries/executables and NetCDF outputs are hash-indexed in the validation record; its detailed metrics are in `rfmip-comparison.json`.

The vendor comparison must not link upstream-compiled client `.o`/`.mod` files to the vendored archive. The forked `ty_gas_optics_rrtmgp` module has a different compiler-visible type/vtable layout; a mismatched client can fail in the coefficient loader (locally a segmentation fault; CI reported “k-distribution file isn't LW” and divide-by-zero). The corrected runner compiles copies of the exact pinned RFMIP client sources in a clean directory against the vendored module directory, while the upstream arm retains its own upstream modules and library. The data-model inputs and numeric oracle are unchanged. This is build-interface isolation, not a production physics change.

At the upstream test tolerance (`atol=1e-5`, `rtol=0`), LW `rld` and `rlu` match published references exactly. SW `rsd` and `rsu` fail that unchanged tolerance with maximum absolute errors of `6.103515625e-4` and `1.8310546875e-4` W m-2. The WRF-vendored CPU backend is bitwise identical to the pinned upstream executable for all four arrays; it has the same SW residual. The published files identify `RTE-RRTMGP-181204`; whether the SW mismatch reflects source/reference-generation revision differences remains unresolved.

The WRF-vendored source declares the same upstream source pin and lists local changes in `WRF/external/rte_rrtmgp/SOURCE.json`: cloud reader field-name/diameter adaptation, a fatal callback, and CPU-only target directive guards. Exact equality here demonstrates execution agreement only for this clear-sky test case; it does not establish equivalence for every backend configuration.

## Reproduce the production-resolution backend run

Run from the root of the current `wrf-rrtmgp` checkout. Both runners refuse to overwrite an existing evidence directory. For a custom NetCDF installation, set `NETCDF_INCLUDE_DIR` and `NETCDF_LIBRARY_DIR` before both commands; otherwise they use `nf-config` and `nc-config`.

```sh
# Fresh g128/g112 backend reproduction at the WRF production gas resolution.
bash validation/rrtmgp37/upstream-reference/run_rfmip.sh build/independent-rfmip-new
bash validation/rrtmgp37/upstream-reference/run_allsky.sh build/independent-rfmip-new
```

The maintained runner fetches the exact source/data pins, builds both libraries, and compiles each client against its matching module files. Do not manually link upstream example objects against the vendored archive. `VENDOR_CLIENT_SHA256SUMS.txt` records the copied client sources, objects, modules, and executables.

The original g256/g224 published-reference experiment is the historical record described above. Its preserved comparison receipts retain the SW reference failure. The current g128/g112 backend reproduction uses different gas resolution and does not replace that published-reference accuracy test. The upstream tolerance remains unchanged.

The upstream all-sky example was also tried without modifying its source. It fails on the pinned current cloud dataset because it requests `radice_lwr`, while the dataset provides `diamice_lwr`/`diamice_upr` and renamed optical fields. That original failure is retained separately from the clear-sky results above. A subsequent [synthetic band-table all-sky comparison](ALLSKY.md) adapts exactly eight dataset-name bindings and compares pinned upstream against fully vendored cloud/gas/RTE frontends. It does not turn the original loader failure into a pass or claim UDM physical-input accuracy.

`SHA256SUMS.txt` retains the original scratch-artifact paths and hashes. It is not a checksum list for this publication directory: the published inventory corrects raw-GitHub URLs that previously had an extra `data/` component. `publication-manifest.json` records the original and published hashes and this metadata-only correction. The original experiment used vendored source from PR #10 (`ca33525`); it is not presented as a newly rebuilt PR #12 executable.

The checked-in comparator was run on the preserved outputs: backend comparison exits 0; adding the published references exits 1. Those outcomes are preserved separately in `rechecked-backend.json` and `rechecked-published-reference.json`.

## Production-resolution gas backend check

A further run uses gas LW g128/SW g112 with the same 1,800 RFMIP profiles, block size 8, pinned upstream driver and frozen libraries. All four flux arrays are finite and bitwise equal between upstream and vendored CPU builds. This aligns gas resolution with WRF, but still does not exercise the WRF adapter, host constants, clouds or precipitation. `g128-g112-comparison.json` records binaries, inputs, coefficients, outputs and labeled descriptive sensitivity versus g256/g224; `g128-g112-runs.json` retains every launch and per-stage output hash. The LW-stage SW files are still templates until the subsequent SW launch; final arrays are compared only after both phases complete.

The preserved `g128-g112-reproduce.sh` helper is specific to the recorded `/NHNHOME/WORKSPACE/...` workspace. For another checkout use the fresh-build `run_rfmip.sh` runner below. To recheck the preserved outputs, compare without high-resolution published reference files:

```sh
RECORDED_RUN_ROOT=/path/to/preserved/official-rrtmgp-reference
python3 validation/rrtmgp37/upstream-reference/compare_rfmip.py \
  --upstream "$RECORDED_RUN_ROOT/run-upstream-g128-g112" \
  --vendor "$RECORDED_RUN_ROOT/run-wrf-cpu-g128-g112" \
  --output "$RECORDED_RUN_ROOT/g128-g112-backend-comparison.json"
```

The recorded maximum g128/g112–g256/g224 flux changes are 1.173/0.601 W m-2 for LW down/up and 2.156/0.813 W m-2 for SW down/up. Those are coefficient-resolution sensitivities, not accuracy pass/fail results. Individual 1.35–1.48 s launch wall times include setup/IO and are not a performance benchmark.

## Continuous independent backend check

`run_rfmip.sh NEW_BUILD_DIRECTORY` fetches and verifies both git pins, builds their unmodified RFMIP driver/helper objects and upstream library, separately builds the **current** vendored CPU library, checks the input/g128/g112 coefficient SHA256s, runs both engines and requires bitwise equality of all four finite flux arrays. It refuses existing build directories. NetCDF paths can be set with `NETCDF_INCLUDE_DIR` and `NETCDF_LIBRARY_DIR`; otherwise `nf-config`/`nc-config` supply them.

The fresh local execution passed with current vendored source (`fresh-build-g128-g112.json`). The independent-rfmip CI job repeats this build/run comparison and uploads fluxes, pins, sources/binaries/input hashes and status. It checks backend execution equivalence at production gas resolution; it does not claim published-reference accuracy for g128/g112. RFMIP supplies its official gas set and uses upstream default constants, so the WRF six-gas subset and WRF host constants are not exercised.
