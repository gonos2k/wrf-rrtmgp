# NetCDF ZZ backend receipts

These copied terminal receipts record the local source review, backend fixture,
current serial regression and fresh full MPI/OpenMP build. Their original paths
and output hashes remain in the JSON. The binaries, full compiler logs, NetCDF
outputs and referenced local artifacts are not redistributed by this directory;
its index authenticates these copied receipts, not an executable archive.

The real backend comparison preserves an initial MPI transport timeout and its
additive loopback continuation. Parent rejection and candidate O0/O2 serial/MPI
wrapper success are distinct results. The MPI wrapper is not WRF module_io.
The reusable current-source serial check uses eight direct children and writes
four variables with ordered dimensions. CI regenerates it from the checkout.

Actual WRF checkpoint persistence/readback is NOT_RUN at this snapshot. The
fresh full build does not launch a forecast. The proposed readback test uses
multi_perturb=0 and a sentinel in a copied checkpoint; it cannot approve active
stochastic forcing, Nc/PSD/LUT physics, or observational accuracy.
