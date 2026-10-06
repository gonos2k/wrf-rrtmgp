cmake_minimum_required(VERSION 3.20)
if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
  project(WRF_RRTMGP LANGUAGES Fortran)
endif()
file(GLOB rte_sources CONFIGURE_DEPENDS rte-frontend/*.F90 rte-kernels/*.F90)
file(GLOB rrtmgp_sources CONFIGURE_DEPENDS gas-optics/*.F90 rrtmgp-frontend/*.F90 rrtmgp-kernels/*.F90)
file(GLOB extension_sources CONFIGURE_DEPENDS extensions/*.F90)
add_library(wrf_rrtmgp STATIC ${rte_sources} ${rrtmgp_sources} ${extension_sources})
target_compile_definitions(wrf_rrtmgp PRIVATE RRTMGP_CPU_ONLY)
# Preserve a translation-unit boundary for the CPU scalar-libm wrappers.
# This is per-source (not a target-wide vectorization disable); array
# arithmetic in the RTE/RRTMGP kernels remains eligible for vectorization.
if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
  set_source_files_properties(rte-frontend/mo_rte_scalar_math.F90 PROPERTIES COMPILE_OPTIONS "-fno-lto")
elseif(CMAKE_Fortran_COMPILER_ID MATCHES "Intel")
  set_source_files_properties(rte-frontend/mo_rte_scalar_math.F90 PROPERTIES COMPILE_OPTIONS "-no-ipo")
endif()
set_target_properties(wrf_rrtmgp PROPERTIES Fortran_MODULE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/modules")
file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/modules")
target_include_directories(wrf_rrtmgp PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/modules>
  $<INSTALL_INTERFACE:include/rte_rrtmgp>
)
if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
  target_compile_options(wrf_rrtmgp PRIVATE -ffree-line-length-none)
endif()

install(DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/modules/"
  DESTINATION include/rte_rrtmgp
  FILES_MATCHING PATTERN "*.mod"
)
if(TARGET netCDF::netcdff)
  target_link_libraries(wrf_rrtmgp PUBLIC netCDF::netcdff)
else()
  find_path(RRTMGP_NETCDF_INCLUDE netcdf.mod HINTS "${NETCDF_INCLUDE_DIR}" REQUIRED)
  find_library(RRTMGP_NETCDFF netcdff HINTS "${NETCDF_LIBRARY_DIR}" REQUIRED)
  find_library(RRTMGP_NETCDF netcdf HINTS "${NETCDF_LIBRARY_DIR}" REQUIRED)
  target_include_directories(wrf_rrtmgp PRIVATE "${RRTMGP_NETCDF_INCLUDE}")
  target_link_libraries(wrf_rrtmgp PUBLIC "${RRTMGP_NETCDFF}" "${RRTMGP_NETCDF}")
endif()
