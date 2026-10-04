# UDM input diagnostics retain native layer and caller identity

The expanded-table Matthew UDM27/RRTMGP37 48-hour attempt passed the former 179.996 K table rejection, then stopped after model time00:50 with `RRTMGP_INPUT_DP_HPA_NOT_FINITE at column=1 layer=1`. Actual model RC=1, all pinned assets remained unchanged, and only the initial history file was produced. It is a failed forecast, not a 48-hour validation or normal-physics-difference result.

The UDM builder had passed its one-dimensional pressure and cloud-fraction arrays to generic `(column,layer)` checkers as `(native_layers,1)`. This misreported a failing native layer as a column and dropped the wrapper-provided grid context. The new checks retain the original finite-before-range ordering and acceptance rules while reporting the actual native layer and supplied column context. Positive inputs and optical calculations are unchanged.

The actual-source GNU fixture now rejects nonfirst-layer invalid pressure/cloud fraction and checks the full caller identity and layer=2, with a separate no-context fallback check. Its complete negative-q/conservation/raw-input harness passes; registration and diff checks pass. No full WRF executable with this diagnostic-only change was built locally.

The failed run receipt, all nine logs, configuration and a read-only source trace are preserved here. The pressure producer remains under investigation. WRF derives pressure interfaces from its model state before this input check; finite native dry mass does not establish finite moisture or temperature. The old complete RA4 forecast is retained and was not rerun. High-frequency state capture is a separate next diagnostic.
