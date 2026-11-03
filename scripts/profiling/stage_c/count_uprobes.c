// Kernel-aggregated profiling probes; no target patching or solver linkage.
#define _GNU_SOURCE
#include <linux/bpf.h>
#include <linux/perf_event.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <signal.h>
#include <errno.h>

enum { MAX_PROBES=256, MAX_INSNS=192 };
struct counts { uint64_t entries,returns,wall_ns,context_entries,context_wall_ns,collisions,unmatched,errors; };
struct probe {char label[96],path[1024];unsigned long long offset;int context,timing,entry_fd,return_fd;};
static struct probe probes[MAX_PROBES];static unsigned nprobes;
static char group[64];static volatile sig_atomic_t interrupted;
static const char *trace="/sys/kernel/tracing";
static void stop(int s){(void)s;interrupted=1;}
static void fatal(const char *s){perror(s);exit(1);}
static int bpf_call(enum bpf_cmd cmd,union bpf_attr *a){return (int)syscall(SYS_bpf,cmd,a,sizeof(*a));}
static int map_create(int type,int key,int value,int size) {
  union bpf_attr a={0};a.map_type=type;a.key_size=key;a.value_size=value;a.max_entries=size;
  int f=bpf_call(BPF_MAP_CREATE,&a);if(f<0)fatal("BPF_MAP_CREATE");return f;
}
struct program {struct bpf_insn code[MAX_INSNS];int n;};
static void emit(struct program *p,int op,int dst,int src,int off,int imm){
  if(p->n>=MAX_INSNS){fprintf(stderr,"too many BPF instructions\n");exit(1);}
  p->code[p->n++]=(struct bpf_insn){.code=op,.dst_reg=dst,.src_reg=src,.off=off,.imm=imm};
}
#define MOVI(p,d,i) emit(p,BPF_ALU64|BPF_MOV|BPF_K,d,0,0,i)
#define MOVR(p,d,s) emit(p,BPF_ALU64|BPF_MOV|BPF_X,d,s,0,0)
#define ADDI(p,d,i) emit(p,BPF_ALU64|BPF_ADD|BPF_K,d,0,0,i)
#define LOAD(p,d,s,o) emit(p,BPF_LDX|BPF_MEM|BPF_DW,d,s,o,0)
#define STORE(p,d,o,s) emit(p,BPF_STX|BPF_MEM|BPF_DW,d,s,o,0)
#define CALL(p,f) emit(p,BPF_JMP|BPF_CALL,0,0,0,f)
static int jump(struct program *p,int op,int reg,int value){int i=p->n;emit(p,BPF_JMP|op|BPF_K,reg,0,0,value);return i;}
static void patch(struct program *p,int at,int dest){p->code[at].off=(short)(dest-at-1);}
static void mapfd(struct program*p,int reg,int fd){emit(p,BPF_LD|BPF_DW|BPF_IMM,reg,BPF_PSEUDO_MAP_FD,0,fd);emit(p,0,0,0,0,0);}
static void lookup(struct program*p,int fd,int stack){mapfd(p,1,fd);MOVR(p,2,10);ADDI(p,2,stack);CALL(p,BPF_FUNC_map_lookup_elem);}
static void add(struct program*p,int offset,int amount_register){LOAD(p,1,7,offset);if(amount_register<0)ADDI(p,1,1);else emit(p,BPF_ALU64|BPF_ADD|BPF_X,1,amount_register,0,0);STORE(p,7,offset,1);}
static int load_program(pid_t pid,int index,int context,int timing,int counters,int states,int identities,int observer,int returning) {
  struct program p={0};int done[8],nd=0,missing=-1;
  MOVR(&p,9,1);
  CALL(&p,BPF_FUNC_get_current_pid_tgid);MOVR(&p,6,0);
  // The perf event is already task-scoped. Use the kernel pid_tgid solely
  // as the pairing key, avoiding assumptions about caller PID namespaces.
  (void)pid;
  emit(&p,BPF_ST|BPF_MEM|BPF_W,10,0,-4,index);
  STORE(&p,10,-24,6);emit(&p,BPF_ST|BPF_MEM|BPF_DW,10,0,-16,index);
  lookup(&p,counters,-4);done[nd++]=jump(&p,BPF_JEQ,0,0);MOVR(&p,7,0);
  if(!returning) {
    add(&p,0,-1);
    if(observer) {
      // Fixed, independently checked x86-64 ABI: bind has an sret argument;
      // stored is RDX, and Mode::observer_binding's pointer is at byte 24.
      LOAD(&p,3,9,96);ADDI(&p,3,24);MOVR(&p,1,10);ADDI(&p,1,-80);MOVI(&p,2,8);CALL(&p,BPF_FUNC_probe_read_user);
      int readable=jump(&p,BPF_JEQ,0,0);add(&p,56,-1);int skip=jump(&p,BPF_JA,0,0);patch(&p,readable,p.n);
      lookup(&p,identities,-80);int insert=jump(&p,BPF_JEQ,0,0);
      LOAD(&p,1,0,0);ADDI(&p,1,1);STORE(&p,0,0,1);int finish=jump(&p,BPF_JA,0,0);patch(&p,insert,p.n);
      emit(&p,BPF_ST|BPF_MEM|BPF_DW,10,0,-88,1);mapfd(&p,1,identities);MOVR(&p,2,10);ADDI(&p,2,-80);MOVR(&p,3,10);ADDI(&p,3,-88);MOVI(&p,4,BPF_ANY);CALL(&p,BPF_FUNC_map_update_elem);
      int ok=jump(&p,BPF_JEQ,0,0);add(&p,56,-1);patch(&p,ok,p.n);patch(&p,finish,p.n);patch(&p,skip,p.n);
    }
    if(timing) {
      lookup(&p,states,-24);int fresh=jump(&p,BPF_JEQ,0,0);
      add(&p,40,-1);done[nd++]=jump(&p,BPF_JA,0,0);patch(&p,fresh,p.n);
    }
    MOVI(&p,8,0);
    if(context>=0) {
      emit(&p,BPF_ST|BPF_MEM|BPF_DW,10,0,-16,context);lookup(&p,states,-24);
      int absent=jump(&p,BPF_JEQ,0,0);MOVI(&p,8,1);add(&p,24,-1);patch(&p,absent,p.n);
      emit(&p,BPF_ST|BPF_MEM|BPF_DW,10,0,-16,index);
    }
    if(timing) {
      CALL(&p,BPF_FUNC_ktime_get_ns);STORE(&p,10,-48,0);STORE(&p,10,-40,8);
      mapfd(&p,1,states);MOVR(&p,2,10);ADDI(&p,2,-24);MOVR(&p,3,10);ADDI(&p,3,-48);MOVI(&p,4,BPF_ANY);CALL(&p,BPF_FUNC_map_update_elem);
      int ok=jump(&p,BPF_JEQ,0,0);add(&p,56,-1);patch(&p,ok,p.n);
    }
  } else {
    lookup(&p,states,-24);missing=jump(&p,BPF_JEQ,0,0);
    LOAD(&p,9,0,0);LOAD(&p,8,0,8);CALL(&p,BPF_FUNC_ktime_get_ns);
    emit(&p,BPF_ALU64|BPF_SUB|BPF_X,0,9,0,0);MOVR(&p,9,0);
    add(&p,8,-1);add(&p,16,9);
    int noctx=jump(&p,BPF_JEQ,8,0);add(&p,32,9);patch(&p,noctx,p.n);
    mapfd(&p,1,states);MOVR(&p,2,10);ADDI(&p,2,-24);CALL(&p,BPF_FUNC_map_delete_elem);
    done[nd++]=jump(&p,BPF_JA,0,0);
    patch(&p,missing,p.n);add(&p,48,-1);
  }
  for(int j=0;j<nd;++j)patch(&p,done[j],p.n);
  MOVI(&p,0,0);emit(&p,BPF_JMP|BPF_EXIT,0,0,0,0);
  char log[65536]={0};const char license[]="GPL";union bpf_attr a={0};
  a.prog_type=BPF_PROG_TYPE_KPROBE;a.insn_cnt=p.n;a.insns=(uint64_t)(uintptr_t)p.code;
  a.license=(uint64_t)(uintptr_t)license;a.log_buf=(uint64_t)(uintptr_t)log;a.log_size=sizeof(log);a.log_level=1;
  int fd=bpf_call(BPF_PROG_LOAD,&a);if(fd<0){fprintf(stderr,"BPF verifier %d/%d: %s\n",index,returning,log);fatal("BPF_PROG_LOAD");}return fd;
}
static int event(pid_t pid,int index,int returning,int program) {
  char path[2048],line[2048];snprintf(path,sizeof(path),"%s/uprobe_events",trace);
  int config=open(path,O_WRONLY|O_APPEND);if(config<0)fatal("uprobe_events");
  int length=snprintf(line,sizeof(line),"%c:%s/%c%u %s:0x%llx\n",returning?'r':'p',group,returning?'r':'e',index,probes[index].path,probes[index].offset);
  if(write(config,line,(size_t)length)!=length)fatal("register uprobe");
  close(config);
  snprintf(path,sizeof(path),"%s/events/%s/%c%u/id",trace,group,returning?'r':'e',index);
  FILE *f=fopen(path,"r");if(!f)fatal("event id");int id;if(fscanf(f,"%d",&id)!=1)fatal("read event id");fclose(f);
  struct perf_event_attr a={0};a.size=sizeof(a);a.type=PERF_TYPE_TRACEPOINT;a.config=id;a.sample_period=1;a.disabled=1;a.inherit=1;
  int fd=(int)syscall(SYS_perf_event_open,&a,pid,-1,-1,PERF_FLAG_FD_CLOEXEC);if(fd<0)fatal("perf_event_open");
  if(ioctl(fd,PERF_EVENT_IOC_SET_BPF,program)<0)fatal("SET_BPF");
  if(ioctl(fd,PERF_EVENT_IOC_ENABLE,0)<0)fatal("ENABLE");
  (void)line;return fd;
}
static void cleanup(void) {
  char path[2048];snprintf(path,sizeof(path),"%s/uprobe_events",trace);
  int fd=open(path,O_WRONLY|O_APPEND);if(fd<0)return;
  for(unsigned i=0;i<nprobes;++i) {
    for(int r=0;r<2;++r) {
      int event_fd=r?probes[i].return_fd:probes[i].entry_fd;if(event_fd<0)continue;close(event_fd);
      char line[128];int n=snprintf(line,sizeof(line),"-:%s/%c%u\n",group,r?'r':'e',i);ssize_t written=write(fd,line,(size_t)n);
      if(written!=n)fprintf(stderr,"cleanup %u/%d: %s\n",i,r,strerror(errno));
    }
  }
  close(fd);
}
int main(int argc,char **argv) {
  if(argc!=5){fprintf(stderr,"count_uprobes PID PROBES.tsv OUT.json POSSIBLE_CPUS\n");return 2;}
  pid_t pid=(pid_t)atoi(argv[1]);int cpus=atoi(argv[4]);if(pid<=0||cpus<=0)return 2;
  snprintf(group,sizeof(group),"pulse_sc_%d",getpid());
  for(unsigned i=0;i<MAX_PROBES;++i)probes[i].entry_fd=probes[i].return_fd=-1;
  FILE *f=fopen(argv[2],"r");if(!f)fatal("probe manifest");char line[2048];
  while(fgets(line,sizeof(line),f)) {
    if(nprobes>=MAX_PROBES)fatal("too many probes");
    struct probe *p=&probes[nprobes];
    p->timing=1;
    if(sscanf(line,"%95[^\t]\t%1023[^\t]\t%llx\t%d\t%d",p->label,p->path,&p->offset,&p->context,&p->timing)<4)fatal("invalid probe line");
    ++nprobes;
  }
  fclose(f);atexit(cleanup);signal(SIGTERM,stop);signal(SIGINT,stop);
  int counters=map_create(BPF_MAP_TYPE_PERCPU_ARRAY,4,sizeof(struct counts),MAX_PROBES);
  int states=map_create(BPF_MAP_TYPE_HASH,16,16,4096);
  int identities=map_create(BPF_MAP_TYPE_PERCPU_HASH,8,8,1024);
  for(unsigned i=0;i<nprobes;++i)for(int r=0;r<(probes[i].timing?2:1);++r) {
    int prog=load_program(pid,i,probes[i].context,probes[i].timing,counters,states,identities,!strcmp(probes[i].label,"bind_observations"),r);
    int fd=event(pid,i,r,prog);close(prog);if(r)probes[i].return_fd=fd;else probes[i].entry_fd=fd;
  }
  printf("READY %s %u\n",group,nprobes);fflush(stdout);
  while(!interrupted&&getchar()!=EOF)break;
  struct counts *values=calloc((size_t)cpus,sizeof(*values));if(!values)fatal("counter buffer");
  f=fopen(argv[3],"w");if(!f)fatal("output");fprintf(f,"{\"group\":\"%s\",\"pid\":%d,\"possible_cpus\":%d,\"probes\":[",group,pid,cpus);
  for(unsigned i=0;i<nprobes;++i) {
    union bpf_attr a={0};a.map_fd=counters;a.key=(uint64_t)(uintptr_t)&i;a.value=(uint64_t)(uintptr_t)values;
    if(bpf_call(BPF_MAP_LOOKUP_ELEM,&a)<0)fatal("counter lookup");
    struct counts total={0};
    for(int cpu=0;cpu<cpus;++cpu){uint64_t *t=(uint64_t*)&total,*v=(uint64_t*)&values[cpu];for(int k=0;k<8;++k)t[k]+=v[k];}
    fprintf(f,"%s{\"index\":%u,\"label\":\"%s\",\"entries\":%llu,\"returns\":%llu,\"wall_ns\":%llu,\"context_entries\":%llu,\"context_wall_ns\":%llu,\"collisions\":%llu,\"unmatched_returns\":%llu,\"map_errors\":%llu}",i?",":"",i,probes[i].label,(unsigned long long)total.entries,(unsigned long long)total.returns,(unsigned long long)total.wall_ns,(unsigned long long)total.context_entries,(unsigned long long)total.context_wall_ns,(unsigned long long)total.collisions,(unsigned long long)total.unmatched,(unsigned long long)total.errors);
  }
  fprintf(f,"],\"observer_binding_identities\":[");
  uint64_t key=0,next=0;int first=1,has_key=0;
  uint64_t *percpu=calloc((size_t)cpus,sizeof(uint64_t));if(!percpu)fatal("identity buffer");
  while(1) {
    union bpf_attr a={0};a.map_fd=identities;a.key=has_key?(uint64_t)(uintptr_t)&key:0;a.next_key=(uint64_t)(uintptr_t)&next;
    if(bpf_call(BPF_MAP_GET_NEXT_KEY,&a)<0)break;
    a=(union bpf_attr){0};a.map_fd=identities;a.key=(uint64_t)(uintptr_t)&next;a.value=(uint64_t)(uintptr_t)percpu;
    if(bpf_call(BPF_MAP_LOOKUP_ELEM,&a)<0)fatal("identity lookup");uint64_t sum=0;for(int c=0;c<cpus;++c)sum+=percpu[c];
    fprintf(f,"%s{\"pointer\":\"0x%llx\",\"bindings\":%llu}",first?"":",",(unsigned long long)next,(unsigned long long)sum);first=0;key=next;has_key=1;
  }
  fprintf(f,"]}\n");fclose(f);free(values);free(percpu);close(counters);close(states);close(identities);return 0;
}
