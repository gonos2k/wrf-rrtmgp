# UDM27 native dry-air gas columns

Production option 37 supplies the same native WRF dry-layer mass used for hydrometeor water paths to RRTMGP gas optics. For bottom-first native layers:

```text
N_dry = M_dry * N_A / (M_molar_dry * 10000)    molecules cm-2
```

`M_dry` is kg dry air m-2 from `-DNW*(C1H*MUT+C2H)/g`. `M_molar_dry` is the initialized WRF dry-air molecular weight in kg mol-1; `N_A=6.02214076e23 mol-1` is the pinned RRTMGP constant. The factor 10000 converts m-2 to cm-2. The passed gas VMRs remain relative to dry air. This removes a second reconstruction of dry mass from loaded hydrostatic pressure thickness and water-vapor VMR.

Both LW and SW adapters append optional `native_dry_layer_mass_kg_m2(ncol, n_native)`. It must have matching columns, 1 to nlay native layers, and positive finite values. The production wrappers require the native WRF field and pass all physical layers. No zero/negative sentinel is used for extension layers. Above the native model top, dry molecular columns retain the existing pressure/VMR `get_col_dry()` policy. Historical standalone calls that omit the optional native matrix retain this helper for every layer.

Pressure and temperature still determine gas interpolation, absorption coefficients and source functions. Only dry molecular column amount changes. Heating still uses pressure-interface flux divergence and the initialized g/cp; this patch does not claim a complete native-coordinate thermodynamic tendency contract. Native dry mass alone also does not validate any hydrometeor optical model, effective-size metric, cloud fraction or McICA policy. Option 4 computation is unchanged.

## Replay and independent checks

Native calls write `RRTMGP_REPLAY_V6`. After the existing physical sections and optional precipitation records, `NATIVE_DRY_LAYER_MASS_KG_M2` precedes the mandatory V5 host constants. Its width is the native-layer count; other atmospheric arrays include the above-top extension. V1–V5 remain readable. All adapter and reference result files now report full-layer `GAS_COL_DRY` in molecules cm-2, including historical pressure-helper calls.

The standalone reference executable reads the physical mass matrix, independently converts it to molecules and calls the official gas-optics `col_dry` interface. It does not call the WRF adapter or its conversion helper. Actual-capture tests compare the native matrix with the sibling WRF raw mass record; the separate native-mass test reconstructs that record from NetCDF MU/MUB/DNW/C1H/C2H. The extension oracle directly evaluates pressure/VMR dry columns. Counterfactual replay removes only the native matrix and selects V5, holding all other input values, constants and the McICA seed fixed.

Measured execution results and reproducible commands are recorded in [the PR17 evidence](../../../validation/rrtmgp37/native-gas-columns/README.md). Numerical identity with an independent execution validates this mapping and gas-optics interface; observational accuracy and completed long UDM forecasts require separate evidence.
