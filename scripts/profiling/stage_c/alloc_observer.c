// Profiling-only LD_PRELOAD observer. Never linked into pulse-solver.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/syscall.h>
#include <unistd.h>

extern void *__libc_malloc(size_t);
extern void *__libc_calloc(size_t,size_t);
extern void *__libc_realloc(void*,size_t);
extern void __libc_free(void*);
extern void *__libc_memalign(size_t,size_t);
enum { MALLOC,CALLOC,REALLOC,MEMALIGN,ALIGNED,POSIX,VALLOC,PVALLOC,REALLOCARRAY,NAPI };
static const char *names[NAPI]={"malloc","calloc","realloc","memalign","aligned_alloc","posix_memalign","valloc","pvalloc","reallocarray"};
typedef struct {
  uint64_t tid,calls[NAPI],bytes[NAPI],failures[NAPI],free_calls,free_null,overflow;
  uint64_t size_calls[64],size_bytes[64];
} Counters;
static Counters slots[1024];
static _Atomic unsigned used,enabled,slot_overflow;
static __thread int slot_id __attribute__((tls_model("initial-exec")))=-1;
static __thread int resolving __attribute__((tls_model("initial-exec")));
static void *(*real_memalign)(size_t,size_t),*(*real_aligned)(size_t,size_t);
static int (*real_posix)(void**,size_t,size_t);
static void *(*real_valloc)(size_t),*(*real_pvalloc)(size_t),*(*real_reallocarray)(void*,size_t,size_t);

