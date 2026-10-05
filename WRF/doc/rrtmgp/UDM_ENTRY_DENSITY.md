# UDM27 call-entry density diagnostic

`WRF_RRTMGP_CAPTURE_UDM_ENTRY_DENSITY=1` adds one selected-column packet
immediately before the UDM call in the initialized RRTMGP37 `have_udm_cf`
branch. The variable must be unset/empty or exactly `1`. It requires an existing
`WRF_RRTMGP_CAPTURE_DIR` and uses the existing physical-column selectors.
Capture is restricted to serial execution. Normal forecasts leave this diagnostic
unset; the disabled branch constructs no diagnostic array arguments.

The V1 packet records actual call-entry TH, PII, pressure, QV, passed DEN,
six condensate categories and three number fields, call constants, native level
bounds, domain/grid/timestep identity and the optional source clock. Raw finite
negative moisture/number values remain visible; the observer does not clip or
change them. The native UDM implementation and its call arguments are unchanged.

`DEND_REEVALUATED_PRECALL_KG_M3` is a **default-REAL reevaluation** of
`(P/T - DEN*RV)/(RD-RV)` after `T=TH*PII`. `DEND_ORIGIN=1` identifies this
observer calculation. It is not a measurement of UDM's private local DEND,
which can evolve later in the call. No packet field is called total density.

The stdlib analyzer compares the simultaneous input state to two explicitly
named EOS hypotheses:

* dry-air density: `P/[T*(RD+RV*QV)]`;
* dry-air-plus-vapour density: the preceding result times `(1+QV)`.

It reports raw residuals for both, checks the packet's source arithmetic within
a fixed default-REAL operation bound, and can join the same-call post-UDM radius
packet by exact domain/step/grid/level/clock identity. Post-call temperature and
moisture can change; they must not replace call-entry values in the EOS check.
The analyzer currently accepts the reviewed GNU default-REAL32 target only.
Packet arithmetic agreement is a diagnostic contract, not a physical accuracy
criterion or an independent proof of the pressure identity.

Run protocol tests with:

```sh
python3 -I -S WRF/test/rrtmgp/test_udm_entry_density.py --self-test
python3 -I -S WRF/test/rrtmgp/test_udm_entry_density_trace.py --wrf-root WRF \
  --receipt-dir build/entry-density-trace
```

The SCM runner separately compares capture off/on and archived source-equivalent
ordinary UDM4 and UDM37 histories. Fresh builds, actual model return codes,
executable/input/source pins and saved packet analysis belong in the accompanying
validation receipt. Ordinary UDM4 does not initialize this RRTMGP diagnostic;
its regression run leaves all capture variables unset.

This instrument does not change the host density, sedimentation density,
activation-number convention, effective-radius closure or LUT size convention.
A physical correction requires the runtime measurements and a separate review
of every affected UDM use of density.
