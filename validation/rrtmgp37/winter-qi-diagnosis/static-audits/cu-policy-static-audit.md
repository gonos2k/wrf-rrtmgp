# Conditional UDM27 + radiation37 convection-input response

The measured hook bracket is native QI=0 at end-of-step and negative QI at the next radiation builder. The CU component hook is being compiled; **QI_CU/product attribution is not yet measured**. This report proposes no source edit, model run, tolerance change, or operational workaround. It uses the actual scratch e7c97 source and local CCPP primary code, pinned in pins.json. It supplements the radiation-preprocess audit; previous failures and reports remain intact.

If components confirm native nonnegative QI and a negative KF diagnosed cloud-ice contribution, the safest immediate37-only contract response is a separate KF/CU diagnostic and refusal before augmentation. That identifies the invalid source correctly and retains the existing native UDM contract. A zero-bound sanitizer for only the diagnosed convective component is a possible subsequent, explicitly reviewed physics policy. Existing conventions provide precedent for nonnegative radiation condensate; they do not establish that this particular KF+UDM27 component policy is physically validated.

## Source facts and primary local conventions

Active case: MP27, CU1/KFETA, cu_rad_feedback=true, ICLOUD1, PBL1, AERCU_OPT0, SHCU0 (replay-v8 namelist.output). physics_init1223–1226 maps KF feedback to ICLOUD_CU2. radiation_driver1252–1259 saves caller-associated incoming QI;1371 sets CF_CU=CLDFRA_DP+CLDFRA_SH;1376 adds QI_CU*CF_CU.3550–3557 restores the saved QI after the radiation calls. The diagnosed convective mixing ratio is distinct from native UDM QI and from RQICUTEN (a tendency).

| Primary local source | Exact convention | Applicability limit |
| --- | --- | --- |
| WRF module_ra_rrtmg_lw.F12159–12163 | Copies combined QI3D, then MAX(0,QI1D) only for .NOT.run_rrtmgp | This is existing RA4 behavior; it cannot distinguish native versus CU invalid mass. |
| WRF module_ra_rrtmg_sw.F10762–10766 | Same combined-input copy and legacy MAX(0) | LW/SW policy must agree if a37-only response is later adopted. |
| WRF module_ra_rrtm.F1962–1966 | QI1D=QI3D then MAX(0,QI1D) | Other radiation scheme; not a KF component convention. |
| WRF module_ra_cam.F567/570 | MAX(0,combined ice specific humidity); may include snow | Different species aggregation and scheme. |
| WRF module_ra_goddard.F1390–1399 | Copies each radiation hydrometeor with MAX(0,species); comment mentions advection | Comment is generic source rationale, not evidence that winter negativity came from dynamics. |
| WRF module_cu_kfeta.F1346–1349 | QI_KF=QICE without an output positivity bound | No KF-specific sanitizer was found here. DTFRZNEW2854–2855 and CONDLOAD2923 are algebraic candidate sign paths, not measured producers. |
| WRF KF2285–2296 | Computed finite fractions have MAX(.01,xcldfra), then MIN(.2/.6); rejected branches set0 | No intended finite negative CF assignment found; actual finite/fraction validation is still necessary. |
| CCPP GFS_rrtmgp_cloud_mp.F90 GF354–377 | Processes positive qci_conv only; nonnegative phase split; MAX(0,LWP/IWP)361–362; separate convective radii367–372 | Grell-Freitas, not KFETA. Positive gate skips processing nonpositive inputs; output args are INOUT, so this alone does not prove clearing their previously initialized outputs. |
| CCPP same file SAMF496–508 | Processes positive cnv_mixratio only; MAX(0,cnv_mixratio)500; separate convective LWP/IWP and default radii503–505 | SAMF, not KFETA or UDM. |
| CCPP radiation_clouds.f1543–1565 | MAX(0,total native+convective liquid/ice path); supplies default convective-dominated ice radius in1560–1565 | Total-path sanitizer, different model/species/phase partition. |

The local CCPP checkout is clean at3e6660c6df54e95a0871e990c2294dd397ae3860. Its RRTMGP interface exposes separate stratiform, convective and PBL paths/radii (arguments139–154) and separately bounds their radius tables276–289. These precedents are primary implementation evidence, not a physical oracle or a demonstration that they fix this KF source.

