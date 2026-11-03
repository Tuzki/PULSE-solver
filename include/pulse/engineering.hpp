#pragma once
#include "pulse/core.hpp"
#include <memory>
#include <optional>
namespace pulse::engineering {
// Point-trajectory engineering evaluator. Bounds describe the computed modal
// approximation, not an inherited enclosure of every physical trajectory.
struct Range {
  double lo = 0, hi = 0;
};
void reset_flow_statistics();
Json flow_statistics();
struct FlowData;
class Flow {
  std::shared_ptr<FlowData> data_;
  Time offset_;
  std::shared_ptr<const Mode> archive_view_;
  // Precondition: caller has certified compatibility. Never called publicly.
  Flow continued_after_check(const Mode &, double elapsed) const;

public:
  Flow(const Mode &, const Vector &);
  // Read-only archive access. Restore uses the existing constructor/evaluators;
  // preserve the original anchor and exact continuation offset, never rebase.
  const Mode &archive_mode() const;
  const Vector &archive_anchor() const;
  Time archive_offset() const;
  uint64_t archive_origin_id() const;
  static Flow restore_archive(const Mode &, const Vector &, Time);
  Vector state(double) const;
  // Continuation retains the original numerical anchor. Compatibility excludes
  // control snapshots and certified observation-only rows. Changed guards are
  // reprojected; unchanged guards share the original anchored evaluator.
  bool compatible(const Mode &) const;
  Flow continued(const Mode &, double elapsed) const;
  // One atomic compatibility decision: nullopt leaves the caller's fallback
  // constructor path unchanged. Equivalent to compatible()+continued().
  std::optional<Flow> continue_if_compatible(const Mode &, double elapsed) const;
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
