#pragma once
#include "pulse/core.hpp"
#include <memory>
namespace pulse::engineering {
// Point-trajectory engineering evaluator. Bounds describe the computed modal
// approximation, not an inherited enclosure of every physical trajectory.
struct Range {
  double lo = 0, hi = 0;
};
struct FlowData;
class Flow {
  std::shared_ptr<FlowData> data_;
  Time offset_;

public:
  Flow(const Mode &, const Vector &);
  Vector state(double) const;
  // Continuation retains the original numerical anchor. Compatibility excludes
  // guard orientation and control bits, but includes every electrical map.
  bool compatible(const Mode &) const;
  Flow continued(const Mode &, double elapsed) const;
  double observe(const Vector &, double time, int derivative = 0) const;
  double value(size_t guard, double time, int derivative = 0) const;
  Range bounds(size_t guard, double lower, double upper,
               int derivative = 0) const;
  double scale(size_t guard) const;
  bool stationary(size_t guard) const;
  bool modal() const;
  static double tangent(const Mode &, const Vector &, const Vector &row);
};
struct Crossing {
  size_t guard = 0;
  double time = 0, lower = 0, upper = 0, slope = 0;
};
struct SearchResult {
  std::vector<Crossing> candidates;
  size_t nodes = 0;
};
// Shared finite, resolved incoming-direction check; no absolute timing-error veto.
void validate_event_timing(const Flow &, const Crossing &, double atom);
SearchResult next_events(const Mode &, const Flow &, double horizon,
                         double atom, size_t budget = 32768);
Mode initial_mode(const Model &, const Vector &,
                  const std::map<std::string, double> &, Stats &);
Mode update_mode(const Model &, const RunState &, const Vector &,
                 const std::map<std::string, double> &,
                 const std::vector<Mode::Guard> &, const std::set<int> &seeds,
                 Stats &, Json *details = nullptr, int algorithm = 2);
} // namespace pulse::engineering
