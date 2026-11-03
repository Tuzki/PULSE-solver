// Differential provenance-fault probe; never linked into pulse-solver.
#include "pulse/core.hpp"
#include <iostream>
int main() { try {
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
  for(auto& part:model.parts) {
    if(part.raw.id=="EVENT_A") part.raw.option_text["DELAY"]="3";
    if(part.raw.id=="EVENT_B") part.raw.option_text["DELAY"]="UNPROVEN_INPUT";
    if(part.raw.id=="EVENT_C") part.raw.option_text["DELAY"]="1";
  }
  auto result=simulate(model);
  std::cout<<Json({{"status",result.status},{"diagnostic",result.diagnostic},
      {"committed_seconds",result.committed.at.seconds()},
      {"transactions",result.stats.transactions},{"events",result.events}}).dump(2)<<'\n';
  return 0;
} catch(const std::exception& error) { std::cerr<<error.what()<<'\n'; return 1; } }
