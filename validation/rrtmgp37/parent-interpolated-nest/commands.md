# Commands and artifact hashes

The exact run used the reviewed runner and original RRTMGP worktree. `ROOT` below is `/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP` in the recorded environment.

```sh
python3 "$ROOT/build/udm-nested-domain-plan/v2/run_nested.py" --repo "$ROOT"
python3 "$ROOT/build/udm-nested-domain-plan/v2/run_nested.py" --repo "$ROOT" --execute --case-dir "$ROOT/build/udm-nested-domain-plan/case-v2"
python3 "$ROOT/build/pr-parent-interpolated-nest/validation/rrtmgp37/parent-interpolated-nest/summarize_histories.py" \
  --case-dir "$ROOT/build/udm-nested-domain-plan/case-v2" \
  --output-dir "$ROOT/build/pr-parent-interpolated-nest/validation/rrtmgp37/parent-interpolated-nest/results/summary-v2"
```

The run command launched `mpiexec -launcher fork -iface lo -n 4 .../wrf.exe` with the pinned MPICH Hydra 4.2 installation. The receipt records the full command and environment. The read-only preflight completed immediately before launch and verified 117 pins, the loader environment, MPICH version, and 512 MiB stack availability.

Run evidence hashes:

| Artifact | SHA256 |
| --- | --- |
| Executable (hash only; binary not included) | `176f589d657ca87df670cef3429d7474e674f3e44445eb7886aed871e36bef8f` |
| Frozen optics table (hash only; table not included) | `8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583` |
| Namelist | `83b5e85c423d441a14d7393844eed3ec0a75735c736fd8c6b0cfe5ef37d5827a` |
| Current guarded runner | `b4ce7e9b750a4c8927c7da2181cca1fc60a7248a608e939135e4ac5a19bcb45f` |
| Parent-reviewed runner before stack adjustment | `b5ad570d33393f1d7bf8d24eb09192167a2ce1af363c79f6d944fd12671bc4d5` |
| Original pre-review runner snapshot | `052171fb0f6c80d86e0a5dd4c2ba3ef650a117a50b020979e25c4e44ab1d95fd` |
| Resource-only diff | `ad6caa9256cd9f82c2c1791ea5fef384e1c8161e119bc3d8f94387a74b87ada9` |
| Execution receipt | `6cae0b65e8eae2bbb177076c5ee2a047c55aaabae10cc2f2118f098c2963555e` |

The SHA256 manifest `artifact_sha256.json` covers each archived evidence file except itself. The history inventory records hashes for all 20 original NetCDF histories; those files are not copied here. To compare against them, pass the original case directory to `verify_evidence.py --case-dir`.
