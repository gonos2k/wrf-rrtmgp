# Same-executable restart continuity check

This is a separate one-hour restart validation using the same executable,
initial/boundary data, coefficient files, and SR-corrected PR26 source build as
the 24-hour pair. RA4 and RA37 were restarted independently from their own
12:00 checkpoint, then compared to their own continuous 13:00 output.

The executable SHA256 is
`176f589d657ca87df670cef3429d7474e674f3e44445eb7886aed871e36bef8f`. The
checkpoint clock was 2010-06-11 12:00; each restarted case completed at
2010-06-11 13:00. Four MPI ranks report success for each segment. The detailed
runner/preflight/execution receipt is in this directory. Restarted output and
checkpoint hashes, continuous references, and input pins are summarized in
`../netcdf-sha-index.json`; no NetCDF files are copied into this evidence
package.

RA4 matched all 201 numeric output variables exactly; RA37 matched all 204.
Dimensions, variable sets, and variable metadata match. The root's independent
raw-byte recheck reports every numeric array and the `Times` array byte-identical
for both arms. It separately retains the global `START_DATE` difference
(continuous anchor 00Z; restarted anchor 12Z), so the whole files are not
claimed byte-identical. The original restart runner's exact value comparator
and the separately labeled posthoc raw-byte reproduction are both retained.
