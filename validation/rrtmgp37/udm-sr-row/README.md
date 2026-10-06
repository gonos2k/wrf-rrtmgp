# UDM27 SR row correction

The legacy UDM dispatch added by commit `d3fea7eb9a1dd9cdd837afc7ea6c6757941ac2b3` passed the whole two-dimensional `SR` field to the row-level `udm2d` dummy. This restores the official `sr(ims,j)` argument. `SR` is the frozen precipitation fraction used by Noah to partition surface precipitation; a wrong row can affect later snowpack and coupled state.

The actual outer-UDM two-row regression passes with the fix and fails when the old argument is restored. A fresh GNU dm+sm `em_real` executable was then compared with unmodified official WRF v4.8.0 at the same 12-hour restart checkpoint. Both the one-rank and four-rank fixed outputs are byte-identical to their corresponding official files, including all 202 variables and metadata. Exact source, executable, input, output and table identities are in [fixed-runtime](fixed-runtime/README.md).

This is a one-minute regression, not a new 24-hour comparison. The existing 24-hour 4/37 differences remain archived measurements with a known defective RA4 surface-precipitation reference; see [the erratum](coupled-comparison-erratum.md). MPI1 and MPI4 still differ in both official and corrected builds. The pre-fix failure and source review are preserved here separately from the corrected runtime evidence.
