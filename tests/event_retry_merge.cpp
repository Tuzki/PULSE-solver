#include "pulse/core.hpp"
#include "pulse/engineering.hpp"
#include "pulse/state_coordinates.hpp"
#include <fstream>
#include <iostream>
#include <cmath>
using namespace pulse;
void check(bool condition,const std::string&message){require(condition,12,"MERGE_REGRESSION",message);}
std::string document(const std::string&network){return "# PULSE Netlist v1.1\n\n## Parameters\n```pulse\n```\n\n## Network\n```pulse\n"+network+"\n```\n\n## Simulation\n```pulse\n.TRAN T_END=1 SAVE_DT=.1\n```\n\n## Layout\n```json\n{}\n```\n";}
void future_comparator_is_deferred(){
 auto m=compile(parse_markdown(document("MATH_ONE ONE = 1\nINT_X X ONE IC=-.5\nI1 0 N X\nR1 N 0 IV_TABLE=[(-1,-1),(0,0),(1,2)] RANGE=EXTEND\nCMP_C G X OP=GE THRESHOLD=.000000001\nEVENT_E E MODE=EDGE SOURCE=G EDGE=RISE"),"future_cmp.md"));
 Options o;o.atomic_time=2e-8;auto r=simulate(m,o);check(r.status=="COMPLETED",r.diagnostic.dump());
 std::optional<double>resistor,comparator;bool deferred=false;
 for(auto&e:r.events){
  if(e.value("kind","")=="ROOT"){
   for(auto&d:e.value("deferred_breakpoints",Json::array()))if(d["part"]=="CMP_C")deferred=true;
   for(auto&part:e.value("actual_changed_members",Json::array()))if(part=="R1"&&!resistor)resistor=e["time_seconds_display"];
  }
  if(e.value("kind","")=="TRIG"&&e.value("source","")=="E")comparator=e["time_seconds_display"];
 }
 check(resistor&&comparator&&*comparator>*resistor,"future CMP fired at the earlier constitutive knot");
 check(deferred,"future CMP was not explicitly deferred from its old prediction");
 check(std::abs(*resistor-.5)<1e-12&&std::abs(*comparator-.500000001)<4e-10,"event order or root location changed");
}
void reconstructed_direction(const std::string&path){
 std::ifstream in(path);Json j;in>>j;int n=j["initial"].size();Mode m;m.M.resize(n,n);Vector x(n);
 for(int i=0;i<n;i++){x[i]=j["initial"][i];for(int k=0;k<n;k++)m.M(i,k)=j["M"][i][k];}
 Vector guard(n);for(int i=0;i<n;i++)guard[i]=j["guard"][i];m.guards.push_back({guard,0,1,"CMP"});engineering::Flow flow(m,x);
 for(auto&sample:j["samples"]){auto state=flow.state(sample["time"]);check(std::abs(state[3]-sample["state"][3].get<double>())<1e-23,"finite fast-mode or difference reconstruction inaccurate");}
 double time=j["event_time"],expected=j["oriented_slope"];auto state=flow.state(time);double direct=guard.dot(m.M*state),along=flow.value(0,time,1);
 check(direct>0&&along>0,"reconstructed state reversed the event direction");
 check(std::abs(direct-expected)<1e-4*std::abs(expected)&&std::abs(along-expected)<1e-6*std::abs(expected),"event derivative lost agreement with the independent reference");
}
void public_storage_and_streaming(){
 auto m=compile(parse_markdown(document("V1 IN 0 DC=5\nR1 IN A R=.5\nL1 A B L=.001 IC_I=.1\nL2 B 0 L=.002 IC_I=.1\nR2 B 0 R=2\nC1 A 0 C=.000001 IC_V=1"),"physical_view.md"));
 Options o;o.t_end=1e-6;o.save_dt=1e-7;auto a=simulate(m,o);o.retain_history=false;auto b=simulate(m,o);check(a.status=="COMPLETED"&&b.status=="COMPLETED","ordinary RLC did not complete");
 check(a.times==b.times&&a.analog==b.analog&&a.digital==b.digital,"streaming changed saved samples");
 check(a.report["persistent_chart"]["enabled"]==true,"graph-derived numerical coordinates were not exercised");
 for(auto&p:m.parts)if(p.raw.kind=="L")check(std::abs(a.committed.physical[p.state]-number(p.raw.options.at("L"))*state_signal(a.committed,"I("+p.raw.id+")"))<1e-13,"public magnetic flux is not physical");
 check(!m.numerical_coordinates,"simulation changed the caller's Model coordinate convention");
}
int main(int argc,char**argv){try{future_comparator_is_deferred();reconstructed_direction(argv[1]);public_storage_and_streaming();std::cout<<"PASS deferred comparator, finite-fast-mode reconstruction, physical snapshots and streaming equivalence\n";return 0;}catch(const std::exception&e){std::cerr<<diagnostic(e).dump(2);return 1;}}
