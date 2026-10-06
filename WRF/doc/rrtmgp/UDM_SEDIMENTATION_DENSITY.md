# UDM37 sedimentation density contract

The UDM call-entry measurements in [PR106](https://github.com/gonos2k/wrf-rrtmgp/pull/106)
show that the WRF host supplies dry-air density for the bounded cold/warm SCM
columns. These measurements are not a claim about every host implementation.

The inherited UDM conversion

```fortran
dend = (p / t - den * rv) / (rd - rv)
```
recovers dry-air density when `den` is total gas density. If `den` is already
dry-air density and `qv` is the dry-air mixing ratio, the conditional EOS gives

```text
p / T = rho_d * (Rd + Rv * qv)
DEND_legacy / rho_d = 1 + Rv * qv / (Rd - Rv)
```

Since `Rd < Rv`, this second conversion reduces the density for positive
`qv`. PR106's warm-column reevaluation reaches a difference of approximately
-2.14% from the conditional dry EOS. This is an inherited host/UDM contract
mismatch; it does not establish that all RRTMG4/RRTMGP37 flux differences are
porting errors or quantify their physical accuracy.

## Scoped runtime change

`udm()` appends optional `input_density_is_dry`. Omitting the argument resolves
to false at each call. The flag reaches all three internal `udm2d()` forwarding
branches. When true, only the sedimentation weight `DEND` uses the supplied
`DEN` directly. `DEN`, `DENFAC`, cloud/precipitation PSD equations, activation,
number concentration, and optics are unchanged by this density patch.

Only the initialized option37 `have_udm_cf` host call supplies true. The
ordinary option4 host call omits the flag and retains its legacy expression.
This default also preserves the existing standalone UDM call convention.

Native `semi_lagrangian()` transports its caller's density-weighted amount.
The caller forms `rql = DEND * q`, obtains a bottom precipitation amount, and
converts the resulting amount back with the same `DEND`. Conservation in that
weight alone does not establish conservation using the WRF dry-mass basis.
The isolated test therefore checks both budgets, including bottom precipitation.
It does not test the complete UDM water budget with all other processes active.

## Versioned observer

The opt-in entry observer writes `RRTMGP_UDM_ENTRY_DENSITY_V2`:

- `INPUT_DENSITY_IS_DRY`: explicit selected policy, 0 or 1.
- `DEND_REEVALUATED_PRECALL_KG_M3`: selected-policy reevaluation.
- `DEND_LEGACY_COUNTERFACTUAL_KG_M3`: the inherited formula evaluated separately.

Both DEND fields are pre-call observer reevaluations. Neither field is a direct
observation of the private `udm2d` array. The observer remains disabled by
default and validates its own enabled output. V1 packets retain their original
legacy interpretation. Historical PR106 evidence is verified against the frozen
`16fb5415cc30ec124f9d9871a236009f1a472c07` sources rather than relabeled as output
from this physics change.

## Validation and remaining gates

The actual source-extracted sedimentation kernel passes O0/O2 caller-weight and
dry-density budget checks for the declared fixture. Native full outer UDM
fixtures compare the original PR106 module with candidate omitted/false calls
bitwise for all three forwarding branches and two moisture cases. True-policy
outputs are separately evaluated. Exact zero-vapor equivalence uses deliberately
exact binary32 inputs; it is not a general bitwise theorem.

A fresh full GNU13.3 serial SCM build completed successfully (472.47 seconds).
Its 7,894 tracked source entries match before/after the exact three-file runtime
overlay, and the executable library closure matches the pinned reference.
Six forecasts completed: cold/warm37 with capture off/on, and cold/warm
ordinary4. Ordinary4 retains all 208 arrays, masks, metadata and whole-file bytes
from PR106. Each37 off/on pair retains all 211 arrays and whole-file bytes.
All 12 V2 entry packets and 12 same-call post-radius packets validate; the
selected DEND equals passed DEN for all 708 native layer/call samples.

Candidate37 vs PR10637 retains the same schema, masks and finite patterns;
59 cold and 64 warm variables have numerical changes. The maximum absolute
SWDOWN response is 0.00039673 W/m² (cold) and 0.00006867 W/m² (warm). These are
bounded one-minute SCM responses, not a general forecast error estimate.
They do not explain the earlier tens-of-W/m² radiation differences. The native
isolated transport budget and defaultfalse compatibility tests establish the
scoped correction; physical accuracy and long-time feedback remain separate.

The native fixture also exposed a separate inherited rain-only read of
uninitialized `rslopec2` above `ktopqc` in the `qrcon` loop through `ktopqr`.
Baseline and candidate legacy controls fail under signaling-NaN instrumentation;
those receipts remain preserved. The compatibility fixture supplies cloud
through its rain top, and this density patch does not repair or conceal that
separate hazard. It needs a distinct correction and regression test.

Nc producer/storage conventions, optical LUT size authority and independent
physical accuracy remain separate open gates.
