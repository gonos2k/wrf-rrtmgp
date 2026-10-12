# Local validation

2026-10-12, parent main `c1ebe4a5e95a20398921d377bcf44ddb14703698`.

- WRF: 10 actual process launches, all TERMINAL / RC0, no timeout. Initial campaign 5; final eligible campaign 5. No Fortran compilation or ideal execution. Final evidence is one manufactured SCM trajectory observed at four columns, not five independent meteorological cases.
- Final actual NetCDF readback: 4 OFF/ON pairs × history/restart = 8 file pairs. Whole file bytes, every variable byte array, dimensions and attributes equal. History has 8 times through 70 s; restart is at 60 s.
- Final raw/input/result capture: 4 columns × LW/SW = 8 phase-calls, source time 60 s, radiation step 7, supplied UDM CF step 6. Full native source Q and QNC to history mapping, native path partition, radius/LUT-coordinate and omitted-layer optical linkage replayed.
- Current and retained source snapshot: all 5,910 tracked production files match after reversible observer blocks are removed. Retained binary matches the existing build receipt; executable and selected library file pins unchanged before/after runs. Actual loader logs are saved; external library hash readback is after execution, not a claim of in-process full-library-byte capture.
- `verify_saved.py`: RC0, PASS_SCOPED, production_accepted=false.
- New boundary suite: 7 tests, PASS in normal isolated stdlib execution and Python -O. No assert-dependent checker validation.
- Existing acceptance integration: 11 tests PASS, including the new 7-test replay, existing PR166 native-window and PR167 contract replay.
- Existing execution-identity boundary suite: 16 tests PASS. These are manufactured schema tests, not final policy approval.
- Acceptance index CLI: RC0, index_integrity=PASS, production_accepted=false, production source subset unchanged.
- Python compilation and staged source/document whitespace check: RC0.

CI will replay stored bytes; it does not run WRF or independently decode NetCDF variable definitions. Full input/state/physics approval, number/PSD/occurrence contracts, RFMIP strict, LBL reference and final policy forecast remain unresolved as recorded in the unchanged seven closure conditions.
