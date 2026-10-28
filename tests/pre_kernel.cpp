#define main inherited_engineering_main
#include "engineering_events.cpp"
#undef main

namespace {
std::vector<Json> roots(const Result&r) {
  std::vector<Json> out;
  for(const auto&e:r.events)if(e.value("kind","")=="ROOT")out.push_back(e);
  return out;
}
void nearby_knots_keep_physical_times() {
  Options o;o.atomic_time=2e-8;
  auto r=run("I_A 0 A DC=1\nC_A A 0 QV_TABLE=[(0,0),(1,1),(2,3)] IC_Q=.5 RANGE=EXTEND\n"
             "I_B 0 B DC=1\nC_B B 0 QV_TABLE=[(0,0),(1,1),(2,3)] IC_Q=.499999999 RANGE=EXTEND", "1", ".1",o);
  complete(r);auto es=roots(r);check(es.size()==2,"nearby knots were collapsed or lost");
  near(es[0]["time_seconds_display"],.5,2e-14,"first knot time");
  near(es[1]["time_seconds_display"],.500000001,2e-14,"second knot time");
  check(es[0]["actual_changed_members"].size()==1,"unreached second knot switched early");
  check(es[0]["deferred_breakpoints"].size()==1,"deferred knot identity missing");
  check(es[0]["mode_update"]["directions"][0]["event_type"]=="CONSTITUTIVE_BREAKPOINT","typed knot evidence missing");
  near(value(r,"V(A)"),1.25,2e-12,"first capacitor constitutive value");
  near(value(r,"V(B)"),1.2499999995,2e-12,"second capacitor constitutive value");
}
void simultaneous_knots_are_joint() {
  auto r=run("I_A 0 A DC=1\nC_A A 0 QV_TABLE=[(0,0),(1,1),(2,3)] IC_Q=.5 RANGE=EXTEND\n"
             "I_B 0 B DC=1\nC_B B 0 QV_TABLE=[(0,0),(1,1),(2,3)] IC_Q=.5 RANGE=EXTEND", "1", ".1");
  complete(r);auto es=roots(r);check(es.size()==1,"equal knots were split");
  check(es[0]["actual_changed_members"].size()==2,"simultaneous knot missing");
  check(es[0]["mode_update"]["directions"].size()==2,"joint constitutive directions missing");
}
void control_cancels_future_knot() {
  Options o;o.atomic_time=2e-8;
  auto r=run("EVENT_OFF OFF MODE=AT AT=.5\nREG_G G MODE=SR SET=OFF RESET=OFF PRIORITY=RESET IC=1\n"
             "SEL_CURRENT CURRENT G -1 1\nI_B 0 B CURRENT\n"
             "C_B B 0 QV_TABLE=[(0,0),(1,1),(2,3)] IC_Q=.499999999 RANGE=EXTEND", "1", ".1",o);
  complete(r);check(roots(r).empty(),"cancelled future knot was committed");
  near(r.committed.physical[0],.499999999,2e-12,"state after current reversal");
  check(r.committed.mode.segments.begin()->second==0,"cancelled knot changed segment");
}
void reverse_crossing() {
  auto r=run("I_A A 0 DC=1\nC_A A 0 QV_TABLE=[(0,0),(1,1),(2,3)] IC_Q=1.5 RANGE=EXTEND","1",".1");
  complete(r);auto es=roots(r);check(es.size()==1,"reverse knot crossing missing");
  auto d=es[0]["mode_update"]["directions"][0];
  check(d["from_segment"]==1&&d["to_segment"]==0,"reverse segment direction wrong");
  near(value(r,"V(A)"),.5,2e-12,"reverse capacitor voltage");
}
}
int main() {
  try {
    nearby_knots_keep_physical_times();simultaneous_knots_are_joint();
    control_cancels_future_knot();reverse_crossing();
    std::cout<<"PASS pre-kernel constitutive/event acceptance, "<<assertions<<" assertions\n";return 0;
  }catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}
}
