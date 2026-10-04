# Selected legacy RRTMG optics export

This is an opt-in observation around the existing legacy RRTMG call in the
same-state audit. With `WRF_RRTMGP_RRTMG4_EXPORT_DIR` unset, the observer
returns without opening files or copying spectral arrays. The per-call
wrapper checks remain inactive and perform no copies on production calls.
With it set, only
the audit's serial engine-4 call at d01, step 2161, column (24,55), 129600 s
can write output. The directory must already exist, and the two phase files
must not already exist. MPI builds and runs configured for more than one
OpenMP thread are rejected when the export is requested because the observer
has process-local file/state ownership.

The two files are `rrtmg4_d01_i24_j55_step2161_lw.txt` and
`rrtmg4_d01_i24_j55_step2161_sw.txt`. Each has a schema line, six context
key/value records, and a layout record. Every stage marker (`INPUT`, `CLOUD`,
`GAS`, `RESULT`) is followed by field headers of the form
`NAME UNITS DIM1 [DIM2]` and a separate numeric record. Values use Fortran
array order (first dimension varies fastest); numeric output is formatted at
REAL64 text precision from the model's native `REAL` values. Integer fields
carry units `1`.

Inputs record both the wrapper profiles (`PLAY`/`PLEV`) and the solver
profiles produced by `inatm` (`SOLVER_PAVEL`/`SOLVER_PZ`). In the current
legacy source, `pavel(l)=play(l)` and `pz(l)=plev(l+1)` for bottom-to-top
layer ordering. VMRs are retained separately from molecular columns;
`COLDRY` and `WKL_MOLECULE_COLUMNS` are molecule cm-2 and the LW
cross-section amounts carry the source's 1e-20 scaling. Cloud records
preserve `cldprmc` outputs, the g-point-to-band map, explicit band IDs and
wavenumber bounds, cloud paths/radii, method flags, and the arrays handed to
the solver. `CLDPRMC_TAUOR` and `SOLVER_CLOUD_UNSCALED_TAU` are the original
non-delta-scaled SW cloud optical depth; `SOLVER_CLOUD_TAU` is separately
captured. LW `TAUTOTAL_GAS_PLUS_AEROSOL_CLOUD_EXCLUDED` combines gas and
aerosol optical depth; cloud optical depth is recorded in the CLOUD stage.
SW gas capture includes Rayleigh optical depth and `zsflxzen`, the per-g-point
TOA solar flux at zenith (`SOLAR_FLUX_GPOINT_ZENITH`), before multiplication
by cosine zenith. `COSZEN`, `SOLAR_CONSTANT_SCALE`, and
`BAND_FLUX_ADJUSTMENT` are captured alongside it for initialized SW bands
16–29 only, in the same order as `BAND_INDEX`. Result records include all-sky
and clear-sky fluxes and heating;
SW and LW heating are K day-1.
The audit requests no LW clean-atmosphere diagnostic, so the export does not
report its inactive clean-sky buffers.

The export is observational: it does not alter solver inputs or outputs. It
does not establish parity, accuracy, or observational skill, and one
selected column is not a domain-wide result.

The standalone writer fixture validates disabled no-output behavior, both
phase files, stage ordering, rank-1/rank-2/integer record grammar, and
Fortran-order payload parsing. Reproduce it from the repository root with:

```sh
python3 validation/rrtmgp37/rrtmg4-optics-export/run_writer_fixture.py
python3 -B -m unittest validation/rrtmgp37/rrtmg4-optics-export/test_read_export.py
```

The checked-in tiny text outputs under `fixture/` were emitted by that actual
writer module; `writer-fixture-receipt.json` records their hashes and the
standalone compiler scope. These checks are not a WRF build or a
radiation-solver run.

A one-minute actual-WRF runtime preservation/export receipt, compressed LW/SW
exports, and a portable package verifier are in
[`runtime-evidence/README.md`](runtime-evidence/README.md). That evidence is
scoped to the stated three-arm serial run and selected column; it makes no
accuracy or observational-skill claim.
