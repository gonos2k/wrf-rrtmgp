# Independent synthetic all-sky backend comparison

The pinned official all-sky driver runs twice at gas g128 LW / g112 SW with the same **band-indexed** cloud tables: once against pinned upstream libraries, once against the current WRF-vendored CPU archive. This checks implementation agreement with positive liquid and ice paths. It does not exercise the UDM input builder, native size conventions, precipitation optics, WRF cloud fractions, McICA masks or host constants.

The unmodified pinned loader fails because it requests `radice_lwr/upr` and `lut_*` fields. The current band datasets provide `diamice_lwr/upr` and `extliq/ssaliq/asyliq/extice/ssaice/asyice`. The runner preserves the original failures, then changes exactly those eight quoted dataset names. Array dimensions, coordinates, coefficient values, cloud-size arithmetic and the solver remain unchanged. G-point cloud tables cannot be substituted for these band tables and are not used.

The synthetic driver uses 24 columns, 72 layers and one iteration, positive liquid and ice paths, midpoint sizes on the loaded axes, and ice roughness category 2. It writes the state and five LW/SW flux arrays. It does not write optical depth, single-scattering albedo or asymmetry arrays, so those are not directly compared.

## Reproduce from a fresh checkout

```bash
bash validation/rrtmgp37/upstream-reference/run_rfmip.sh build/independent-rfmip
bash validation/rrtmgp37/upstream-reference/run_allsky.sh build/independent-rfmip
```

The second command uses the exact source/data and current vendor archive built by the first command, verifies their pins and file hashes, and creates a separate all-sky work directory. It refuses to overwrite that evidence. If NetCDF is installed outside the default compiler paths, set `NETCDF_INCLUDE_DIR` and `NETCDF_LIBRARY_DIR` before both commands.

Both arms compile the same pinned driver and IO/loader source files separately against their own module sets. The vendor arm uses only the vendored module directory and freshly generated client modules; it does not reuse upstream `.mod` or `.o` files. The vendor linker map must show the cloud and aerosol frontends selected from `libwrf_rrtmgp.a`. The source-only eight-name dataset adapter is applied to both arms; this is not an independent test of WRF's production cloud loader. Aerosol frontend symbols are linked from the vendored archive, but aerosol optics are not numerically exercised (`aerosols=0`).

The input schema checker requires optical-table units `m2/g` and `unitless`, size axes `microns`, and spectral edges `cm-1`. The output comparator requires matching dimensions, variable sets, datatypes, unit metadata when present, finite/unmasked values and exact array bytes, including the required five flux arrays. The official output variables omit unit attributes: matching missing metadata is not an independent physical-unit check. Backend agreement and published-reference accuracy remain separate: this all-sky run has no published reference accuracy gate.

CI runs this procedure after the independent RFMIP comparison and uploads the original failure logs, loader diff, linkage evidence, binary/input/source hashes, NetCDF outputs and comparison status. The local fresh-build receipt records the actual results and source/library identities. This check cannot settle whether a UDM physical radius or snow/graupel/hail optical model is correct.

## Recorded local result

The preserved earlier local run passed: 13 SW and 12 LW variables, including five flux arrays, were finite and bitwise equal. Each phase had 176 positive LWP and 432 positive IWP cells. [Full comparison and provenance](allsky-local/allsky-backend-comparison.json), [loader-only diff](allsky-local/loader-only-adaptation.diff), and [publication manifest](allsky-local/publication-manifest.json) retain the actual source, library, data and executable identities. Paths inside these records identify preserved local artifacts and are not portable runner arguments.

A fresh rerun after client/module isolation also passed the same 13 SW and 12 LW arrays. Its workspace receipts are hash-pinned in [the CPU batching evidence](../column-batching-source/result.json); the historical `allsky-local` publication remains unchanged.

A separate mutation check on copies of the actual output accepted the baseline and rejected changed flux, NaN, masked samples, unequal unit metadata, missing required flux and a liquid-cloud-free pair. [Failure-check receipt](allsky-local/comparator-probes.json) retains each exit/status; no original outputs or tolerance were changed.
