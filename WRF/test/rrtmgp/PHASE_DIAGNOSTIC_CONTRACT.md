# Native phase paths and CU clipping diagnostics

These option37 diagnostics supply metrics for unresolved scientific questions without changing condensate, CF, radii, optics, seeds or radiation outputs. They do not validate occurrence assumptions, clipping accuracy, CU fallback sizes/shared sampling or experimental frozen G/H optics.

`RRTMGP_UDM_PHASE_PATH` reports native LIQ/ICE/RAIN/SNOW per LW/SW wrapper invocation and tile. Its denominator sums returned native grid paths after the existing native correction contract, including CF0 paths. It excludes CU accepted/rejected paths and G/H, and does not use in-cloud paths. Its numerator is the existing omitted grid-path sum. Positive totals emit rows even when omission is0; zero totals emit no row and have no defined fraction. Existing `RRTMGP_UDM_CF0_OMITTED` rows keep their format.

Fields are `native_grid_path_sum_g_m2`, `cf0_omitted_grid_path_sum_g_m2`, `cf0_omitted_layer_count` and `cf0_grid_path_fraction`. Kind8 diagnostic sums promote the builder's existing host REAL values, recovering no lost input precision. The ratio describes CF0 builder exclusion, not all optical exclusion under overlap0. It differs from the positive-CF eligible denominator of LUT clipping.

CU clipping summaries require nonzero overlap, consistent with native LUT summaries. At overlap0, accepted/rejected/negative-source CU input summaries remain; no CU clipping row is emitted. Overlap1–3 retain their existing coordinates, bounds and weights. CU clipping rows remain conditional on positive clipped path; an absent row alone is not an accepted-path denominator.

CU population/clipping and new native rows include supplied `domain`, `radiation_step`, `source_time_seconds`, `overlap`, and wrapper `tile_i`/`tile_j` bounds. The driver already supplies `id`, `itimestep` and `xtime*60.`; no argument or process-wide counter is added. Absent standalone-call context is `UNAVAILABLE` and cannot authenticate a call join. Source seconds retain host clock precision and are not a fabricated UTC timestamp. Edge wrapper bounds may include boundary indices outside the clipped mass loop; consult the recorded mass bounds for coverage. Under OpenMP, match explicit context rather than adjacent lines; rank identity comes from the rank log.

Sums count material again across radiation calls. They are layer-grid paths in g/m², not area-integrated kilograms, time integrals, unique atmospheric layers or precipitation rates. LW and daylight SW are separate sample families; there is no MPI reduction or flux-error interpretation.

The defensive `UNAVAILABLE` handling in the extracted context block does not relax the full wrapper's existing mandatory domain/calendar seed-input checks. Audit step and time may be absent; a missing required seed input can still be rejected before the diagnostic block is reached.

Existing reporting gates remain: a present nonnegative seed override suppresses summaries; a negative override or absent argument permits reporting. No generic trace-active suppression is added. SW remains subject to its daylight branch; RA4 does not enter option37 diagnostic branches.

Focused tests are `udm_phase_path_statistics` and GNU `phase_diagnostic_wrapper_contract`. The latter compiles actual wrapper reset, accumulation, CU gate, context and row-writing blocks with bounds checking and NaN initialization. It checks zero omission/path, repeated invocation resets, native/CU/G/H separation, overlap0–3, safe absent context, rows exceeding512 characters, seed reporting, legacy4 gating and explicit parser schemes. Counterfactuals remove the gate, contaminate the denominator with CU paths, poison resets or shorten the buffer; each is detected. These tests do not establish full-model preservation or scientific accuracy.
