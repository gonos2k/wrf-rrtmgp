#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <omp.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <time.h>
#include <unistd.h>
#include <sys/syscall.h>

/* Diagnostic-only interposition: the original callback/data/flags are preserved.
 * GOMP_parallel is synchronous, so each stack-owned context survives its team.
 * No production source, physics values, team settings, or scheduling are changed.
 */
typedef void (*callback)(void *);
typedef void (*parallel_fn)(callback,void *,unsigned,unsigned);
static parallel_fn real_parallel;
static int log_fd=-1;
__attribute__((constructor)) static void init(void) {
  real_parallel=(parallel_fn)dlsym(RTLD_NEXT,"GOMP_parallel");
  const char *path=getenv("WRF_OMP_PROBE_LOG");
  if(path && *path) log_fd=open(path,O_WRONLY|O_CREAT|O_APPEND,0600);
}
struct context {callback fn;void *data;};
static void record(const char *event,callback fn) {
  if(log_fd<0)return;
  Dl_info info={0};dladdr((void *)fn,&info);
  struct timespec cpu={0};clock_gettime(CLOCK_THREAD_CPUTIME_ID,&cpu);
  unsigned long long ns=(unsigned long long)cpu.tv_sec*1000000000ULL+(unsigned long long)cpu.tv_nsec;
  char buf[320];int n=snprintf(buf,sizeof(buf),"%s pid=%ld tid=%ld worker=%d team=%d callback=0x%lx base=0x%lx cpu_ns=%llu\n",event,(long)getpid(),(long)syscall(SYS_gettid),omp_get_thread_num(),omp_get_num_threads(),(unsigned long)(uintptr_t)fn,(unsigned long)(uintptr_t)info.dli_fbase,ns);
  if(n>0 && n<(int)sizeof(buf)) {ssize_t ignored=write(log_fd,buf,(size_t)n);(void)ignored;}
}
static void dispatch(void *ptr) {
  struct context *c=ptr;record("ENTER",c->fn);c->fn(c->data);record("EXIT",c->fn);
}
void GOMP_parallel(callback fn,void *data,unsigned nthreads,unsigned flags) {
  if(!real_parallel) _exit(127);
  if(log_fd<0){real_parallel(fn,data,nthreads,flags);return;}
  struct context c={fn,data};real_parallel(dispatch,&c,nthreads,flags);
}
