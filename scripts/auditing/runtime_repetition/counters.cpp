// Count-only audit runtime. No clocks, stack sampling or numerical operations.
#define _GNU_SOURCE
#include "audit.hpp"
#include <dlfcn.h>
#include <unistd.h>
#include <atomic>
#include <cstdlib>
#include <cstring>
#include <cerrno>
#include <fstream>
#include <string>
#include <unordered_map>
#include <json.hpp>
extern "C" void *__libc_malloc(size_t);
extern "C" void *__libc_calloc(size_t,size_t);
extern "C" void *__libc_realloc(void*,size_t);
extern "C" void __libc_free(void*);
using U=unsigned long long;
constexpr unsigned N=8192,H=32768,L=256;
struct Node {unsigned parent,label;U entries,calls[3],bytes[3],failures[3],frees,nulls,bins[64],binbytes[64],hashes,hashbytes;};
struct SizeCount {size_t size;U calls,bytes;bool used;};
static SizeCount exact_sizes[16384];
static Node nodes[N];static unsigned slots[H],used=1;
static U counts[L],key_requests[L],key_unique[L],key_bytes[L],errors,tool_calls,tool_bytes;
static thread_local unsigned current,suppressed;
static bool enabled;
static std::atomic<unsigned> thread_count;
static thread_local bool registered;
static const char *extra_names[32];static unsigned extra_count;
extern "C" unsigned pa_named_id(const char* name){
 for(unsigned i=0;i<extra_count;++i)if(!std::strcmp(extra_names[i],name))return audit::label_count+i;
 if(extra_count>=32){++errors;return 0;}
 extra_names[extra_count]=name;return audit::label_count+extra_count++;
}
static const char* label_name(unsigned id){return id<audit::label_count?audit::names[id]:extra_names[id-audit::label_count];}
static void reg_thread(){if(!registered){registered=true;++thread_count;}}
extern "C" unsigned pa_enter(unsigned label) {
  reg_thread();unsigned previous=current;
  unsigned h=(current*2654435761u+label*2246822519u)&(H-1);
  while(slots[h]&&(nodes[slots[h]].parent!=current||nodes[slots[h]].label!=label))h=(h+1)&(H-1);
  if(!slots[h]){if(used==N){++errors;return previous;}slots[h]=used;nodes[used].parent=current;nodes[used].label=label;++used;}
  current=slots[h];++nodes[current].entries;++counts[label];return previous;
}
extern "C" void pa_leave(unsigned old){current=old;}
extern "C" void pa_count(unsigned label,U n){reg_thread();counts[label]+=n;}
extern "C" U pa_blob(unsigned label,const void*a,size_t na,const void*b,size_t nb,const void*c,size_t nc) {
  struct ToolScope {ToolScope(){++suppressed;}~ToolScope(){--suppressed;}} tool_scope;
  using Table=std::unordered_map<std::string,U>;
  static auto *tables=new std::unordered_map<unsigned,Table>;
  std::string key;size_t sizes[]={na,nb,nc};key.append((const char*)sizes,sizeof(sizes));
  if(na)key.append((const char*)a,na);if(nb)key.append((const char*)b,nb);if(nc)key.append((const char*)c,nc);
  auto &table=(*tables)[label];auto [it,inserted]=table.try_emplace(std::move(key),table.size()+1);
  ++key_requests[label];key_unique[label]+=inserted;key_bytes[label]+=na+nb+nc;
  return it->second;
}
static void record(unsigned api,size_t n,void*p,bool failure) {
  if(!enabled)return;
  if(suppressed){++tool_calls;tool_bytes+=n;return;}
  reg_thread();auto &v=nodes[current];++v.calls[api];v.bytes[api]+=n;v.failures[api]+=failure;
  unsigned bin=n?64-__builtin_clzll(n):0;if(bin>63)bin=63;
  ++v.bins[bin];v.binbytes[bin]+=n;(void)p;
  unsigned s=(n*2654435761u)&16383;while(exact_sizes[s].used&&exact_sizes[s].size!=n)s=(s+1)&16383;
  exact_sizes[s].used=true;exact_sizes[s].size=n;++exact_sizes[s].calls;exact_sizes[s].bytes+=n;
}
extern "C" void *malloc(size_t n){void*p=__libc_malloc(n);int e=errno;record(0,n,p,!p);errno=e;return p;}
extern "C" void *calloc(size_t n,size_t s){size_t bytes;bool over=__builtin_mul_overflow(n,s,&bytes);void*p=__libc_calloc(n,s);int e=errno;record(1,over?0:bytes,p,!p);errno=e;return p;}
extern "C" void *realloc(void *p,size_t n){void*q=__libc_realloc(p,n);int e=errno;record(2,n,q,!q&&n!=0);errno=e;return q;}
extern "C" void free(void*p){int e=errno;if(enabled&&!suppressed){reg_thread();++nodes[current].frees;nodes[current].nulls+=!p;}errno=e;__libc_free(p);}
static size_t(*real_hash)(const void*,size_t,size_t);
extern "C" size_t hash_bytes(const void*p,size_t n,size_t seed) asm("_ZSt11_Hash_bytesPKvmm");
extern "C" size_t hash_bytes(const void*p,size_t n,size_t seed){
  if(!real_hash){++suppressed;real_hash=(decltype(real_hash))dlsym(RTLD_NEXT,"_ZSt11_Hash_bytesPKvmm");--suppressed;}
  if(enabled&&!suppressed){pa_count(audit::hash_std,1);pa_count(audit::hash_std_bytes,n);++nodes[current].hashes;nodes[current].hashbytes+=n;}
  return real_hash(p,n,seed);
}
__attribute__((constructor)) static void start(){enabled=true;}
static std::string path(unsigned i){if(!i)return "outside_scopes";return path(nodes[i].parent)+"/"+label_name(nodes[i].label);}
__attribute__((destructor)) static void finish(){
 enabled=false;++suppressed;const char *file=getenv("PULSE_COUNT_OUTPUT");if(!file)return;
 using J=nlohmann::ordered_json;J j;
 j["method"]="Exact count-only isolated source instrumentation; no timestamps or CPU sampling";
 j["threads"]=thread_count.load();j["overflow_errors"]=errors;
 j["tool_allocation_requests_excluded"]=tool_calls;j["tool_requested_bytes_excluded"]=tool_bytes;
 j["metrics"]=J::object();j["keys"]=J::object();j["paths"]=J::array();j["exact_sizes"]=J::array();
 for(const auto&s:exact_sizes)if(s.used)j["exact_sizes"].push_back({{"size",s.size},{"calls",s.calls},{"bytes",s.bytes}});
 for(unsigned i=1;i<audit::label_count+extra_count;++i){j["metrics"][label_name(i)]=counts[i];
  if(key_requests[i])j["keys"][label_name(i)]={{"requests",key_requests[i]},{"distinct",key_unique[i]},{"repeats",key_requests[i]-key_unique[i]},{"bytes_examined",key_bytes[i]}};}
 for(unsigned i=0;i<used;++i){const auto&v=nodes[i];J a={{"path",path(i)},{"entries",v.entries},{"free_calls",v.frees},{"free_null",v.nulls},{"std_hash_calls",v.hashes},{"std_hash_bytes",v.hashbytes}};
  a["apis"]=J::array();for(unsigned k=0;k<3;++k)a["apis"].push_back({{"name",k==0?"malloc":k==1?"calloc":"realloc"},{"calls",v.calls[k]},{"bytes",v.bytes[k]},{"failures",v.failures[k]}});
  a["sizes"]=J::array();for(unsigned k=0;k<64;++k)if(v.bins[k])a["sizes"].push_back({{"bin",k},{"calls",v.bins[k]},{"bytes",v.binbytes[k]}});
  j["paths"].push_back(std::move(a));}
 std::ofstream(file)<<j.dump(2)<<'\n';
}
