# UDM surface-rain row regression

The outer UDM wrapper calls its two-dimensional microphysics routine once per
horizontal `j` row. The inner routine accepts `sr(ims:ime)` and resets and
updates that row's surface snow-to-rain ratio. Passing the whole rank-2 `sr`
array relies on sequence association and repeatedly addresses the first row;
the legacy path must pass `sr(ims,j)`, as the other UDM branches already do.

This test compiles the actual outer UDM source and runs a clear, two-row case
with distinct nonzero `sr` sentinels. It also compiles a negative-control copy
with the old whole-array argument restored and requires the second row to
fail the zero-reset assertion. This protects the surface precipitation ratio
that WRF passes downstream to land-surface handling, including Noah-family
schemes. The test does not measure a Noah flux response.

Run through the standalone test suite as `udm_surface_rain_row`; the Python
runner writes each execution into a new timestamped directory and retains both
compiler outputs and a JSON receipt.
