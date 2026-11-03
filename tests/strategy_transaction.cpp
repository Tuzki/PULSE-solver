#include "pulse/core.hpp"
#include "pulse/engineering.hpp"
#include "pulse/solver_strategy.hpp"
#include "pulse/state_coordinates.hpp"
#include <iostream>
#include <cmath>
using namespace pulse;
void check(bool ok,const std::string&why){if(!ok)throw std::runtime_error(why);}
std::string document(){return R"(# PULSE Netlist v1.1

## Parameters
```pulse
```

## Network
```pulse
V1 IN 0 DC=5
R1 IN A R=.5
L1 A B L=.001 IC_I=.1
L2 B 0 L=.002 IC_I=.1
R2 B 0 R=2
C1 A 0 C=.000001 IC_V=1
SW_PATH B D G RON=.25 ROFF=10
R3 D 0 R=1
MATH_ONE ONE = 1000000
INT_X X ONE IC=-.5
CMP_POS POS X OP=GT THRESHOLD=0
CMP_NEG NEG X OP=LT THRESHOLD=0
EVENT_SET SET MODE=AT AT=.75u
EVENT_RESET RESET MODE=AT AT=.9u
REG_GATE G MODE=SR SET=SET RESET=RESET PRIORITY=RESET IC=0
```

## Simulation
```pulse
.TRAN T_END=1u SAVE_DT=.1u
```

## Layout
```json
{}
```
)";}
void explicit_closure(){
 auto m=compile(parse_markdown(document(),"strategy_transaction.md"));m.numerical_coordinates=true;
 check(persistent_chart(m).active,"test failed to exercise a nontrivial storage chart");
 Stats stats;ScopedModeCache cache(m,128);RunState initial;
 initial.internal=persistent_encode(m,m.initial);initial.physical=m.initial;initial.regs={{"G",0}};
 initial.mode=engineering::initial_mode(m,initial.internal,initial.regs.read(),stats);
 for(int algorithm=0;algorithm<3;algorithm++){
  auto mode=portfolio_mode(m,initial,algorithm,stats);
  check(mode.numerical_strategy==algorithm,"prediction provenance wrong");
  check((mode.elimination_path.find("QR")!=std::string::npos)==(algorithm==1),"prediction factorization wrong");
  engineering::Flow flow(mode,initial.internal);
  auto roots=engineering::next_events(mode,flow,.6e-6,1e-14);
  check(roots.candidates.size()==2,"one physical crossing must predict both comparators");
  double at=roots.candidates.front().time;
  check(std::abs(at-.5e-6)<1e-14,"analytical crossing time changed");
  check(roots.candidates[0].time==roots.candidates[1].time,"same crossing times differ");
  RunState snap=initial;snap.mode=mode;snap.internal=flow.state(at);snap.at=Time::from(at);
  snap.electrical_strategy=algorithm;
  snap.electrical_flow=std::make_shared<engineering::Flow>(flow.continued(mode,at));
  std::vector<Mode::Guard> candidates;std::set<int>seeds;
  for(auto&root:roots.candidates){candidates.push_back(mode.binding.read().guards[root.guard]);seeds.insert(mode.binding.read().guards[root.guard].part);}
  Json details;auto before=snap.internal;
  auto next=engineering::update_mode(m,snap,snap.internal,snap.regs.read(),candidates,seeds,stats,&details,algorithm);
  check(next.numerical_strategy==algorithm&&details["numerical_strategy"]==algorithm,"closure silently changed strategy");
  check(next.elimination_path==mode.elimination_path,"comparator closure changed factorization");
  check(next.bools.at("POS")&&!next.bools.at("NEG"),"joint complementary comparator update wrong");
  check(snap.electrical_flow->compatible(next),"no-op electrical event lost trajectory");
  auto continued=snap.electrical_flow->continued(next,0);
  check(continued.observe(next.binding.read().maps.at("X"),1e-8)==flow.observe(mode.binding.read().maps.at("X"),at+1e-8),"original anchor lost at comparator event");
  // A real gate transition must retain strategy but replace the electrical flow.
  RunState switched=snap;switched.mode=next;switched.internal=continued.state(.1e-6);
  switched.electrical_flow=std::make_shared<engineering::Flow>(continued.continued(next,.1e-6));
  auto regs=switched.regs.read();regs["G"]=1;auto untouched=switched.internal;
  auto right=engineering::update_mode(m,switched,switched.internal,regs,{}, {},stats,&details,algorithm);
  check(right.numerical_strategy==algorithm,"gate closure silently changed strategy");
  check((right.definition.read().M-next.definition.read().M).norm()>0,"test gate did not alter electrical equations");
  check(!switched.electrical_flow->compatible(right),"true topology change reused incoming flow");
  check((untouched-switched.internal).isZero(0),"mode closure changed storage state");
  // Exercise hot template entries as well as cold construction.
  auto hot=engineering::update_mode(m,switched,switched.internal,regs,{}, {},stats,&details,algorithm);
  check((hot.definition.read().M-right.definition.read().M).isZero(0)&&hot.numerical_strategy==algorithm,"hot cache changed strategy or equation chart");
  check((before-snap.internal).isZero(0),"closure mutated the checkpoint");
 }
}
void whole_attempt_rollback(){
 auto m=compile(parse_markdown(document(),"strategy_retry.md"));Options o;
 o.fault="retry_after_closure";auto r=simulate(m,o);
 check(r.status=="STOPPED_UNRESOLVED",r.diagnostic.dump());
 check(r.report["transactions"]==0,"failed attempts committed part of a transaction");
 const auto &failures=r.report["algorithm_portfolio"]["failures"];
 check(failures.size()==3,"all three staged strategies were not exercised");
 for(int k=0;k<3;k++){
  const auto&e=failures[k];check(e["algorithm"]==k,"retry order changed");
  check(e["checkpoint_seconds"]==0,"strategy restarted from a partial event state");
  check(std::abs(e["candidate_seconds"].get<double>()-.5e-6)<1e-14,"strategy did not recompute the common event");
  check(e["diagnostic"]["subcode"]=="INJECTED_EVENT_CLOSURE_REJECTION","attempt did not complete consistent closure before test rejection");
 }
 check(!r.committed.mode.bools.at("POS")&&r.committed.mode.bools.at("NEG"),"failed closure leaked comparator bits");
 check(r.committed.regs.read().at("G")==0&&r.committed.agenda.read().size()==2,"failed closure leaked gate/queue changes");
 check(std::abs(state_signal(r.committed,"X")+.5)<1e-12,"failed retry changed integrator storage");
}
int main(){try{explicit_closure();whole_attempt_rollback();std::cout<<"PASS three strategies, nontrivial chart, simultaneous comparators, preserved flow, true gate change, cache and whole-attempt rollback\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
