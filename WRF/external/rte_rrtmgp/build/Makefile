# WRF CPU backend: outer WRF OpenMP remains enabled; GPU target directives
# are excluded without removing -fopenmp and its thread-local compilation.
override FCFLAGS += -DRRTMGP_CPU_ONLY
include Makefile.upstream
VPATH += ../extensions
FCINCLUDE += -I$(NETCDFPATH)/include

# Keep only the scalar-libm helper across a translation-unit boundary.  Do
# not disable vectorization for any kernel arithmetic.  WRF does not enable
# IPO/LTO by default, but make the boundary explicit for GNU and Intel builds.
RTE_SCALAR_MATH_FC := $(firstword $(FC))
RTE_SCALAR_MATH_COMPILER_ID := $(shell $(RTE_SCALAR_MATH_FC) --version 2>/dev/null | head -n 1)
RTE_SCALAR_MATH_COMPILER_NAME := $(notdir $(RTE_SCALAR_MATH_FC))
ifneq (,$(findstring GNU Fortran,$(RTE_SCALAR_MATH_COMPILER_ID)))
RTE_SCALAR_MATH_BOUNDARY_FLAG := -fno-lto
else ifneq (,$(filter ifort ifx,$(RTE_SCALAR_MATH_COMPILER_NAME)))
RTE_SCALAR_MATH_BOUNDARY_FLAG := -no-ipo
else ifneq (,$(findstring Intel,$(RTE_SCALAR_MATH_COMPILER_ID)))
RTE_SCALAR_MATH_BOUNDARY_FLAG := -no-ipo
else
RTE_SCALAR_MATH_BOUNDARY_FLAG :=
endif
# `override` is required because WRF supplies FCFLAGS on make's command line.
# `private` prevents this boundary-only setting propagating to prerequisites.
ifneq (,$(RTE_SCALAR_MATH_BOUNDARY_FLAG))
mo_rte_scalar_math.o: private override FCFLAGS += $(RTE_SCALAR_MATH_BOUNDARY_FLAG)
endif
WRF_RRTMGP_SCALAR_BOUNDARY_FLAG := $(RTE_SCALAR_MATH_BOUNDARY_FLAG)

# Keep the WRF archive input list explicit.  In particular, do not let an
# unrelated *.o left in this directory silently become part of libwrf.a.
WRF_RRTMGP_EXTENSION_OBJECTS = \
	mo_cloud_optics_rrtmgp.o mo_simple_netcdf.o mo_load_coefficients.o \
	mo_load_cloud_coefficients.o mo_cloud_sampling.o mo_fluxes_byband.o \
	mo_heating_rates.o
WRF_RRTMGP_OBJECTS = $(sort $(RTE_FORTRAN_KERNELS) $(RTE_FORTRAN_INTERFACE) \
	$(RRTMGP_FORTRAN_KERNELS) $(RRTMGP_FORTRAN_INTERFACE) \
	$(WRF_RRTMGP_EXTENSION_OBJECTS))
WRF_RRTMGP_MODULES = $(addsuffix .mod,$(basename $(WRF_RRTMGP_OBJECTS)))
WRF_RRTMGP_LIBRARIES = librte.a librrtmgp.a librtekernels.a librtef.a \
	librrtmgpkernels.a librrtmgpf.a

# A signature-named stamp avoids rebuilding on every invocation while ensuring
# a compiler, flags, include path, kernel selection, or object-list change
# invalidates only generated files owned by this build directory.

# Inventory-only callers do not create configuration files.  For builds, use
# a unique short-lived request file so concurrent make processes cannot hash
# each other's compiler settings.
ifneq ($(filter print-wrf-objects,$(MAKECMDGOALS)),print-wrf-objects)
WRF_RRTMGP_CONFIG_REQUEST_ID := $(shell printf '%s' $$$$)
WRF_RRTMGP_CONFIG_REQUEST = .wrf-rrtmgp-config-request-$(WRF_RRTMGP_CONFIG_REQUEST_ID)
WRF_RRTMGP_CONFIG_CONTENT := $(file >$(WRF_RRTMGP_CONFIG_REQUEST),FC=$(FC))$(file >>$(WRF_RRTMGP_CONFIG_REQUEST),FC_VERSION=$(shell $(FC) --version 2>/dev/null | head -n 1))$(file >>$(WRF_RRTMGP_CONFIG_REQUEST),FCFLAGS=$(FCFLAGS))$(file >>$(WRF_RRTMGP_CONFIG_REQUEST),FCINCLUDE=$(FCINCLUDE))$(file >>$(WRF_RRTMGP_CONFIG_REQUEST),NETCDFPATH=$(NETCDFPATH))$(file >>$(WRF_RRTMGP_CONFIG_REQUEST),RTE_KERNELS=$(RTE_KERNELS))$(file >>$(WRF_RRTMGP_CONFIG_REQUEST),SCALAR_BOUNDARY_FLAG=$(WRF_RRTMGP_SCALAR_BOUNDARY_FLAG))$(file >>$(WRF_RRTMGP_CONFIG_REQUEST),OBJECTS=$(WRF_RRTMGP_OBJECTS))
WRF_RRTMGP_CONFIG_STAMP = .wrf-rrtmgp-config.stamp
WRF_RRTMGP_CONFIG_UPDATE := $(shell \
	set -e; \
	lock=.wrf-rrtmgp-config.lock; \
	while ! mkdir "$$lock" 2>/dev/null; do sleep 0.1; done; \
	if ! cmp -s $(WRF_RRTMGP_CONFIG_REQUEST) $(WRF_RRTMGP_CONFIG_STAMP); then \
		old_objects=$$(sed -n 's/^OBJECTS=//p' $(WRF_RRTMGP_CONFIG_STAMP) 2>/dev/null || :); \
		for obj in $$old_objects; do rm -f "$$obj" "$${obj%.o}.mod"; done; \
		rm -f $(WRF_RRTMGP_OBJECTS) $(WRF_RRTMGP_MODULES) $(WRF_RRTMGP_LIBRARIES); \
		cp $(WRF_RRTMGP_CONFIG_REQUEST) $(WRF_RRTMGP_CONFIG_STAMP).tmp; \
		mv $(WRF_RRTMGP_CONFIG_STAMP).tmp $(WRF_RRTMGP_CONFIG_STAMP); \
	fi; \
	rm -f $(WRF_RRTMGP_CONFIG_REQUEST); \
	rmdir "$$lock")
else
WRF_RRTMGP_CONFIG_STAMP = .wrf-rrtmgp-config-inventory-only.stamp
endif

.PHONY: extensions print-wrf-objects
libs: extensions
extensions: $(WRF_RRTMGP_EXTENSION_OBJECTS)
print-wrf-objects:
	@printf '%s\n' $(WRF_RRTMGP_OBJECTS)

$(WRF_RRTMGP_OBJECTS): $(WRF_RRTMGP_CONFIG_STAMP)

mo_simple_netcdf.o: librte.a
mo_load_coefficients.o: librrtmgp.a mo_simple_netcdf.o
mo_load_cloud_coefficients.o: librrtmgp.a mo_simple_netcdf.o mo_cloud_optics_rrtmgp.o
mo_cloud_sampling.o: librte.a
mo_fluxes_byband.o: librte.a
mo_heating_rates.o: librrtmgp.a

mo_cloud_optics_rrtmgp.o: librrtmgp.a
