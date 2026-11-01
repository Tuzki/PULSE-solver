#include "pulse/trajectory.hpp"
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
using namespace pulse;
void check(bool ok,const char*message){if(!ok)throw std::runtime_error(message);}
int main(int argc,char**argv){
  check(argc==3,"fixture and scratch paths required");
  std::filesystem::path fixtures=argv[1],scratch=argv[2];
  for(auto name:{"linear_rc","buck_ccm","boost_dcm"}){
    auto file=fixtures/(std::string(name)+".md");std::ifstream f(file);check(bool(f),"fixture missing");
    std::string text((std::istreambuf_iterator<char>(f)),{});auto model=compile(parse_markdown(text,file.string()));
    Options options;options.retain_history=false;
    auto original=simulate(model,options);check(original.status=="COMPLETED","original did not complete");
    options.trajectory_output=true;auto trace=simulate(model,options);
    check(trace.status==original.status,"trajectory completion differs");
    check(trace.times.empty()&&trace.analog.empty(),"trajectory materialized dense output");
    check(trace.report.at("internal_state")==original.report.at("internal_state"),"final internal state changed");
    check(trace.events==original.events,"event semantics changed");
    auto dir=scratch/name;write_result(model,trace,dir);auto replay=replay_trajectory(dir);
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
    auto path=dir/"segments.bin";std::fstream stream(path,std::ios::in|std::ios::out|std::ios::binary);
    char first;stream.read(&first,1);char corrupted=first^1;stream.seekp(0);stream.write(&corrupted,1);stream.close();
    bool rejected=false;try{replay_trajectory(dir);}catch(const Error&e){rejected=e.subcode=="TRAJECTORY_HASH";}
    check(rejected,"corrupted stream was accepted");
    {std::fstream restore(path,std::ios::in|std::ios::out|std::ios::binary);restore.write(&first,1);}
    auto metadata_path=dir/"metadata.json";Json metadata;{std::ifstream in(metadata_path);in>>metadata;}
    metadata["long_double_digits"]=1;{std::ofstream out(metadata_path);out<<metadata;}
    rejected=false;try{replay_trajectory(dir);}catch(const Error&e){rejected=e.subcode=="TRAJECTORY_PRECISION";}
    check(rejected,"different replay precision was accepted");
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
