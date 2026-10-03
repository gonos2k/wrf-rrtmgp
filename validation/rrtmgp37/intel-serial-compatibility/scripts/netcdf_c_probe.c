#include <netcdf.h>
#include <stdio.h>
int main(void) { int id, rc; rc=nc_open("probe.nc", NC_NOWRITE, &id); if (rc) return rc; rc=nc_close(id); puts(nc_inq_libvers()); return rc; }
