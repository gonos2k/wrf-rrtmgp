# Winter radiation preprocessing: native and temporary cloud ice

The actual radiation driver contains a QI write between the existing native-state hooks and RAD_PRE_BUILDER. It temporarily augments the caller's hydrometeors for radiation, then restores them after radiation. Native POST_SPEC_BDY QI=0 therefore does **not** establish that prognostic QI became negative in dynamics or UDM. The observed negative wrapper input may be the augmented radiation state. Its actual signed producer remains unresolved until QI_CU and the cloud-fraction product are measured.

This is a read-only audit of `build/udm-winter-qi-hook/source/WRF`, Git e7c97ed661403b3922fcf752300c052611ef89cd, with scratch observer changes. Exact audited bytes are in pins.json. No model, reference call, build, or production edit was performed.

## Exact active path

The original namelist enables MP27, CU1, cu_rad_feedback=.true., ICLOUD1 and PBL1. Executed replay-v8 namelist.output confirms those and ICLOUD_BL1, AERCU_OPT0, SHCU_PHYSICS0. Generated frame/module_state_description.F:161 defines KFETASCHEME=1. module_physics_init.F:1223–1226 selects ICLOUD_CU=2 for KF with feedback enabled and publishes it via nl_set_icloud_cu:1274. module_first_rk_step_part1.F:481–482 passes that flag and grid%QC_CU/QI_CU; line444 passes QI=moist(...,P_QI) to radiation.

module_radiation_driver.F:881–887 declares qi as optional INTENT(INOUT). Its local automatic arrays include qi_save/qc_save:982, not a separate radiation-qi allocation. It saves incoming qi at1252–1259, then under ICLOUD1, PRESENT(CLDFRA_DP), and ICLOUD_CU2, defines:

```fortran
cldfra_cu(i,k,j)=cldfra_dp(i,k,j)+cldfra_sh(i,k,j) !1371
qi(i,k,j)=qi(i,k,j)+qi_cu(i,k,j)*cldfra_cu(i,k,j) !1376
```

The resolved CLDFRA calculation cal_cldfra1 at1357 reads QI (INTENT(IN),4190); it does not change it. The driver then passes this augmented QI as QI3D to RRTMG_LWRAD:2118. RRTMGP selects the same wrapper:2073 and USE_RRTMGP=true:2147. The eventual restore qi=qi_save:3550–3557 is after the radiation calls. A fatal builder return terminates before restoration. These temporary writes operate on the caller-associated QI argument but are intended to be undone; they must be distinguished from the prognostic state passed into radiation.

The wrapper initializes QI1D:12074, then copies QI3D at12159–12163. The legacy max(0,QI1D) executes only when .NOT.run_rrtmgp. All other QI1D assignments are guarded by no-QI layouts, Ferrier schemes, or .NOT.run_rrtmgp; they do not rewrite MP27 RRTMGP QI after the copy. RAD_PRE_BUILDER:12849 records this QI1D and builder12859 consumes it. Thus the hook named RAD_PRE_BUILDER is an adapter-input observation after driver feedback, not a native-state observation before radiation preprocessing.

## KF producer and sign checks

module_cumulus_driver.F:1021–1049 calls KF_ETA_CPS for KFETASCHEME, mapping QI_KF=QI_CU:1046 and deep/shallow cloud fractions:1044–1045. KF stores QI_KF=QICE(NK) directly at module_cu_kfeta.F:1346–1349; no positivity check protects this output assignment. This is a mixing ratio. RQICUTEN=DQIDT at513 is a separate tendency output, not the term added directly by radiation. Radiation precedes the current-step cumulus call (module_first_rk_step_part1 radiation293, cumulus1580 onward), so it consumes the stored prior available cumulus fields.

KF initializes fractions/QI_KF to zero at422–425 when it recomputes a column; NCA>=0.5*DT skips recomputation:409–412 and can retain existing fields. Rejected-cloud branches also zero fractions and QI_KF:1378–1381,1412–1415,1504–1507,1547–1550. All nonzero fraction assignments found are at2285–2296: lower MAX(.01,xcldfra), then upper MIN(.2,...) for shallow or MIN(.6,...) for deep. No intentional finite negative DP/SH assignment was found. This does not replace checking their actual values, initialization, or finite arithmetic.

Updraft QICE begins at zero:1094 and propagates through TPMIX2:1131–1132, freezing and DTFRZNEW:1157–1160, CONDLOAD:1177–1178, and detrainment mixing:1306. DTFRZNEW subtracts DQEVAP=QS−QU directly from QICE:2854–2855, without a lower bound. CONDLOAD final QICE expression:2923 and the direct QI_KF output have no positivity clamp. These are candidate algebraic sign paths, not an attribution that any particular calculation produced the measured negative QI_CU. TPMIX2:2776–2780 also redistributes a saturation deficit, and zeroes condensate in its exhausted branch:2807. Signed actual intermediate values would be needed to choose a lower producer after the feedback product is established.

## Other preprocessing and size scope

ICLOUD1 also has the PBL feedback branch:1435–1454, guarded by PRESENT(CLDFRA_BL/QC_BL), ICLOUD_BL>0, CLDFRA_BL>.001 and QI<1e−8; it may add QI_BL. Effective ICLOUD_BL is1, so capture these fields rather than assume the branch is inert. The active PBL is YSU1 (module_pbl_driver:1232); the QI_BL/CLDFRA_BL producer found is the MYNN5 call:1663/1727 and its Registry package3236. This narrows but does not numerically prove the inactive PBL cloud term. ICLOUD3 rewriting, BMJ QICONV, KFCUP and SHCU5 paths are excluded by this case's flags. F_QI2/F_QI3 extra ice belongs to other registered categories, not MP27.

The convective mass addition is not UDM's diagnosed native cloud-ice population. With AERCU_OPT0 the driver does not execute its EFIS/EFIG radius weighting:1380–1425. The MP27 wrapper uses native re_ice as gp_rei:12747 and re_cloud as gp_rel:12736. Therefore a later physical-policy review must distinguish combined radiation mass from native UDM radius provenance. No new size policy, clipping, negative tolerance, or optical behavior is proposed here.

## Narrow discriminating observation

At target i17,j58,k7 and the immediately preceding radiation calls, record qi_save/current qi before1376, QI_CU, CLDFRA_DP, CLDFRA_SH, cldfra_cu, the signed product, and qi immediately after1376. Also record QI_BL/CLDFRA_BL and qi immediately before the LW call to exclude1452. Preserve explicit native and derived labels, flags, step/time/rank and real-kind metadata. This distinguishes an incoming native negative, negative convective mass, negative fraction, and a later local write without asserting any of them beforehand. Parent owns any observer edit/run authorization; this report adds no hook.

## Evidence and correction scope

Root's retained replay-v8 independent readback authenticates the whole history SHA e3fa7be56062c640e52f66c73aaa0bd798d56f0809c1d4501e3b4a0c9c227e4c (21,298,954 bytes,225 variables,224 numeric,3 finite/unmasked Times). The previous HDF reader error was a postprocessing harness error, not file corruption. Exact history identity authenticates retained original history outputs; it does not independently identify the substep producer.

The prior `build/udm-winter-qi-source-audit-v1/report.md` remains untouched. Its search from POST_SPEC_BDY to driver entry did not include the driver hydrometeor feedback writes before the wrapper. The six hooks establish native QI zero at the end of steps168–170 and negative derived builder input at171, but that bracket includes this temporary feedback operation. Any inference that the negative necessarily came from prognostic dynamics/UDM is withdrawn. The actual lower cause is open pending the signed-product observation.
