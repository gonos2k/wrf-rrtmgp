# Current-source UDM27 same-state radiation audit

**Result: three serial forecasts completed and the scoped no-feedback checks passed.** This is a one-hour, all-sky, single-column comparison on a pinned October 7, 2016 restart state. It is not a radiation-accuracy or forecast-readiness result.

All arms ran the same production RA37 forecast from the same 12:00 UTC restart and forcing. `OFF` disabled the scratch audit; `ON_native4_0` and `ON_native4_1` enabled scratch RRTMG4 calls at the live RA37 state. Each arm returned RC 0 and completed without timeout. The independent terminal review confirms that the two output histories (231 variables each) and final restart (667 variables) are byte-identical across all three arms, including full schema and attributes. That is the no-feedback result: enabling the audit did not change the production RA37 trajectory in this experiment.

The scratch comparison used one preselected all-sky column (`i=24, j=55`) at six observed times from 12:00 through 12:50 UTC. At each time it captured one LW and one SW call, with 128 deterministic seed values per call. The campaign contains 12 calls per arm and 36 raw/input/result files per arm. The complete OFF capture set is included as deterministic gzip files with original and compressed hashes; the execution receipt records matching hash triplets for both ON arms. No WRF output files or executable binaries are bundled. The CSVs contain 564 selected records plus 564 duplicate aggregate records per arm; the latter are not additional observations. Seed values describe the configured deterministic sample and do not provide IID confidence intervals.

`native4_0` versus `native4_1` is a bundled RRTMG4 counterfactual at the same production-37 state. It changes effective radii, ice/path mapping, and optics together, so the comparison cannot isolate one of those effects. Production remains RA37 in both ON arms. The OFF/ON comparison is the no-feedback control; it is not a coupled forecast comparison between production radiation configurations.

Production used MP27 with RA37 in both bands, `use_mp_re=1`, ice roughness option 1, frozen-optics mode 1 and the experimental table SHA256 `ebeafb9746164d5414a45eab4061c5c855f0f91e92be77003b3829722514fe6a`. The timestep was 60 seconds, radiation interval 10 minutes, and CU interval 5 minutes. The run restarted at 12:00 UTC, elapsed hour 36 of the parent 48-hour forecast. These settings define this experiment; they do not establish accuracy for the default production optics configuration.

The selected column was dark/opaque: operational SW surface-down flux was 0.38–1.02 W/m² across the six calls. That absolute flux is distinct from the paired-seed-mean RA37-minus-RRTMG4 SW surface-down contrast, which ranged from −0.14 to −0.73 W/m² for `native4_0` and −0.02 to −0.08 W/m² for `native4_1`. SW_DIRECT was zero in these samples. The small surface contrast does not imply small vertical or TOA contrasts: paired-seed-mean `TOA_UP` differences (RA37 minus RRTMG4) ranged from about −10.31 to −18.70 W/m² for `native4_0`, and −11.19 to −22.52 W/m² for `native4_1`. An independent numeric derivation places the largest absolute RA37-minus-native-radius-RRTMG4 paired-mean heating differences near 16039 Pa at layer 31: +5.255 K/day in SW at step 2211 and −4.976 K/day in LW at step 2161. Switching RRTMG4 from generic to native radius changes paired-mean heating by up to −0.600 K/day in SW and +3.285 K/day in LW. These remain unresolved optical/heating contrasts, not evidence that either result is accurate or normal. This is one all-sky column over one hour, not a domain or regime estimate. No clear-sky comparison was run.

The executable was freshly built from exact source commit `1cb6920a43d8ba10ecfa179487839f9df7022cb4` (PR70) with GNU serial configuration. PR70 radius-input-context changes are present in the compiled source, but this campaign is not a dedicated radius-input diagnostic test. The frozen-optics path is experimental; this campaign does not validate its physical accuracy. Build, stage, authorization, run, analysis, and independent review receipts are included. The original execution receipt records three model invocations and all wrapper capture identities. The independent reviewer performed no build, forecast, or numerical re-analysis.

## Contents and verification

`provenance/` contains the pinned source/build identity, build and runtime receipts, staged namelists, and authorization. `analysis/` contains both CSVs, their analyzer outputs, the pairing analysis, its script, and the independent numerical review plus derivation script. `captures/off/` contains the canonical OFF captures in reproducible gzip form. `logs/` contains the three rank-0 serial logs. `review/` contains build and terminal review receipts plus the terminal review script. The portable `verify_artifacts.py` checks an exact file manifest, capture decompression hashes and receipt clocks, run roster, no-feedback comparison gates, CSV row pairing and contrast algebra, and terminal-review pins. `tests/test_verify_artifacts.py` confirms extra-file, changed-clock, and changed-CSV-algebra tampering is rejected. It does not need WRF, NetCDF libraries, or the original large forecast outputs.

Run the package check and focused tamper controls:

```sh
python3 verify_artifacts.py
python3 tests/test_verify_artifacts.py
```

The verifier covers included artifacts only. External model inputs, the built executable, and linked libraries remain identified by hashes in the included receipts and are not bundled.
