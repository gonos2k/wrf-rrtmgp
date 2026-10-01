/* Non-fatal NetCDF-C bridge. CPU initialization only; serialize NetCDF calls.
 * No NetCDF-Fortran dependency. File axes are explicitly reversed for Fortran.
 * Outputs are committed only after shape, type and finite-value checks pass.
 */
#include <netcdf.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <limits.h>

#define GP37_MAX_RANK 4
#define GP37_MAX_BYTES ((size_t)512*1024*1024)
static int err(char *msg, size_t cap, const char *text) {
    if (msg && cap) snprintf(msg, cap, "%s", text);
    return 1;
}
static int gp37_ncerr(char *msg, size_t cap, int code) {
    return err(msg, cap, nc_strerror(code));
}
static int inspect(int ncid, const char *var, int *vid, int *rank,
                   int64_t *fshape, nc_type *type, char *msg, size_t cap) {
    int rc, ids[NC_MAX_VAR_DIMS];
    if ((rc=nc_inq_varid(ncid,var,vid))) return gp37_ncerr(msg,cap,rc);
    if ((rc=nc_inq_var(ncid,*vid,NULL,type,rank,ids,NULL))) return gp37_ncerr(msg,cap,rc);
    if (*rank<0 || *rank>GP37_MAX_RANK) return err(msg,cap,"NC_RANK_EXCEEDS_4");
    for (int j=0;j<*rank;++j) {
        size_t n;
        if ((rc=nc_inq_dimlen(ncid,ids[*rank-1-j],&n))) return gp37_ncerr(msg,cap,rc);
        if (n>(size_t)INT64_MAX) return err(msg,cap,"NC_DIMENSION_OVERFLOW");
        fshape[j]=(int64_t)n;
    }
    return 0;
}
int gp37_nc_info(const char *path, const char *var, int *rank,
                 int64_t *fshape, int *xtype, char *msg, size_t cap) {
    int ncid=-1,vid,r=0,rc; int64_t dims[4]={0}; nc_type type=NC_NAT;
    if (msg && cap) msg[0]='\0';
    if ((rc=nc_open(path,NC_NOWRITE,&ncid))) return gp37_ncerr(msg,cap,rc);
    rc=inspect(ncid,var,&vid,&r,dims,&type,msg,cap);
    int close_rc=nc_close(ncid);
    if (!rc && close_rc) rc=gp37_ncerr(msg,cap,close_rc);
    if (rc) return rc;
    *rank=r; *xtype=(int)type; memcpy(fshape,dims,sizeof(dims));
    return 0;
}
/* A finite NetCDF fill value is not physical data. Reject both implicit
 * default fills and explicit _FillValue/missing_value sentinels. */
