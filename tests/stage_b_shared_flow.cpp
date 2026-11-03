// Stage B: exercise the actual pulse_core, not a fake Mode or Flow.
// The existing engineering test helper provides document(), check(), and complete().
#define main engineering_original_main
#include "engineering_events.cpp"
#undef main
#include "pulse/engineering.hpp"
#include "pulse/state_coordinates.hpp"
#include <cstring>
#include <stdexcept>
#include <iostream>

int main() {
  try {
    auto m = compile(parse_markdown(document(
      "V1 IN 0 DC=1\nR1 IN OUT R=1\nC1 OUT 0 C=1 IC_V=0", ".1", ".01"),
      "stage-b.md"));
    Stats stats;
    RunState s;
    s.internal = m.initial;
    s.physical = m.initial;
    s.mode = engineering::initial_mode(m, s.internal, {}, stats);
    engineering::Flow flow(s.mode, s.internal);
    auto next = flow.continue_if_compatible(s.mode, 0);
    check(bool(next), "same Mode must permit an exact continuation");
    auto old = flow.continued(s.mode, 0);
    check(next->archive_offset() == old.archive_offset(), "continuation offset changed");
    check(next->archive_mode().id == old.archive_mode().id, "archive Mode changed");
    check(next->archive_origin_id() == old.archive_origin_id(), "archive lineage changed");
    auto x = next->state(0), y = old.state(0);
    check(x.size() == y.size() &&
          !std::memcmp(x.data(), y.data(), size_t(x.size()) * sizeof(double)),
          "continued state differs bitwise");
    Mode incompatible = s.mode;
    incompatible.definition.edit().M(0, int(m.ns)) += 1;
    check(!flow.continue_if_compatible(incompatible,0).has_value(),
          "changed generator must reject exact-compatibility shortcut");
    const std::vector<std::string> names = {"0.75", "V(OUT)", "V(IN)", "V(OUT)", "1"};
    auto plan = prepare_signals(names);
    auto old_inputs = state_signals(s,names);
    auto new_inputs = state_signals_prepared(s,plan);
    check(old_inputs.size()==new_inputs.size() &&
          !std::memcmp(old_inputs.data(),new_inputs.data(),old_inputs.size()*sizeof(double)),
          "prepared inputs differ without Flow");
    s.electrical_flow = std::make_shared<engineering::Flow>(s.mode,s.internal);
    old_inputs = state_signals(s,names);
    new_inputs = state_signals_prepared(s,plan);
    check(!std::memcmp(old_inputs.data(),new_inputs.data(),old_inputs.size()*sizeof(double)),
          "prepared inputs differ with Flow");
    Options o; o.retain_history=false;
    auto result = simulate(m,o);
    check(result.status == "COMPLETED", "basic regression did not complete");
    std::cout << "PASS Stage B immutable template interface, Flow validation and prepared C task reads\n";
    return 0;
  }catch(const std::exception&e){
    std::cerr << e.what() << '\n'; return 1;
  }
}
