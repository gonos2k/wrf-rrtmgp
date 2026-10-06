# PR60 active-CU pre-run review

**PASS** — read-only integrity check of the fresh `em_real` build and staged case. No REAL/WRF executable was invoked.

The source snapshot has 6805 tracked entries and re-hashes without missing files, content mismatches, or symlink-target mismatches. It is pinned to PR60 head `b66bd3724890c3d3a8d415e221a748309f93597e` and the worktree is clean. Comparing tracked WRF Fortran against the immutable d05 source-v4 snapshot found exactly two production differences: `module_ra_rrtmg_lw.F` and `module_ra_rrtmg_sw.F`; the remaining difference is the new standalone test file.

The recorded build is `BUILD_PASS` (return code 0, no timeout, successful footer) using GNU Fortran 13.3.0, MPICH 4.2.0 ch3:sock dm+sm, NetCDF 4.9.2 and the pinned configure. Source/dependency inventories match before/after. `wrf.exe` SHA256 is `6378764a2119e3475a4ec8b80cce20f5434739c428dc7fb401c899bcdeb309ed` and `real.exe` SHA256 is `632b2c3ff4cef46773dd50087289f8bf0d9d552b979ef94062b8d390beb9d54e`. Both runtime-library sets resolve all 51 recorded libraries with verified paths and hashes.

The staged case is `/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/udm37-pr60-active-cu-current-build-v1/runs-v1/case-pr60-cu-active`. Its `namelist.input` SHA256 `be55e9b8fdd6eb6494b3642d5cae8226b31be8dd509ea4fd8121a8baa704e47d` exactly matches the accepted `long-b1` template. It has 97 unbroken runtime links, expected `wrfinput_d01` and `wrfbdy_d01` SHA256 values match the stage receipt, and `wrf.exe` resolves to the newly built executable. The namelist selects MP27, RA37/37, active CU in domains 1 and 2 (`cu_physics=1,1,0`), and frozen optics. The only non-link regular file is `namelist.input`; stage receipt says `STAGED_NOT_RUN`, with zero model invocations.

Detailed pins and checks are in `review.json`.
