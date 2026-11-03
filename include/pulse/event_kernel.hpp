#pragma once
#include "pulse/core.hpp"
#include <map>
#include <set>
#include <string>
#include <vector>

namespace pulse {
// Compiled per-model dispatch data. Its lifetime is bounded by a single
// simulate() call and all members are immutable after construction.
// No physical or numerical state is cached in this class.
class EventKernel final {
 public:
  struct RegisterRule {
    enum class Kind { SetReset, Clocked } kind = Kind::Clocked;
    std::string name, set, reset, clock, expression;
    bool set_priority = false;
  };
  struct DelayRule {
    int part = -1;
    std::string source, cancel, trigger, delay_input, delay_literal, delay_text;
    bool has_cancel = false, has_delay_input = false, replace = false;
  };
  struct EdgeRule {
    enum class Direction { Both, Rise, Fall, Other } direction = Direction::Other;
    std::string source, trigger;
  };
  struct PeriodicRule {
    std::string start_literal, period_literal;
    std::string start_origin, period_origin;
  };

  explicit EventKernel(const Model&);
  const std::vector<RegisterRule>& registers() const noexcept { return registers_; }
  const std::vector<DelayRule>& delays() const noexcept { return delays_; }
  const PeriodicRule* periodic(int part) const noexcept;
  std::set<std::string> changed_edges(const Mode&, const Mode&) const;

 private:
  std::vector<RegisterRule> registers_;
  std::vector<DelayRule> delays_;
  std::vector<EdgeRule> edges_;
  std::map<int, PeriodicRule> periodics_;
};

// Byte-for-byte textual representation of the legacy closure cycle key in the
// default classic C++ locale. The first component is the unchanged Mode.id.
// No hash-only shortcut is used: equality remains exact.
std::string event_fingerprint(const RunState&, const std::set<std::string>&);
} // namespace pulse
