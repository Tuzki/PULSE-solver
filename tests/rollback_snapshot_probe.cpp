// Independent regression probe; never linked into pulse-solver.
#include "pulse/core.hpp"
#include <fstream>
#include <iostream>
#include <iomanip>
#include <sstream>
#if __has_include("pulse/cow_value.hpp")
#include "pulse/cow_value.hpp"
template<class T> const T& values(const pulse::CowValue<T>& x) { return x.read(); }
#endif
template<class T> const T& values(const T& x) { return x; }
using namespace pulse;
std::string bits(const Vector& v) {
  std::ostringstream s; s << std::hex << std::setfill('0');
  auto p=reinterpret_cast<const unsigned char*>(v.data());
  for(size_t i=0;i<size_t(v.size())*sizeof(double);++i) s<<std::setw(2)<<unsigned(p[i]);
  return s.str();
}
int main(int argc,char**argv) { try {
  require(argc==2,1,"PROBE_USAGE","rollback_snapshot_probe NETLIST");
  std::ifstream f(argv[1]); std::string text((std::istreambuf_iterator<char>(f)),{});
  auto model=compile(parse_markdown(text,argv[1])); Json all=Json::object();
  for(const auto& point:{"after_queue","after_reg","after_mode","after_propagation","before_output","retry_after_closure"}) {
    Options o; o.t_end=.5; o.trajectory_output=true; o.retain_history=false; o.fault=point;
    auto r=simulate(model,o); const auto& s=r.committed;
    require(r.status!="COMPLETED",12,"FAULT_NOT_REACHED",point);
    Json sw=Json::object(),agenda=Json::array();
    for(const auto& [name,v]:values(s.software)) sw[name]={{"bytes",v.bytes},{"invocation",v.invocation}};
    for(const auto& v:values(s.agenda)) agenda.push_back({{"seconds",v.at.seconds()},{"origin",v.origin},{"part",v.part},{"cycle",v.cycle},{"generation",v.generation},{"trigger",v.trigger}});
    all[point]={{"status",r.status},{"diagnostic",r.diagnostic},{"time_origin",s.time_origin},
      {"seconds",s.at.seconds()},{"internal_bits",bits(s.internal)},{"physical_bits",bits(s.physical)},
      {"regs",values(s.regs)},{"software",sw},{"agenda",agenda},{"generations",values(s.generations)},
      {"version",s.version},{"mode_id",s.mode.id},{"mode_bools",s.mode.bools},{"mode_segments",s.mode.segments},
      {"events",r.events},{"transactions",r.stats.transactions},
      {"software_outputs",r.report.at("software_final_outputs")},
      {"portfolio_failures",r.report.at("algorithm_portfolio").at("failures")}};
  }
  std::cout << all.dump(2) << '\n'; return 0;
} catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; } }