static int reject_missing(int ncid, int vid, nc_type type,
                          const double *a, size_t n, char *msg, size_t cap) {
    double fill=0; int has_default=1, rc;
    switch(type) {
      case NC_BYTE: fill=NC_FILL_BYTE; break;
      case NC_UBYTE: fill=NC_FILL_UBYTE; break;
      case NC_SHORT: fill=NC_FILL_SHORT; break;
      case NC_USHORT: fill=NC_FILL_USHORT; break;
      case NC_INT: fill=NC_FILL_INT; break;
      case NC_UINT: fill=NC_FILL_UINT; break;
      case NC_INT64: fill=(double)NC_FILL_INT64; break;
      case NC_UINT64: fill=(double)NC_FILL_UINT64; break;
      case NC_FLOAT: fill=(double)NC_FILL_FLOAT; break;
      case NC_DOUBLE: fill=NC_FILL_DOUBLE; break;
      default: has_default=0;
    }
    if(has_default) for(size_t j=0;j<n;++j) if(a[j]==fill)
      return err(msg,cap,"NC_DEFAULT_FILL_VALUE");
    const char *names[]={"_FillValue","missing_value"};
    for(int k=0;k<2;++k) {
      size_t na=0; nc_type at;
      rc=nc_inq_att(ncid,vid,names[k],&at,&na);
      if(rc==NC_ENOTATT) continue;
      if(rc) return gp37_ncerr(msg,cap,rc);
      if(na>1024 || at==NC_CHAR || at==NC_STRING)
        return err(msg,cap,"NC_INVALID_MISSING_ATTRIBUTE");
      double *values=malloc(na?na*sizeof(double):sizeof(double));
      if(!values) return err(msg,cap,"NC_ALLOCATION_FAILED");
      if(na && (rc=nc_get_att_double(ncid,vid,names[k],values))) {
        free(values); return gp37_ncerr(msg,cap,rc);
      }
      int missing=0;
      for(size_t i=0;i<na && !missing;++i)
        for(size_t j=0;j<n;++j) if(a[j]==values[i]) {missing=1;break;}
      free(values);
      if(missing) return err(msg,cap,"NC_EXPLICIT_MISSING_VALUE");
    }
    return 0;
}
int gp37_nc_read_f64(const char *path, const char *var, int rank,
                    const int64_t *fshape, double *out, size_t count,
                    char *msg, size_t cap) {
    int ncid=-1,vid,r,rc; int64_t dims[4]={0}; nc_type type;
    double *tmp=NULL; size_t n=1;
    if (msg && cap) msg[0]='\0';
    if (rank<0 || rank>4) return err(msg,cap,"NC_INVALID_EXPECTED_RANK");
    if (!out && count) return err(msg,cap,"NC_NULL_OUTPUT");
    if ((rc=nc_open(path,NC_NOWRITE,&ncid))) return gp37_ncerr(msg,cap,rc);
    rc=inspect(ncid,var,&vid,&r,dims,&type,msg,cap);
    if (rc) goto done;
    if (r!=rank) {rc=err(msg,cap,"NC_RANK_MISMATCH");goto done;}
    if (type==NC_CHAR || type==NC_STRING || type==NC_NAT) {
        rc=err(msg,cap,"NC_EXPECTED_NUMERIC_VARIABLE");goto done;
    }
    for (int j=0;j<rank;++j) {
        if (dims[j]!=fshape[j] || dims[j]<0) {rc=err(msg,cap,"NC_SHAPE_MISMATCH");goto done;}
        if ((size_t)dims[j] && n>SIZE_MAX/(size_t)dims[j]) {rc=err(msg,cap,"NC_SIZE_OVERFLOW");goto done;}
        n *= (size_t)dims[j];
    }
    if (n!=count) {rc=err(msg,cap,"NC_ELEMENT_COUNT_MISMATCH");goto done;}
    if (n>GP37_MAX_BYTES/sizeof(double)) {rc=err(msg,cap,"NC_READ_EXCEEDS_MEMORY_LIMIT");goto done;}
    tmp=malloc(n ? n*sizeof(double) : sizeof(double));
    if (!tmp) {rc=err(msg,cap,"NC_ALLOCATION_FAILED");goto done;}
    if (n && (rc=nc_get_var_double(ncid,vid,tmp))) {rc=gp37_ncerr(msg,cap,rc);goto done;}
    for (size_t j=0;j<n;++j) if (!isfinite(tmp[j])) {rc=err(msg,cap,"NC_NONFINITE_VALUE");goto done;}
    rc=reject_missing(ncid,vid,type,tmp,n,msg,cap);
    if(rc) goto done;
    rc=nc_close(ncid); ncid=-1;
    if (rc) {rc=gp37_ncerr(msg,cap,rc);goto done;}
    if(n) memcpy(out,tmp,n*sizeof(double));
    rc=0;
done:
    free(tmp);
    if(ncid>=0) { int x=nc_close(ncid); if(!rc && x) rc=gp37_ncerr(msg,cap,x); }
    return rc;
}
int gp37_nc_read_names(const char *path, const char *var, int nname,
                      int width, char *out, char *msg, size_t cap) {
    int ncid=-1,vid,r,rc; int64_t dims[4]={0}; nc_type type;
    char *raw=NULL,*tmp=NULL; size_t n=0, outn=0;
    if (msg && cap) msg[0]='\0';
    if(nname<0 || width<1) return err(msg,cap,"NC_INVALID_STRING_EXTENT");
    if((rc=nc_open(path,NC_NOWRITE,&ncid))) return gp37_ncerr(msg,cap,rc);
    rc=inspect(ncid,var,&vid,&r,dims,&type,msg,cap);
    if(rc) goto done;
    if(r!=2 || type!=NC_CHAR || dims[1]!=nname || dims[0]<1) {
        rc=err(msg,cap,"NC_EXPECTED_CHAR_NAME_MATRIX");goto done;
    }
    if((size_t)nname>GP37_MAX_BYTES/(size_t)dims[0] || (size_t)nname>GP37_MAX_BYTES/(size_t)width) {
        rc=err(msg,cap,"NC_STRING_MEMORY_LIMIT");goto done;
    }
    n=(size_t)nname*(size_t)dims[0]; outn=(size_t)nname*(size_t)width;
    raw=malloc(n?n:1);tmp=malloc(outn?outn:1);
    if(!raw || !tmp) {rc=err(msg,cap,"NC_ALLOCATION_FAILED");goto done;}
    if(n && (rc=nc_get_var_text(ncid,vid,raw))) {rc=gp37_ncerr(msg,cap,rc);goto done;}
    memset(tmp,' ',outn);
    for(int j=0;j<nname;++j) for(size_t k=0;k<(size_t)dims[0];++k) {
        char ch=raw[(size_t)j*(size_t)dims[0]+k];
        if(!ch) ch=' ';
        if(k>=(size_t)width) {
            if(ch!=' ') {rc=err(msg,cap,"NC_NONBLANK_STRING_TRUNCATION");goto done;}
        } else tmp[(size_t)j*(size_t)width+k]=ch;
    }
    rc=nc_close(ncid);ncid=-1;
    if(rc) {rc=gp37_ncerr(msg,cap,rc);goto done;}
    if(outn) memcpy(out,tmp,outn);
    rc=0;
done:
    free(raw);free(tmp);
    if(ncid>=0) {int x=nc_close(ncid);if(!rc&&x)rc=gp37_ncerr(msg,cap,x);}
    return rc;
}
