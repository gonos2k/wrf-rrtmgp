# PR10 UDM runtime evidence receipt

Consolidated from saved agent receipts on 2026-10-02. The serial restart receipt in its original scratch directory was augmented with the resolved executable SHA-256 and path-provenance evidence; run artifacts remain in their original scratch directories.

## Serial restart continuity

The restart cases use `build/pr-wrf-rrtmgp/WRF/main/wrf.exe` (SHA-256 `5f616b6e0bb39e7a097bb0ce68200d5260b04532e92f85f2451f37f22f7bbb66`). All four case `wrf.exe` symlinks resolve to that binary. Process-level executable hashing was not captured at launch. The binary timestamp (21:58 local) precedes the restart run (run directories created 22:11 local); the three tracked observer edits in that checkout are timestamped 22:32 local, after the run. This supports that they were not incorporated into the tested executable. Process-level executable hashing was not captured, so invocation identity is established by the run receipt path/hash, matching case symlinks, and unchanged executable file rather than a process audit. Control and mixed UDM27/RA37 runs used 10-second steps, 10-second history, `radt=0.5`, and one-minute restart output. Each continuous run covered 120 seconds; a separate run resumed from its actual 19:01 restart file and covered the remaining 60 seconds.

At the restart checkpoint, all 201 fields common to the restart and continuous history matched exactly. Across the six shared postrestart history times from 19:01:10 through 19:02:00, all 210 variables matched bitwise in both cases. `ACSWDNB` and `ACLWDNB` preserve the 19:01 accumulator values, and the first 10-second recurrence after restart and every later interval match exactly. There are no differing array values; L-infinity and L2 differences are zero. The report separates expected restart metadata differences (`START_DATE`, the `ISLAKE` sentinel, and the history `Time` dimension length).

## OpenMP SCM

The GNU 13.3 OpenMP executable is `build/omp-wrf-udm-contracts/WRF/main/wrf.exe` (SHA-256 `4b706c7dcb8ee52d83173224cc4bfcfef558b166ab279b0ec0e1471a8f9ba6f1`). For both control and mixed cases, the seven-record OMP1 and OMP2 SCM histories are bitwise identical across 210 common history variables. The paired runs used identical input and namelist hashes; capture and audit environment settings were unset.

## Real-data MPI and hybrid smoke

`real.exe` initialized the NCAR WRF developer test for 2010-06-11 00:00 UTC from the supplied six-hourly metgrid files. The model configuration uses MP27, RA37/RA37, `use_mp_re=1`, a 60-second timestep, and a 10-minute radiation interval.

| Run | Result |
| --- | --- |
| MPI1 / OMP1 | Completed from 00:00 through 00:10 UTC |
| MPI2 / OMP1 | Completed; at 00:10 all 203 numeric history variables matched MPI1 with zero nonfinite values and zero maximum absolute difference |
| MPI2 / OMP2 | Completed; matched MPI2 / OMP1 bitwise at 00:00 and 00:10 across all 203 numeric fields |
| MPI2 missing-coefficient case | Deliberate missing gas coefficient produced the expected WRF fatal and MPI abort; exit code 1, no timeout or hang |

The MPI1, MPI2/OMP1, and hybrid runs share identical `wrfinput_d01`, `wrfbdy_d01`, and namelist hashes. The receipt records hashes for both executable variants, run histories, metgrid inputs, and rank logs.

The real-data integration evidence covers ten minutes only. Although `real.exe` initialized a full 24-hour window, no completed 24-hour 37 forecast is covered by these receipts; these results do not establish long-forecast readiness.

## Files

- Consolidated JSON with binary, input, restart, history, namelist, and log hashes: [runtime-receipt.json](runtime-receipt.json)
- Reusable history/restart comparison tool: [compare_restart.py](compare_restart.py)
- Serial restart source receipt: [restart-comparison.json](restart-comparison.json)
- OpenMP source receipt: [omp-runtime-result.json](omp-runtime-result.json)
- Real-data MPI source receipt: [realdata-manifest.json](realdata-manifest.json)
- Hybrid MPI2/OMP2 source receipt: [hybrid-mpi2-omp2-receipt.json](hybrid-mpi2-omp2-receipt.json)

Run the comparison tool as:

```sh
python compare_restart.py continuous-history.nc restarted-history.nc \
  --checkpoint wrfrst_d01_YYYY-MM-DD_HH:MM:SS \
  --checkpoint-time YYYY-MM-DD_HH:MM:SS
```

It compares each history field by matching physical `Times`, reports per-variable L-infinity and L2 differences, and compares the checkpoint fields with the continuous history at the requested time. Omit both checkpoint options for a history-only comparison.
