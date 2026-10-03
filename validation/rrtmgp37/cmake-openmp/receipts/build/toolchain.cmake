# https://cmake.org/cmake/help/latest/module/FindMPI.html#variables-for-locating-mpi
set( MPI_Fortran_COMPILER "mpif90" )
set( MPI_C_COMPILER       "mpicc" )

# https://cmake.org/cmake/help/latest/variable/CMAKE_LANG_COMPILER.html
set( CMAKE_Fortran_COMPILER "gfortran" )
set( CMAKE_C_COMPILER       "gcc" )

# Our own addition
set( CMAKE_C_PREPROCESSOR       "/lib/cpp" )
set( CMAKE_C_PREPROCESSOR_FLAGS   )

# https://cmake.org/cmake/help/latest/variable/CMAKE_LANG_FLAGS_INIT.html
set( CMAKE_Fortran_FLAGS_INIT    " -w -fconvert=big-endian -frecord-marker=4" )
set( CMAKE_C_FLAGS_INIT          " -w -O3" )

# https://cmake.org/cmake/help/latest/variable/CMAKE_LANG_FLAGS_CONFIG_INIT.html
set( CMAKE_Fortran_FLAGS_DEBUG_INIT    "" )
set( CMAKE_Fortran_FLAGS_RELEASE_INIT  "" )
set( CMAKE_C_FLAGS_DEBUG_INIT          "" )
set( CMAKE_C_FLAGS_RELEASE_INIT        "" )

# Project specifics now
set( WRF_MPI_Fortran_FLAGS  ""   )
set( WRF_MPI_C_FLAGS        ""   )
set( WRF_ARCH_LOCAL         "NONSTANDARD_SYSTEM_SUBR"    )
set( WRF_M4_FLAGS           "-G"      )
set( WRF_FCOPTIM            "-O2 -ftree-vectorize -funroll-loops"       )
set( WRF_FCNOOPT            "-O0"       )
set( WRF_LINK_FLAGS         "" )
