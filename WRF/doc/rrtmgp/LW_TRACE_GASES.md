# UDM37 longwave trace gases

WRF option 37 uses the existing longwave wrapper's per-layer CFC11, CFC12,
CFC22 and CCl4 volume mixing ratios, in addition to H2O, CO2, O3, N2O, CH4
and O2. This is a host-input correction: the pinned LW coefficient data already
contain minor-absorber coefficients for these species. Previously, initialization
filtered out these minor intervals because the adapter listed only six gases.

Current LW initializes the coefficient model with eleven available gases,
including the fixed dry-background N2 described in
[`LW_BACKGROUND_N2.md`](../../test/rrtmgp/LW_BACKGROUND_N2.md). Historical
replay formats V1–V11 retain their original ten-gas closure. SW retains its
six-gas configuration: the pinned SW file has no key/minor-absorber intervals
using these four trace gases. Existing RRTMG4 calls retain their prior arguments.

## Host state is authoritative

The wrapper passes its existing `cfc11vmr`, `cfc12vmr`, `cfc22vmr` and `ccl4vmr`
arrays directly. It retains the same upper-atmosphere extension and units
(dimensionless mol/mol) used by the legacy LW call. In real-data runs with `ghg_input=1`, WRF
initializes its time-varying CAM gas reader and supplies CFC11/12 from that
reader. Ideal SCM initialization skips the CAM-file load; setting
`ghg_input=1` there does not establish that the table was consumed, and the
observed SCM profiles retain the existing fallback values. CFC22/CCl4 use
the existing wrapper constants. With `ghg_input=0`, the existing static
fallback values are used. The adapter passes the host profiles without
replacing them with a new climatology.

Standalone callers may omit all four optional arrays to request explicit
zero-trace-gas compatibility. Providing only some arrays is an error; supplied
arrays must match the layer shape and be finite/nonnegative. This compatibility
path does not imply that missing trace gases are physically negligible.

## Replay and causal comparison

New LW captures use V12 (without CU records) or V13 (with CU records). Both
record `VMR_N2` and an explicit `TRACE_GASES_PRESENT` flag. The four CFC sections
are included only when all four host arrays are supplied; otherwise the flag is
zero and the replay initializes those arrays to zero. Raw native-column records
permit checking the host-to-adapter mapping, and complete adapter arrays retain
above-top values. These new formats can also record the opt-in frozen-optics
metadata/table identity. SW captures and historical V1–V11 LW captures retain
their original formats and ten-gas closure. V8/V10 consume their recorded CFC
profiles; older LW formats without CFC records use zero profiles rather than
reconstructing unrecorded CAM values. All V1–V11 formats omit the new N2 input.

The reference executable recomputes gas optics from recorded VMRs. The
historical controlled comparison set only these four arrays to zero in a copied
V8 input using the then-current ten-gas closure, preserving
pressure, temperature, six common gases, surfaces, cloud/precipitation state,
table, seed and dry mass. `GAS_TAU_RAW`, clear/all-sky LW flux and heating changes
then measure the four-gas contribution within this RRTMGP configuration.

This isolates an omission in the port. It does not equate RRTMGP and RRTMG4
spectral coefficients, cloud optics or solvers. The total 4/37 difference also
contains those physical differences and coupled state feedback. A short SCM or
same-core replay cannot establish general forecast or observational accuracy.

The validation record at `validation/rrtmgp37/lw-trace-gases/` separates ideal
fallback checks from an actual real-data CAM case. In the latter, equality is
checked against the first LW wrapper interpolation at its radiation date, not
the integer-day physics initialization log. The measured four-gas contribution
to that captured column is at most 0.4403 W/m2 over the LW flux profile; this
single-column contribution is not a model bias or domain-mean accuracy score.
