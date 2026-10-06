# Frozen-optics restart validation plan

This scratch-only plan is for the same mode-1 WRF configuration as `build/udm-frozen-runtime-mpi/case-mode1`. It does not edit that 24-hour case. The only model-ready directories are separate children of this plan directory.

## Proposed sequence

The first segment starts from the same `wrfinput_d01` and `wrfbdy_d01`, with `ra_lw_physics=37`, `ra_sw_physics=37`, `rrtmgp_udm_frozen_optics=1`, the same frozen table, `time_step=60 s`, and the same four-rank MPICH executable. It runs 00:00–12:00 and requests a restart every 720 minutes. The second segment starts from `wrfrst_d01_2010-06-11_12:00:00`, runs 12:00–13:00, then compares its 13:00 output against the continuous run's 13:00 output.

The current continuous output confirms the comparison clock: `Times=2010-06-11_13:00:00`, `ITIMESTEP=780`, and `XTIME=780.0` minutes. With `DT=60 s`, the checkpoint target is `Times=2010-06-11_12:00:00`, `ITIMESTEP=720`, `XTIME=720.0`. The actual checkpoint fields will be validated when that file exists.

Current logs show four MPI ranks arranged 2×2. WRF uses one tile per rank with 1D-Y tile strategy: rank 0 `(i=1..145,j=1..95)`, rank 1 `(i=146..290,j=1..95)`, rank 2 `(i=1..145,j=96..190)`, rank 3 `(i=146..290,j=96..190)`. The driver asserts the same rank grid and bounds in both segments.

The boundary file's `md___thisbdytime...` records run from 00:00 through 18:00, while `md___nextbdytime...` extends through 2010-06-12 00:00. Together these metadata cover the planned 12:00–13:00 restart segment and the 24-hour endpoint. The boundary hash is pinned in `preflight-plan.json`.

## Commands

Inspect current hashes and clocks without preparing or running:

```sh
python3 build/udm-frozen-restart-plan/run_mode1_restart_trial.py --inspect
```

Prepare the two isolated directories and namelists only:

```sh
python3 build/udm-frozen-restart-plan/run_mode1_restart_trial.py --prepare
```

Run both WRF segments only when explicitly authorized later:

```sh
python3 build/udm-frozen-restart-plan/run_mode1_restart_trial.py --execute
```

`--execute` verifies the recorded executable, production-source, input, table, namelist, and continuous-output hashes before running. It rechecks and records those immutable hashes after each segment and in a `finally` receipt, including failure exits. It validates the checkpoint clock and rank decomposition, then writes `restart-output-comparison.json` and `restart-run-receipt.json` under this scratch directory.

The comparator checks the expected timestamp, all dimension names/lengths/unlimited flags, every variable name/shape/dtype/value, every variable attribute, and every global attribute. Numeric fields use exact equality (`rtol=0`, `atol=0`); no variables are ignored. Non-finite numeric values fail. Array/dimension/time differences are reported separately as dynamics results; metadata differences (including legitimate run-control attributes such as `SIMULATION_START_DATE` or restart settings) are listed explicitly and do not get mislabeled as dynamics divergence. The overall exact-match result remains false when metadata differs. Array differences include count, maximum absolute difference, and first differing index. No tolerance is chosen in advance to conceal restart divergence.

## Current status

The isolated restart trial completed. The checkpoint clock was verified at 12:00, and the restart segment completed at 13:00. The exact comparator found all 54,643,036 numeric values across 204 variables equal and finite. It separately reports one metadata difference (`START_DATE`, continuous 00:00 versus restarted 12:00), so the overall exact-match result is false while the numerical dynamics comparison passes. All 21 immutable asset checks passed after each segment and finally. `comparator-self-test.json` compares the continuous 13:00 output with itself; it verifies comparator coverage, not restart continuity. The active 24-hour frozen case remains untouched.
