# BON background-gas contract audit

Read-only audit at current evidence HEAD `371a5f035b0390281362ffc44e9251dbbc0da10e`. Five relevant current source files match the executed f731 snapshot byte-for-byte. No source edit, compile, forecast or standalone solver was performed. `audit.json` pins source, actual LW128 coefficients, first legacy export and primary upstream examples.

The production `names_lw(10)` and matching reference `gas_names_lw(10)` contain H2O, CO2, O3, N2O, CH4, O2 and four CFC/CCl4 species; they omit N2 and CO. These lists are supplied at coefficient initialization. The pinned loader resolves each minor identifier through `identifier_minor → gas_minor`, tests that gas against the available host list, and removes unavailable intervals without error. It has no automatic background-N2 replacement. This establishes omission of the explicit N2 minor terms in both current production and the independent reference. Replay parity within that shared gas closure cannot detect the omission.

| Removed N2 region/interval | Gpoints (inclusive, 1-based) | GP physical band, cm⁻¹ |
| --- | --- | --- |
| Lower row 1 | 1–12 | 10–250 |
| Lower row 4 | 13–26 | 250–500 |
| Lower row 56 | 123–124 | 2390–2680 |
| Upper row 1 | 1–12 | 10–250 |
| Upper row 4 | 13–26 | 250–500 |

These cover 28 lower and 26 upper gpoint indices; lower/upper counts are not additive spectral bandwidth or flux fractions. The actual coefficient blocks contain nonzero values. Rows 1 and 4 use density scaling and a second N2 scaling-gas factor; lower row 56 uses density scaling without a separate scaling gas. Other foreign-continuum/broadener terms may still represent air implicitly: this finding must not be stated as absence of every physical N2-related effect.

The actual source list removes 13 of 60 lower and 11 of 34 upper minor intervals in total, including unprovided HFC/CF4 species. These counts describe loader selection, not a claim all omitted trace species should be nonzero in BON. CO's lower row 52, gpoints 115–119 (2080–2250 cm⁻¹), is also removed. Actual legacy WKL slot 5 is zero in all 45 layers; legacy setcoef later installs a tiny scaled floor `1.e-32_rb × COLDry`. The floor is source-derived and unexported, so the audit does not assert exact zero legacy CO optical effect.

Legacy's N2 implementation differs: bands 1 and 15 use N2 coefficient arrays with `colbrd` and minor-scaling factors. That broadener surrogate is not an exported explicit N2 VMR. Therefore enabling N2 in GP does not create termwise equivalence with legacy.

Primary pinned upstream evidence is the CCPP-embedded RTE all-sky example (CCPP commit `3e6660c6df54e95a0871e990c2294dd397ae3860`, embedded RTE commit `41c5fcd950fed09b8afe186dede266824eca7fd3`), which declares N2/CO and explicitly sets N2=0.7808 and CO=0. The pinned CCPP LW host main itself initializes a configurable gas list but sets only six ordinary gases; it does not establish a universal N2 host policy. RFMIP forcing protocols also use different lists. In the current API gas amounts equal `VMR × COLDry`; H2O is defined relative to dry air. Thus 0.7808 is a defensible predeclared diagnostic dry-column abundance from the primary example, not a measured BON profile or exact legacy broadener reconstruction. Do not substitute `1 − sum(provided gases)` without a separate justified mixture contract.

The narrow next experiment can hold the first BON legacy-dry diagnostic input, default angular transport, every other input byte, source, table and dependencies fixed, then add N2 to the diagnostic-only gas list and explicitly set 0.7808 before coefficient load. Retain realized interval/column and gas-optics/source sidecars with flux/heating responses. First establish the no-N2 baseline identity. Keep CO separate and keep the three-angle campaign's gas closure unchanged so attribution remains orthogonal.

Confirmed: an explicit background-gas contract omission shared by the current port and reference. Unmeasured: its flux contribution, whether it explains the retained +1.2498835111 W m⁻² residual, domain-scale importance, physical accuracy, or the final production policy. No production change or numerical run is authorized by this audit.
