#pragma once
#include "dataset.hpp"
#include <array>
#include <chrono>
#include <string>
namespace fri {
using rfr::I;
using rfr::Input;
using rfr::IV;
using rfr::Mode;
using rfr::Vec;
enum class Status { FOUND_CERTIFIED, FOUND_NUMERICAL, FOUND_ENGINEERING, NO_EVENT_CERTIFIED, UNRESOLVED, UNSUPPORTED };
const char *name(Status);
struct Options {
    int algorithm = 3, p = 12, max_depth = 64, max_nodes = 8192, max_iterations = 96;
    double abs_tol = 2e-18, rel_tol = 1e-10, scheduled = INFINITY;
    size_t memory_budget = 64 * 1024 * 1024;
    bool include_left = false, profile = false, allow_numerical = false, require_tick_order = false;
    double engineering_window = 0; // >0 permits a representative when certified roots overlap
    std::vector<int> directions; // +1 PULSE orientation, -1 downward, 0 either strict crossing
};
struct Statistics {
    uint64_t evaluations = 0, state_calls = 0, matvecs = 0, subdivisions = 0, nodes = 0, iterations = 0;
    uint64_t ca_transforms = 0, ca_zero = 0, ca_one = 0, ca_ambiguous = 0, l1_excluded = 0;
    uint64_t cache_hits = 0, cache_misses = 0, cache_evictions = 0, peak_bytes = 0;
    double isolation_s = 0, refinement_s = 0, taylor_s = 0, bounds_s = 0, transform_s = 0,
           cache_prepare_s = 0, cpu_s = 0;
};
struct Result {
    Status status = Status::UNRESOLVED;
    int event_id = -1, direction = 0;
    double time = NAN;
    I bracket{NAN, NAN}, residual{NAN, NAN};
    std::vector<int> simultaneous;
    IV state;
    Statistics stats;
    std::string reason, scope = "exact binary64 autonomous affine IVP; supplied initial box; continuous time";
    bool engineering_representative = false;
    double time_uncertainty = NAN;
    double unresolved_frontier = NAN;
    // CR-002 diagnostics: populated for an unresolved search, without changing
    // the acceptance path.
    I failed_bracket{NAN, NAN};
    int failed_guard = -1, failed_depth = 0;
    uint64_t failed_nodes = 0;
};
struct ModelCache {
    std::map<uint64_t, Mode> modes;
    size_t capacity = 64 * 1024 * 1024;
    uint64_t hits = 0, misses = 0, evictions = 0;
    Mode &get(const Mode &);
    size_t bytes() const;
    void clear() { modes.clear(); }
};
Result find_first_event(const Mode &, const Input &, const Options &, ModelCache * = nullptr);
I exp_interval(I);
I sin_interval(I);
I cos_interval(I);
// Public test seam: coefficients of (1+u)^p P((a+b*u)/(1+u)), interval arithmetic.
IV ca_transform(const IV &, double a = 0, double b = 1);
int sign_variations(const IV &); // -1 if any coefficient sign is indeterminate
IV exponential_action(const Mode &, const IV &, double, Statistics * = nullptr, size_t max_steps = 4096);
} // namespace fri
