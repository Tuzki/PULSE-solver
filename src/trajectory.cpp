#include "pulse/trajectory.hpp"
#include "pulse/software.hpp"
#include "pulse/pevt.hpp"
#include <bit>
#include <fstream>
#include <limits>
namespace pulse {
namespace {
constexpr size_t limit=64*1024*1024; // explicit v1 per-stream resource limit
constexpr size_t archive_limit=512*1024*1024; // archive files, not C modules
void u64(std::vector<uint8_t>&b,uint64_t v){for(int i=0;i<8;i++)b.push_back(uint8_t(v>>(i*8)));}
void real(std::vector<uint8_t>&b,double v){u64(b,std::bit_cast<uint64_t>(v));}
void time(std::vector<uint8_t>&b,Time t){u64(b,uint64_t(t.whole));u64(b,t.tick);u64(b,t.subtick);}
Json encode_matrix(const Matrix&m){
  std::vector<double> values;if(m.size())values.assign(m.data(),m.data()+m.size());
  return {{"rows",m.rows()},{"cols",m.cols()},{"data",values}};
}
Matrix decode_matrix(const Json&j){
  auto r=j.at("rows").get<size_t>(),c=j.at("cols").get<size_t>();
  require(r<=10000&&c<=10000&&r*c<=1000000,11,"TRAJECTORY_SHAPE","invalid matrix shape");
  auto v=j.at("data").get<std::vector<double>>();require(v.size()==r*c,11,"TRAJECTORY_SHAPE","matrix payload size differs");
  Matrix m(r,c);for(size_t i=0;i<v.size();i++)m.data()[i]=v[i];
  require(m.allFinite(),11,"TRAJECTORY_NONFINITE","nonfinite numerical template");return m;
}
Json encode(const Mode&m){
  Json j={{"M",encode_matrix(m.M)},{"observations",encode_matrix(m.observations)},
    {"constraints",encode_matrix(m.constraints)},{"residual_map",encode_matrix(m.residual_map)},
    {"residual_reference",encode_matrix(m.residual_reference)},
    {"lift",encode_matrix(m.invariant_lift)},{"generator",encode_matrix(m.invariant_generator)},
    {"reduce",encode_matrix(m.invariant_reduce)},{"strategy",m.numerical_strategy},
    {"maps",Json::object()},{"bools",m.bools},{"segments",Json::array()},{"guards",Json::array()}};
  j["observer_maps"]=m.observer_maps;j["observer_rows"]=m.observer_rows;
  for(auto&[n,v]:m.maps)j["maps"][n]=encode_matrix(v);
  for(auto&[part,region]:m.segments)j["segments"].push_back({part,region});
  for(auto&g:m.guards)j["guards"].push_back({{"row",encode_matrix(g.row)},{"part",g.part},
    {"direction",g.direction},{"kind",g.kind},{"knot",g.knot},{"segment",g.segment},{"step",g.step}});
  return j;
}
Mode decode(const Json&j){
  Mode m;m.M=decode_matrix(j.at("M"));m.observations=decode_matrix(j.at("observations"));
  m.constraints=decode_matrix(j.at("constraints"));m.residual_map=decode_matrix(j.at("residual_map"));
  m.residual_reference=decode_matrix(j.at("residual_reference"));
  m.invariant_lift=decode_matrix(j.at("lift"));m.invariant_generator=decode_matrix(j.at("generator"));m.invariant_reduce=decode_matrix(j.at("reduce"));
  m.observer_maps=j.value("observer_maps",std::set<std::string>{});m.observer_rows=j.value("observer_rows",std::vector<int>{});
  m.numerical_strategy=j.at("strategy");m.bools=j.at("bools").get<std::map<std::string,bool>>();
  for(auto it=j.at("maps").begin();it!=j.at("maps").end();++it){Matrix a=decode_matrix(it.value());require(a.cols()==1,11,"TRAJECTORY_SHAPE","observation is not a column");m.maps[it.key()]=a;}
  for(auto&v:j.at("segments"))m.segments[v.at(0).get<int>()]=v.at(1).get<int>();
  for(auto&v:j.at("guards")){
    Mode::Guard g;g.row=decode_matrix(v.at("row"));g.part=v.at("part");g.direction=v.at("direction");g.kind=v.at("kind").get<std::string>();
    g.knot=v.at("knot");g.segment=v.at("segment");g.step=v.at("step");m.guards.push_back(std::move(g));
  }
  return m;
}
void write(const std::filesystem::path&p,const std::string&s){std::ofstream f(p,std::ios::binary);f.exceptions(std::ios::failbit|std::ios::badbit);f<<s;}
Json json(const std::filesystem::path&p){std::ifstream f(p,std::ios::binary);require(bool(f),11,"TRAJECTORY_IO","cannot read "+p.string());Json j;f>>j;return j;}
struct Reader{
  std::vector<uint8_t>b;size_t i=0;
  uint64_t word(){require(i+8<=b.size(),11,"TRAJECTORY_TRUNCATED","truncated record");uint64_t v=0;for(int k=0;k<8;k++)v|=uint64_t(b[i++])<<(8*k);return v;}
  Time at(){Time t;t.whole=int64_t(word());t.tick=word();t.subtick=word();require(t.whole>=0,11,"TRAJECTORY_TIME","negative time");return t;}
  Vector vector(size_t n){Vector v(n);for(size_t k=0;k<n;k++)v[k]=std::bit_cast<double>(word());require(v.allFinite(),11,"TRAJECTORY_NONFINITE","nonfinite archived state");return v;}
  RunState state(size_t n,const std::vector<Mode>&m){
    RunState s;s.at=at();auto mid=word(),fid=word();require(mid<m.size()&&(fid==UINT64_MAX||fid<m.size()),11,"TRAJECTORY_TEMPLATE","invalid template index");
    s.mode=m[mid];s.internal=vector(n);auto offset=at();auto anchor=vector(n);
    if(fid!=UINT64_MAX)s.electrical_flow=std::make_shared<engineering::Flow>(engineering::Flow::restore_archive(m[fid],anchor,offset));
    return s;
  }
};
}
Json archive_encode_mode(const Mode&m){return encode(m);}
Mode archive_decode_mode(const Json&j){return decode(j);}
uint32_t Trajectory::mode(const Mode&m){
  auto root=pool_.encode(encode(m));auto found=ids_.find(root);if(found!=ids_.end())return found->second;
  require(ids_.size()<100000,11,"TRAJECTORY_LIMIT","too many templates");
  auto id=uint32_t(ids_.size());ids_[root]=id;templates_.push_back(root);return id;
}
void Trajectory::state(const RunState&s){
  require(size_t(s.internal.size())==dimension_,11,"TRAJECTORY_SHAPE","state dimension changed");
  time(bytes_,s.at);u64(bytes_,mode(s.mode));u64(bytes_,s.electrical_flow?mode(s.electrical_flow->archive_mode()):UINT64_MAX);
  for(double v:s.internal)real(bytes_,v);
  time(bytes_,s.electrical_flow?s.electrical_flow->archive_offset():Time{});
  const Vector&anchor=s.electrical_flow?s.electrical_flow->archive_anchor():s.internal;
  for(double v:anchor)real(bytes_,v);
  require(bytes_.size()<=limit,11,"TRAJECTORY_LIMIT","v1 record stream exceeds 64 MiB");
}
void Trajectory::initial(const RunState&s){initial(Model{},s);}
void Trajectory::initial(const Model&m,const RunState&s){pevt_=std::make_shared<PevtArchive>(m,s);}
void Trajectory::append(const RunState&a,const RunState&b){
  if(pevt_){pevt_->append(a,b,{},0);return;}
  const auto checkpoint=bytes_.size();
  try{state(a);state(b);++records_;}catch(...){bytes_.resize(checkpoint);throw;}
}
void Trajectory::append(const RunState&a,const RunState&b,const std::vector<Json>&logs,uint64_t transaction){
  require(bool(pevt_),11,"PEVT_CAPTURE","event archive not initialized");pevt_->append(a,b,logs,transaction);
}
void Trajectory::write(const std::filesystem::path&dir,const Result&r)const{
  if(pevt_){std::filesystem::create_directories(dir);pulse::write(dir/"simulation_report.json",r.report.dump(2)+"\n");pevt_->write(dir/"out.pevt",r);return;}
  std::filesystem::create_directories(dir);
  pulse::write(dir/"simulation_report.json",r.report.dump(2)+"\n"); // preserve state even if archive I/O fails
  {std::ofstream f(dir/"segments.bin",std::ios::binary);f.exceptions(std::ios::failbit|std::ios::badbit);f.write(reinterpret_cast<const char*>(bytes_.data()),std::streamsize(bytes_.size()));}
  pool_.write(dir/"templates.bin",templates_);
  {std::ofstream log(dir/"event_log.jsonl",std::ios::binary);log.exceptions(std::ios::failbit|std::ios::badbit);for(auto&e:r.events)log<<e.dump()<<'\n';}
  Json manifest={{"format","PULSE_TRAJECTORY"},{"version",2},{"byte_order","little"},
    {"time_encoding","signed seconds + uint64 tick + uint64 subtick; T128"},
    {"dimension",dimension_},{"records",records_},{"templates",templates_.size()},
    {"long_double_digits",std::numeric_limits<long double>::digits},
    {"long_double_max_exponent",std::numeric_limits<long double>::max_exponent},
    {"cache_policy","rebuild derived caches with original Flow constructor; original anchor and T128 offset retained"},
    {"analog_names",r.analog_names},{"digital_names",r.digital_names},
    {"save_dt",r.save_dt},{"T_atom",r.t_atom},{"t_end",r.t_end},
    {"waveform_validation","DEFERRED_TO_REPLAY"},{"sha256",Json::object()}};
  for(auto name:{"segments.bin","templates.bin","event_log.jsonl","simulation_report.json"})manifest["sha256"][name]=software::file_sha256((dir/name).string(),archive_limit);
  pulse::write(dir/"metadata.json",manifest.dump(2)+"\n");
}
Result Trajectory::read(const std::filesystem::path&dir,const std::function<void(Result&,const RunState&,const RunState&,bool)>&emit){
  if(std::filesystem::is_regular_file(dir))return PevtArchive::read(dir,emit);
  if(std::filesystem::exists(dir/"out.pevt"))return PevtArchive::read(dir/"out.pevt",emit);
  auto meta=json(dir/"metadata.json");
  const int version=meta.at("version");
  require(meta.at("format")=="PULSE_TRAJECTORY"&&(version==1||version==2),11,"TRAJECTORY_VERSION","unsupported trajectory format");
  require(meta.at("long_double_digits")==std::numeric_limits<long double>::digits&&meta.at("long_double_max_exponent")==std::numeric_limits<long double>::max_exponent,11,"TRAJECTORY_PRECISION","replay precision differs");
  const auto template_file=version==1?"templates.json":"templates.bin";
  for(auto name:{"segments.bin",template_file,"event_log.jsonl","simulation_report.json"})require(meta.at("sha256").at(name)==software::file_sha256((dir/name).string(),archive_limit),11,"TRAJECTORY_HASH","trajectory stream checksum mismatch");
  auto n=meta.at("dimension").get<size_t>(),count=meta.at("records").get<size_t>();
  require(n>0&&n<=10000&&count<=10000000,11,"TRAJECTORY_SHAPE","invalid record dimensions");
  std::vector<Mode> modes;
  auto add_mode=[&](const Json&v){
    auto m=decode(v);require(size_t(m.M.rows())==n&&size_t(m.M.cols())==n,11,"TRAJECTORY_SHAPE","template/state dimension differs");
    for(auto&[name,row]:m.maps)require(size_t(row.size())==n,11,"TRAJECTORY_SHAPE","observation dimension differs");
    for(auto&g:m.guards)require(size_t(g.row.size())==n,11,"TRAJECTORY_SHAPE","guard dimension differs");
    modes.push_back(std::move(m));
  };
  if(version==1){auto templates=json(dir/template_file);require(templates.is_array()&&templates.size()<=100000&&meta.at("templates")==templates.size(),11,"TRAJECTORY_SHAPE","invalid template count");for(auto&v:templates){add_mode(v);v=Json();}}
  else {auto [pool,roots]=TrajectoryPool::read(dir/template_file);require(meta.at("templates")==roots.size(),11,"TRAJECTORY_SHAPE","template count differs");for(auto root:roots)add_mode(pool.decode(root));}
  require(std::filesystem::file_size(dir/"segments.bin")<=limit,11,"TRAJECTORY_LIMIT","record stream exceeds 64 MiB");
  Reader reader;{std::ifstream f(dir/"segments.bin",std::ios::binary);reader.b.assign(std::istreambuf_iterator<char>(f),{});}
  Result out;out.report=json(dir/"simulation_report.json");out.status=out.report.at("status");out.diagnostic=out.report.at("diagnostic");
  out.save_dt=meta.at("save_dt");out.t_atom=meta.at("T_atom");out.t_end=meta.at("t_end");
  out.analog_names=meta.at("analog_names").get<std::vector<std::string>>();out.digital_names=meta.at("digital_names").get<std::vector<std::string>>();
  out.evidence=out.report.at("evidence");
  auto initial=reader.state(n,modes);out.committed=initial;emit(out,initial,initial,true);
  for(size_t k=0;k<count;k++){
    auto old=reader.state(n,modes),next=reader.state(n,modes);
    require(old.at==out.committed.at&&next.at>=old.at,11,"TRAJECTORY_TIME","noncontiguous trajectory records");
    emit(out,old,next,false);out.committed=std::move(next);
  }
  require(reader.i==reader.b.size(),11,"TRAJECTORY_TRAILING","trailing trajectory bytes");
  std::ifstream events(dir/"event_log.jsonl");std::string line;while(std::getline(events,line))if(!line.empty())out.events.push_back(Json::parse(line));
  return out;
}
}