static Counters *counter(void) {
  if (!atomic_load_explicit(&enabled,memory_order_relaxed) || resolving) return NULL;
  if (slot_id<0) {
    unsigned i=atomic_fetch_add_explicit(&used,1,memory_order_relaxed);
    if(i>=1024) { atomic_fetch_add(&slot_overflow,1); return NULL; }
    slot_id=(int)i; slots[i].tid=(uint64_t)syscall(SYS_gettid);
  }
  return &slots[slot_id];
}
static void record(unsigned api,size_t size,int failed,int overflow) {
  int saved=errno;
  Counters *c=counter();
  if(c) {
    ++c->calls[api]; c->bytes[api]+=size; c->failures[api]+=failed; c->overflow+=overflow;
    unsigned bin=size?64-__builtin_clzll((unsigned long long)size):0;
    if(bin>63)bin=63;
    ++c->size_calls[bin];c->size_bytes[bin]+=size;
  }
  errno=saved;
}
void *malloc(size_t n) { void *p=__libc_malloc(n);record(MALLOC,n,!p,0);return p; }
void *calloc(size_t n,size_t s) {
  size_t bytes;int over=__builtin_mul_overflow(n,s,&bytes);
  void *p=__libc_calloc(n,s);record(CALLOC,over?0:bytes,!p,over);return p;
}
void *realloc(void *p,size_t n) {void *q=__libc_realloc(p,n);record(REALLOC,n,!q&&n!=0,0);return q;}
void free(void *p) {
  int saved=errno;Counters *c=counter();if(c){++c->free_calls;c->free_null+=p==NULL;}
  errno=saved;__libc_free(p);
}
void *memalign(size_t a,size_t n) {++resolving;void *p=real_memalign?real_memalign(a,n):__libc_memalign(a,n);--resolving;record(MEMALIGN,n,!p,0);return p;}
void *aligned_alloc(size_t a,size_t n) {++resolving;void *p=real_aligned?real_aligned(a,n):__libc_memalign(a,n);--resolving;record(ALIGNED,n,!p,0);return p;}
int posix_memalign(void **p,size_t a,size_t n) {
  int rc;
  if(real_posix){++resolving;rc=real_posix(p,a,n);--resolving;}
  else {
    int saved=errno;
    if(a<sizeof(void*)||(a&(a-1)))rc=EINVAL;
    else {void *q=__libc_memalign(a,n);rc=q?0:ENOMEM;if(q)*p=q;}
    errno=saved;
  }
  record(POSIX,n,rc!=0,0);return rc;
}
void *valloc(size_t n) {++resolving;void *p=real_valloc?real_valloc(n):__libc_memalign((size_t)sysconf(_SC_PAGESIZE),n);--resolving;record(VALLOC,n,!p,0);return p;}
void *pvalloc(size_t n) {++resolving;size_t page=(size_t)sysconf(_SC_PAGESIZE);void *p=real_pvalloc?real_pvalloc(n):__libc_memalign(page,(n+page-1)&~(page-1));--resolving;record(PVALLOC,n,!p,0);return p;}
void *reallocarray(void *p,size_t n,size_t s) {
  size_t bytes;int over=__builtin_mul_overflow(n,s,&bytes);void *q;
  if(real_reallocarray){++resolving;q=real_reallocarray(p,n,s);--resolving;}
  else if(over){errno=ENOMEM;q=NULL;}else q=__libc_realloc(p,bytes);
  record(REALLOCARRAY,over?0:bytes,!q&&(over||bytes!=0),over);return q;
}
__attribute__((constructor)) static void begin(void) {
  resolving=1;
  real_memalign=dlsym(RTLD_NEXT,"memalign");real_aligned=dlsym(RTLD_NEXT,"aligned_alloc");
  real_posix=dlsym(RTLD_NEXT,"posix_memalign");real_valloc=dlsym(RTLD_NEXT,"valloc");
  real_pvalloc=dlsym(RTLD_NEXT,"pvalloc");real_reallocarray=dlsym(RTLD_NEXT,"reallocarray");
  resolving=0;atomic_store(&enabled,1);
}
static void emit(int fd,const char *s,size_t n) {while(n){ssize_t k=write(fd,s,n);if(k<=0)return;s+=k;n-=k;}}
// Observer self-test accessor; the solver never resolves or calls this symbol.
void pulse_alloc_totals(uint64_t out[3]) {
  out[0]=out[1]=out[2]=0;unsigned count=atomic_load(&used);if(count>1024)count=1024;
  for(unsigned i=0;i<count;++i)for(unsigned a=0;a<NAPI;++a){out[0]+=slots[i].calls[a];out[1]+=slots[i].bytes[a];out[2]+=slots[i].failures[a];}
}
__attribute__((destructor)) static void finish(void) {
  atomic_store(&enabled,0);
  const char *path=getenv("PULSE_ALLOC_REPORT");if(!path)return;
  int fd=open(path,O_WRONLY|O_CREAT|O_TRUNC,0644);if(fd<0)return;
  char line[512];unsigned count=atomic_load(&used);if(count>1024)count=1024;
  int n=snprintf(line,sizeof(line),"{\"scope\":\"libc public allocation API requests after observer initialization; startup and cleanup included; requested bytes are cumulative and include realloc replacement sizes\",\"slot_overflow\":%u,\"observer_static_bytes\":%zu,\"threads\":[",atomic_load(&slot_overflow),sizeof(slots));emit(fd,line,(size_t)n);
  for(unsigned i=0;i<count;++i) {
    Counters *c=&slots[i];n=snprintf(line,sizeof(line),"%s{\"tid\":%llu,\"free_calls\":%llu,\"free_null\":%llu,\"size_overflows\":%llu,\"apis\":[",i?",":"",(unsigned long long)c->tid,(unsigned long long)c->free_calls,(unsigned long long)c->free_null,(unsigned long long)c->overflow);emit(fd,line,(size_t)n);
    for(unsigned a=0;a<NAPI;++a) {
      n=snprintf(line,sizeof(line),"%s{\"name\":\"%s\",\"calls\":%llu,\"requested_bytes\":%llu,\"failures\":%llu}",a?",":"",names[a],(unsigned long long)c->calls[a],(unsigned long long)c->bytes[a],(unsigned long long)c->failures[a]);emit(fd,line,(size_t)n);
    }
    emit(fd,"],\"size_bins\":[",15);
    for(unsigned b=0;b<64;++b){n=snprintf(line,sizeof(line),"%s{\"bin\":%u,\"calls\":%llu,\"requested_bytes\":%llu}",b?",":"",b,(unsigned long long)c->size_calls[b],(unsigned long long)c->size_bytes[b]);emit(fd,line,(size_t)n);}
    emit(fd,"]}",2);
  }
  emit(fd,"]}\n",3);close(fd);
}
