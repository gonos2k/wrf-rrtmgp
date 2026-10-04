# UDM37 CPU column-batching performance evidence

The terminal 12-arm campaign completed with status
`PASS_BENCHMARK_DATA_COMPLETE_NO_PERFORMANCE_CLAIM`. It ran three sequential,
interleaved blocks at batch sizes 1, 32, 64, and 128, using one frozen GNU CPU
build, one 40-minute case, MPI4/OMP2, and the same inputs. Each arm returned
zero, passed case quality validation, and produced five 10-minute history
files plus its 40-minute restart checkpoint. Immutable postflight passed.

Each batched arm matched that block's batch-1 output exactly across six output
files: five history outputs with 209 variables each and one checkpoint with
653 variables. Raw bytes, decoded values, and file metadata matched.
Comparisons across repeated blocks also passed exactly. No numeric tolerance or field exemption was used. This is the prerequisite for reading
these timings as paired observations.

| Batch | Mean launcher wall (s) | Paired batch/B1 launcher ratio, median [range] | Mean rank-0 main sum (s) | Paired batch/B1 main ratio, median [range] |
|---:|---:|---:|---:|---:|
| 1 | 66.99 | 1.000 [1.000, 1.000] | 53.69 | 1.000 [1.000, 1.000] |
| 32 | 54.99 | 0.826 [0.800, 0.837] | 40.98 | 0.761 [0.759, 0.771] |
| 64 | 57.36 | 0.850 [0.835, 0.884] | 42.52 | 0.792 [0.790, 0.794] |
| 128 | 61.67 | 0.904 [0.882, 0.975] | 46.09 | 0.861 [0.853, 0.861] |

Ratios are batch elapsed divided by B1 elapsed within each block; values
below 1 indicate lower observed elapsed time for that batch in this test. The
three paired samples and their raw times are retained in `result.json`. The
summary is descriptive: it reports medians and ranges for three blocks, not a
formal significance test or a general speedup guarantee.

Launcher wall time covers MPI launch through all-rank exit. Rank-0 main timing
is the sum of the 40 `Timing for main` records. Neither measure isolates RTE,
gas, cloud optics, or allocation time. The host exposed 72 logical CPUs; all
four ranks had the full CPU set available rather than a pinned subset. Load is
recorded before, at launch, and after every arm in the JSON artifact.

The receipt records `benchmark_models=0` despite 12 model invocations and 12
validated arm records. The count in this report follows the explicit invocation
and arm records; the receipt value is retained rather than corrected. This
measurement applies only to the pinned GNU build, case, and MPI4/OMP2 setup. It
is not an accelerator result, an RTE-only measurement, or an accuracy result.

The terminal receipt, frozen plan, runner, tests, source manifest, build result,
and executable hashes are recorded in `result.json`. Large model outputs remain
in the local artifact tree and are identified by their hashes in the receipt.
