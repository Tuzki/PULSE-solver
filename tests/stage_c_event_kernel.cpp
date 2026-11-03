#include "pulse/event_kernel.hpp"
#include "pulse/engineering.hpp"
#include "pulse/state_coordinates.hpp"
#include <algorithm>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <cstring>

#define VERIFY(cond) do { if(!(cond)) throw std::runtime_error("event kernel assertion: " #cond); } while(false)

// Independent implementation of the legacy cycle fingerprint. This checks
// formatting, order, software bytes and canonical agenda tokens exactly.
static std::string reference_fingerprint(const pulse::RunState& s,
                                         const std::set<std::string>& trig) {
  std::ostringstream x;
  x << std::setprecision(17) << s.mode.id;
  for(const auto& name:trig) x << "!" << name;
  for(const auto& [name,state]:s.software.read()) {
    x << "$" << name << ":" << state.invocation << ":";
    for(const auto value:state.bytes) x << unsigned(value) << ",";
  }
  std::vector<std::string> pending;
  for(const auto& a:s.agenda.read()) {
    auto it=s.generations.read().find(a.part);
    if(a.generation==(it==s.generations.read().end()?0:it->second))
      pending.push_back(a.at.canonical()+":"+a.trigger+":"+a.origin);
  }
  std::sort(pending.begin(),pending.end());
  for(const auto& a:pending) x << "@" << a;
  return x.str();
}
static void actual_delay_cancellation() {
  using namespace pulse;
  const std::string network =
      "MATH_ONE ONE = 1\nINT_X X ONE\n"
      "EVENT_CLK CLK MODE=PERIODIC START=0 PERIOD=.25\n"
      "EVENT_CANCEL CANCEL MODE=AT AT=.0625\n"
      "EVENT_DELAY DELAYED MODE=DELAY SOURCE=CLK DELAY=.125 POLICY=REPLACE CANCEL=CANCEL\n"
      "EVENT_TRAN TRAN MODE=DELAY SOURCE=CLK DELAY=.375 POLICY=TRANSPORT\n"
      "REG_Q Q X DELAYED IC=-1\n";
  const std::string text = "# PULSE Netlist v1.1\n\n## Parameters\n```pulse\n```\n\n## Network\n```pulse\n"+
      network+"```\n\n## Simulation\n```pulse\n.TRAN T_END=.75 SAVE_DT=.0625\n```\n\n## Layout\n```json\n{}\n```\n";
  auto model=compile(parse_markdown(text,"stage-c-delay.md"));
  auto result=simulate(model);
  VERIFY(result.status=="COMPLETED");
  std::vector<Time> delayed,transport;
  for(const auto& event:result.events) {
    if(event.value("kind","")!="TRIG") continue;
    if(event.value("source","")=="DELAYED") delayed.push_back(Time::decode(event.at("time_canonical")));
    if(event.value("source","")=="TRAN") transport.push_back(Time::decode(event.at("time_canonical")));
  }
  const std::vector<Time> expected={Time::from(.375),Time::from(.625)};
  VERIFY(delayed==expected); // The .125 deadline was cancelled, later ones survive.
  VERIFY(transport==expected); // Co-timed distinct origins and triggers remain valid.
  VERIFY(state_signal(result.committed,"Q")==.625);
  const auto delay_part=std::find_if(model.parts.begin(),model.parts.end(),
      [](const auto& part){return part.raw.id=="EVENT_DELAY";});
  VERIFY(delay_part!=model.parts.end());
  VERIFY(result.committed.generations.read().at(int(delay_part-model.parts.begin()))==5);
}

static void basis_identity_lifetime() {
  using namespace pulse;
  Mode original; original.definition.edit().M=Matrix::Zero(2,2);
  original.definition.edit().M(0,1)=1;
  Vector x(2); x<<.25,1;
  Vector row(2); row<<1,0;
  original.binding.edit().maps["X"]=row;
  original.binding.edit().guards.push_back({row,0,1,"OBSERVE"});
  engineering::Flow first(original,x), shared(original,x);
  auto before=first.state(.125),again=shared.state(.125);
  VERIFY(std::memcmp(before.data(),again.data(),size_t(before.size())*sizeof(double))==0);
  Mode changed=original; changed.definition.edit().M(0,1)=2;
  engineering::Flow different(changed,x);
  VERIFY(first.state(.125)[0]==.375);
  VERIFY(different.state(.125)[0]==.5);
  // Evict both bounded caches while the original Flow and definition survive.
  for(int i=0;i<160;++i) {
    Mode next=original; next.definition.edit().M(0,1)=double(i+3)/64;
    engineering::Flow flow(next,x);
    VERIFY(flow.state(.125)[0]==.25+double(i+3)/512);
  }
  engineering::Flow restored(original,x);
  auto after=restored.state(.125);
  VERIFY(std::memcmp(before.data(),after.data(),size_t(before.size())*sizeof(double))==0);
}

