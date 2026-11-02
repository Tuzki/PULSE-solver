#include "pulse/trajectory.hpp"
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include "pulse/software.hpp"
using namespace pulse;
void check(bool ok,const char*message){if(!ok)throw std::runtime_error(message);}
int main(int argc,char**argv){
  check(argc==3,"fixture and scratch paths required");
  std::filesystem::path fixtures=argv[1],scratch=argv[2];
  // Many almost-identical templates must share their unchanged data, while
  // signed zeros and adjacent binary64 values remain distinct and round-trip.
  {
    TrajectoryPool pool;std::vector<uint32_t> roots;size_t naive=0;
    Json base={{"matrix",Json::array()},{"control",0.0}};
    for(int i=0;i<2049;++i)base["matrix"].push_back(0.0);
    for(int i=0;i<500;++i){base["control"]=double(i);base["matrix"][1030]=std::nextafter(double(i),INFINITY);naive+=base.dump().size();roots.push_back(pool.encode(base));}
    auto plus=pool.encode(0.0),minus=pool.encode(-0.0);check(plus!=minus,"signed zero was coalesced");
    check(std::bit_cast<uint64_t>(pool.decode(minus).get<double>())==std::bit_cast<uint64_t>(-0.0),"signed zero was lost");
    std::filesystem::create_directories(scratch);auto path=scratch/"shared-templates.bin";pool.write(path,roots);
    check(std::filesystem::file_size(path)<naive/10,"almost-identical templates grew as full copies");
    auto [restored,ids]=TrajectoryPool::read(path);check(ids.size()==500,"template roots lost");
    for(int i=0;i<500;++i){base["control"]=double(i);base["matrix"][1030]=std::nextafter(double(i),INFINITY);check(restored.decode(ids[i]).dump()==base.dump(),"shared template roundtrip differs");}
    std::filesystem::resize_file(path,std::filesystem::file_size(path)-1);
    bool rejected=false;try{TrajectoryPool::read(path);}catch(const Error&e){rejected=e.subcode=="TRAJECTORY_TRUNCATED";}
    check(rejected,"truncated shared pool accepted");
  }
  for(auto name:{"linear_rc","buck_ccm","boost_dcm"}){
    auto file=fixtures/(std::string(name)+".md");std::ifstream f(file);check(bool(f),"fixture missing");
    std::string text((std::istreambuf_iterator<char>(f)),{});auto model=compile(parse_markdown(text,file.string()));
    Options options;options.retain_history=true;
    auto original=simulate(model,options);check(original.status=="COMPLETED","original did not complete");
    options.trajectory_output=true;auto trace=simulate(model,options);
    check(trace.status==original.status,"trajectory completion differs");
    check(trace.times.empty()&&trace.analog.empty(),"trajectory materialized dense output");
    check(trace.report.at("internal_state")==original.report.at("internal_state"),"final internal state changed");
    check(trace.events==original.events,"event semantics changed");
    auto dir=scratch/name;write_result(model,trace,dir);auto replay=replay_trajectory(dir);
    Json expected=Json::array();for(auto&segment:original.segments){auto&s=segment.state;std::vector<double>x(s.internal.data(),s.internal.data()+s.internal.size());Json regions=Json::array();for(auto [part,region]:s.mode.segments)regions.push_back({part,region});expected.push_back({{"time",s.at.canonical()},{"x",x},{"bools",s.mode.bools},{"regions",regions}});}
    {std::ofstream out(dir/"expected-slices.json");out<<expected;}
    check(replay.times==original.times,"replay time axis differs");
    check(replay.analog.size()==original.analog.size(),"sample count differs");
    check(std::memcmp(replay.analog.data(),original.analog.data(),original.analog.size()*sizeof(float))==0,"analog samples differ bitwise");
    check(replay.digital==original.digital,"digital values differ");
    check(replay.events==original.events,"replay event log differs");
    check(replay.report.at("waveform_validation")=="PASSED","replay checks not completed");
    if(original.committed.electrical_flow){
      auto flow=original.committed.electrical_flow->continued(original.committed.electrical_flow->archive_mode(),.125);
      auto restored=engineering::Flow::restore_archive(flow.archive_mode(),flow.archive_anchor(),flow.archive_offset());
      auto a=flow.state(.03125),b=restored.state(.03125);
      check(a.size()==b.size()&&std::memcmp(a.data(),b.data(),size_t(a.size())*sizeof(double))==0,"continuation anchor/offset not preserved");
    }
    auto path=dir/"out.pevt";std::ifstream input(path,std::ios::binary);std::vector<uint8_t> original_file((std::istreambuf_iterator<char>(input)),{});input.close();
    auto put_file=[&](const std::vector<uint8_t>&b){std::ofstream out(path,std::ios::binary);out.write(reinterpret_cast<const char*>(b.data()),b.size());};
    auto corrupted=original_file;corrupted[80]^=1;put_file(corrupted);
    bool rejected=false;try{replay_trajectory(dir);}catch(const Error&e){rejected=e.subcode=="PEVT_HASH";}
    check(rejected,"corrupted stream was accepted");
    auto word=[&](size_t pos){uint64_t v=0;for(int i=0;i<8;++i)v|=uint64_t(original_file[pos+i])<<(8*i);return v;};auto length=word(24);
    Json metadata=Json::parse(original_file.begin()+80,original_file.begin()+80+length);metadata["numerical_context"]["long_double_digits"]=1;auto encoded=metadata.dump();
    std::vector<uint8_t> wrong(original_file.begin(),original_file.begin()+80);for(int i=0;i<8;++i){wrong[24+i]=uint8_t(uint64_t(encoded.size())>>(8*i));wrong[32+i]=wrong[24+i];}
    std::vector<uint8_t> payload(encoded.begin(),encoded.end());auto hash=software::buffer_sha256(payload);std::copy(hash.begin(),hash.end(),wrong.begin()+48);wrong.insert(wrong.end(),payload.begin(),payload.end());wrong.insert(wrong.end(),original_file.begin()+80+length,original_file.end());put_file(wrong);
    rejected=false;try{replay_trajectory(dir);}catch(const Error&e){rejected=e.subcode=="TRAJECTORY_PRECISION";}
    check(rejected,"different replay precision was accepted");
    wrong=original_file;wrong.pop_back();put_file(wrong);rejected=false;try{replay_trajectory(dir);}catch(const Error&e){rejected=e.subcode=="PEVT_TRUNCATED";}check(rejected,"truncated file accepted");put_file(original_file);
  }
  // Deferred materialization must still run the original per-sample check.
  Result invalid;invalid.status="COMPLETED";invalid.evidence="ENGINEERING_POINT_TRAJECTORY";
  invalid.save_dt=.1;invalid.t_end=.1;invalid.analog_names={"X"};
  RunState state;state.internal=Vector::Ones(2);state.mode.M=Matrix::Zero(2,2);
  state.mode.maps["X"]=Vector::Constant(2,std::numeric_limits<double>::max());
  invalid.trajectory=std::make_shared<Trajectory>();invalid.trajectory->initial(state);
  invalid.report={{"status","COMPLETED"},{"diagnostic",Json::object()},{"evidence",invalid.evidence}};
  invalid.trajectory->write(scratch/"nonfinite",invalid);
  bool rejected=false;try{replay_trajectory(scratch/"nonfinite");}catch(const Error&e){rejected=e.subcode=="OUTPUT_NONFINITE";}
  check(rejected,"deferred waveform finite-value check was bypassed");
  std::cout<<"Trajectory equivalence, exact continuation, corruption and precision checks passed\n";
}
