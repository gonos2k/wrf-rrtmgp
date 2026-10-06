# WRF Shinhong `ccpp_kind_types` parallel-build dependency

This record demonstrates and fixes one actual Fortran module dependency in the WRF build graph. The original `WRF/phys/physics_mmm/bl_shinhong.F90` imports `ccpp_kind_types` (`USE` at source line 3), so its object must wait until `ccpp_kind_types.o` has produced `ccpp_kind_types.mod`.

`WRF/main/depend.common` is tracked and included by `WRF/phys/Makefile`. A repository search found no rule or tool in `WRF/tools`, `WRF/compile`, or the main Makefiles that regenerates this file. Before the change, its wrapper rule listed `ccpp_kind_types.o` and `physics_mmm/bl_shinhong.o` as sibling prerequisites of `module_bl_shinhong.o`; that does not order compilation of the two siblings under `make -j`. The dependency file already has direct `physics_mmm/...o: ccpp_kind_types.o` rules for adjacent MMM modules, but omitted Shinhong.

The branch adds only this prerequisite near those neighboring entries:

```make
physics_mmm/bl_shinhong.o: \
	ccpp_kind_types.o
```

## Reproduction

The checked-in `reproduce.sh` builds the original WRF source files with the original configured WRF Make rules and GNU Fortran flags. It uses a compiler shim that delegates every invocation to `/usr/bin/gfortran` and sleeps three seconds only before compiling `ccpp_kind_types.f90`. That timing perturbation makes the missing edge deterministic; it does not alter the Fortran inputs or compiler options.

Pass a configured WRF root containing `configure.wrf` and `tools/standard.exe`, plus a new output directory. The script refuses to use an existing output directory and preserves all generated logs and files there:

```sh
validation/rrtmgp37/physics-mmm-kind-dependency/reproduce.sh \
  /path/to/configured/WRF \
  /path/to/new/repro-output
```

It tests four real Make targets in isolated source copies: baseline and fixed `module_bl_shinhong.o` fan-out, plus baseline and fixed direct `physics_mmm/bl_shinhong.o`. The baseline cases are expected to fail with `Cannot open module file 'ccpp_kind_types.mod'`; both fixed cases must pass. The baseline dependency file is retrieved from parent commit `361c05ad36c149dc7e9d700fa80fc47ea8843d60`; the fixed case uses this branch's tracked file. The script copies only the Makefile and three relevant Fortran files into each case, then uses the configured tree for WRF preprocessing support.

## Recorded result

The original Make targets were run in scratch copies from the built WRF tree. Baseline wrapper fan-out failed with exit 2 while the delayed producer compiled; fixed fan-out passed with exit 0. Baseline direct-target compilation failed with exit 2; the fixed direct target passed with exit 0. The packaged reproduction script was also run successfully with the same four outcomes. Logs are retained under `logs/`, and `manifest.json` records their SHA-256 hashes along with source, configuration, compiler, and dependency-file identities.

This is a targeted Make-graph regression test, not a complete WRF physics build. No Fortran source changed, and no full WRF integration build is claimed here.
