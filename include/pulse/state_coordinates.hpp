#pragma once
#include "pulse/core.hpp"
namespace pulse {
struct PersistentChart {
  bool active=false;
  Vector weights;
  Matrix mix,unmix,T,L;
  std::vector<std::string> coordinate_ids;
  std::string selection_reason;
  int difference_slot=-1;
};
const PersistentChart& persistent_chart(const Model&);
Vector persistent_encode(const Model&,const Vector&);
Vector physical_view(const Model&,const Vector&);
Vector physical_increment(const Model&,const Vector&);
void persistent_stamp(const Model&,Matrix&,Matrix&,Matrix&);
Json persistent_description(const Model&);
double state_signal(const RunState&,const std::string&);
// Batch read uses one Flow compatibility check per immutable snapshot.
std::vector<double> state_signals(const RunState&,const std::vector<std::string>&);
// Precompiled netlist-time software input selectors. Literal values and
// canonical signal keys no longer require parsing for every event.
struct PreparedSignal {
 bool literal=false;
 double value=0;
 std::string key;
};
std::vector<PreparedSignal> prepare_signals(const std::vector<std::string>&);
std::vector<double> state_signals_prepared(const RunState&,const std::vector<PreparedSignal>&);
void publish_physical_state(const Model&,RunState&);
}

