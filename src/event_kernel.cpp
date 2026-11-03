#include "pulse/event_kernel.hpp"
#include <algorithm>
#include <array>
#include <charconv>
#include <utility>

namespace pulse {
namespace {
std::string option(const Primitive& part, const char* key, const char* fallback="") {
  const auto it=part.options.find(key);
  return it==part.options.end()?std::string(fallback):it->second;
}
std::string original_text(const Primitive& part, const char* key, const char* fallback="") {
  const auto it=part.option_text.find(key);
  return it==part.option_text.end()?std::string(fallback):it->second;
}
void append_decimal(std::string& out, uint64_t value) {
  std::array<char,32> buffer{};
  const auto result=std::to_chars(buffer.data(),buffer.data()+buffer.size(),value);
  out.append(buffer.data(),result.ptr);
}
}
EventKernel::EventKernel(const Model& model) {
  registers_.reserve(model.registers.size());
  delays_.reserve(model.events.size());
  edges_.reserve(model.events.size());
  for (const int index: model.registers) {
    const auto& p=model.parts.at(index).raw;
    const auto name=net_name(p.args.at(0));
    if (model.software_outputs.count(name)) continue;
    RegisterRule rule;
    rule.name=name;
    if (option(p,"MODE")=="SR") {
      rule.kind=RegisterRule::Kind::SetReset;
      rule.set=net_name(option(p,"SET"));
      rule.reset=net_name(option(p,"RESET"));
      rule.set_priority=(option(p,"PRIORITY")=="SET");
    } else {
      rule.clock=net_name(p.args.at(2));
      rule.expression=p.args.at(1); // Preserve state_signal() interpretation.
    }
    registers_.push_back(std::move(rule));
  }
  for (const int index: model.events) {
    const auto& p=model.parts.at(index).raw;
    const auto mode=option(p,"MODE");
    if (mode=="EDGE") {
      EdgeRule rule;
      rule.source=net_name(option(p,"SOURCE"));
      rule.trigger=net_name(p.args.at(0));
      const auto direction=option(p,"EDGE");
      rule.direction=direction=="BOTH"?EdgeRule::Direction::Both:
                     direction=="RISE"?EdgeRule::Direction::Rise:
                     direction=="FALL"?EdgeRule::Direction::Fall:
                     EdgeRule::Direction::Other;
      edges_.push_back(std::move(rule));
    } else if (mode=="DELAY") {
      DelayRule rule;
      rule.part=index;
      rule.source=net_name(option(p,"SOURCE"));
      rule.trigger=net_name(p.args.at(0));
      rule.has_cancel=p.options.count("CANCEL")!=0;
      if (rule.has_cancel) rule.cancel=net_name(option(p,"CANCEL"));
      rule.has_delay_input=p.options.count("DELAY_INPUT")!=0;
      if (rule.has_delay_input) rule.delay_input=option(p,"DELAY_INPUT");
      else {
        rule.delay_literal=option(p,"DELAY");
        rule.delay_text=original_text(p,"DELAY");
      }
      rule.replace=(option(p,"POLICY","TRANSPORT")=="REPLACE");
      delays_.push_back(std::move(rule));
    } else if (mode=="PERIODIC") {
      periodics_.emplace(index,PeriodicRule{
        option(p,"START","0"),option(p,"PERIOD"),
        original_text(p,"START","0"),original_text(p,"PERIOD")});
    }
  }
}
const EventKernel::PeriodicRule* EventKernel::periodic(int part) const noexcept {
  auto it=periodics_.find(part);
  return it==periodics_.end()?nullptr:&it->second;
}
std::set<std::string> EventKernel::changed_edges(const Mode& before, const Mode& after) const {
  std::set<std::string> result;
  for (const auto& edge:edges_) {
    const bool a=before.bools.at(edge.source),b=after.bools.at(edge.source);
    if (a==b) continue;
    const bool selected=edge.direction==EdgeRule::Direction::Both ||
        (edge.direction==EdgeRule::Direction::Rise && b) ||
        (edge.direction==EdgeRule::Direction::Fall && !b);
    if (selected) result.insert(edge.trigger);
  }
  return result;
}
std::string event_fingerprint(const RunState& state, const std::set<std::string>& triggers) {
  std::string out;
  out.reserve(state.mode.id.size()+128);
  out+=state.mode.id;
  for (const auto& trigger:triggers) {out+='!';out+=trigger;}
  for (const auto& [name,software]:state.software.read()) {
    out+='$';out+=name;out+=':';
    append_decimal(out,software.invocation);
    out+=':';
    for (const auto value:software.bytes) {
      append_decimal(out,value);
      out+=',';
    }
  }
  std::vector<std::string> pending;
  pending.reserve(state.agenda.read().size());
  const auto& generations=state.generations.read();
  for (const auto& agenda:state.agenda.read()) {
    const auto it=generations.find(agenda.part);
    if (agenda.generation!=(it==generations.end()?0:it->second)) continue;
    pending.push_back(agenda.at.canonical()+":"+agenda.trigger+":"+agenda.origin);
  }
  std::sort(pending.begin(),pending.end());
  for (const auto& item:pending) {out+='@';out+=item;}
  return out;
}
} // namespace pulse
