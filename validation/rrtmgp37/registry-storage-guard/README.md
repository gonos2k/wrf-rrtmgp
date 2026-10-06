# Registry storage-kind guard

Classic Make compiles Fortran with USE_ALLOCATABLES while its Registry C tools
emit POINTER state fields. The former macro therefore cannot select the
ALLOCATED/ASSOCIATED checks for UDM restart diagnostics. Same-head whole-port
run [37443922887](https://github.com/gonos2k/wrf-rrtmgp/actions/runs/37443922887)
failed at six checks, before runtime.

Registry now emits inc/registry_state_storage.h from the same C compile-time
condition that generates state_struct.inc. input_wrf uses that numeric value for
all six checks; sentinel values, conditions and physics are retained. CMake
tracks the header as a Registry output. Existing global storage types are retained.

The focused test builds real isolated Registry tools in two modes, uses the
three actual diagnostic state entries and ARW dimensions, verifies declaration
and header coherence, then runs six source-selected Fortran guard fixtures
with deliberately differing macro definitions. It is not a full Registry or
full WRF runtime test. See [the report](LOCAL_VALIDATION.json).

```sh
python3 WRF/test/rrtmgp/test_input_wrf_udm_sentinel_kinds.py WRF \
  --workdir /tmp/fresh-storage-test --output /tmp/fresh-storage-test.json
python3 tools/register37.py --check
```

The earlier fixture preparation failures remain recorded. A fresh isolated
classic WRF build is separate and still in progress. The existing Make
module_state_description recipe masks some Registry failures and lacks direct
header object dependencies; arbitrary incremental/cleanup behavior is not
claimed. Physical reference and Nc/PSD acceptance remain open.

Terminal local follow-up: [VALIDATION_COMPLETE.json](VALIDATION_COMPLETE.json)
records fresh classic configure/build RC0, pointer fields plus storage header 0,
and one ideal plus one 60-second candidate37 startup SCM RC0. This is additive
to the earlier in-progress report. The three production correction files match
PR134 code head 06b88ba; the test harness changed after the local source snapshot,
so whole Git tree equality is not claimed. Remote correction CI remains separate.
