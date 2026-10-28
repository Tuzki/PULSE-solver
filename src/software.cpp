#include "pulse/software.hpp"
#include "pulse/state_coordinates.hpp"
#include <cmath>
#include <bit>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <bcrypt.h>
#endif
namespace pulse::software {
std::string file_sha256(const std::string &path) {
#if defined(_WIN32)
  std::ifstream f(std::filesystem::path(path),std::ios::binary);
  require(bool(f),2,"SOFTWARE_FILE_MISSING","cannot read module dependency: "+path);
  std::vector<unsigned char> bytes((std::istreambuf_iterator<char>(f)),{});
  require(bytes.size()<=64*1024*1024,2,"SOFTWARE_FILE_SIZE","module dependency exceeds 64 MiB");
  struct Hash {
    BCRYPT_ALG_HANDLE algorithm=nullptr;BCRYPT_HASH_HANDLE hash=nullptr;
    std::vector<unsigned char> object;
    ~Hash(){if(hash)BCryptDestroyHash(hash);if(algorithm)BCryptCloseAlgorithmProvider(algorithm,0);}
  } h;
  require(BCryptOpenAlgorithmProvider(&h.algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)>=0,12,"SOFTWARE_HASH","SHA256 provider failed");
  DWORD size=0,written=0;
  require(BCryptGetProperty(h.algorithm,BCRYPT_OBJECT_LENGTH,reinterpret_cast<PUCHAR>(&size),sizeof(size),&written,0)>=0,12,"SOFTWARE_HASH","SHA256 property failed");
  h.object.resize(size);unsigned char digest[32];
  require(BCryptCreateHash(h.algorithm,&h.hash,h.object.data(),size,nullptr,0,0)>=0&&
          BCryptHashData(h.hash,bytes.data(),ULONG(bytes.size()),0)>=0&&
          BCryptFinishHash(h.hash,digest,sizeof(digest),0)>=0,12,"SOFTWARE_HASH","SHA256 failed");
  std::ostringstream s;s<<std::hex<<std::setfill('0');for(auto b:digest)s<<std::setw(2)<<unsigned(b);return s.str();
#else
  throw Error(2,"SOFTWARE_PLATFORM","native software modules currently require Windows");
#endif
}
namespace {
struct Loaded {
#if defined(_WIN32)
  HMODULE handle=nullptr;
  ~Loaded(){if(handle)FreeLibrary(handle);}
  pulse_software_entry_fn entry(const std::string &name) {
    if(name.empty())return nullptr;
    auto f=std::bit_cast<pulse_software_entry_fn>(GetProcAddress(handle,name.c_str()));
    require(f!=nullptr,2,"SOFTWARE_ENTRY","missing C entry: "+name);return f;
  }
#endif
  pulse_software_info info{};
};
double read(const RunState&s,const std::string&name) {
  return state_signal(s,name);
}
}
struct Data {
  const Model&m;
  std::map<std::string,std::unique_ptr<Loaded>> modules;
  struct Task {const Netlist::Task *spec;Loaded *module;pulse_software_entry_fn init,step;int self_part=-1;};
  std::vector<Task> tasks;
  Json identity=Json::array();
  explicit Data(const Model&model):m(model){}
  void call(const Task&t,const RunState&snapshot,RunState&candidate,
            std::map<std::string,double>&writes,bool initial,
            std::vector<Wakeup>&wakeups,std::vector<Json>*logs,uint64_t tx,size_t delta,
            uint32_t trigger_flags=0) {
    auto &spec=*t.spec;auto old=snapshot.software.at(spec.name);
    auto next=old;std::vector<double> inputs,outputs;
    for(auto &name:spec.inputs)inputs.push_back(read(snapshot,name));
    for(auto &name:spec.outputs)outputs.push_back(snapshot.regs.at(net_name(name)));
    pulse_software_call c{PULSE_SOFTWARE_ABI,sizeof(pulse_software_call),snapshot.at.seconds(),
      old.invocation,inputs.data(),inputs.size(),spec.parameters.data(),spec.parameters.size(),
      old.bytes.data(),next.bytes.data(),next.bytes.size(),outputs.data(),outputs.size(),
      std::numeric_limits<double>::quiet_NaN(),initial?PULSE_SW_INITIALIZE:trigger_flags};
    auto fn=initial?t.init:t.step;
    if(fn)require(fn(&c)==0,7,"SOFTWARE_EXECUTION","C task returned failure: "+spec.name,false,spec.source);
    require(c.abi_version==PULSE_SOFTWARE_ABI&&c.struct_size==sizeof(c)&&
      c.input_count==inputs.size()&&c.output_count==outputs.size()&&c.state_bytes==next.bytes.size(),
      7,"SOFTWARE_ABI_MUTATION","task modified immutable call metadata",false,spec.source);
    for(size_t j=0;j<outputs.size();++j) {
      auto name=net_name(spec.outputs[j]);double v=outputs[j];
      require(std::isfinite(v),7,"SOFTWARE_OUTPUT","nonfinite C output",false,spec.source);
      require(m.signals.at(name).type!=Signal::BOOL||v==0||v==1,7,"SOFTWARE_OUTPUT","BOOL output must be 0 or 1",false,spec.source);
      writes[name]=v;
    }
    if(!initial)++next.invocation;
    candidate.software[spec.name]=std::move(next);
    if(!std::isnan(c.next_delay)) {
      require(!initial&&std::isfinite(c.next_delay)&&c.next_delay>0&&t.self_part>=0,
        7,"SOFTWARE_WAKEUP","next_delay must be finite, positive and associated with a task wakeup",false,spec.source);
      wakeups.push_back({t.self_part,c.next_delay,spec.wake_trigger});
    }
    if(logs)logs->push_back({{"kind","SOFTWARE_TASK"},{"source",spec.name},
      {"time_canonical",snapshot.at.canonical()},{"time_seconds_display",snapshot.at.seconds()},
      {"delta",delta},{"transaction_id",tx},{"inputs",inputs},{"outputs",outputs},
      {"invocation",old.invocation},{"state_bytes",old.bytes.size()},
      {"trigger_flags",trigger_flags}});
  }
};
Session::Session(const Model&m):data_(std::make_unique<Data>(m)) {
  if(m.netlist.tasks.empty())return;
#if defined(_WIN32)
  for(const auto &task:m.netlist.tasks) {
    const auto &p=m.netlist.programs.at(task.program);
    if(!data_->modules.count(p.name)) {
      auto module=std::make_unique<Loaded>();
      auto manifest_path=p.binary+".json";std::ifstream manifest_file{std::filesystem::path(manifest_path)};
      require(bool(manifest_file),2,"SOFTWARE_MODULE_NOT_BUILT","build software first: scripts/build_software.py "+m.netlist.filename,false,p.source);
      Json manifest;manifest_file>>manifest;
      require(manifest.at("abi")==PULSE_SOFTWARE_ABI&&manifest.at("binary_sha256")==file_sha256(p.binary),2,"SOFTWARE_STALE_MODULE","module hash or ABI differs from build manifest",false,p.source);
      require(manifest.at("sources").get<std::vector<std::string>>()==p.sources&&
        manifest.at("inline_source").get<std::string>()==p.inline_source,2,"SOFTWARE_STALE_MODULE","code declarations changed since module build",false,p.source);
      for(auto &dependency:manifest.at("dependencies"))
        require(dependency.at("sha256")==file_sha256(dependency.at("path")),2,"SOFTWARE_STALE_MODULE","module source/header changed; rebuild software",false,p.source);
      auto dll=std::filesystem::absolute(std::filesystem::path(p.binary));
      module->handle=LoadLibraryExW(dll.wstring().c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
      require(module->handle!=nullptr,2,"SOFTWARE_LOAD","cannot load software DLL: "+p.binary,false,p.source);
      auto describe=std::bit_cast<pulse_software_describe_fn>(GetProcAddress(module->handle,"pulse_software_describe"));
      require(describe!=nullptr,2,"SOFTWARE_ABI","missing pulse_software_describe",false,p.source);
      const auto *info=describe();
      require(info&&info->abi_version==PULSE_SOFTWARE_ABI&&info->struct_size==sizeof(*info)&&
        info->state_bytes<=65536&&info->input_count<=128&&info->output_count<=128,
        2,"SOFTWARE_ABI","unsupported software descriptor or state size",false,p.source);
      module->info=*info;data_->modules[p.name]=std::move(module);
      data_->identity.push_back({{"program",p.name},{"binary_sha256",manifest.at("binary_sha256")},
        {"sources",manifest.at("sources")},{"dependencies",manifest.at("dependencies")},{"compiler",manifest.at("compiler")}});
    }
    auto *module=data_->modules.at(p.name).get();auto &info=module->info;
    require(info.input_count==task.inputs.size()&&info.output_count==task.outputs.size()&&
      info.parameter_count==task.parameters.size(),2,"SOFTWARE_PORTS","C descriptor does not match task bindings",false,task.source);
    int part=-1;
    for(int i:m.events)if(net_name(m.parts[i].raw.args[0])==task.wake_trigger)part=i;
    data_->tasks.push_back({&task,module,module->entry(task.init),module->entry(task.entry),part});
  }
#else
  throw Error(2,"SOFTWARE_PLATFORM","native software modules currently require Windows");
#endif
}
Session::~Session()=default;
void Session::initialize(RunState&s,Stats&) {
  for(auto &t:data_->tasks)s.software[t.spec->name].bytes.resize(t.module->info.state_bytes,0);
  RunState snapshot=s;auto writes=s.regs;std::vector<Wakeup> wakeups;
  for(auto &t:data_->tasks)data_->call(t,snapshot,s,writes,true,wakeups,nullptr,0,0);
  s.regs=std::move(writes);
}
std::vector<Wakeup> Session::execute(const RunState&snapshot,RunState&candidate,
 const std::set<std::string>&triggers,std::map<std::string,double>&writes,
 std::vector<Json>&logs,uint64_t tx,size_t delta) {
  std::vector<Wakeup>w;
  for(auto &t:data_->tasks) {
    uint32_t flags=0;
    if(triggers.count(t.spec->trigger)&&!t.spec->self_trigger)flags|=PULSE_SW_EXTERNAL;
    if(triggers.count(t.spec->wake_trigger))flags|=PULSE_SW_WAKEUP;
    if(flags)data_->call(t,snapshot,candidate,writes,false,w,&logs,tx,delta,flags);
  }
  return w;
}
Json Session::identity()const{return data_->identity;}
}
