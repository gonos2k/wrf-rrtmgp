# Ordered nonspatial NetCDF fields

`ISEEDARR_MULT3D` is a two-dimensional restart field with `ZZ` memory order:
its axes are `bottom_top` and `num_pert_3d`. They are not horizontal tile
coordinates. Both the rank and the supplied axis order must survive NetCDF
definition, transfer, and readback.

After fixing the Registry subgrid flags, all MPI ranks reach this field's
writer call consistently. A completed restart file still omitted the field:
the NetCDF backend reported `BAD MEMORY ORDER |ZZ|` during definition and
`VARIABLE NOT FOUND` during transfer. A completed file and aligned calls do
not establish successful storage of every registered field.

The backend now recognizes `ZZ`/`zz` as rank two. Dimension names and extents
retain their incoming order; the layout has no zero-length horizontal axis.
Integer and real transfers use the existing identity transpose mapping.
The double-to-REAL4 path uses the same mapping. `reorder` canonicalizes this
specific order to uppercase `ZZ`, which prevents the lowercase transpose
branch from reversing two nonspatial axes. Other accepted and rejected
memory orders keep their existing branches.

The generic I/O rank helper also recognizes rank two. Its existing replicated
field policy remains: the monitor performs backend I/O and reads are
broadcast. This change does not turn nonspatial dimensions into distributed
X/Y coordinates or introduce a horizontal gather. The caller must supply
consistent replicated field state.

## Focused regression

The test compiles the actual `wrf_io.F90` and `field_routines.F90` with their
CPP/M4 includes, then calls the external NetCDF APIs. Only the WRF diagnostic
sink is stubbed. An ordered 3-by-5 integer sentinel checks type, both dimension
names and extents, and every value after write/read. REAL4 and double-to-REAL4
controls exercise the real transfer paths. Uppercase and lowercase `ZZ` must
work; an unrelated `qq` order must remain rejected. Two distinct time records must append to an unlimited Time dimension and
read back without aliasing. Stored REAL4 is also read through the DOUBLE API;
an invalid read order must be rejected before a valid read still succeeds.
The generic rank and case helpers are selected verbatim from `module_io.F`
and executed in the same fixture. O0 and O2 use bounds checking. No radiation solver or WRF forecast is invoked.

The Fortran inquiry reports `(vertical_k, independent_n, Time)`; C/Python sees
the conventional reversed NetCDF order `(Time, independent_n, vertical_k)`.
Preserved order means the two nonspatial axes retain their respective names,
extents and value indexing in each API view, not identical dimension tuples
between Fortran and C/Python.

With GNU Fortran, NetCDF Fortran development files, CPP and M4 installed:

```sh
python3 WRF/test/rrtmgp/test_netcdf_zz.py WRF \
  --workdir build/netcdf-zz --output build/netcdf-zz/receipt.json
```

Use a new work directory. The receipt retains source/fixture hashes, commands,
actual return codes and logs. Optional MPI fixture execution tests monitor
backend calls plus a fixture broadcast; it does not execute `module_io.F`.
Actual WRF checkpoint storage and restart consumption require separate model
tests. Inactive `multi_perturb=0` cases can establish storage/readback and
ordinary forecast continuity; they do not approve active stochastic forcing
or radiation accuracy.
