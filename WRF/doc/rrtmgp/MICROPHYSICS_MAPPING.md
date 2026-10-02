# WRF microphysics inputs mapped to RRTMGP cloud paths

This note describes the current `use_rrtmgp` path in the WRF longwave and shortwave wrappers, `RRTMG_LWRAD` and `RRTMG_SWRAD`. The species passed to `rrtmgp_build_cloud_inputs` are the wrapper's prepared `qc1d`, `qi1d`, and `qs1d` arrays at the builder call. They are not necessarily copies of the model's original prognostic arrays: shared phase handling and scheme-specific overrides run first.

## Units and builder contract

The wrapper supplies condensate mixing ratios in kg/kg, layer pressure thickness `pdel` in hPa, and gravity in m/s². `rrtmgp_build_cloud_inputs` converts a grid-box mixing ratio (q) to a grid-box water path with

```text
q * dp_hPa * 100 / gravity * 1000   [g/m²]
```

For positive cloud fraction, it divides each species path by that fraction to produce the in-cloud `lwp`, `iwp`, and `swp` passed to the radiation adapter. For a clear layer containing condensate, the wrappers enable `allow_clear_condensate`; the builder returns zero cloud paths and reports the excluded grid-box path from its three input species. The debug record is therefore based on `qc1d + qi1d + qs1d` at the builder call, after common phase handling and any scheme override. It is not a reconstruction of every raw prognostic water field.

The builder accepts only finite, nonnegative condensate mixing ratios. In the RRTMGP branch, the legacy `max(0., q)` repairs are guarded by `.NOT.run_rrtmgp` and do not run. Negative condensate is an input error; no epsilon or small-negative tolerance is applied.

