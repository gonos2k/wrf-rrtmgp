# UDM cloud-fraction diagnostic extent

The UDM microphysics working vector `UDM_CLDFRA` is accompanied by
`UDM_CF_TOP` and `UDM_CF_STEP` (raw-capture name `UDM_CF_SOURCE_STEP`). The
top and step describe the last actual `cldf_diag` call for each horizontal
column during the UDM call:

| `UDM_CF_TOP` | Meaning |
| ---: | --- |
| `-1` | `cldf_diag` was not called; step is also `-1`. |
| `0` | `cldf_diag` was called with an empty cloud/ice extent. |
| `1..n` | `cldf_diag` wrote the diagnosed fraction through this one-based native level. |

For the supported WRF column layout, `kts=1`; thus the top is a count from
the native bottom-up column and is also the exact `ktop` passed to
`cldf_diag`. The step is the WRF microphysics timestep. A later subcycle that skips the diagnostic does not
erase an earlier actual result. If no subcycle calls it, the two fields keep
their `-1` sentinels. The helper writes only levels `1:ktop`. Its dummy uses
`INTENT(INOUT)` so values above `ktop` retain the caller's initialization.

`UDM_CLDFRA` remains the full working array used by UDM. The routine initializes
that array to one before its calculation, so values above `UDM_CF_TOP` may be
working placeholders rather than diagnosed cloud fractions. This metadata
does not change the operational radiation cloud fraction, condensate paths,
or overlap policy. The `INTENT(INOUT)` declaration documents the helper's partial-write behavior; it is not evidence of an MPI-specific defect.

The diagnostic replay's `B` case is intentionally an extent-limited hybrid:
it uses the saved UDM fraction on `1:UDM_CF_TOP` and the original radiation
fraction above the recorded top, then rebuilds paths for that selected
fraction. A top of zero therefore leaves the original radiation fraction in
all layers; a top of `-1` means `B` is skipped. This is a controlled
counterfactual, not a production policy. Old raw captures without top metadata
remain readable; their whole saved vector can only be labeled
`LEGACY_UNKNOWN`, never a fully diagnosed profile.

`UDM_CF_RECOMPUTED` is separate: it recomputes cloud fraction for the current
state and full physical column. It has a different time/state contract from
the fraction UDM last used and must not be substituted for the saved working
vector or its extent.
