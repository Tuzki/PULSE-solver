#include "pulse/core.hpp"
#include <chrono>
#include <iostream>
int main(int argc,char**argv){
  try{
    pulse::require(argc>=2,1,"CLI_USAGE","pulse-replay TRAJECTORY [--save-dt N] --out DIR");
    std::string destination="out-replay";std::optional<double>dt;
    for(int i=2;i<argc;i++){
      std::string option=argv[i];pulse::require(i+1<argc,1,"CLI_USAGE","missing replay option value");
      std::string value=argv[++i];
      if(option=="--out")destination=value;
      else if(option=="--save-dt")dt=pulse::number(value);
      else throw pulse::Error(1,"CLI_USAGE","unknown replay option");
    }
    auto start=std::chrono::steady_clock::now();
    auto result=pulse::replay_trajectory(argv[1],dt);pulse::Model model;
    pulse::write_result(model,result,destination);
    std::cout<<pulse::Json({{"status",result.status},{"samples",result.times.size()},
      {"waveform_validation",result.report.at("waveform_validation")},
      {"replay_and_write_seconds",std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count()}}).dump(2)<<'\n';
    return result.status=="COMPLETED"?0:1;
  }catch(const std::exception&e){std::cerr<<pulse::diagnostic(e).dump(2)<<'\n';return 1;}
}