static void cancelled_unknown_origin_must_recheck() {
  using namespace pulse;
  const std::string text =
      "# PULSE Netlist v1.1\n\n## Parameters\n```pulse\n```\n\n## Network\n```pulse\n"
      "MATH_ONE ONE = 1\nINT_X X ONE\n"
      "EVENT_START CLK MODE=AT AT=0\nEVENT_CANCEL CANCEL MODE=AT AT=.5\n"
      "EVENT_A A MODE=DELAY SOURCE=CLK DELAY=1 POLICY=TRANSPORT\n"
      "EVENT_B B MODE=DELAY SOURCE=CLK DELAY=2 POLICY=TRANSPORT CANCEL=CANCEL\n"
      "EVENT_C C MODE=DELAY SOURCE=CLK DELAY=3 POLICY=TRANSPORT\n"
      "```\n\n## Simulation\n```pulse\n.TRAN T_END=4 SAVE_DT=.5\n```\n\n## Layout\n```json\n{}\n```\n";
  auto model=compile(parse_markdown(text,"stage-c-origin-fault.md"));
  // Inject conflicting provenance with an unknown middle entry. The original
  // full check rejects the conflict once cancellation invalidates that entry.
  for(auto& part:model.parts) {
    if(part.raw.id=="EVENT_A") part.raw.option_text["DELAY"]="3";
    if(part.raw.id=="EVENT_B") part.raw.option_text["DELAY"]="UNPROVEN_INPUT";
    if(part.raw.id=="EVENT_C") part.raw.option_text["DELAY"]="1";
  }
  auto result=simulate(model);
  VERIFY(result.status!="COMPLETED");
  VERIFY(result.diagnostic.value("subcode","")=="TIME_RESOLUTION_UNRESOLVED");
  VERIFY(result.committed.at==Time{}); // Cancellation failed before commit.
}

int main() {
  try {
  using namespace pulse;
  Model model;
  model.parts.resize(5);
  model.registers={0,1};
  model.events={2,3,4};
  model.parts[0].raw.args={"Q"};
  model.parts[0].raw.options={{"MODE","SR"},{"SET","SET"},
                              {"RESET","RESET"},{"PRIORITY","SET"}};
  model.parts[1].raw.args={"R","1","CLK"};
  model.parts[2].raw.args={"D"};
  model.parts[2].raw.options={{"MODE","DELAY"},{"SOURCE","CLK"},
                              {"DELAY","0.01"},{"CANCEL","CANCEL"},
                              {"POLICY","REPLACE"}};
  model.parts[2].raw.option_text["DELAY"]="10m";
  model.parts[3].raw.args={"EDGE"};
  model.parts[3].raw.options={{"MODE","EDGE"},{"SOURCE","G"},{"EDGE","RISE"}};
  model.parts[4].raw.args={"CLK2"};
  model.parts[4].raw.options={{"MODE","PERIODIC"},{"START","0.25"},{"PERIOD","0.5"}};
  model.parts[4].raw.option_text={{"START","250m"},{"PERIOD","500m"}};
  EventKernel kernel(model);
  VERIFY(kernel.periodic(4)!=nullptr);
  VERIFY(kernel.periodic(4)->period_literal=="0.5");
  VERIFY(kernel.periodic(4)->period_origin=="500m");
  VERIFY(kernel.registers().size()==2);
  VERIFY(kernel.delays().size()==1);
  VERIFY(kernel.registers()[0].kind==EventKernel::RegisterRule::Kind::SetReset);
  VERIFY(kernel.registers()[0].set_priority);
  VERIFY(kernel.delays()[0].replace);
  VERIFY(kernel.delays()[0].has_cancel);
  VERIFY(kernel.periodic(2)==nullptr);
  Mode before,after;
  before.bools["G"]=false;after.bools["G"]=true;
  auto edges=kernel.changed_edges(before,after);
  VERIFY(edges.size()==1 && edges.count("EDGE")!=0);
  VERIFY(kernel.changed_edges(after,before).empty());
  RunState s;
  s.mode.id="sample:1";
  s.software.edit()["controller"].invocation=18446744073709551615ULL;
  s.software.edit()["controller"].bytes={0,1,10,255,0};
  s.generations.edit()[2]=4;
  s.agenda.edit().push_back({Time::from(0.125),2,0,4,"D","125e-3"});
  s.agenda.edit().push_back({Time::from(0.25),3,0,0,"R","250e-3"});
  s.agenda.edit().push_back({Time::from(0.375),2,0,3,"OLD","375e-3"});
  const std::set<std::string> trig={"A","Z"};
  VERIFY(event_fingerprint(s,trig)==reference_fingerprint(s,trig));
  s.software.edit()["other"].invocation=10;
  VERIFY(event_fingerprint(s,{})==reference_fingerprint(s,{}));
  actual_delay_cancellation();
  basis_identity_lifetime();
  cancelled_unknown_origin_must_recheck();
  std::cout<<"PASS: compiled event dispatch, byte-exact cycle key, actual delay cancellation and basis identity lifetime\n";
  return 0;
  } catch(const std::exception& error) {
    std::cerr<<error.what()<<'\n';
    return 1;
  }
}
