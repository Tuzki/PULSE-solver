#pragma once
#include "json.hpp"
#include "netlist.hpp"
#include <Eigen/Dense>
#include <array>
#include <compare>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <set>
#include <stdexcept>
namespace pulse {
namespace validated {
struct State;
}
using Matrix = Eigen::MatrixXd;
using Vector = Eigen::VectorXd;
using Json = nlohmann::json;
struct Error : std::runtime_error {
  int code;
  std::string subcode;
  bool unresolved;
  Source source;
  Error(int c, std::string s, std::string message, bool u = false,
        Source src = {})
      : std::runtime_error(std::move(message)), code(c), subcode(std::move(s)),
        unresolved(u), source(std::move(src)) {}
};
void require(bool, int, const std::string &, const std::string &, bool = false,
             Source = {});
// Portable signed seconds + two fractional limbs. Q_repr stays 2^-64;
// the second limb preserves exact binary64 sub-tick digital deadlines.
struct Time {
  int64_t whole = 0;
  uint64_t tick = 0, subtick = 0;
  auto operator<=>(const Time &) const = default;
  static Time from(double);
  static Time decode(const std::string &);
  double seconds() const;
  std::string canonical() const;
  Time operator+(Time) const;
  Time operator-(Time) const;
  Time times(uint64_t) const;
  Time ceil_tick() const;
};
struct Affine {
  std::map<std::string, double> terms;
  double bias = 0;
};
Affine affine(const std::string &, const std::set<std::string> &known = {});
std::string net_name(const std::string &);
bool is_literal(const std::string &);
double number(const std::string &);
struct Curve {
  std::vector<double> x, y;
  bool extend = false;
  std::pair<double, double> segment(int) const;
  int locate(double, bool inverse = false) const;
  double value(double, bool inverse = false) const;
};
struct Part {
  Primitive raw;
  int state = -1;
  std::vector<std::pair<std::string, std::string>> ports;
  Curve curve;
  Matrix inductance;
  Affine math;
};
struct Signal {
  enum Type { REAL, BOOL, TRIG };
  Type type = REAL;
  bool held = false;
  std::string driver;
};
struct Model {
  Netlist netlist;
  std::vector<Part> parts;
  std::map<std::string, Signal> signals;
  std::map<std::string, int> nodes, branches;
  // Physical port connectivity, not signal/magnetic coupling. Reference nodes
  // remain distinct model nodes; each floating component gets local coordinates.
  std::map<std::string, std::string> node_reference;
  std::vector<std::string> floating_references;
  std::vector<int> cmps, pwas, registers, events;
  std::vector<std::string> state_ids, registry;
  std::set<std::string> software_outputs;
  Vector initial;
  int ns = 0;
  double compile_seconds = 0;
  bool numerical_coordinates = false; // enabled only on a simulation-owned copy
};
Model compile(Netlist);
Vector reconstruct_physical(const Matrix &, const Vector &);
Vector reduce_physical(const Matrix &, const Vector &);
struct Mode {
  // A region-classification candidate is never an accepted physical flow.
  bool classification_only = false;
  // Shared by compiled definitions; released from accepted trajectory states.
  std::shared_ptr<const Matrix> candidate_roundoff_scale;
  Matrix M, observations, constraints, residual_map,
      residual_reference; // homogeneous physical coordinate [q,phi,eta,1]
  // Descriptor tangent flow is retained in factored coordinates. The exact
  // product lift*generator*reduce avoids independently rounding dependent
  // physical derivative rows and preserves the compiled constraint subspace.
  Matrix invariant_lift, invariant_generator, invariant_reduce;
  std::map<std::string, Vector> maps;
  std::map<std::string, bool> bools;
  std::map<int, int> segments;
  struct Guard {
    Vector row;
    int part;
    int direction;
    std::string kind;
    int knot = -1, segment = -1, step = 0;
    double arrival_error = 0;
  };
  std::vector<Guard> guards;
  std::string id;
  uint64_t version = 0;
  double residual = 0;
};
struct Stats {
  uint64_t modes = 0, exponentials = 0, root_queries = 0, root_failures = 0,
           microsteps = 0, transactions = 0, rollbacks = 0, queue_peak = 0,
           cache_hits = 0;
  uint64_t mode_cache_misses = 0, mode_cache_evictions = 0,
           mode_cache_peak_entries = 0;
  uint64_t projections = 0;
  uint64_t cegs_calls = 0, cegs_certified = 0, cegs_not_certified = 0;
  double cegs_prep_seconds = 0, cegs_certify_seconds = 0;
  double compile_seconds = 0, run_seconds = 0, max_residual = 0;
  double max_projection_correction = 0, max_projected_residual = 0;
};
// Each simulation owns a bounded cache for its frozen Model. Entries contain
// equations, never accepted physical states or transaction outcomes.
struct ModeCacheData;
class ScopedModeCache {
  std::unique_ptr<ModeCacheData> data_;
  ModeCacheData *previous_ = nullptr;

public:
  ScopedModeCache(const Model &, size_t capacity);
  ~ScopedModeCache();
  ScopedModeCache(const ScopedModeCache &) = delete;
  ScopedModeCache &operator=(const ScopedModeCache &) = delete;
};
Mode settle(const Model &, const Vector &,
            const std::map<std::string, double> &, Stats &,
            const std::set<int> &just_crossed = {}, bool initial = false);
// Compile exactly one specified complete mode; no CMP/PWA combination
// enumeration.  Used by derivative-driven joint reclassification.
enum class CompilePurpose { AcceptedEntry, RegionClassification };
Mode compile_specified(const Model &, const Vector &,
                       const std::map<std::string, double> &, Stats &,
                       const std::map<int, bool> &bits,
                       const std::map<int, int> &segments,
                       CompilePurpose purpose = CompilePurpose::AcceptedEntry);
void accept_mode_entry(const Model &, Mode &, const Vector &);
Vector propagate(const Mode &, const Vector &, double, Stats &);
void validate_physical(const Mode &, const Vector &);
struct Options {
  std::optional<double> t_end, save_dt;
  std::optional<std::vector<std::string>> channels;
  int atom_exponent = -1;
  double atomic_time = 1e-14;
  size_t mode_cache_capacity = 128;
  size_t max_microsteps = 256, max_transactions = 0;
  std::string fault;
  bool retain_history = true; // CLI/C ABI stream outputs without retaining every Mode
};
struct Agenda {
  Time at;
  int part;
  uint64_t cycle = 0, generation = 0;
  std::string trigger;
  std::string origin;
};
struct RunState {
  Time at;
  std::string time_origin = "0";
  Vector physical; // public q/phi/INT view, never used to recover small differences
  Vector internal; // authoritative numerical state during simulation
  std::shared_ptr<const Mode> internal_mode; // retained for accurate observation of published snapshots
  std::shared_ptr<const validated::State> validated_state;
  bool validated_chain = false;
  std::map<std::string, double> regs;
  struct SoftwareState {
    std::vector<unsigned char> bytes;
    uint64_t invocation = 0;
  };
  std::map<std::string, SoftwareState> software;
  Mode mode;
  std::vector<Agenda> agenda;
  std::map<int, uint64_t> generations;
  uint64_t version = 0;
};
struct Segment {
  RunState state;
};
struct Result {
  std::string status = "STOPPED_ERROR", evidence = "NOT_CERTIFIED";
  Json diagnostic = Json::object(), report = Json::object();
  std::vector<Json> events;
  std::vector<Segment> segments;
  std::vector<double> times;
  std::vector<std::string> analog_names, digital_names;
  std::vector<float> analog;
  std::vector<uint8_t> digital;
  RunState committed;
  Stats stats;
  double t_end = 0, save_dt = 0, t_atom = 0;
};
Result simulate(const Model &, const Options & = {});
void write_result(const Model &, const Result &, const std::filesystem::path &);
Json diagnostic(const std::exception &);
} // namespace pulse
