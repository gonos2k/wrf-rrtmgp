cmake_minimum_required(VERSION 3.20)
project(WRF_RRTMGP_COLUMN_TEST LANGUAGES Fortran)
enable_testing()
find_package(Python3 REQUIRED COMPONENTS Interpreter)
add_test(NAME lw_n2_result_contract COMMAND "${Python3_EXECUTABLE}" -B
  "${CMAKE_CURRENT_SOURCE_DIR}/test_n2_result_contract.py")
add_test(NAME cf0_precip_sidecar_python_contract COMMAND "${Python3_EXECUTABLE}" -B
  "${CMAKE_CURRENT_SOURCE_DIR}/test_cf0_precip_sidecar.py")
add_test(NAME cf0_cu_precip_sidecar_context_contract COMMAND "${Python3_EXECUTABLE}" -B
  "${CMAKE_CURRENT_SOURCE_DIR}/test_cf0_cu_precip_sidecar.py")
get_filename_component(WRF_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
set(RRTMGP_DATA_DIR "${WRF_ROOT}/run" CACHE PATH "RRTMGP coefficient directory")
add_test(NAME frozen_raw_replay_contract COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_frozen_raw_replay_contract.py")
add_test(NAME cu_population_replay_contract COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_cu_population_replay.py")
add_test(NAME udm_radius_stage_join COMMAND "${Python3_EXECUTABLE}" -B
  "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_radius_stage.py" --self-test)
add_test(NAME udm_entry_density_packet COMMAND "${Python3_EXECUTABLE}" -I -S
  "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_entry_density.py" --self-test)
if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
  add_test(NAME udm_entry_density_trace COMMAND "${Python3_EXECUTABLE}" -I -S
    "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_entry_density_trace.py"
    --wrf-root "${WRF_ROOT}" --compiler "${CMAKE_Fortran_COMPILER}"
    --receipt-dir "${CMAKE_CURRENT_BINARY_DIR}/udm-entry-density-trace")
  add_test(NAME udm_radius_trace COMMAND "${Python3_EXECUTABLE}" -B
    "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_radius_trace.py"
    --wrf-root "${WRF_ROOT}" --compiler "${CMAKE_Fortran_COMPILER}")
  add_test(NAME phase_diagnostic_wrapper_contract COMMAND "${Python3_EXECUTABLE}"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_phase_diagnostic_contract.py"
    --compiler "${CMAKE_Fortran_COMPILER}"
    --output-root "${CMAKE_CURRENT_BINARY_DIR}/phase-diagnostic-wrapper-runs")
  add_test(NAME fractional_seaice_state_contract COMMAND "${Python3_EXECUTABLE}"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_fractional_seaice_state.py"
    --repo "${WRF_ROOT}/.."
    --compiler "${CMAKE_Fortran_COMPILER}"
    --output-root "${CMAKE_CURRENT_BINARY_DIR}/fractional-seaice-state-runs")
  add_test(NAME rrtmgp_column_selection_contract COMMAND "${Python3_EXECUTABLE}"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_column_selection.py" "${WRF_ROOT}")
  add_test(NAME native_hydro_snapshot COMMAND "${Python3_EXECUTABLE}"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_hydro_snapshot.py")
  add_test(NAME udm_negative_input_contract COMMAND "${Python3_EXECUTABLE}"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_negative_policy.py")
endif()
add_subdirectory("${WRF_ROOT}/external/rte_rrtmgp" rte_rrtmgp)
# Compile isolated copies so traditional WRF .mod files beside source cannot
# shadow the standalone interface. configure_file tracks source changes.
foreach(name IN ITEMS module_ra_rrtmgp module_ra_rrtmgp_input module_ra_rrtmgp_trace module_ra_rrtmgp_precip module_ra_rrtmgp_hash module_ra_rrtmgp_frozen)
  configure_file("${WRF_ROOT}/phys/${name}.F" "${CMAKE_CURRENT_BINARY_DIR}/src/${name}.F" COPYONLY)
endforeach()
set(precip "${CMAKE_CURRENT_BINARY_DIR}/src/module_ra_rrtmgp_precip.F")
set_source_files_properties("${precip}" PROPERTIES Fortran_FORMAT FREE Fortran_PREPROCESS ON)
add_library(test_rrtmgp_precip STATIC "${precip}")
target_link_libraries(test_rrtmgp_precip PUBLIC wrf_rrtmgp)
set_target_properties(test_rrtmgp_precip PROPERTIES Fortran_MODULE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/precip_modules")
target_include_directories(test_rrtmgp_precip PUBLIC "${CMAKE_CURRENT_BINARY_DIR}/precip_modules")
set(frozen "${CMAKE_CURRENT_BINARY_DIR}/src/module_ra_rrtmgp_frozen.F")
set(hash "${CMAKE_CURRENT_BINARY_DIR}/src/module_ra_rrtmgp_hash.F")
set_source_files_properties("${frozen}" "${hash}" PROPERTIES Fortran_FORMAT FREE Fortran_PREPROCESS ON)
add_library(test_rrtmgp_frozen STATIC "${hash}" "${frozen}")
if(TARGET netCDF::netcdff)
  target_link_libraries(test_rrtmgp_frozen PUBLIC netCDF::netcdff)
else()
  find_path(FROZEN_NETCDF_INCLUDE netcdf.mod HINTS "${NETCDF_INCLUDE_DIR}" REQUIRED)
  find_library(FROZEN_NETCDFF netcdff HINTS "${NETCDF_LIBRARY_DIR}" REQUIRED)
  find_library(FROZEN_NETCDF netcdf HINTS "${NETCDF_LIBRARY_DIR}" REQUIRED)
  target_include_directories(test_rrtmgp_frozen PRIVATE "${FROZEN_NETCDF_INCLUDE}")
  target_link_libraries(test_rrtmgp_frozen PUBLIC "${FROZEN_NETCDFF}" "${FROZEN_NETCDF}")
endif()
set_target_properties(test_rrtmgp_frozen PROPERTIES Fortran_MODULE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/frozen_modules")
target_include_directories(test_rrtmgp_frozen PUBLIC "${CMAKE_CURRENT_BINARY_DIR}/frozen_modules")
if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
  target_compile_options(test_rrtmgp_frozen PRIVATE -ffree-line-length-none -fcheck=bounds)
endif()
add_executable(test_rrtmgp_hash test_hash.f90)
target_link_libraries(test_rrtmgp_hash PRIVATE test_rrtmgp_frozen)
add_test(NAME frozen_file_sha256 COMMAND test_rrtmgp_hash)
add_executable(test_rrtmgp_frozen_lookup test_frozen_lookup.f90)
target_link_libraries(test_rrtmgp_frozen_lookup PRIVATE test_rrtmgp_frozen)
get_filename_component(REPO_ROOT "${WRF_ROOT}/.." ABSOLUTE)
set(FROZEN_TABLE "${REPO_ROOT}/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc"
  CACHE FILEPATH "Experimental frozen optics table for integration tests")
add_test(NAME frozen_fortran_python_lookup COMMAND "${Python3_EXECUTABLE}"
  "${REPO_ROOT}/tools/udm_frozen_optics/test_fortran_lookup.py" --executable "$<TARGET_FILE:test_rrtmgp_frozen_lookup>"
  --generation "${REPO_ROOT}/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50"
  --ctest-output-root "${CMAKE_CURRENT_BINARY_DIR}/frozen-lookup-equivalence-runs")
add_test(NAME frozen_planck_temperature_coverage COMMAND "${Python3_EXECUTABLE}"
  "${REPO_ROOT}/tools/udm_frozen_optics/test_planck_coverage.py"
  --executable "$<TARGET_FILE:test_rrtmgp_frozen_lookup>"
  --generation "${REPO_ROOT}/validation/rrtmgp37/frozen-planck-coverage/expanded"
  --old-generation "${REPO_ROOT}/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50"
  --ctest-output-root "${CMAKE_CURRENT_BINARY_DIR}/frozen-planck-coverage-runs")
set(adapter "${CMAKE_CURRENT_BINARY_DIR}/src/module_ra_rrtmgp.F")
set(trace "${CMAKE_CURRENT_BINARY_DIR}/src/module_ra_rrtmgp_trace.F")
set(input_builder "${CMAKE_CURRENT_BINARY_DIR}/src/module_ra_rrtmgp_input.F")
set_source_files_properties("${adapter}" "${input_builder}" "${trace}" PROPERTIES Fortran_FORMAT FREE Fortran_PREPROCESS ON)
add_library(test_rrtmgp_adapter STATIC standalone_wrf_error.f90 "${trace}" "${input_builder}" "${adapter}")
target_link_libraries(test_rrtmgp_adapter PUBLIC wrf_rrtmgp test_rrtmgp_precip test_rrtmgp_frozen)
set_target_properties(test_rrtmgp_adapter PROPERTIES Fortran_MODULE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/modules")
target_include_directories(test_rrtmgp_adapter PUBLIC "${CMAKE_CURRENT_BINARY_DIR}/modules")

# Fault-path tests compile isolated copies of the production adapter with one
# exact, test-generated NaN/overflow insertion. The production source has no
# runtime fault switch or test-only branch.
set(output_fault_dir "${CMAKE_CURRENT_BINARY_DIR}/output-finite-fault-src")
execute_process(
  COMMAND "${Python3_EXECUTABLE}" -B "${CMAKE_CURRENT_SOURCE_DIR}/generate_output_finite_fault_sources.py"
          --source "${adapter}" --output-dir "${output_fault_dir}"
  RESULT_VARIABLE output_fault_generation_status
  OUTPUT_VARIABLE output_fault_generation_output
  ERROR_VARIABLE output_fault_generation_error)
if(NOT output_fault_generation_status EQUAL 0)
  message(FATAL_ERROR "Could not generate output-finite fault sources: ${output_fault_generation_error}")
endif()
foreach(fault_case IN ITEMS lw_clear_flux_nan sw_allsky_heat_nan lw_allsky_default_overflow)
  set(fault_source "${output_fault_dir}/module_ra_rrtmgp_${fault_case}.F")
  set_source_files_properties("${fault_source}" PROPERTIES Fortran_FORMAT FREE Fortran_PREPROCESS ON)
  set(fault_library "test_rrtmgp_adapter_fault_${fault_case}")
  set(fault_modules "${CMAKE_CURRENT_BINARY_DIR}/modules-${fault_case}")
  add_library(${fault_library} STATIC standalone_wrf_error.f90 "${trace}" "${input_builder}" "${fault_source}")
  target_link_libraries(${fault_library} PUBLIC wrf_rrtmgp test_rrtmgp_precip test_rrtmgp_frozen)
  set_target_properties(${fault_library} PROPERTIES Fortran_MODULE_DIRECTORY "${fault_modules}")
  target_include_directories(${fault_library} PUBLIC "${fault_modules}")
  if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
    target_compile_options(${fault_library} PRIVATE -ffree-line-length-none -fcheck=bounds)
  endif()
  add_executable(test_rrtmgp_output_finite_${fault_case} test_output_finite_fault.f90)
  target_link_libraries(test_rrtmgp_output_finite_${fault_case} PRIVATE ${fault_library})
endforeach()
foreach(test IN ITEMS columns cloud_inputs multicolumn validation adapter_invalid small_cf_sampling ice_roughness transparent_overlap spectral_surface udm_inputs precip_optics udm_adapter udm_dry_mass domain_seed native_gas_columns frozen_adapter udm_frozen_inputs lw_trace_gases sw_predelta_direct phase_path_stats cu_population_inputs cu_population_optics)
  add_executable(test_rrtmgp_${test} test_${test}.f90)
  target_link_libraries(test_rrtmgp_${test} PRIVATE test_rrtmgp_adapter)
  if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
    target_compile_options(test_rrtmgp_${test} PRIVATE -ffree-line-length-none -fcheck=bounds)
  endif()
endforeach()
add_executable(test_rrtmgp_workspace test_workspace.F90)
target_link_libraries(test_rrtmgp_workspace PRIVATE test_rrtmgp_adapter)
if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
  target_compile_options(test_rrtmgp_workspace PRIVATE -ffree-line-length-none -fcheck=bounds)
endif()
add_test(NAME workspace_reuse_states_mode0 COMMAND test_rrtmgp_workspace "${RRTMGP_DATA_DIR}" 0 "${FROZEN_TABLE}")
add_test(NAME workspace_reuse_states_mode1 COMMAND test_rrtmgp_workspace "${RRTMGP_DATA_DIR}" 1 "${FROZEN_TABLE}")
add_test(NAME workspace_frozen_mode_lock COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_workspace_modeflip.py" "$<TARGET_FILE:test_rrtmgp_workspace>"
  "${RRTMGP_DATA_DIR}" "${FROZEN_TABLE}")
set_tests_properties(workspace_reuse_states_mode0 workspace_reuse_states_mode1
  PROPERTIES ENVIRONMENT "OMP_NUM_THREADS=1;OMP_DYNAMIC=FALSE")

add_executable(test_rrtmgp_host_constants test_host_constants.f90)
target_link_libraries(test_rrtmgp_host_constants PRIVATE test_rrtmgp_adapter)
if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
  target_compile_options(test_rrtmgp_host_constants PRIVATE -ffree-line-length-none -fcheck=bounds)
endif()
add_executable(test_rrtmgp_delta_policy test_delta_policy.f90)
target_link_libraries(test_rrtmgp_delta_policy PRIVATE test_rrtmgp_precip wrf_rrtmgp)
if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
  target_compile_options(test_rrtmgp_delta_policy PRIVATE -ffree-line-length-none -fcheck=bounds)
endif()
if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
  target_compile_options(test_rrtmgp_adapter PRIVATE -ffree-line-length-none -fcheck=bounds)
endif()
add_test(NAME wrf_rrtmgp_columns COMMAND test_rrtmgp_columns "${RRTMGP_DATA_DIR}")
add_test(NAME udm_phase_path_statistics COMMAND test_rrtmgp_phase_path_stats "${RRTMGP_DATA_DIR}")
add_test(NAME cloud_mass_contract COMMAND test_rrtmgp_cloud_inputs)
foreach(case IN ITEMS success native_tiny)
  add_test(NAME cu_population_inputs_${case} COMMAND test_rrtmgp_cu_population_inputs ${case})
endforeach()
foreach(case_error IN ITEMS
    "native_masked|RRTMGP_INPUT_UDM_QI_NEGATIVE"
    "cf_below_cu|RRTMGP_INPUT_CU_CF_EXCEEDS_COMBINED"
    "cf_zero|RRTMGP_INPUT_CU_CF_ZERO_COMBINED"
    "cf_sum|RRTMGP_INPUT_CU_CF_SUM_MISMATCH"
    "negative_fraction|RRTMGP_INPUT_CU_CF_OUT_OF_RANGE"
    "cf_nan|RRTMGP_INPUT_CU_CF_NOT_FINITE"
    "q_nan|RRTMGP_INPUT_CU_Q_NOT_FINITE"
    "mass_zero|RRTMGP_INPUT_CU_DRY_MASS_NOT_POSITIVE_FINITE"
    "overflow|RRTMGP_INPUT_CU_PATH_OVERFLOW"
    "shape|RRTMGP_INPUT_CU_SHAPE_MISMATCH")
  string(REPLACE "|" ";" case_error "${case_error}")
  list(GET case_error 0 case)
  list(GET case_error 1 error)
  add_test(NAME reject_cu_population_inputs_${case} COMMAND "${Python3_EXECUTABLE}"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_invalid_inputs.py" "$<TARGET_FILE:test_rrtmgp_cu_population_inputs>"
    "${case}" "${error}")
endforeach()
add_test(NAME domain_calendar_seed_contract COMMAND test_rrtmgp_domain_seed)
foreach(mode IN ITEMS mixed overlap_zero no_precip night)
  foreach(frozen IN ITEMS 0 1)
    add_test(NAME cu_population_optics_${mode}_frozen${frozen}
      COMMAND test_rrtmgp_cu_population_optics "${RRTMGP_DATA_DIR}" "${mode}" "${FROZEN_TABLE}" "${frozen}")
  endforeach()
endforeach()
foreach(case_error IN ITEMS
    "partial|RRTMGP_INPUT_CU_PARTIAL_BUNDLE"
    "shape|CU_SHAPE_MISMATCH"
    "radius|CU_RADIUS_NOT_POSITIVE"
    "radius_nan|CU_RADIUS_NOT_FINITE"
    "path_negative|CU_IWP_NEGATIVE"
    "cf_zero|CU_ZERO_CF_WITH_PATH")
  string(REPLACE "|" ";" case_error "${case_error}")
  list(GET case_error 0 case)
  list(GET case_error 1 error)
  add_test(NAME reject_cu_population_optics_${case} COMMAND "${Python3_EXECUTABLE}"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_invalid_inputs.py" "$<TARGET_FILE:test_rrtmgp_cu_population_optics>"
    "${case}" "${error}" --data-path "${RRTMGP_DATA_DIR}")
endforeach()
add_test(NAME multi_column_equivalence COMMAND test_rrtmgp_multicolumn "${RRTMGP_DATA_DIR}")
foreach(case_error IN ITEMS
    "solar_shape|RRTMGP_SW_SOLAR_COLUMN_SHAPE_MISMATCH"
    "solar_negative|RRTMGP_INPUT_SOLAR_BY_COLUMN_NEGATIVE"
    "solar_nan|RRTMGP_INPUT_SOLAR_BY_COLUMN_NOT_FINITE")
  string(REPLACE "|" ";" case_error "${case_error}")
  list(GET case_error 0 case)
  list(GET case_error 1 error)
  add_test(NAME reject_multicolumn_${case} COMMAND "${Python3_EXECUTABLE}"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_invalid_inputs.py" "$<TARGET_FILE:test_rrtmgp_multicolumn>"
    "${case}" "${error}" --data-path "${RRTMGP_DATA_DIR}")
endforeach()
foreach(case IN ITEMS clear cloud overlap_zero)
  add_test(NAME sw_predelta_direct_${case} COMMAND test_rrtmgp_sw_predelta_direct "${RRTMGP_DATA_DIR}" ${case})
endforeach()
add_test(NAME sw_predelta_direct_night COMMAND test_rrtmgp_sw_predelta_direct "${RRTMGP_DATA_DIR}" night)
add_test(NAME reject_sw_predelta_partial_group_a COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_invalid_inputs.py" "$<TARGET_FILE:test_rrtmgp_sw_predelta_direct>"
  partial_a RRTMGP_SW_PREDELTA_OUTPUTS_MUST_BE_ALL_OR_NONE --data-path "${RRTMGP_DATA_DIR}")
add_test(NAME reject_sw_predelta_partial_group_b COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_invalid_inputs.py" "$<TARGET_FILE:test_rrtmgp_sw_predelta_direct>"
  partial_b RRTMGP_SW_PREDELTA_OUTPUTS_MUST_BE_ALL_OR_NONE --data-path "${RRTMGP_DATA_DIR}")
add_test(NAME reject_sw_predelta_bad_output_shape COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_invalid_inputs.py" "$<TARGET_FILE:test_rrtmgp_sw_predelta_direct>"
  bad_shape RRTMGP_SW_PREDELTA_OUTPUT_SHAPE_MISMATCH --data-path "${RRTMGP_DATA_DIR}")
function(reject_input executable case diagnostic)
  add_test(NAME reject_${case} COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_invalid_inputs.py"
    "$<TARGET_FILE:${executable}>" "${case}" "${diagnostic}")
endfunction()
foreach(case IN ITEMS native_mixed native_clear_omission native_hail_tiny legacy_pressure_gravity)
  add_test(NAME udm_dry_mass_${case} COMMAND test_rrtmgp_udm_dry_mass ${case})
endforeach()
reject_input(test_rrtmgp_udm_dry_mass dry_shape RRTMGP_INPUT_SHAPE_MISMATCH)
foreach(case IN ITEMS dry_zero dry_negative dry_nan dry_inf)
  reject_input(test_rrtmgp_udm_dry_mass ${case} RRTMGP_INPUT_UDM_DRY_LAYER_MASS_NOT_POSITIVE_FINITE)
endforeach()
reject_input(test_rrtmgp_udm_dry_mass dry_path_overflow RRTMGP_INPUT_PATH_OVERFLOW)

reject_input(test_rrtmgp_cloud_inputs cf_negative RRTMGP_INPUT_CF_OUT_OF_RANGE)
reject_input(test_rrtmgp_cloud_inputs cf_above_one RRTMGP_INPUT_CF_OUT_OF_RANGE)
reject_input(test_rrtmgp_cloud_inputs cf_nan RRTMGP_INPUT_CF_NOT_FINITE)
reject_input(test_rrtmgp_cloud_inputs qc_negative RRTMGP_INPUT_QC_NEGATIVE)
reject_input(test_rrtmgp_cloud_inputs qc_nan RRTMGP_INPUT_QC_NOT_FINITE)
reject_input(test_rrtmgp_cloud_inputs dp_negative RRTMGP_INPUT_DP_NOT_POSITIVE)
reject_input(test_rrtmgp_cloud_inputs cf_zero_wet RRTMGP_INPUT_ZERO_CLOUD_FRACTION_WITH_CONDENSATE)
reject_input(test_rrtmgp_cloud_inputs tiny_cf_overflow RRTMGP_INPUT_PATH_OVERFLOW)

add_test(NAME common_input_validation COMMAND test_rrtmgp_validation)
reject_input(test_rrtmgp_validation cf_range RRTMGP_INPUT_CF_OUT_OF_RANGE)
reject_input(test_rrtmgp_validation path_negative RRTMGP_INPUT_LWP_NEGATIVE)
reject_input(test_rrtmgp_validation cf_zero_path RRTMGP_INPUT_ZERO_CLOUD_FRACTION_WITH_PATH)
reject_input(test_rrtmgp_validation pressure_order RRTMGP_INPUT_PLEV_NOT_STRICTLY_DECREASING)
reject_input(test_rrtmgp_validation radius_inactive_nan RRTMGP_INPUT_RES_NOT_FINITE)
reject_input(test_rrtmgp_validation radius_active_zero RRTMGP_INPUT_REI_NOT_POSITIVE)
reject_input(test_rrtmgp_validation shape RRTMGP_INPUT_SHAPE_MISMATCH)
add_test(NAME reject_validation_cf_nan COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_invalid_inputs.py"
  "$<TARGET_FILE:test_rrtmgp_validation>" cf_nan RRTMGP_INPUT_CF_NOT_FINITE)

function(reject_adapter case diagnostic)
  add_test(NAME reject_adapter_${case} COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_invalid_inputs.py"
    "$<TARGET_FILE:test_rrtmgp_adapter_invalid>" "${case}" "${diagnostic}" --data-path "${RRTMGP_DATA_DIR}")
endfunction()
reject_adapter(cf_overlap1 RRTMGP_INPUT_CF_OUT_OF_RANGE)
reject_adapter(cf_overlap3 RRTMGP_INPUT_CF_OUT_OF_RANGE)
reject_adapter(gas_nan RRTMGP_INPUT_H2O_NOT_FINITE)
reject_adapter(albedo_above_one RRTMGP_INPUT_AVDIR_OUT_OF_RANGE)
reject_adapter(emissivity_nan RRTMGP_INPUT_EMIS_NOT_FINITE)
reject_adapter(mu0_nan_night "mu0 must be finite")
reject_adapter(solar_negative RRTMGP_INPUT_SOLAR_NEGATIVE)
reject_adapter(changed_init_path "rrtmgp_data_path must be global and unchanged after initialization")
reject_adapter(coefficient_load_missing "RRTMGP: load_and_init(): can't open file")
add_test(NAME reject_output_finite_lw_clear_flux_nan COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_output_finite_fault.py"
  "$<TARGET_FILE:test_rrtmgp_output_finite_lw_clear_flux_nan>" lw_clear_flux_nan "${RRTMGP_DATA_DIR}")
add_test(NAME reject_output_finite_sw_allsky_heat_nan COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_output_finite_fault.py"
  "$<TARGET_FILE:test_rrtmgp_output_finite_sw_allsky_heat_nan>" sw_allsky_heat_nan "${RRTMGP_DATA_DIR}")
add_test(NAME reject_output_finite_lw_allsky_default_overflow COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_output_finite_fault.py"
  "$<TARGET_FILE:test_rrtmgp_output_finite_lw_allsky_default_overflow>" lw_allsky_default_overflow "${RRTMGP_DATA_DIR}")
set_tests_properties(reject_output_finite_lw_allsky_default_overflow PROPERTIES SKIP_RETURN_CODE 77)

add_test(NAME small_cf_sampling COMMAND test_rrtmgp_small_cf_sampling "${RRTMGP_DATA_DIR}")

# Independent executable shares the pinned library and data, not the WRF adapter.
add_executable(reference_column reference_column.f90)
target_link_libraries(reference_column PRIVATE wrf_rrtmgp test_rrtmgp_frozen)
add_test(NAME cf0_precip_compiled_reader COMMAND "${Python3_EXECUTABLE}" -B
  "${CMAKE_CURRENT_SOURCE_DIR}/test_cf0_precip_compiled_reader.py"
  --data "${RRTMGP_DATA_DIR}"
  --reference "$<TARGET_FILE:reference_column>"
  --lw-generator "$<TARGET_FILE:test_rrtmgp_lw_trace_gases>"
  --sw-generator "$<TARGET_FILE:test_rrtmgp_sw_predelta_direct>"
  --work-root "${CMAKE_CURRENT_BINARY_DIR}/cf0-precip-compiled-reader"
  --output "${CMAKE_CURRENT_BINARY_DIR}/cf0-precip-compiled-reader.json")
add_test(NAME cu_population_independent_replay COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_cu_population_optics_replay.py"
  --generator "$<TARGET_FILE:test_rrtmgp_cu_population_optics>"
  --reference "$<TARGET_FILE:reference_column>" --data "${RRTMGP_DATA_DIR}" --table "${FROZEN_TABLE}"
  --ctest-output-root "${CMAKE_CURRENT_BINARY_DIR}/cu-population-replay")
add_test(NAME sw_predelta_v9_independent_replay COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_sw_predelta_replay.py" "${RRTMGP_DATA_DIR}"
  "$<TARGET_FILE:test_rrtmgp_sw_predelta_direct>" "$<TARGET_FILE:reference_column>" "${FROZEN_TABLE}")
add_test(NAME lw_trace_gases_replay COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_lw_trace_gases_replay.py"
  "$<TARGET_FILE:test_rrtmgp_lw_trace_gases>" "$<TARGET_FILE:reference_column>"
  "${RRTMGP_DATA_DIR}" "${CMAKE_CURRENT_BINARY_DIR}/lw-trace-gases-replay.json")
if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
  target_compile_options(reference_column PRIVATE -ffree-line-length-none -fcheck=bounds)
endif()
add_test(NAME coefficient_load_failure_callbacks COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_coefficient_load_failures.py" "${RRTMGP_DATA_DIR}"
  "$<TARGET_FILE:reference_column>")
add_test(NAME sw_optics_override_contract COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_sw_optics_override.py" "${RRTMGP_DATA_DIR}"
  "$<TARGET_FILE:reference_column>")
add_test(NAME replay_format_compatibility COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_replay_formats.py" "${RRTMGP_DATA_DIR}"
  "$<TARGET_FILE:test_rrtmgp_columns>" "$<TARGET_FILE:reference_column>"
  --output "${CMAKE_CURRENT_BINARY_DIR}/replay-format-compatibility.json")

reject_adapter(roughness_low "rrtmgp_ice_roughness must be 1")
reject_adapter(roughness_high "rrtmgp_ice_roughness must be 1")
reject_adapter(changed_init_roughness "rrtmgp_ice_roughness must be global and unchanged")
reject_adapter(changed_init_constants "RRTMGP gravity, cp_dry, and mol_weight_dry must be global and unchanged")
add_test(NAME transparent_overlap COMMAND test_rrtmgp_transparent_overlap)
add_test(NAME spectral_surface_contract COMMAND test_rrtmgp_spectral_surface "${RRTMGP_DATA_DIR}"
  "${CMAKE_CURRENT_BINARY_DIR}/spectral-surface.csv")
foreach(roughness IN ITEMS 1 2 3)
  add_test(NAME ice_roughness_${roughness} COMMAND test_rrtmgp_ice_roughness "${RRTMGP_DATA_DIR}" "${roughness}"
    "${CMAKE_CURRENT_BINARY_DIR}/ice-roughness-${roughness}.csv")
  set_tests_properties(ice_roughness_${roughness} PROPERTIES FIXTURES_SETUP ice_roughness_${roughness})
endforeach()
add_test(NAME ice_roughness_invariance COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/analyze_ice_roughness.py"
  --run 1 "${CMAKE_CURRENT_BINARY_DIR}/ice-roughness-1.csv"
  --run 2 "${CMAKE_CURRENT_BINARY_DIR}/ice-roughness-2.csv"
  --run 3 "${CMAKE_CURRENT_BINARY_DIR}/ice-roughness-3.csv"
  --output "${CMAKE_CURRENT_BINARY_DIR}/ice-roughness-summary.json")
set_tests_properties(ice_roughness_invariance PROPERTIES FIXTURES_REQUIRED "ice_roughness_1;ice_roughness_2;ice_roughness_3")

# Exploratory optics comparison uses the core directly, with no WRF adapter.
add_executable(compare_snow_optics compare_snow_optics.f90)
target_link_libraries(compare_snow_optics PRIVATE wrf_rrtmgp)
if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
  target_compile_options(compare_snow_optics PRIVATE -ffree-line-length-none -fcheck=bounds)
endif()
add_test(NAME snow_optics_source_comparison COMMAND compare_snow_optics "${RRTMGP_DATA_DIR}")

add_test(NAME udm_mass_contract COMMAND test_rrtmgp_udm_inputs)
add_test(NAME host_constants_and_column_energy COMMAND test_rrtmgp_host_constants "${RRTMGP_DATA_DIR}")
add_test(NAME host_constants_replay_v5 COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_host_constants_replay.py"
  "${RRTMGP_DATA_DIR}" "$<TARGET_FILE:test_rrtmgp_host_constants>" "$<TARGET_FILE:reference_column>"
  --output "${CMAKE_CURRENT_BINARY_DIR}/host-constants-replay.json")
add_test(NAME udm_precip_optics COMMAND test_rrtmgp_precip_optics)

add_test(NAME udm_native_radii COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_native_radii.py" "${WRF_ROOT}" --workdir "${CMAKE_CURRENT_BINARY_DIR}/udm-native-radii")
add_test(NAME udm_warm_ice_radius COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_warm_ice_radius.py" --wrf-root "${WRF_ROOT}"
  --workdir "${CMAKE_CURRENT_BINARY_DIR}/udm-warm-ice-radius")
add_test(NAME udm_startup_snow COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_startup_snow.py" --wrf-root "${WRF_ROOT}"
  --workdir "${CMAKE_CURRENT_BINARY_DIR}/udm-startup-snow")
add_test(NAME udm_startup_snow_replay COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_startup_snow_replay.py")
add_test(NAME udm_startup_snow_scm_process COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_startup_snow_scm_process.py")
add_test(NAME udm_startup_snow_scm_namelist COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_startup_snow_scm_namelist.py")
add_test(NAME udm_startup_optics_contract COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_startup_optics_contract.py")
add_test(NAME udm_ccn_tile_startup COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_ccn_startup.py")
add_test(NAME udm_surface_rain_row COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_sr_rows.py" "${WRF_ROOT}" --workdir "${CMAKE_CURRENT_BINARY_DIR}/udm-sr-row")
add_test(NAME udm_cldf_partial_output COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_cldf_extent.py" "${WRF_ROOT}" --workdir "${CMAKE_CURRENT_BINARY_DIR}/udm-cldf-partial-output")

add_test(NAME udm_cf_extent_parser COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_cf_extent.py")

add_test(NAME udm_precip_adapter COMMAND test_rrtmgp_udm_adapter "${RRTMGP_DATA_DIR}")
add_test(NAME udm_precip_replay COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_replay.py"
  "${RRTMGP_DATA_DIR}" "$<TARGET_FILE:test_rrtmgp_udm_adapter>" "$<TARGET_FILE:reference_column>"
  --output "${CMAKE_CURRENT_BINARY_DIR}/udm-precip-replay.json")

add_test(NAME delta_policy_benchmark COMMAND test_rrtmgp_delta_policy "${RRTMGP_DATA_DIR}"
  "${CMAKE_CURRENT_BINARY_DIR}/delta-policy.csv")
set_tests_properties(delta_policy_benchmark PROPERTIES FIXTURES_SETUP delta_policy)
add_test(NAME delta_policy_summary COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/analyse_delta_policy.py"
  "${CMAKE_CURRENT_BINARY_DIR}/delta-policy.csv" --output "${CMAKE_CURRENT_BINARY_DIR}/delta-policy-summary.json")
set_tests_properties(delta_policy_summary PROPERTIES FIXTURES_REQUIRED delta_policy)
add_test(NAME udm_sw_delta_policy_replay COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_udm_delta_policy.py"
  "${RRTMGP_DATA_DIR}" "$<TARGET_FILE:test_rrtmgp_udm_adapter>" "$<TARGET_FILE:reference_column>"
  --output "${CMAKE_CURRENT_BINARY_DIR}/udm-sw-delta-policy.json")

# A separate CI build enables host OpenMP in both the library and adapter.
# GPU target directives stay disabled by the WRF CPU backend contract.
option(RRTMGP_TEST_OPENMP "Build the concurrent CPU adapter stress test" OFF)
if(RRTMGP_TEST_OPENMP)
  find_package(OpenMP REQUIRED COMPONENTS Fortran)
  target_link_libraries(wrf_rrtmgp PUBLIC OpenMP::OpenMP_Fortran)
  target_link_libraries(test_rrtmgp_adapter PUBLIC OpenMP::OpenMP_Fortran)
  target_link_libraries(test_rrtmgp_frozen PUBLIC OpenMP::OpenMP_Fortran)
  add_executable(test_rrtmgp_openmp test_openmp_reentrancy.f90)
  target_link_libraries(test_rrtmgp_openmp PRIVATE test_rrtmgp_adapter OpenMP::OpenMP_Fortran)
  if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
    target_compile_options(test_rrtmgp_openmp PRIVATE -ffree-line-length-none -fcheck=bounds)
  endif()
  add_executable(test_rrtmgp_frozen_openmp test_frozen_openmp.f90)
  target_link_libraries(test_rrtmgp_frozen_openmp PRIVATE test_rrtmgp_frozen OpenMP::OpenMP_Fortran)
  if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
    target_compile_options(test_rrtmgp_frozen_openmp PRIVATE -ffree-line-length-none -fcheck=bounds)
  endif()
  add_test(NAME frozen_openmp_queries COMMAND test_rrtmgp_frozen_openmp "${FROZEN_TABLE}")
  add_test(NAME cpu_openmp_reentrancy COMMAND test_rrtmgp_openmp "${RRTMGP_DATA_DIR}")
  add_executable(test_rrtmgp_omp_fatal_reason test_openmp_fatal_reason.f90 "${input_builder}")
  set_target_properties(test_rrtmgp_omp_fatal_reason PROPERTIES
    Fortran_MODULE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/omp-fatal-modules")
  target_include_directories(test_rrtmgp_omp_fatal_reason PRIVATE
    "${CMAKE_CURRENT_BINARY_DIR}/omp-fatal-modules")
  target_link_libraries(test_rrtmgp_omp_fatal_reason PRIVATE OpenMP::OpenMP_Fortran)
  if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
    target_compile_options(test_rrtmgp_omp_fatal_reason PRIVATE -ffree-line-length-none)
  endif()
  add_test(NAME omp_fatal_reason_visible_from_worker COMMAND "${Python3_EXECUTABLE}"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_openmp_fatal_reason.py"
    "$<TARGET_FILE:test_rrtmgp_omp_fatal_reason>")
  set_tests_properties(cpu_openmp_reentrancy PROPERTIES ENVIRONMENT "OMP_NUM_THREADS=1;OMP_DYNAMIC=FALSE")
endif()

add_test(NAME native_gas_columns_v6 COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/test_native_gas_columns.py"
  --executable "$<TARGET_FILE:test_rrtmgp_native_gas_columns>"
  --reference "$<TARGET_FILE:reference_column>"
  --data-dir "${RRTMGP_DATA_DIR}"
  --output-dir "${CMAKE_CURRENT_BINARY_DIR}/native-gas-columns"
  --output "${CMAKE_CURRENT_BINARY_DIR}/native-gas-columns.json")

foreach(case IN ITEMS zero tiny graupel hail mixed mixed_cloud overlap_zero)
  add_test(NAME frozen_adapter_${case} COMMAND test_rrtmgp_frozen_adapter "${RRTMGP_DATA_DIR}" "${FROZEN_TABLE}" ${case})
endforeach()
foreach(pair IN ITEMS "missing_inputs|RRTMGP_FROZEN_INPUTS_REQUIRED_IN_MODE_1" "mode_zero_input|RRTMGP_FROZEN_INPUTS_REQUIRE_MODE_1"
  "bad_mode|rrtmgp_udm_frozen_optics must be 0 or 1" "changed_path|UDM frozen optics mode and table path must be global and unchanged"
  "lambda_range|RRTMGP_FROZEN_LW_GRAUPEL" "temperature_range|RRTMGP_FROZEN_LW_HAIL")
  string(REPLACE "|" ";" fields "${pair}")
  list(GET fields 0 case)
  list(GET fields 1 diagnostic)
  add_test(NAME frozen_reject_${case} COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_frozen_invalid.py"
    "$<TARGET_FILE:test_rrtmgp_frozen_adapter>" "${RRTMGP_DATA_DIR}" "${FROZEN_TABLE}" "${case}" "${diagnostic}")
endforeach()

add_test(NAME udm_frozen_input_contract COMMAND test_rrtmgp_udm_frozen_inputs)

add_test(NAME frozen_reject_missing_table COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_frozen_invalid.py"
  "$<TARGET_FILE:test_rrtmgp_frozen_adapter>" "${RRTMGP_DATA_DIR}" "${FROZEN_TABLE}.missing" "mixed" "RRTMGP_FROZEN_TABLE")

add_test(NAME frozen_independent_replay COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_frozen_replay.py"
  "${RRTMGP_DATA_DIR}" "${FROZEN_TABLE}" "$<TARGET_FILE:test_rrtmgp_frozen_adapter>" "$<TARGET_FILE:reference_column>"
  --output "${CMAKE_CURRENT_BINARY_DIR}/frozen-independent-replay.json")
