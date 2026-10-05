# UDM cloud-top shrink and slope-retention evidence

This package separates two standalone source-extracted fixture records. Both use the rain-slope initialization candidate (`module_mp_udm.F`, SHA-256 `18bac4328061b828c1a57fcbead77986eb71bf5b6a56985fbed0672647bc7d4d`) and synthetic microphysics states; neither is a WRF forecast, radiation call, or meteorological frequency study.

## Initial experiment

`initial-experiment/` archives the first native natural-shrink experiment, receipt, plan, runner, driver, generated instrumented source, support stub, and losslessly gzipped logs. It reports a cloud-top transition from level 5 to 4 and exact retention of the changed level-5 slope across a second call. Its receipt records 10 compile/link processes, 2 fixture processes, 18 UDM calls, and zero WRF, REAL, or RTE calls. This initial runner/result remains a distinct historical experiment; it is not a receipt for the public wrapper below.

## Public native wrapper

`native-shrink/execution-receipt.json` records the later wrapper test, with its driver, runner, shared parser helper, O0/O2 instrumented source copies, logs, and independent review alongside it. Both optimization runs contain nine branch/density-mode records. Each record shows first top 5, second top 4, a changed level-5 slope after the first call, and exact equality of that value before and after the second call. The reviewed scope is 10 compile/link processes and 2 fixture processes (18 UDM calls); WRF forecasts, REAL calls, and RTE calls are zero.

The cloud-top shrink and retained slope are directly observed in this synthetic source fixture. No rain is initialized, so the evidence does not show a downstream rain consumer reading the retained slope. It does not establish precipitation occurrence or accuracy, whole-column conservation, coupled-forecast behavior, or domain-wide impact.

Run `python3 -I -S validation/rrtmgp37/cloud-top-shrink/verify.py` to authenticate the sealed package, source pins, receipts, and archived text logs without compiling or running the model.
