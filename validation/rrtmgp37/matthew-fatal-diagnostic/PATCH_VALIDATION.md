# Fatal reporter patch validation scope

This note describes the diagnostic patch separately from the earlier forecast runs preserved in the adjacent evidence bundle.

The component worker test passed and the RRTMGP adapter library compiled in the component build. These checks exercise the worker-level diagnostic and adapter-library source only. The full WRF executable has not yet been rebuilt with the reporter patch, and no forecast has been run with that patched executable.

Both RA37 runs recorded in the evidence bundle used the pre-patch executable (`6378764a2119e3475a4ec8b80cce20f5434739c428dc7fb401c899bcdeb309ed`). The OMP=2 continuation stopped at model time 00:40 with return code 1 and a rank-0 `MPI_Abort`; its logs do not identify the WRF fatal cause. The separate OMP=1, one-hour diagnostic also stopped at 00:40, but its log explicitly identifies a graupel longwave lookup at 179.996 K, outside the frozen table's [180, 300] K range. This is a tested lookup-coverage failure for that state, not a radiation-accuracy result or a completed 48-hour RA37 forecast.

The reporter patch changes fatal-message reporting. It does not expand the frozen-optics table or alter the no-extrapolation behavior. A proposed table extension has not been generated or tested. The original REAL/v1 validator and RA4/v1 validator failures remain preserved alongside their separately corrected postflight receipts; none of these receipts were rewritten for this patch note.