## Options if the measured sign bracket confirms invalid KF ice

1. **Separate invalid-CU refusal (recommended first change).** Under radiation37, validate saved native hydrometeors using the existing native contract before any feedback can hide a negative. Validate CU components and their fractions for finite/range validity. Refuse an optically participating negative KF cloud-ice contribution with a new CU-specific reason, reporting native QI, QI_CU, DP/SH, product, augmented QI, coordinates, step, units and kind. Keep the native error distinct from the CU error. Do not relabel this as a UDM/dynamics failure. This is the smallest defensible classification fix and changes no accepted optical input. It does not complete the winter forecast.

2. **Reject KF feedback as unsupported for37.** A configuration refusal before integration is clearer than attributing augmented mass to native UDM. It also rejects all positive KF feedback states and turns an implicit existing capability into an explicitly unsupported configuration. Native-size provenance and convective cloud occurrence then have a clear boundary, but this does not satisfy a goal of supporting this case. Do not silently disable cu_rad_feedback; that changes the requested physics. Choose this only if the project decides not to support diagnosed convective populations yet.

3. **Sanitize diagnosed KF radiation condensate only (conditional future policy).** If measured components show a valid native state, finite nonnegative fractional area, and negative QI_CU, define the convective radiation ice as MAX(0,QI_CU) before its multiplication/addition. Zero is the physical nonnegative boundary, not a tuned epsilon. Limit the branch to37; preserve the native QI save/restore, stored QI_CU and all RA4 arithmetic. Maintain separate raw/rejected convective mass and water-path counters. Reject nonfinite/out-of-range fractions and invalid native inputs rather than clip them. Positive CU behavior, occurrence fractions and particle sizes require separate stated policies; do not silently change those while fixing a negative component. This sanitizer can let a run proceed, but it is a substantive radiative-input policy requiring explicit review and evidence.

A product-only MAX(0,QI_CU*CF_CU) is insufficient: it could conceal a negative fraction or two negative factors. Clipping the combined QI1D is also insufficient: positive CU can hide invalid native QI, and negative CU can remove valid native ice. Avoid broad hydrometeor clipping or increasing gp_negative_limits.

The sanitizer is **not numerically equivalent to legacy combined clipping**. For native2e−8 and a grid-mean CU term−1e−8, legacy MAX(0,total)=1e−8 whereas component sanitation gives2e−8. With native0 and a negative CU term both give0. RA4's current result remains unchanged only if its branch is literally unchanged; that does not establish37 optical parity after the new policy.

## Native contract remains unchanged

module_ra_rrtmgp_input.F238–286 initializes strict negative limits to0, or uses the host's existing six declared limits. It only corrects -limit<q<0 and refuses equal/exceeding magnitudes. Wrapper12858–12866 passes gp_negative_limits and records native negative corrections. Any future37 feedback handling must preserve these limits and accounting and check native mass before augmentation, rather than treat the augmented mass as native input. A shared helper may apply the same existing checks without running optical solvers twice. Native, convective, augmented, and rejected paths require explicit provenance in captures/replay; the old capture schema must not silently reinterpret its RAW_QI label.

## Radius and occurrence are separate physical scope

The wrapper's native UDM effective radii are mandatory (LW11986–11988). With AERCU_OPT0, driver EFIS/EFIG radius weighting1380–1425 is inactive, yet the augmented mass is passed with native re_ice (gp_rei12747) and re_cloud (gp_rel12736). A positive diagnosed KF cloud population is not automatically described by the native UDM particle distribution. Fixing negative CU mass neither validates that radius assumption nor establishes a convection occurrence/overlap policy.

CCPP's separate convective radii/defaults demonstrate explicit population treatment; its defaults must not be imported here without justification. Supporting positive KF feedback with native UDM radii is a distinct scientific-policy decision even if existing summer anchors pass. A clear native column with only positive CU ice is an especially useful bounded test of this provenance; it must not be marketed as a domain-wide physical bound.

## Review gates for a later implementation

Before any response, require actual signed components to reproduce the observed derived negative from the saved native state; account for the secondary QI_BL branch1435–1454. If the components do not close the bracket, continue diagnosis instead of implementing a CU fix.

