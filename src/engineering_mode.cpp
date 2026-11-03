#include <cstdlib>
#include "pulse/engineering.hpp"
#include "pulse/constitutive.hpp"
#include "pulse/solver_strategy.hpp"
#include <algorithm>
namespace pulse::engineering {
namespace {
std::string option(const Primitive &p, const std::string &key,
                   const std::string &fallback = "") {
  auto it = p.options.find(key);
  return it == p.options.end() ? fallback : it->second;
}
Vector input(const Model &m, const Mode &mode, const std::string &name) {
  if (!is_literal(name))
    return mode.binding.read().maps.at(net_name(name));
  Vector row = Vector::Zero(m.ns + 1);
  row[m.ns] = number(name);
  return row;
}
bool predicate(const Primitive &p, double value) {
  auto op = option(p, "OP");
  return op == "GE"   ? value >= 0
         : op == "GT" ? value > 0
         : op == "LE" ? value <= 0
                      : value < 0;
}
bool isheld(const Model &m, const Part &p) {
  return is_literal(p.raw.args[1]) ||
         m.signals.at(net_name(p.raw.args[1])).held;
}
Vector threshold(const Model &m, const Mode &mode, int part) {
  const auto &p = m.parts[part];
  Vector row = input(m, mode, p.raw.args[1]);
  row[m.ns] -= number(option(p.raw, "THRESHOLD"));
  return row;
}
using constitutive::coordinate;
using constitutive::direction;
std::string fingerprint(const std::map<int, bool> &bits,
                        const std::map<int, int> &segments) {
  std::string id;
  for (auto [i, v] : bits)
    id += std::to_string(i) + ":" + std::to_string(v) + ";";
  for (auto [i, v] : segments)
    id += std::to_string(i) + "=" + std::to_string(v) + ";";
  return id;
}
} // namespace
Mode initial_mode(const Model &m, const Vector &x,
                  const std::map<std::string, double> &regs, Stats &stats) {
  std::map<int, bool> bits;
  std::map<int, int> segments;
  for (int i : m.cmps)
    bits[i] = false;
  for (int i : m.pwas) {
    auto &p = m.parts[i];
    segments[i] = p.raw.kind == "R" ? 0 : p.curve.locate(x[p.state], true);
  }
  std::set<std::string> seen;
  for (int iteration = 0; iteration < 64; ++iteration) {
    require(seen.insert(fingerprint(bits, segments)).second, 9,
            "INITIAL_MODE_CYCLE",
            "initial mode classification cycles; provide a physically regular "
            "initial model",
            true);
    Mode mode = compile_specified(m, x, regs, stats, bits, segments,
                                 CompilePurpose::RegionClassification);
    auto next = bits;
    auto segnext = segments;
    for (int i : m.cmps) {
      auto row = threshold(m, mode, i);
      double value = row.dot(x);
      bool actual = predicate(m.parts[i].raw, value);
      if (value == 0 && !isheld(m, m.parts[i])) {
        double slope = row.dot(mode.definition.read().M * x);
        if (slope != 0)
          actual = (option(m.parts[i].raw, "OP") == "GT" ||
                    option(m.parts[i].raw, "OP") == "GE") == (slope > 0);
      }
      next[i] = actual;
    }
    for (int i : m.pwas)
      if (m.parts[i].raw.kind == "R") {
        auto [a, b] = m.parts[i].ports[0];
        double v = 0;
        if (a != "0")
          v += mode.binding.read().maps.at("V(" + a + ")").dot(x);
        if (b != "0")
          v -= mode.binding.read().maps.at("V(" + b + ")").dot(x);
        segnext[i] = m.parts[i].curve.locate(v);
      }
    if (next == bits && segnext == segments) {
      accept_mode_entry(m, mode, x);
      validate_physical(mode, x);
      return mode;
    }
    bits = std::move(next);
    segments = std::move(segnext);
  }
  throw Error(9, "INITIAL_MODE_BUDGET",
              "initial mode classification did not converge", true);
}
Mode update_mode(const Model &m, const RunState &old, const Vector &x,
                 const std::map<std::string, double> &regs,
                 const std::vector<Mode::Guard> &candidates,
                 const std::set<int> &seeds, Stats &stats, Json *details, int algorithm) {
  require(old.mode.numerical_strategy==algorithm,12,"STRATEGY_MISMATCH",
          "event closure must use the same strategy as root prediction");
  std::map<int, bool> bits;
  for (int i : m.cmps)
    bits[i] = old.mode.bools.at(net_name(m.parts[i].raw.args[0]));
  auto original = bits;
  auto segments = old.mode.segments, initial_segments = segments;
  for (const auto &g : candidates)
    if (seeds.count(g.part) || g.kind == "PWA") {
      if (g.kind == "CMP")
        bits[g.part] = !original[g.part];
      else if (g.kind == "PWA") {
        const int step = direction(m, old.mode, g);
        const Vector left_row=coordinate(m,old.mode,g.part);
        const double left=old.electrical_flow?old.electrical_flow->observe(left_row,0,1):Flow::tangent(old.mode,x,left_row);
        require(std::isfinite(left) && step * left > 0, 9, "BREAKPOINT_LEFT_DIRECTION",
                "breakpoint does not have a resolved incoming direction", true, m.parts[g.part].raw.source);
        // Runtime verifies each member at its own root before advancing the group.
        const bool reached=constitutive::arrived(g,x,g.arrival_error) || g.row.dot(x)>=0;
        require(reached, 9, "BREAKPOINT_NOT_REACHED",
                "a nonlinear segment cannot change before its knot is reached: " +
                Json({{"residual", g.row.dot(x)}, {"evaluation_bound", g.arrival_error},
                      {"coordinate_scale", g.row.cwiseAbs().dot(x.cwiseAbs())}}).dump(),
                true, m.parts[g.part].raw.source);
        segments[g.part] += step;
      }
      else
        throw Error(5, "PWA_OUT_OF_RANGE", "PWA table range exhausted", false,
                    m.parts[g.part].raw.source);
    }
  std::set<std::string> seen;
  for (int iteration = 0; iteration < 32; ++iteration) {
    require(seen.insert(fingerprint(bits, segments)).second, 9,
            "MODE_DIRECTION_CYCLE",
            "candidate derivative decisions do not have a stable joint mode",
            true);
    Mode mode = portfolio_compile(m, x, regs, stats, bits, segments, algorithm,
                                 CompilePurpose::RegionClassification);
    auto next = bits;
    auto segnext = segments;
    for (int i : m.cmps)
      if (isheld(m, m.parts[i]) || regs != old.regs.read())
        next[i] = predicate(m.parts[i].raw, threshold(m, mode, i).dot(x));
    // A continuous comparator can change a switch without changing a REG.
    // At fixed q/phi/INT, the resulting algebraic voltage jump may invalidate
    // a diode's old IV segment. Close that causal topology change in the same
    // bounded iteration, rather than delaying the gate or accepting a bad IV
    // segment. State-bearing C/L segments retain the directed-root policy.
    bool switch_changed = false;
    if (regs == old.regs.read())
      for (const auto &part : m.parts)
        if (part.raw.kind == "SW") {
          const auto gate = net_name(part.raw.args[2]);
          if (mode.bools.at(gate) != old.mode.bools.at(gate)) {
            switch_changed = true;
            break;
          }
        }
    // A constitutive breakpoint can also change algebraic maps of coupled
    // nonlinear resistors. Close every event's invalid algebraic IV regions,
    // rather than restricting this operation to external gate/REG changes.
    if (regs != old.regs.read() || switch_changed || !candidates.empty())
      for (int i : m.pwas)
        if (m.parts[i].raw.kind == "R") {
          bool invalid = regs != old.regs.read();
          if (!invalid)
            for (const auto &guard : mode.binding.read().guards)
              if (guard.part == i) {
                const double tolerance =
                    64 * std::numeric_limits<double>::epsilon() *
                    (guard.row.cwiseAbs().dot(x.cwiseAbs()) + 1e-300);
                invalid = invalid || guard.row.dot(x) > tolerance;
              }
          if (invalid)
            segnext[i] =
                m.parts[i].curve.locate(coordinate(m, mode, i).dot(x));
        }
    Json directions = Json::array();
    for (const auto &g : candidates) {
      if (g.kind == "CMP") {
        Vector left = threshold(m, old.mode, g.part),
               right = threshold(m, mode, g.part);
        double dl = old.electrical_flow ? old.electrical_flow->observe(left,0,1) : left.dot(old.mode.definition.read().M*x);
        // A classification candidate cannot itself be propagated. Reuse the
        // incoming representation only if all electrical data are compatible;
        // otherwise independently evaluate the candidate's right tangent.
        double dr;
        if(old.electrical_flow && old.electrical_flow->compatible(mode))
          dr=old.electrical_flow->observe(right,0,1);
        else dr=Flow::tangent(mode,x,right);
        require(std::isfinite(dr) && dr != 0 && dl != 0, 9,
                "ZERO_EVENT_DERIVATIVE",
                "event candidate has zero or nonfinite right derivative", true,
                m.parts[g.part].raw.source);
        bool desired = (option(m.parts[g.part].raw, "OP") == "GE" ||
                        option(m.parts[g.part].raw, "OP") == "GT") == (dr > 0);
        require(!seeds.count(g.part) || ((dl > 0) == (dr > 0)), 9,
                "NO_FORWARD_ADMISSIBLE_MODE",
                "first event reverses its crossing direction after switching",
                true, m.parts[g.part].raw.source);
        next[g.part] = desired;
        directions.push_back({{"part", m.parts[g.part].raw.id},
                              {"left_derivative", dl},
                              {"right_derivative", dr},
                              {"changed", desired != original[g.part]}});
      } else if (g.kind == "PWA") {
        // C/L guards are physical charge/flux boundaries. R guards are
        // voltage boundaries and are reconstructed in the new mode.
        int step = direction(m, old.mode, g);
        Vector row = step * coordinate(m, mode, g.part);
        double dr=old.electrical_flow&&old.electrical_flow->compatible(mode)
          ? old.electrical_flow->observe(row,0,1):Flow::tangent(mode,x,row);
        require(std::isfinite(dr) && dr != 0, 9, "ZERO_EVENT_DERIVATIVE",
                "PWA candidate has zero crossing derivative", true);
        bool change = dr > 0;
        require(!seeds.count(g.part) || change, 9, "NO_FORWARD_ADMISSIBLE_MODE",
                "PWA transition reverses crossing direction", true);
        segnext[g.part] = initial_segments.at(g.part) + (change ? step : 0);
        directions.push_back(constitutive::transition(m, old.mode, mode, x, g,
                              initial_segments.at(g.part), segnext[g.part]));
      }
    }
    if (next == bits && segnext == segments) {
      accept_mode_entry(m, mode, x);
      validate_physical(mode, x);
      // A discrete source may jump algebraic quantities. Handle supported
      // causal REG/switch-driven algebraic closure above; reject any remaining invalid
      // noncandidate before committing, without searching mode families.
      for (const auto &g : mode.binding.read().guards) {
        bool member =
            std::any_of(candidates.begin(), candidates.end(),
                        [&](const auto &c) { return c.part == g.part; });
        bool unchanged =
            std::any_of(old.mode.binding.read().guards.begin(), old.mode.binding.read().guards.end(),
                        [&](const auto &before) {
                          return before.part == g.part &&
                                 before.kind == g.kind &&
                                 before.row.size() == g.row.size() &&
                                 (before.row.array() == g.row.array()).all();
                        });
        double tolerance = 64 * std::numeric_limits<double>::epsilon() *
                           (g.row.cwiseAbs().dot(x.cwiseAbs()) + 1e-300);
        require(member || unchanged || g.row.dot(x) <= tolerance, 9,
                "UNPREDICTED_GUARD_JUMP",
                "new local system has an invalid noncandidate boundary: " +
                Json({{"part",m.parts[g.part].raw.id},{"kind",g.kind},
                      {"residual",g.row.dot(x)},{"tolerance",tolerance},
                      {"old_coordinate",old.mode.segments.count(g.part) ? coordinate(m,old.mode,g.part).dot(x) : 0.0},
                      {"new_coordinate",mode.segments.count(g.part) ? coordinate(m,mode,g.part).dot(x) : 0.0}}).dump(),
                true, m.parts[g.part].raw.source);
      }
      if (details)
        *details = {{"numerical_strategy",algorithm},{"elimination_path",mode.elimination_path},{"iterations", iteration + 1},
                    {"directions", directions},
                    {"policy", "CONTROL_AND_CONSTITUTIVE_JOINT"}};
      return mode;
    }
    bits = std::move(next);
    segments = std::move(segnext);
  }
  throw Error(9, "MODE_DIRECTION_BUDGET",
              "joint derivative mode update did not converge", true);
}
} // namespace pulse::engineering
