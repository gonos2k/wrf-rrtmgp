# UDM native hydrometeor diagnostics

`WRF_RRTMGP_HYDRO_DIAG_DIR` enables a read-only observer on UDM27 with radiation 4/4 or 37/37. The directory must already exist. An unset or empty variable disables observation. This is separate from the serial-only same-state replay and capture facilities; the native observer supports MPI and OpenMP.

```sh
mkdir -p hydro-diagnostics
export WRF_RRTMGP_HYDRO_DIAG_DIR="$PWD/hydro-diagnostics"
./wrf.exe
```

The radiation driver observes its actual inputs after cloud-fraction and convection-feedback preparation, before either radiation wrapper can clip or reject a hydrometeor. Each physical tile writes its own `hydro_d<domain>_i<start>-<end>_j<start>-<end>.csv`. Configuration and local output use named OpenMP critical regions. The file is closed after every snapshot so evidence survives a subsequent WRF collective fatal. Restart appends records; step and physical source seconds distinguish them.

Each radiation activation writes six phase summaries in QC/QI/QR/QS/QG/QH order, once for the LW/SW pair. These contain negative/positive/nonfinite counts, finite extrema and the global WRF indices of the minimum. Every negative value has its own row with the original i/j/k and kg/kg value. Positive, negative and zero-cloud-fraction water paths use the actual interface pressure difference and WRF gravity:

\[
WP_x=q_x(p_k-p_{k+1})g^{-1}1000\quad [\mathrm{g\,m^{-2}}].
\]

The phase sums run over the selected tile's cells and layers. They are sums of water-path diagnostics, **not an area-integrated domain mass or a time accumulation**. Multiply by the appropriate grid-cell area when forming a physical mass budget. Invalid pressure differences are counted instead of converted. The observer does not clip negatives, change cloud fraction, map graupel/hail, or establish that omitted condensate is radiatively negligible.

The UDM builder's strict negative rejection now includes the actual value, physical-column context supplied by the LW/SW wrapper, and the vertical vector layer. Previously `RESHAPE(q,[nlay,1])` fed a generic 2-D validator and could label a vertical layer as a column. Correcting the message does not change the acceptance policy: any negative still fails, and any positive hail is still unsupported.

In the first real-data 24-hour attempt, 37/37 stopped after 00:10 at a negative QI input. The original message did not retain its magnitude. The paired 4/4 integration continued and hourly outputs contain tiny negatives plus substantial positive graupel/hail. Output samples alone do not identify the failed 37 input or justify a tolerance. New per-activation observations are used to measure that input before changing the production contract.

The standalone tests exercise finite/nonfinite values, tiny and material negatives, global indices, multiple tiles, append behavior, water-path accounting and unchanged input arrays. Actual WRF observation-on/off and the failing real-data input are recorded separately under `validation/rrtmgp37/native-hydro/`; scoped successes must not be described as completed 24-hour 37 forecasts.

## Actual failing input and noninterference

The diagnostic GNU MPI4/OMP1 run identifies the first rejected 37 input at step 11 / 600 seconds: `LW i=217 j=1`, QI `-2.887890293650070E-035 kg/kg`, vector layer 22. The identical value and indices are present in the native CSV; all four tile snapshots were closed before the collective abort. This replaces the old misleading `column=22 layer=1` interpretation.

For the paired 4/4 20-minute cases, observer OFF and ON have identical inputs, namelist and binary. All 201 common numeric history variables at 0/600/1200 seconds are finite and bitwise equal, with L∞/L2=0. Radiation-driver snapshots occur at 0 and 600 seconds only: there is no invocation at the final 1200-second boundary. The summary CSV marks that missing snapshot as `NOT_OBSERVED`, rather than inferring values from history.

The 600-second baseline snapshot contains small negatives in five phases and positive graupel. Hail is still zero at this early snapshot; positive hail observed later in the separate hourly 24-hour baseline must not be assigned to this input. [Receipt](../../../validation/rrtmgp37/native-hydro/realdata-diagnostic.json), [phase summaries](../../../validation/rrtmgp37/native-hydro/diagnostic-summary.csv) and [standalone validation](../../../validation/rrtmgp37/native-hydro/validation-summary.json) retain the numerical evidence. No tolerance, CF replacement or graupel/hail mapping is selected by this patch.

The original paired 4/4 attempt completed 24 hours with all four MPI ranks successful and all 201 numeric history variables finite at 25 hourly times. Later snapshots contain positive graupel/hail and negatives larger than the first rejected 37 QI; the hourly QI minimum reaches about -5.35e-14 kg/kg. [The 24-hour receipt](../../../validation/rrtmgp37/native-hydro/24h-comparison-receipt.json) preserves per-phase extrema/counts and file hashes. These are hourly samples from the 4/4 state, not every radiation activation and not the evolving 37 state. The shared initial outputs match bitwise; the failed 37 attempt supplies no paired post-integration 24-hour comparison.
