# Stock LBLRTM coupling and sampling controls

This follow-up to PR114 records three new stock LBLRTM v12.17 solves and one stock LNFL v3.2 NOCPL generation. All use the same captured 45-layer UDM state, full continuum/CIA (ICNTNM=1), seven line species and four cross-section species. No WRF, RTE, compiler, production source or workflow is changed. The prior ICNTNM=0 arm is not part of this factorial.

| Coupling | SAMPLE | OD samples | Negative samples | Minimum OD |
|---|---:|---:|---:|---:|
| on, prior PR114 | 4 | 63,838,065 | 21,712 | -4.884429085432753 |
| on | 8 | 127,948,502 | 40,770 | -4.880947884913931 |
| NOCPL | 4 | 63,838,065 | 2,391 | -0.0009924067060697163 |
| NOCPL | 8 | 127,948,502 | 1,774 | -0.00005739147942124939 |

**All four physical reference checks remain FAIL.** None is clipped, accepted by a relaxed tolerance, or promoted to the physical reference. Finite outputs and child RC0 are execution evidence. Changing SAMPLE alters the adaptive spectral mesh and sample count; counts on different meshes are not accuracy scores. SAMPLE controls test sensitivity, not a direct replacement of the cubic interpolation formula.

At the exact same layer21 panel/grid point (666.3964444444449 cm-1), the original optical depth -4.884429085432753 becomes +4.4625484239488955 under NOCPL. The larger negative is coupling-dependent in this setup. This does not identify a particular molecular signed term or explain the +0.6806384666588787 W/m2 held WRF 4/37 flux residual. NOCPL removes physical line-coupling information and is a diagnostic control, not a recommended forecast setting.

## Input and source controls

The SAMPLE8 TAPE5 differs from the full-continuum baseline in exactly one byte: offset193, 4→8. NOCPL uses the baseline LBLRTM TAPE5 unchanged and changes the generated TAPE3: its LNFL TAPE5 differs only in offsets145–149 containing NOCPL. The fourth arm combines these two controls. Saved readback verifies all38 staged inputs, executable identity, and all45 pressure/temperature/broadener headers. Actual child RC receipts precede parser/numeric inspection. Every new solve, full parser and independent raw OD reader reports RC0.

The first NOCPL preparation review rejected a missing post-run staged-input check before any model invocation. The corrected V2 runner used a fresh run-v2 directory; its execution/postflight receipts are authoritative. The unrun V1 draft and its rejection remain private and the review rejection is included here.

## Raw line-record comparison: failure retained

The strict comparator found648464 paired ordinary lines and128015 removed coupling records. Centers, strengths, air/self widths, energies, molecular/isotope codes, temperature exponents, shifts, additional-broadening data and speed data are byte exact. **Additional-broadening flags differ at5702 ordinary lines**, so the strict byte comparison stays FAIL. No return code is inferred for the original comparator from an agent's later capacity error.

A separate saved-reader/source check shows all5702 differences are -654321 versus zero in the first component at a block's first slot. LNFL's `EQUIVALENCE(addflag(1,1),lstw2)` and `lstw2=-654321` store a word-count sentinel there. Removing companions changes which ordinary line occupies the first slot. ADDFLAG is `(7,250)`: the original contiguous28-byte layout is correct, not an array-stride defect. The other six flag components agree. Both LNFL decks omit EXBRD, and all four executed LBLRTM logs have IBRD=0. OPROP's broadening corrections require IBRD>0; its unguarded O2 self-shift test reads component7, which is zero in both files. Thus consumed line fields agree for this specific setting while the raw-byte FAIL is retained. This conclusion does not cover EXBRD/IBRD>0.

## Reader correction and reproduction

The additive raw-reader successor fixes closest-to-zero-negative initialization and the all-positive-file/run case. Original raw outputs and strict failures remain preserved. Three small fixtures exercise these reporting branches; they do not establish solver accuracy. Full parser reports and private spectra are pinned by hash; compact45-layer summaries and raw proofs are included. `analyze_negative_od.py` and the comparison scripts require the staged private assets at their recorded workspace paths. Runners and `verify_saved_controls.py` are archived executed sources, not directly runnable from their packaged locations: the latter computes ROOT from its own parent directories and refuses to overwrite its existing report. Its original private execution path is `build/udm37-lblrtm-negative-control-readback-v1/verify_saved_controls.py`. Use the saved receipts for this result; a relocated reproduction needs an explicitly reviewed path/output adaptation, not an unrecorded rerun. Fixed-format TAPE5 padding is intentional and must not be stripped.

AER line lists, generated TAPE3, coefficient datasets, OD spectra and executables are not redistributed. Further work must resolve independent-reference nonnegativity and spectral/flux correctness before using it to decide whether WRF 4/37 differences are expected physics or port errors. No physical gate is closed here.