For a classification-only patch: meaningful tests cover invalid native ice masked by positive CU, valid native/invalid CU, invalid/nonfinite fraction, two negative factors, CF0 inactive contribution, and both LW/SW error attribution. Accepted positive states must be bitwise unchanged; corresponding RA4 must remain bitwise unchanged.

For an explicitly approved sanitizer: additionally test finite negative CU of different magnitudes with native0 and positive native ice; exact zero-bound behavior; positive-CU identity; rejected raw path accounting with native dry mass; no stored-state mutation; no RA4 branch change; mode0/1, padding, repeated tiles, and LW/SW agreement. Strict replay must receive both native and derived populations and verify declared sanitation provenance rather than weaken the native negative tests. A bounded winter rerun would test runtime consequences, not independently validate KF cloud-size physics or establish climate validity. No such tests/builds/runs were performed in this audit.

## Exact native-zero radius branch and positive-CU scope

UDM module_mp_udm.F:102 sets reimin=5.01e−6m. Before diagnosis it initializes every re_qi to this minimum:466; it publishes bounded re_ice:480. In udm_mp_effective_radius, native rqi=MAX(1e−12,qi*rho):3718; native qi=0 makes rqi equal this floor and the loop skips its radius diagnosis at3737. The untouched minimum is therefore a valid native zero-mass placeholder, not a radius diagnosed from KF cloud ice. No new size threshold is proposed.

LW12747 and SW11297 use this native re_ice for augmented radiation QI. The optional existing fallback requires exact RE_QI_BG equality at LW12751/SW11301; module_model_constants.F:63 defines that background as4.99e−6m, distinct from UDM's5.01e−6m minimum. Thus adding positive CU mass to a zero-native-QI layer does not trigger a CU-specific fallback.

| Native ice / participating CU ice | Current37 input behavior | What remains unresolved |
| --- | --- | --- |
| Native0 / CU0 | UDM minimum radius exists but no ice mass from these terms | No CU ice optical population is present. |
| Native0 / positive CU | Combined ice mass positive; UDM zero-native minimum5.01µm used | Radius has no KF PSD provenance; positivity sanitation cannot fix that meaning. |
| Positive native / positive CU | All combined mass uses native UDM radius | A single native radius is not automatically a mass-weighted or extinction-weighted mixture of populations. |
| Valid native / negative CU | Current raw combined input may reduce native mass or become negative | Classification/sanitizer options above are conditional on measured components. |
| Invalid native / positive CU | Combined total can appear nonnegative | Preaugmentation native validation is necessary to preserve the native contract. |

The root trajectory receipt `build/udm-winter-qi-hook/root-replay-v8-trajectory-readback.json` SHA45c6c8e9a27ea8e86add1bafd08cdf4f747fa2ff0284ea2e569df51035a2f33f records RAD_PRE_BUILDER171 QI−5.623554244493789e−8, native-radius input5.01000022268272e−6m and CF0.20000000298023224. Its UDM_POST radii are unavailable (-999 sentinel), so do not describe them as measured prior-stage radii. The actual wrapper radius matches the static minimum branch; the receipt does not measure QI_CU or its product. These numeric input values establish neither positive-CU occurrence across the domain nor optical-depth/flux magnitude.

The audited KF feedback write is inside ICLOUD1 and ICLOUD_CU2. ICLOUD_CU1 has a separate unweighted QI_CU addition:1304–1308 for other schemes; ICLOUD2 does not execute the KF ICLOUD1 feedback branch. A future KF-scoped response must not silently apply an assumed convention to these other paths. With AERCU_OPT>0 the driver has an existing EFIS/EFIG weighting branch; the current case is AERCU0, and switching aerosol flags to obtain that branch is not a justified size-policy solution.

Generic replacement of re_ice for positive CU-only layers would break the claim that all input ice sizes are native UDM diagnoses. If supporting KF clouds is chosen, retain native UDM optics with their own mass/radius and define CU optics/size/overlap explicitly (or state and validate a reviewed effective-mixture assumption). This is a broader science change than the minimal invalid-input classification or zero-bound component response. No generic radius, CCPP default, empirical threshold, or sensitivity-derived magnitude is recommended here.
