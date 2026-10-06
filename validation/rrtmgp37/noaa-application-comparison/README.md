# NOAA application comparison for UDM27–RRTMGP37

Evidence date: **2026-10-06**. This package compares public NOAA/NWS application evidence and pinned HAFS/CCPP source contracts with the **unmerged WRF candidate at `79a58e27cddb8d737d81c925c299a868a86596d6`**. Remote main was separately checked at `1a2cd8d11993a5fb829a5103c0775ff69f820244` (PR7). The candidate and main are not interchangeable.

## Application evidence

* **HAFS v2.2:** [NWS SCN26-76](https://www.weather.gov/media/notification/pdf_2026/scn26-76_HAFSv2.2.pdf), issued September 9, announces RRTMG→RRTMGP with an effective date of **October 13, 2026**. On the evidence date this is scheduled, not yet effective. Skill improvements concern a multi-component upgrade, not radiation alone.
* **GFS v17:** [NWS PNS26-29](https://www.weather.gov/media/notification/pdf_2026/pns26-29_Science_for_GFSv17.pdf), issued April 15, specifies Thompson–Eidhammer microphysics and **RRTMG improvements**. A development suite named `GFS_v17_p8_rrtmgp` is not proof of an operational RRTMGP switch.
* **CCPP evaluation:** [DTC's 2022 assessment](https://epic.noaa.gov/wp-content/uploads/2022/07/3.-MRW-Li.pdf), slides 10–11, describes global and SCM comparisons (LASSO, TWP-ICE, ARM AWARE), a duplicated cloud-fraction temporal-average bug that led to a fix, and remaining cloud/radiation heating differences. These historical findings motivate separating implementation faults from physics and sampling; they do not attribute this WRF candidate's residual.

## Source comparison

The pinned public branch chain is HAFS `6ac5af973faf2d9bb72208c4292bb8362f1308d4` → forecast/UFS `9ad9fab316e87dbb547a924f073f8a2221717fda` → UFSATM `8f3a2ecd5b0b6ecaf6331356fb6fa3aed917b229` → CCPP `9c64d49ba93e06ba2e7e0e6f63d8edd707ac1c51` → RTE `763cc15f7a6d2d4f4893f83460cdd81209b6fce7`. This authenticates public source, **not a deployed binary or release-tag identity**. Blob URLs and byte hashes are in the two JSON reports. The five CCPP wrapper/setup/mapper files were also checked against the Git blob IDs at the exact pinned CCPP commit. Independent review caught an earlier draft that mixed files from a different CCPP revision; the corrected V5 comparison uses the HAFS-pinned files and retains the same qualitative conclusions.

| Contract | Public HAFS/CCPP source | Unmerged UDM27 WRF candidate |
|---|---|---|
| Microphysics | HAFS-v2 suite uses Thompson; mapper also has GFDL branches | UDM27 only |
| Condensate/fraction | Scheme-specific mapping; GFDL unified branch folds graupel into snow, Thompson branch does not; `precip_frac=cld_frac` | UDM-native radii with WRF-specific cloud/precipitation contracts; no inference of NOAA UDM parity |
| Gases | SW/LW wrappers explicitly expose six gases; additional linked-object defaults require separate audit | Six SW gases; eleven LW species including explicit dry N2 and optional four CFC profiles |
| Dry gas columns | Wrapper supplies pressure/temperature/gas concentrations, no explicit native dry-mass argument | Explicit native dry-mass prefix; pressure/VMR extension; explicit `col_dry` |
| Constants | Linked-engine initialization not established by wrapper alone | WRF initialization passes g=9.81, cp=1004.5, molar mass=0.028966 kg/mol |
| LW angles | Explicit clear-sky optimal-angle or Gaussian control; all-sky Gaussian control | Calls omit angular keywords; linked RTE default applies |
| SW optics | Cloud delta-scaling call is commented in pinned wrapper | Cloud delta-scaled once; CCPP precipitation already scaled separately |

Ice-size and roughness contracts remain separate scientific questions. The inspected public mapper passes its microphysics ice-size field directly; this does not resolve the UDM metric versus LUT metric. Exact HAFS runtime roughness selection was not established. No UDM-specific adapter was found in the bounded source inspection; this is not proof of absence in internal or other NOAA systems.

## Interpretation and follow-up

NOAA's application provides a useful comparator, not automatic validation of UDM27. Source policy differences are **not yet causes of a measured flux difference**, and copying them is not an accuracy proof. Compare identical held states with matched gas tables, amounts, cloud/precipitation optics, roughness, angular treatment, and sampling before attributing residuals. Keep diagnostic accumulation checks separate from physical accuracy.

This is documentation and source inspection only. No model, RTE, opacity calculation, or observation validation was run for this comparison. Existing numerical evidence and unresolved physical gates are unchanged; no production source or CI workflow is altered.