The conversion, strict validation, and clear-grid omitted-path calculation are implemented in [`rrtmgp_build_cloud_inputs`](../../phys/module_ra_rrtmgp_input.F#L27).

| Prepared input | RRTMGP path | Size input |
| --- | --- | --- |
| `qc1d` (liquid cloud water) | `LWP` | `gp_rel` |
| `qi1d` (cloud ice) | `IWP` | `gp_rei` |
| `qs1d` (snow) | `SWP` | `gp_res` |
| `qr1d` (rain) | Not passed separately; it contributes only if the common cold-phase branch moves it into `qs1d` | None |
| `qg1d` (graupel) | Not passed to the cloud-path builder | None |
| `qv1d` (water vapor) | Gas input, not cloud condensate path | None |

## Common phase handling before the builder

Both wrappers initialize the local condensate arrays, read fields whose `F_Q*` flags are present and true, then apply common phase logic before calling the RRTMGP builder. When `F_QI` is absent or false and `warm_rain` is false, a layer colder than 273.15 K transfers `qc1d` to `qi1d` and `qr1d` to `qs1d`, then zeros `qc1d` and `qr1d`. If `warm_rain` is true, that frozen transfer is skipped: rain remains `qr1d`, which the builder does not accept as a separate input. This is the existing WRF phase branch, not extra mass inferred by the RRTMGP mapping.

The code also applies `QS3D` after that generic branch when `F_QS` is true. Read the phase behavior together with the scheme-specific overrides below; the builder sees the final local arrays.

## Scheme-specific mapping

| Scheme family | Prepared fields reaching the RRTMGP mapping | Mapping consequence |
| --- | --- | --- |
| WSM3 (`mp_physics=3`, `wsm3scheme`) | Registry has neither `QI` nor `QS`. The common no-`F_QI` branch transfers subfreezing `QC` to `qi1d` and `QR` to `qs1d` when `warm_rain` is false. | Warm `QC` maps to `LWP`; transferred cold `QC` maps to `IWP`; transferred cold rain maps to `SWP`. |
| WSM5 (`mp_physics=4`, `wsm5scheme`) | Registry provides `QI` and `QS`, so both are read directly and the common no-`F_QI` fallback is skipped. | `QC` maps to `LWP`, `QI` to `IWP`, and `QS` to `SWP`. |
| Ferrier/Aligo high resolution (`mp_physics=5`, `FER_MP_HIRES`; often called “MP5”) | Registry provides `QI` but no `QS`. The generic no-`F_QI` cold transfer is skipped because `F_QI` is present; the later Ferrier override assigns combined frozen `QI3D` to `qi1d`, zeroes `qs1d`, and reads `QC3D`. | Liquid maps to `LWP`; combined ice-plus-snow `QI3D` maps once to `IWP`; `SWP` is zero. |
| ETAMPNEW (`mp_physics=95`) | Registry provides `QS` but no `QI`. The common no-`F_QI` transfer runs first; then the wrapper's special `F_QC .AND. .NOT.F_QI .AND. F_QS` block selects its RRTMGP branch and restores `qc1d=QC3D`, `qi1d=0`, and `qs1d=QS3D`. | `QC3D` remains liquid, including supercooled cloud water, and maps to `LWP`; `QS3D` maps wholly to `SWP`. No 10/90 split occurs in RRTMGP. |
| Thompson | `qc1d`, `qi1d`, and `qs1d` retain their distinct species fields when available. | Cloud water maps to `LWP`, cloud ice to `IWP`, and snow to `SWP`; use the explicit radii when the corresponding `has_reqc`, `has_reqi`, or `has_reqs` flag is set. |
| P3 | Its special legacy block would move `QI3D` into `QS1D` and zero `QI1D`, but the block is guarded by `.NOT.run_rrtmgp`. | In the RRTMGP path, `QI3D` remains `qi1d` and maps to `IWP`; the legacy P3 ice-to-snow optics conversion is not applied. |
| Ferrier/Aligo advected variant (`mp_physics=15`, `FER_MP_HIRES_ADVECT`) | Same explicit override as `FER_MP_HIRES`: `qi1d=QI3D`, `qs1d=0`, and `qc1d=QC3D`; `QI3D` stores combined frozen water. | Combined frozen water maps once to `IWP`; `SWP` is zero. |

Option names in comments are not reliable substitutes for Registry identities: WSM3 is option 3, WSM5 is option 4, Ferrier/Aligo `FER_MP_HIRES` is option 5, its advected variant is 15, and ETAMPNEW is option 95. In particular, “MP5” is ambiguous in review shorthand. The wrapper's legacy comment labels the 10/90 block “MP option 5”, but its guard checks optional-field flags and `.NOT.run_rrtmgp`; for RRTMGP, the alternative branch in that same block explicitly restores ETAMPNEW's original liquid/snow categories after the generic cold transfer. The generic transfer therefore describes WSM3 here, not ETAMPNEW. The Ferrier override applies only to its explicit constants and variants.

## Radius units and fallback

The default `gp_rel` and `gp_rei` values come from the wrappers' diagnosed `reliq` and `reice` arrays, which are in micrometres (`relcalc` and `reicalc`). Thompson's `re_cloud`, `re_ice`, and `re_snow` fields are in metres and are converted with `*1.e6` when their `has_re*` flag is set. The CAM-MGMP `lradius` and `iradius` inputs are already in micrometres and are copied without conversion.

`has_re*` is a scheme capability flag, not a per-cell diagnosis-validity flag. WRF initializes the fields to `RE_QC_BG=2.49e-6 m`, `RE_QI_BG=4.99e-6 m`, and `RE_QS_BG=9.99e-6 m`. On a wet layer with positive cloud fraction, an explicit source exactly equal to its BG value uses the already prepared WRF host fallback (`recloud1d`, `reice1d`, or `resnow1d`); all other source radii are preserved. This retains the host liquid land/ocean and temperature-based ice diagnosis without restoring RRTMG mass reduction, its cloud-fraction floor, or its general size clamps. A real microphysics radius exactly at the BG floor is indistinguishable from the initial placeholder and follows the same fallback contract.

`gp_res` defaults to `gp_rei`, the ice-radius proxy. It is replaced by `re_snow*1.e6` only when `has_reqs` is set. CAM-MGMP sets `gp_res=gp_rei` as well. Thus a missing explicit snow radius does not imply that `re_snow` was read or that the snow radius is a separately diagnosed snow size.

The Registry identities and fields are declared in [`Registry.EM_COMMON`](../../Registry/Registry.EM_COMMON#L3073) (WSM3 3, WSM5 4, Ferrier 5/15, ETAMPNEW 95). The relevant implementation is in [`RRTMG_LWRAD`](../../phys/module_ra_rrtmg_lw.F#L11584) and [`RRTMG_SWRAD`](../../phys/module_ra_rrtmg_sw.F#L10048). The common phase/read branches are near LW lines 12055–12158 and SW lines 10664–10763; the “MP option 5” block with legacy split and RRTMGP ETAMPNEW restoration is near LW line 12131 and SW line 10736. Ferrier/Aligo overrides are near LW line 12150 and SW line 10750. Radius selection and the builder call are near LW lines 12667–12684 and SW lines 11221–11236.

These statements document the source-derived mapping contract; they do not claim that the planned phase-specific runtime matrix or capture/replay validation has run.
