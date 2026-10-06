# Actual WRF ZZ persistence follow-up

This additive snapshot follows the parent directory's earlier NOT_RUN archive.
Production commit 474c4af4 / tree56a693a5 was built using GNU13.3, REAL32, CMake
MPI/OpenMP. PR head eb376a0 has the same selected production sources; its general
CI8/8 and CMake installed-consumer/SCM runs succeeded. Raw CI and full local
outputs remain referenced by their pinned receipts and are not redistributed here.

MPI4 × OpenMP2 paired UDM4/37 continuous13-hour controls returned0/reaped.
Actual12-hour checkpoints now store the ordered nonspatial INTEGER32 seed.
Independent saved-file comparison found all228/231 history variables over14
hourly records and664/667 common checkpoint variables byte-exact against the
previous binary, including all variable and global attributes.

On copied checkpoints only, seed values were set to -1..-660. Two bounded
12→13-hour model runs returned0/reaped, read and re-saved the exact seed values
and order, and matched every228/231 history variable and variable attribute
at13:00 to the continuous controls. START_DATE differs(12:00 vs00:00) and is
explicitly recorded. Independent review read the saved outputs without reruns.
Original checkpoints and earlier failed evidence remain unchanged.

This is inactive I/O persistence(multi_perturb=0), not active stochastic
acceptance. RA37 uses experimental frozen mode1/batch32/CU1. It does not close
Nc/population/PSD/LUT, RFMIP strict, LBLRTM negativeOD, or physical accuracy gates.
The execution manifest separates source, toolchain, executable, runtime-library,
input/coefficient, policy and result identities. Physical acceptance stays false.
