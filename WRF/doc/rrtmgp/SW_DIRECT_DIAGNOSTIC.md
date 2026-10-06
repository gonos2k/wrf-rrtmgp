# UDM SW direct-flux diagnostic

The WRF-facing UDM shortwave direct-flux fields retain the legacy diagnostic convention: they represent attenuation by the unscaled optical depth. The RRTMGP solver still uses its existing delta-scaled cloud optical properties for its flux and heating calculation. The added diagnostic does not feed back into the solver, so the solver's upwelling/downwelling fluxes, heating rates, and existing standalone adapter outputs remain unchanged.

For each g-point, the diagnostic initializes the top interface with the incident direct beam and attenuates downward with the raw extinction:

```text
Fdir(k) = Fdir(k+1) * exp(-tau_raw(k) / mu0)
tau_raw = tau_gas + mask * (tau_cloud + tau_rain_snow) + tau_graupel + tau_hail
```

The MCICA mask applies to native cloud and rain/snow extinction only. UDM frozen graupel and hail use uniform occurrence one and are added outside that mask, including for overlap mode zero. With no cloud, rain, snow, graupel, or hail, the diagnostic reduces to the existing gas-only direct beam. G-point direct fluxes are summed to broadband direct flux; the existing RRTMGP band mapping and the 12850–16000 cm⁻¹ half-visible convention produce VIS/NIR direct fluxes. WRF diffuse diagnostics are the solver's unchanged total downwelling flux minus the corresponding pre-delta direct flux.

The optional adapter outputs are all-or-none: broadband direct, clear direct, VIS direct, and NIR direct. Calls that omit them retain the prior interface and behavior. A selected SW capture with these outputs uses `RRTMGP_REPLAY_V9`, which records the input spectrum, gas/cloud/precipitation/frozen raw extinction, realized MCICA mask, and spectral mapping needed to reconstruct this diagnostic independently. Earlier replay versions remain unchanged; LW captures continue to use their existing versions.

This change restores the legacy meaning of the direct-flux diagnostic in the UDM path. It is not a claim that delta-scaled RRTMGP beam output is physically invalid, nor does it establish observational accuracy for any surface direct-beam product.

The focused standalone suite checks clear, cloudy, overlap-zero, and night behavior, optional-output group rejection, output shape rejection, and two-column independence. V9 captures are replayed independently for cloud, precipitation, and frozen G/H with overlap zero. A one-minute SCM check verifies captured direct-flux replay, broadband direct surface-history mapping, VIS/NIR-to-broadband closure, RA37 mode-zero parent comparisons, and RA4 bitwise preservation. Its initial-state-only scope and hash-pinned receipts are in [the SW direct runtime receipt](../../../validation/rrtmgp37/sw-direct-diagnostic/README.md); this is not long-forecast or observational-accuracy validation.
