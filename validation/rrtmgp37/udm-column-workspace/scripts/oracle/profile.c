#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
void *__real_malloc(size_t);
void *__real_realloc(void *,size_t);
static _Thread_local int active,phase,diag_depth;
static _Thread_local unsigned long calls[2],allocs,bytes,diag_allocs,diag_bytes,gas_init,descriptor_init,opt1,opt2,source_alloc;
void *__wrap_malloc(size_t n) {
  if(active) { allocs++;bytes+=n;if(diag_depth) {diag_allocs++;diag_bytes+=n;} }
  return __real_malloc(n);
}
void *__wrap_realloc(void *p,size_t n) {
  if(active) { allocs++;bytes+=n;if(diag_depth) {diag_allocs++;diag_bytes+=n;} }
  return __real_realloc(p,n);
}
void __cyg_profile_func_enter(void *fn,void *caller) {
  Dl_info d;
  if(!dladdr(fn,&d)||!d.dli_sname) return;
  const char *s=d.dli_sname;
  if(!strcmp(s,"__module_ra_rrtmgp_MOD_rrtmgp_lw_column")||!strcmp(s,"__module_ra_rrtmgp_MOD_rrtmgp_sw_column")) {
    phase=strstr(s,"sw_column")!=NULL;active=1;diag_depth=0;
    allocs=bytes=diag_allocs=diag_bytes=gas_init=descriptor_init=opt1=opt2=source_alloc=0;
  }
  if(!active) return;
  if(!strcmp(s,"__mo_gas_concentrations_MOD_init")) gas_init++;
  if(!strcmp(s,"__mo_optical_props_MOD_init_base")) descriptor_init++;
  if(!strcmp(s,"__mo_optical_props_MOD_alloc_only_1scl")) opt1++;
  if(!strcmp(s,"__mo_optical_props_MOD_alloc_only_2str")) opt2++;
  if(!strcmp(s,"__mo_source_functions_MOD_alloc_lw")) source_alloc++;
  if(!strcmp(s,"__module_ra_rrtmgp_MOD_ensure_sw_diagnostics")) diag_depth++;
}
void __cyg_profile_func_exit(void *fn,void *caller) {
  Dl_info d;
  if(!dladdr(fn,&d)||!d.dli_sname) return;
  const char *s=d.dli_sname;
  if(active&&!strcmp(s,"__module_ra_rrtmgp_MOD_ensure_sw_diagnostics")) diag_depth--;
  if(!strcmp(s,"__module_ra_rrtmgp_MOD_rrtmgp_lw_column")||!strcmp(s,"__module_ra_rrtmgp_MOD_rrtmgp_sw_column")) {
    active=0;calls[phase]++;
    const char *path=getenv("WORKSPACE_PROFILE_FILE");
    if(!path) return;
    FILE *f=fopen(path,"a");if(!f) abort();
    fprintf(f,"%s,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu,%lu\n",phase?"SW":"LW",calls[phase],allocs,bytes,gas_init,descriptor_init,opt1,opt2,source_alloc,diag_allocs,diag_bytes);
    fclose(f);
  }
}
