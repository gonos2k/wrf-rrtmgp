# Bounded same-call RRTMG4 optics export

The opt-in legacy optics exporter previously accepted only the Matthew comparison point: domain 1, i=24, j=55, step=2161, elapsed time=129600 seconds. A winter BON comparison needs another physical column and time. This patch permits one explicit target while retaining that historical target when no override is supplied.

Export remains confined to the serial selected-column audit's engine-4, native-radius, operational-seed call. The driver does not activate it around production radiation calls or ensemble calls. No solver formula, radiation input, result mapping, or physical default changes.

Set `WRF_RRTMGP_RRTMG4_EXPORT_DIR` to an existing output directory. To override the historical target, supply **all five** environment variables:

| Variable | Value |
|---|---|
| `WRF_RRTMGP_RRTMG4_EXPORT_DOMAIN` | Positive integer, at most 99 |
| `WRF_RRTMGP_RRTMG4_EXPORT_I` | Positive physical WRF i index |
| `WRF_RRTMGP_RRTMG4_EXPORT_J` | Positive physical WRF j index |
| `WRF_RRTMGP_RRTMG4_EXPORT_STEP` | Positive model step |
| `WRF_RRTMGP_RRTMG4_EXPORT_SECONDS` | Finite, nonnegative model elapsed seconds |

Partial overrides, empty values, integer overflow and malformed numeric values are rejected. Selection still requires both the step and elapsed time, with the existing 0.01-second matching allowance. Set the existing selected-column audit coordinates to the same i/j. A restart checkpoint's stored step/time is not proof of the next radiation-call time: obtain the actual call metadata before choosing a target.

Output names carry the selected domain, i, j, step and phase. `STATUS='new'` preserves the existing refusal to overwrite a capture. INPUT, CLOUD, GAS and RESULT stages must all be present before closing an active export.

For SW the driver passes the same `COSZEN` supplied as `xcoszen` to the wrapper. An export is not opened when this value is nonpositive, because the wrapper bypasses the entire shortwave calculation at night. Thus a nighttime LW capture does not require a nonexistent SW optics capture. A missing or nonfinite cosine on an otherwise selected SW export is rejected. MPI and multiple OpenMP threads remain unsupported for this diagnostic.

Run the focused check with:

```sh
python3 WRF/test/rrtmgp/test_rrtmg4_export_selection.py
```

The check compiles the actual exporter module in serial, DM_PARALLEL and OpenMP variants and runs 33 controls covering the historical target, every nonmatching coordinate, a new target, disabled export, all partial overrides, invalid values, day/night and nonfinite SW, capture collision, nested/incomplete capture, and parallel rejection. It verifies four exported stages and unchanged input arrays. This is an exporter check with **zero WRF, REAL or radiation-solver calls**; it does not establish physical accuracy or full-build success. The check is included in the standalone-column CI job.
