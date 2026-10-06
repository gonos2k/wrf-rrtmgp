# UDM first-step CCN initialization contract

The option-37 path initializes `QNN_CURR(ims:ime,kms:kme,jms:jme)` once, before the OpenMP tile loop, when the diagnosed-CF pointers are associated and `itimestep == 1`. It passes `ccn_preinitialized=.true.` into UDM so each tile skips the legacy full-memory reset. The extracted code covers the allocation/halo bounds used by the driver.

The optional UDM argument remains backward compatible: absent means `initialize_ccn=.true.`, so non-option-37 callers retain the legacy first-timestep reset. The test extracts the actual nested driver initialization guard and actual UDM optional reset block from the current production files, injects those source blocks into a minimal Fortran harness, and compiles that generated source. It checks the associated-CF false path, missing required driver optional, skip-flag omission counterfactual, storage/halo initialization, both tile updates, and timestep-2 state.

Run `python3 test_udm_ccn_startup.py`. The test compiles with GNU Fortran at `-O0` and `-O2` and runs each binary with one and two OpenMP threads. Tile advancement in the fixture is a small deterministic stand-in; it does not execute or validate the UDM microphysics itself.
