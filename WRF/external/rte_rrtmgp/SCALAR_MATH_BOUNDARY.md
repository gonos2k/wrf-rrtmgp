# CPU scalar-libm boundary

On CPU builds, the solver, gas-optics kernel, and gas-optics frontend route
their `exp`, `log`, and `cos` calls through `mo_rte_scalar_math`. The helper is
a separate Fortran translation unit, compiled without IPO/LTO (`-fno-lto` for
GNU Fortran and `-no-ipo` for Intel Fortran). This keeps those calls scalar
when an enclosing array expression is evaluated for different column batch
sizes. It does not disable vectorization for other arithmetic in the kernels.

The aliases are guarded by `RRTMGP_CPU_ONLY`; accelerator source branches are
untouched and have not been validated by this CPU change. WRF's outer OpenMP
flags are also unchanged. GNU standalone verification compiled the helper
with `-O2 -ftree-vectorize -fno-lto`, compiled array callers with vectorization
enabled (including an LTO caller), checked the object symbols, and compared
all 24 `exp`/`log`/`cos` results from a 2-by-4 array bitwise against scalar
intrinsic calls. This is a focused compiler-boundary check, not a full RRTMGP
or WRF numerical validation.
