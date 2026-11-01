#include "pulse/core.hpp"
#include "pulse/state_coordinates.hpp"
#include "pulse/solver_strategy.hpp"
#include <fstream>
#include <cstdlib>
#include "pulse/engineering.hpp"
#include "pulse/constitutive.hpp"
#include "pulse/software.hpp"
#include "pulse/time_origin.hpp"
#include "pulse/trajectory.hpp"
#include <algorithm>
#include <chrono>
#include <iomanip>
#include <regex>
#include <sstream>
namespace pulse {
namespace {
Json model_identity(const Model &m) {
  Json deadlines = Json::object();
  for (int index : m.events) {
    const auto &p = m.parts[index].raw;
    for (auto key : {"AT", "START", "PERIOD", "DELAY"})
      if (p.option_text.count(key))
        deadlines[p.id][key] = p.option_text.at(key);
  }
  return {{"encoding", "canonical pulse-netlist-1.1"},
          {"canonical", m.netlist.canonical},
          {"parameter_inputs", m.netlist.parameter_text},
          {"deadline_inputs", deadlines}};
}
std::string op(const Primitive &p, const std::string &k,
               const std::string &d = "") {
  auto i = p.options.find(k);
  return i == p.options.end() ? d : i->second;
}
std::string time_input(std::string text, const Netlist &net) {
  for (int i = 0; i < 100; ++i) {
    std::erase_if(text, [](unsigned char c) { return std::isspace(c); });
    if (text.size() >= 2 && text.front() == '{' && text.back() == '}')
      text = text.substr(1, text.size() - 2);
    auto p = net.parameter_text.find(text);
    if (p == net.parameter_text.end())
      break;
    text = p->second;
  }
  static const std::regex pattern(
      R"(([+-]?)([0-9]*\.?[0-9]+)([eE][+-]?[0-9]+)?([A-Za-z]*))");
  std::smatch match;
  if (!std::regex_match(text, match, pattern))
    return "UNPROVEN:" + text;
  std::string digits = match[2];
  int exponent =
      match[3].str().empty() ? 0 : std::stoi(match[3].str().substr(1));
  auto dot = digits.find('.');
  if (dot != std::string::npos) {
    exponent -= int(digits.size() - dot - 1);
    digits.erase(dot, 1);
  }
  static const std::map<std::string, int> units = {
      {"", 0},    {"T", 12},  {"G", 9},  {"Meg", 6}, {"meg", 6},
      {"MEG", 6}, {"k", 3},   {"K", 3},  {"m", -3},  {"u", -6},
      {"n", -9},  {"p", -12}, {"f", -15}};
  auto unit = units.find(match[4]);
  if (unit == units.end())
    return "UNPROVEN:" + text;
  exponent += unit->second;
  auto first = digits.find_first_not_of('0');
  if (first == std::string::npos)
    return "0";
  digits.erase(0, first);
  while (digits.back() == '0') {
    digits.pop_back();
    ++exponent;
  }
  return (match[1].str() == "-" ? "-" : "") + digits + "e" +
         std::to_string(exponent);
}
std::string exact_time_origin(Time at) {
  auto value = decimal_origin_from_binary_time(at.whole, at.tick, at.subtick);
  require(value.value.has_value(), 7, "TIME_RESOLUTION_UNRESOLVED",
          "time origin exceeds exact decimal bookkeeping budget", true);
  return canonical_decimal_origin(*value.value).value();
}
std::string sum_origin(const std::string &a, const std::string &b,
                       uint64_t factor = 1) {
  if (factor == 0 || b == "0")
    return a;
  auto av = parse_decimal_origin(a), bv = parse_decimal_origin(b);
  if (av.value && bv.value) {
    auto multiple = times_decimal_origin(*bv.value, factor);
    if (multiple.value) {
      auto result = add_decimal_origins(*av.value, *multiple.value);
      if (result.value)
        return canonical_decimal_origin(*result.value).value();
    }
    throw Error(7, "TIME_RESOLUTION_UNRESOLVED",
                "deadline origin arithmetic exceeds budget", true);
  }
  if (a == "0" && factor == 1)
    return b;
  auto symbolic =
      "UNPROVEN_SUM(" + a + "," + b + "," + std::to_string(factor) + ")";
  require(symbolic.size() <= 16384, 7, "TIME_RESOLUTION_UNRESOLVED",
          "symbolic deadline origin exceeds bookkeeping budget", true);
  return symbolic;
}
void fault(const Options &o, const std::string &point) {
  require(o.fault != point, 12, "INJECTED_FAULT",
          "fault injection at " + point);
}
bool valid(const RunState &s, const Agenda &a) {
  auto i = s.generations.find(a.part);
  return a.generation == (i == s.generations.end() ? 0 : i->second);
}
void check_agenda_origins(const Model &m, const RunState &s) {
  std::map<Time, const Agenda *> ordered;
  for (auto &a : s.agenda) {
    if (!valid(s, a))
      continue;
    auto [it, inserted] = ordered.emplace(a.at, &a);
    require(inserted || it->second->origin == a.origin, 7,
            "TIME_RESOLUTION_UNRESOLVED",
            "distinct external deadline origins collapse at a future effective "
            "time; equality unproven",
            true, m.parts[a.part].raw.source);
  }
  if (ordered.empty())
    return;
  auto before = ordered.begin();
  for (auto after = std::next(before); after != ordered.end();
       before = after++) {
    auto a = parse_decimal_origin(before->second->origin),
         b = parse_decimal_origin(after->second->origin);
    if (!a.value || !b.value)
      continue;
    auto order = compare_decimal_origins(*a.value, *b.value);
    require(order && *order < 0, 7, "TIME_RESOLUTION_UNRESOLVED",
            "external deadline equality/order is not preserved by effective "
            "binary64 conversion",
            true, m.parts[after->second->part].raw.source);
  }
}
void prune(RunState &s) {
  std::erase_if(s.agenda, [&](auto &a) { return !valid(s, a); });
}
std::string fingerprint(const RunState &s, const std::set<std::string> &trig) {
  std::ostringstream x;
  x << std::setprecision(17) << s.mode.id;
  for (auto &t : trig)
    x << "!" << t;
  for (const auto &[name, state] : s.software) {
    x << "$" << name << ":" << state.invocation << ":";
    for (auto byte : state.bytes) x << unsigned(byte) << ",";
  }
  std::vector<std::string> pending;
  for (auto &a : s.agenda)
    if (valid(s, a))
      pending.push_back(a.at.canonical() + ":" + a.trigger + ":" + a.origin);
  std::sort(pending.begin(), pending.end());
  for (auto &a : pending)
    x << "@" << a;
  return x.str();
}
double snapshot(const RunState &s, const std::string &name) {
  return state_signal(s,name);
}
std::set<std::string> edges(const Model &m, const Mode &before,
                            const Mode &after) {
  std::set<std::string> result;
  for (int i : m.events) {
    const auto &p = m.parts[i].raw;
    if (op(p, "MODE") != "EDGE")
      continue;
    auto source = net_name(op(p, "SOURCE"));
    bool a = before.bools.at(source), b = after.bools.at(source);
    auto direction = op(p, "EDGE");
    if (a != b && (direction == "BOTH" || (direction == "RISE" && b) ||
                   (direction == "FALL" && !b)))
      result.insert(net_name(p.args[0]));
  }
  return result;
}
void closure(const Model &m, RunState &candidate,
             std::set<std::string> triggers,
             const std::vector<Mode::Guard> &crossings,
             const std::set<int> &seeds, Result &out, const Options &o,
             std::vector<Json> &logs, uint64_t tx, Json &mode_details,
             software::Session *software_session, int algorithm) {
  std::set<std::string> seen;
  bool first = true;
  for (size_t delta = 0; !triggers.empty() || (first && !crossings.empty());
       ++delta) {
    require(delta < o.max_microsteps, 9, "MICROSTEP_BUDGET",
            "same-time transaction budget exhausted", true);
    require(seen.insert(fingerprint(candidate, triggers)).second, 9,
            "ZERO_TIME_CYCLE", "same-time configuration repeated", true);
    ++out.stats.microsteps;
    RunState snap = candidate;
    auto newregs = snap.regs;
    std::set<std::string> next;
    for (const auto &t : triggers)
      logs.push_back({{"time_canonical", candidate.at.canonical()},
                      {"time_seconds_display", candidate.at.seconds()},
                      {"delta", delta},
                      {"kind", "TRIG"},
                      {"source", t},
                      {"source_instance", m.signals.at(t).driver},
                      {"transaction_id", tx},
                      {"before_mode", snap.mode.id},
                      {"policy", "SCHEDULED_OR_CAUSAL"},
                      {"certificate_scope", "ENGINEERING_POINT_TRAJECTORY"}});
    for (int i : m.registers) {
      const auto &p = m.parts[i].raw;
      auto name = net_name(p.args[0]);
      if (m.software_outputs.count(name)) continue;
      if (op(p, "MODE") == "SR") {
        bool set = triggers.count(net_name(op(p, "SET"))),
             reset = triggers.count(net_name(op(p, "RESET")));
        if (set || reset)
          newregs[name] = set && reset ? (op(p, "PRIORITY") == "SET") : set;
      } else if (triggers.count(net_name(p.args[2])))
        newregs[name] = snapshot(snap, p.args[1]);
    }
    for (int i : m.events) {
      const auto &p = m.parts[i].raw;
      if (op(p, "MODE") == "DELAY" && p.options.count("CANCEL") &&
          triggers.count(net_name(op(p, "CANCEL"))))
        ++candidate.generations[i];
    }
    for (int i : m.events) {
      const auto &p = m.parts[i].raw;
      if (op(p, "MODE") != "DELAY" ||
          !triggers.count(net_name(op(p, "SOURCE"))))
        continue;
      double delay = p.options.count("DELAY_INPUT")
                         ? snapshot(snap, op(p, "DELAY_INPUT"))
                         : number(op(p, "DELAY"));
      require(delay >= 0 && std::isfinite(delay), 7, "INVALID_DELAY",
              "latched delay is negative or nonfinite", false, p.source);
      if (op(p, "POLICY", "TRANSPORT") == "REPLACE")
        ++candidate.generations[i];
      auto trigger = net_name(p.args[0]);
      if (delay == 0)
        next.insert(trigger);
      else
        candidate.agenda.push_back(
            {candidate.at + Time::from(delay), i, 0, candidate.generations[i],
             trigger,
             sum_origin(
                 candidate.time_origin,
                 p.options.count("DELAY_INPUT")
                     ? exact_time_origin(Time::from(delay))
                     : time_input(p.option_text.at("DELAY"), m.netlist))});
    }
    if (software_session) {
      auto wakeups = software_session->execute(snap, candidate, triggers, newregs, logs, tx, delta);
      for (const auto &wake : wakeups) {
        Time delay = Time::from(wake.delay);
        require(candidate.at + delay > candidate.at, 7, "SOFTWARE_WAKEUP_RESOLUTION",
                "software wakeup does not advance simulated time", true);
        candidate.agenda.push_back({candidate.at + delay, wake.part, 0, 0, wake.trigger,
                                    sum_origin(candidate.time_origin, exact_time_origin(delay))});
      }
    }
    check_agenda_origins(m, candidate);
    fault(o, "after_queue");
    candidate.regs = std::move(newregs);
    fault(o, "after_reg");
    Json delta_details;
    candidate.mode = engineering::update_mode(
        m, snap, candidate.internal, candidate.regs,
        first ? crossings : std::vector<Mode::Guard>{},
        first ? seeds : std::set<int>{}, out.stats, &delta_details, algorithm);
    require(candidate.mode.numerical_strategy==algorithm,12,"STRATEGY_MISMATCH",
            "event closure changed numerical strategy inside an attempt");
    if (first)
      mode_details = delta_details;
    else
      mode_details["subsequent_delta_updates"].push_back(
          {{"delta", delta}, {"update", delta_details}});
    if(snap.electrical_flow && snap.electrical_flow->compatible(candidate.mode))
      candidate.electrical_flow=std::make_shared<engineering::Flow>(snap.electrical_flow->continued(candidate.mode,0));
    else { candidate.electrical_flow.reset(); candidate.electrical_strategy=-1; }
    candidate.mode.version = ++candidate.version;
    fault(o, "after_mode");
    auto newedges = edges(m, snap.mode, candidate.mode);
    next.insert(newedges.begin(), newedges.end());
    for (auto &log : logs)
      if (log.value("delta", size_t(-1)) == delta)
        log["after_mode"] = candidate.mode.id;
    triggers = std::move(next);
    prune(candidate);
    out.stats.queue_peak =
        std::max(out.stats.queue_peak, uint64_t(candidate.agenda.size()));
    first = false;
  }
}
void stream_setup(const Model&m,Result&out,const Options&o){
  auto selected=o.channels?o.channels:m.netlist.channels;std::set<std::string> chosen;
  if(selected&&selected->size()==1&&selected->front()=="*")selected.reset();
  if(selected)for(const auto&n:*selected){require(std::find(m.registry.begin(),m.registry.end(),n)!=m.registry.end()||(m.signals.count(n)&&m.signals.at(n).type==Signal::TRIG),11,"UNKNOWN_CHANNEL","unknown output channel: "+n);chosen.insert(n);}
  for(const auto&n:m.registry)if(!selected||chosen.count(n)){bool digital=m.signals.count(n)&&m.signals.at(n).type==Signal::BOOL;(digital?out.digital_names:out.analog_names).push_back(n);}
}
void stream_emit(const Model&,Result&out,const RunState&old,const RunState&next,Time at,bool,bool replace=false){
  Vector x;const Mode*mode=nullptr;
  if(at==next.at){x=next.internal;mode=&next.mode;}
  else if(at==old.at){x=old.internal;mode=&old.mode;}
  else {engineering::Flow flow=old.electrical_flow?*old.electrical_flow:engineering::Flow(old.mode,old.internal);x=flow.state((at-old.at).seconds());mode=&old.mode;}
  if(replace){out.times.pop_back();out.analog.resize(out.analog.size()-out.analog_names.size());out.digital.resize(out.digital.size()-out.digital_names.size());}
  size_t width=out.analog_names.size()*sizeof(float)+out.digital_names.size()+sizeof(double);
  require(out.times.size()<10000000&&(out.times.size()+1)*width<512.*1024*1024,11,"OUTPUT_LIMIT","output exceeds 512 MiB or 10 million samples");
  out.times.push_back(at.seconds());
  for(const auto&name:out.analog_names){double v=0;v=mode->maps.at(name).dot(x);
    const RunState &anchor=at==next.at?next:old;
    if(anchor.electrical_flow && anchor.electrical_flow->compatible(*mode))
      v=anchor.electrical_flow->observe(mode->maps.at(name),(at-anchor.at).seconds());
    require(std::isfinite(v)&&std::abs(v)<=std::numeric_limits<float>::max(),11,"OUTPUT_NONFINITE","streamed output cannot be represented");out.analog.push_back(float(v));}
  for(const auto&name:out.digital_names)out.digital.push_back(mode->bools.at(name));
}
void stream_commit(const Model&m,Result&out,const RunState&old,const RunState&next,bool backward,uint64_t&index){
  if(next.at==old.at){if(!out.times.empty()&&out.times.back()==next.at.seconds())stream_emit(m,out,old,next,next.at,backward,true);return;}
  const Time dt=Time::from(out.save_dt);
  for(;;){Time at=dt.times(index);if(at>next.at)break;require(at>=old.at,12,"STREAM_TIME","output sample precedes current segment");stream_emit(m,out,old,next,at,backward);++index;}
}
} // namespace
Result simulate(const Model &original, const Options &o) {
  Model owned_model=original;owned_model.numerical_coordinates=true;const Model&m=owned_model;
  portfolio_reset_equations();
  Result out;PortfolioStats portfolio;uint64_t output_index=1,total_event_records=0;
  auto begin = std::chrono::steady_clock::now();
  ScopedModeCache mode_cache(m, o.mode_cache_capacity);
  std::unique_ptr<software::Session> software_session;
  try {
    out.t_end = o.t_end.value_or(m.netlist.t_end.value_or(0));
    out.save_dt = o.save_dt.value_or(m.netlist.save_dt.value_or(0));
    require(out.t_end > 0 && out.save_dt > 0 && std::isfinite(out.t_end) &&
                std::isfinite(out.save_dt),
            1, "MISSING_SIMULATION_CONFIG",
            "positive T_END and SAVE_DT required");
    require(o.atom_exponent >= -1 && o.atom_exponent <= 18, 1, "ATOM_EXPONENT",
            "legacy atom exponent outside supported range");
    out.t_atom = m.netlist.atomic_time.value_or(o.atomic_time);
    if (o.atom_exponent >= 0)
      out.t_atom = out.save_dt * std::pow(10., -o.atom_exponent);
    require(out.t_atom >= 0x1p-64 && std::isfinite(out.t_atom), 7,
            "TIME_RESOLUTION_UNRESOLVED",
            "atomic time is below representation or nonfinite", true);
    Time end = Time::from(out.t_end);
    RunState state;
    // This experimental RunState vector is the authoritative fixed-chart xi.
    // Physical q/phi views are never fed back across an event.
    state.internal = persistent_encode(m,m.initial);state.physical=m.initial;
    for (int i : m.registers)
      state.regs[net_name(m.parts[i].raw.args[0])] =
          number(op(m.parts[i].raw, "IC", "0"));
    state.mode =
        engineering::initial_mode(m, state.internal, state.regs, out.stats);
    if (!m.netlist.tasks.empty()) {
      software_session = std::make_unique<software::Session>(m);
      software_session->initialize(state, out.stats);
      state.mode = engineering::initial_mode(m, state.internal, state.regs, out.stats);
    }
    state.version = 1;
    for (int i : m.events) {
      const auto &p = m.parts[i].raw;
      auto mode = op(p, "MODE");
      const bool private_wakeup = std::any_of(m.netlist.tasks.begin(),m.netlist.tasks.end(),
          [&](const auto &task){return !task.self_trigger && task.wake_trigger==net_name(p.args[0]);});
      if (private_wakeup) continue;
      if (mode == "AT" || mode == "PERIODIC") {
        auto key = mode == "AT" ? "AT" : "START";
        state.agenda.push_back(
            {Time::from(number(op(p, key, "0"))), i, 0, 0, net_name(p.args[0]),
             time_input(p.option_text.count(key) ? p.option_text.at(key) : "0",
                        m.netlist)});
      }
    }
    check_agenda_origins(m, state);
    out.stats.queue_peak = state.agenda.size();
    out.committed = state;
    out.segments.push_back({state});stream_setup(m,out,o);
    if(o.trajectory_output){out.trajectory=std::make_shared<Trajectory>();out.trajectory->initial(state);}
    else stream_emit(m,out,state,state,state.at,false);
    bool first = true;
    while (first || out.committed.at < end) {
      first = false;
      if(const char*limit=std::getenv("PULSE_WALL_SECONDS"))require(std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count()<number(limit),9,"WALL_BUDGET","caller wall budget reached; committed prefix preserved",true);
      require(o.max_transactions == 0 || out.stats.transactions < o.max_transactions, 9,
              "TRANSACTION_BUDGET", "physical transaction budget exhausted",
              true);
      const RunState &old = out.committed;
      Time target = end;
      bool due = false;
      for (const auto &a : old.agenda)
        if (valid(old, a) && a.at <= target) {
          target = a.at;
          due = true;
        }
      require(target >= old.at, 12, "AGENDA_PAST",
              "scheduled event precedes current time");

      const Time scheduled_target=target;const bool scheduled_due=due;
      RunState candidate=old;std::vector<Mode::Guard> crossings;std::set<int> seeds;Json root_log;bool found=false;

      const RunState checkpoint=old;

      RunState propagation_old=old;
      bool accepted_algorithm=false;Json failures=Json::array();std::vector<Json> logs;
      std::string attempt_phase;
      for(int algorithm=0;algorithm<3;algorithm++){
       ++portfolio.attempts[algorithm];
       target=scheduled_target;due=scheduled_due;candidate=checkpoint;
       found=false;crossings.clear();seeds.clear();root_log=Json::object();logs.clear();attempt_phase="compile_or_propagate";
       try {
        Mode algorithm_mode=portfolio_mode(m,checkpoint,algorithm,out.stats);
        ++portfolio.executed_paths[algorithm][algorithm_mode.elimination_path];
        engineering::Flow flow = checkpoint.electrical_flow && checkpoint.electrical_strategy==algorithm && checkpoint.electrical_flow->compatible(algorithm_mode)
          ? checkpoint.electrical_flow->continued(algorithm_mode,0)
          : engineering::Flow(algorithm_mode, checkpoint.internal);
      engineering::SearchResult roots;
      if (target > old.at && !algorithm_mode.guards.empty()) {
        ++out.stats.root_queries;
        try {
          roots = engineering::next_events(
              algorithm_mode, flow, (target - old.at).seconds(), out.t_atom);
        } catch (const std::exception &) {
          ++out.stats.root_failures;
          throw;
        }
      }
      found = !roots.candidates.empty();

      if (found) {
        auto root = roots.candidates.front();
        // Recheck every candidate before grouping, propagation or mode closure.
        // Any failure unwinds the entire strategy attempt to its checkpoint.
        for (const auto &r : roots.candidates)
          engineering::validate_event_timing(flow, r, out.t_atom);
        const auto execution_root=roots.candidates.back();
        Time root_at = old.at + Time::from(execution_root.time);
        require(root_at <= target, 8, "TIME_ORDER_UNRESOLVED",
                "computed root overtakes an independent deadline", true);
        due = due && root_at == target;
        target = root_at;
        for (const auto &r : roots.candidates) {
          auto g = algorithm_mode.guards.at(r.guard);
          if (g.kind == "PWA" || g.kind == "RANGE" || g.kind == "CMP") {
            // The scalar modal guard and reconstructed state use different
            // cancellation paths. Use the existing guard evaluation scale,
            // in addition to root-location error; never a fixed voltage epsilon.
            g.arrival_error = std::abs(r.slope) * ((r.upper - r.lower) + (root.upper - root.lower)) +
                              64 * std::numeric_limits<double>::epsilon() * flow.scale(r.guard);

          }
          require(g.kind != "RANGE", 5, "PWA_OUT_OF_RANGE",
                  "PWA table range exhausted", false,
                  m.parts[g.part].raw.source);
          if(g.kind=="PWA"){
            const Vector at_own_root=flow.state(r.time);
            require(constitutive::arrived(g,at_own_root,g.arrival_error),9,
              "BREAKPOINT_PREDICTION_MISMATCH","predicted breakpoint is not reached at its own predicted time: "+
              Json({{"part",m.parts[g.part].raw.id},{"local_time",r.time},{"residual",g.row.dot(at_own_root)},{"evaluation_bound",g.arrival_error}}).dump(),true,m.parts[g.part].raw.source);
          }
          crossings.push_back(g);
        }
        seeds.insert(algorithm_mode.guards.at(root.guard).part);
        root_log = {
            {"kind", "ROOT"},
            {"time_canonical", target.canonical()},
            {"time_seconds_display", target.seconds()},
            {"delta", 0},
            {"transaction_id", out.stats.transactions + 1},
            {"before_mode", old.mode.id},
            {"policy", "FIRST_PLUS_ATOM_EXECUTE_AT_LAST_OWN_ROOTS_CHECKED"},
            {"certificate_scope", "ENGINEERING_POINT_TRAJECTORY"},
            {"root_interval",
             {{"lower", (old.at + Time::from(execution_root.lower)).canonical()},
              {"upper", (old.at + Time::from(execution_root.upper)).canonical()}}},
            {"T_atom", out.t_atom},
            {"first_predicted_local_time",root.time},{"execution_local_time",execution_root.time},
            {"execution_delay_from_first",execution_root.time-root.time},
            {"search_nodes", roots.nodes},{"prediction_strategy",algorithm},
            {"root_time_precision_checked",false},
            {"root_old_noise",8*std::numeric_limits<double>::epsilon()*flow.scale(root.guard)},
            {"root_slope_times_atom",std::abs(root.slope)*out.t_atom},
            {"candidate_members", Json::array()},
            {"predicted_events", Json::array()}};
        for (const auto &r : roots.candidates) {
          auto &id = m.parts[algorithm_mode.guards[r.guard].part].raw.id;
          root_log["candidate_members"].push_back(id);
          root_log["predicted_events"].push_back(
              {{"part", id},
               {"old_mode_local_time", r.time},
               {"offset_from_first_seconds",r.time-root.time},
               {"left_slope", r.slope}});
        }
      }
      candidate.internal = flow.state((target - old.at).seconds());
      if (target > old.at)
        ++out.stats.exponentials;
      validate_physical(algorithm_mode,candidate.internal);
      for(double fraction:{0.,.5,1.}){
        Vector probe=flow.state(fraction*(target-checkpoint.at).seconds());
        portfolio_original_check(m,checkpoint,algorithm_mode,probe);
      }
      propagation_old.mode=std::move(algorithm_mode);
      attempt_phase="event_closure";
      candidate.mode=propagation_old.mode;
      propagation_old.electrical_flow=std::make_shared<engineering::Flow>(flow);
      propagation_old.electrical_strategy=algorithm;
      candidate.electrical_flow=std::make_shared<engineering::Flow>(flow.continued(candidate.mode,(target-checkpoint.at).seconds()));
      candidate.electrical_strategy=algorithm;
      candidate.physical=physical_view(m,candidate.internal);
      candidate.at = target;
      candidate.time_origin = exact_time_origin(target);
      fault(o, "after_propagation");

      std::set<std::string> triggers;
      if (due) {
        std::vector<Agenda> remaining;
        for (const auto &a : candidate.agenda) {
          if (!valid(candidate, a))
            continue;
          if (a.at != target) {
            remaining.push_back(a);
            continue;
          }
          triggers.insert(a.trigger);
          candidate.time_origin = a.origin;
          const auto &p = m.parts[a.part].raw;
          if (op(p, "MODE") == "PERIODIC") {
            auto cycle = a.cycle + 1;
            remaining.push_back(
                {Time::from(number(op(p, "START", "0"))) +
                     Time::from(number(op(p, "PERIOD"))).times(cycle),
                 a.part, cycle, 0, a.trigger,
                 sum_origin(time_input(p.option_text.count("START")
                                           ? p.option_text.at("START")
                                           : "0",
                                       m.netlist),
                            time_input(p.option_text.at("PERIOD"), m.netlist),
                            cycle)});
          }
        }
        candidate.agenda = std::move(remaining);
        check_agenda_origins(m, candidate);
      }
      Json mode_details;
      closure(m, candidate, std::move(triggers), crossings, seeds, out, o, logs,
              out.stats.transactions + 1, mode_details, software_session.get(), algorithm);
      if (found) {
        root_log["after_mode"] = candidate.mode.id;
        root_log["mode_update"] = mode_details;
        root_log["actual_changed_members"] = Json::array();
        for (int i : m.cmps) {
          auto name = net_name(m.parts[i].raw.args[0]);
          if (old.mode.bools.at(name) != candidate.mode.bools.at(name))
            root_log["actual_changed_members"].push_back(m.parts[i].raw.id);
        }
        for (int i : m.pwas)
          if (old.mode.segments.at(i) != candidate.mode.segments.at(i))
            root_log["actual_changed_members"].push_back(m.parts[i].raw.id);
        root_log["members"] = root_log["actual_changed_members"];
        root_log["accepted_state_kind"] = "approx";
        root_log["first_root_evidence"] = "ENGINEERING_NUMERICAL";
        {Vector physical=physical_view(m,candidate.internal);root_log["state_before_switch"]=std::vector<double>(physical.data(),physical.data()+m.ns);}
        logs.insert(logs.begin(), root_log);
      }
      require(candidate.mode.numerical_strategy==algorithm,12,"STRATEGY_MISMATCH",
              "committed strategy must equal the strategy that predicted the event");
      validate_physical(candidate.mode,candidate.internal);
      for(auto &log:logs){log["numerical_strategy"]=algorithm;log["committed_elimination_path"]=candidate.mode.elimination_path;}
      if(o.fault=="retry_after_closure"){
        candidate.internal[0]+=1.;throw Error(7,"INJECTED_EVENT_CLOSURE_REJECTION","test rejects staged MCU/electrical/queue updates before commit",true);
      }
      fault(o, "before_output");
      accepted_algorithm=true;++portfolio.accepted[algorithm];
      break;
       }catch(const Error&e){
        if(!portfolio_retryable(e))throw;
        const auto recorded_failures=portfolio.failures.size();
        portfolio.record_failure(algorithm,checkpoint,target,e);
        if(portfolio.failures.size()>recorded_failures){
          auto &record=portfolio.failures.back();
          record["attempt_phase"]=attempt_phase;
          record["uncommitted_root_prediction"]=root_log;
          record["selected_crossings"]=Json::array();
          for(const auto&g:crossings)record["selected_crossings"].push_back({{"part",m.parts[g.part].raw.id},{"kind",g.kind},{"arrival_error",g.arrival_error}});
        }
        failures.push_back({{"algorithm",algorithm},{"stage",attempt_phase},{"diagnostic",diagnostic(e)}});
        candidate=checkpoint;
       }
      }
      require(accepted_algorithm,7,"ALL_EVENT_ALGORITHMS_FAILED","all registered methods failed from the same event checkpoint: "+failures.dump(),true);
      ++candidate.version;
      if(out.trajectory)out.trajectory->append(propagation_old,candidate);
      else stream_commit(m,out,propagation_old,candidate,false,output_index);
      out.committed = std::move(candidate);
      if(!o.retain_history)out.segments.clear();
      out.segments.push_back({out.committed});

      total_event_records+=logs.size();out.events.insert(out.events.end(),logs.begin(),logs.end());
      ++out.stats.transactions;
      if (target == end)
        break;
    }
    out.status = "COMPLETED";
    out.evidence = "ENGINEERING_POINT_TRAJECTORY";
  } catch (const std::exception &e) {
    out.diagnostic = diagnostic(e);
    auto p = dynamic_cast<const Error *>(&e);
    out.status = p && p->unresolved ? "STOPPED_UNRESOLVED" : "STOPPED_ERROR";
    ++out.stats.rollbacks;
  }
  try {
    if(!out.trajectory&&out.save_dt>0&&(out.times.empty()||out.times.back()!=out.committed.at.seconds()))stream_emit(m,out,out.committed,out.committed,out.committed.at,false);
  } catch (const std::exception &e) {
    out.status = "STOPPED_ERROR";
    out.diagnostic = diagnostic(e);
    out.times.clear();
    out.analog.clear();
    out.digital.clear();
  }
  out.stats.run_seconds =
      std::chrono::duration<double>(std::chrono::steady_clock::now() - begin)
          .count();
  Json software_states = Json::object(), software_outputs = Json::object();
  for (const auto &[name, state] : out.committed.software)
    software_states[name] = {{"invocations",state.invocation},{"state_bytes",state.bytes.size()}};
  for (const auto &name : m.software_outputs)
    if (out.committed.regs.count(name)) software_outputs[name] = out.committed.regs.at(name);
  out.report = {
      {"software_states", software_states},
      {"software_final_outputs", software_outputs},
      {"version", "1.2.0-pre"},
      {"source_sha256", PULSE_SOURCE_SHA256},
      {"model_version", model_identity(m)},
      {"algorithm", "EVENT_CHECKPOINT_STRATEGY_RETRY"},
      {"strategy_consistency",{{"policy","One explicit numerical strategy for prediction, propagation, all closure microsteps and commit; failed attempts roll back and recompute all candidates from the immutable checkpoint."},{"enforced",true},{"committed_strategy",out.committed.mode.numerical_strategy}}},
      {"event_timing_policy","First+T_atom fixed window, execute at latest member, validate every PWA at own prediction; no absolute time-error veto; exact software deadlines unchanged"},
      {"spice_policy","NOT_IMPLEMENTED: event propagation only"},
      {"algorithm_portfolio",portfolio.description()},
      {"persistent_chart",persistent_description(m)},
      {"internal_state",std::vector<double>(out.committed.internal.data(),out.committed.internal.data()+out.committed.internal.size())},
      {"physical_state_view",[&](){if(out.committed.internal.size()!=m.ns+1)return std::vector<double>{};Vector x=physical_view(m,out.committed.internal);return std::vector<double>(x.data(),x.data()+x.size());}()},
      {"state_storage","internal coordinates are authoritative; public physical q/phi/INT snapshots are read-only views"},
      {"event_records_total",total_event_records},
      {"history_retained",o.retain_history},
      {"netlist_format", m.netlist.format},
      {"software_modules", software_session ? software_session->identity() : Json::array()},
      {"breakpoint_policy", "FIRST_PLUS_ATOM; execute at latest member; verify each knot at its own prediction"},
      {"status", out.status},
      {"evidence", out.evidence},
      {"diagnostic", out.diagnostic},
      {"effective_T_END", out.t_end},
      {"effective_SAVE_DT", out.save_dt},
      {"T_atom", out.t_atom},
      {"atomic_time_policy", o.atom_exponent >= 0
                                 ? "EXPLICIT_LEGACY_OUTPUT_RELATIVE"
                                 : "FIXED_INDEPENDENT_OF_OUTPUT_GRID"},
      {"Q_repr", 0x1p-64},
      {"time_backend", "T128: signed seconds plus 128 fractional bits"},
      {"committed_prefix_end", out.committed.at.canonical()},
      {"simulated_seconds", out.committed.at.seconds()},
      {"transactions", out.stats.transactions},
      {"transaction_limit", o.max_transactions},
      {"transaction_limit_policy", o.max_transactions == 0 ?
         "UNLIMITED_TOTAL; BOUNDED_SAME_TIME_CLOSURE" : "EXPLICIT_CALLER_BUDGET"},
      {"root_queries", out.stats.root_queries},
      {"root_failures", out.stats.root_failures},
      {"mode_compilations", out.stats.modes},
      {"microsteps", out.stats.microsteps},
      {"rollbacks", out.stats.rollbacks},
      {"queue_peak", out.stats.queue_peak},
      {"matrix_exponentials", out.stats.exponentials},
      {"mode_cache_hits", out.stats.cache_hits},
      {"mode_cache_misses", out.stats.mode_cache_misses},
      {"mode_cache_capacity", o.mode_cache_capacity},
      {"mode_cache_peak_entries", out.stats.mode_cache_peak_entries},
      {"mode_cache_evictions", out.stats.mode_cache_evictions},
      {"mode_cache_policy", "RUN_SCOPED_COMPLETE_CANDIDATE_KEY_FIFO"},
      {"run_seconds", out.stats.run_seconds},
      {"parse_seconds", m.netlist.parse_seconds},
      {"compile_seconds", m.compile_seconds},
      {"physical_state_ids", m.state_ids},
      {"registry", m.registry},
      {"analog_channels", out.analog_names},
      {"digital_channels", out.digital_names},
      {"max_algebraic_residual", out.stats.max_residual},
      {"projection_count", 0},
      {"certificate_scope", "engineering numerical point trajectory; no "
                            "all-history or global mathematical certificate"},
      {"model_contract",
       "piecewise-affine modes; explicit transition dynamics where needed; "
       "nonzero crossing derivatives; unsupported degeneracy stops safely"}};
  publish_physical_state(m,out.committed);
  for(auto&segment:out.segments)publish_physical_state(m,segment.state);
  auto selected=o.channels?o.channels:m.netlist.channels;
  if(selected&&!(selected->size()==1&&selected->front()=="*"))std::erase_if(out.events,[&](const Json&e){return e.value("kind","")=="TRIG"&&std::find(selected->begin(),selected->end(),e.value("source",""))==selected->end();});
  out.report["output_format"]=out.trajectory?"trajectory":"waveform";
  out.report["waveform_validation"]=out.trajectory?"DEFERRED_TO_REPLAY":"PERFORMED_DURING_SIMULATION";
  return out;
}
Result replay_trajectory(const std::filesystem::path &path,std::optional<double>save_dt){
  Model model;uint64_t index=1;auto start=std::chrono::steady_clock::now();
  auto out=Trajectory::read(path,[&](Result&r,const RunState&old,const RunState&next,bool initial){
    if(initial){
      if(save_dt)r.save_dt=*save_dt;
      require(std::isfinite(r.save_dt)&&r.save_dt>0,1,"MISSING_SIMULATION_CONFIG","positive replay SAVE_DT required");
      stream_emit(model,r,old,next,next.at,false);
    }else stream_commit(model,r,old,next,false,index);
  });
  if(out.times.empty()||out.times.back()!=out.committed.at.seconds())stream_emit(model,out,out.committed,out.committed,out.committed.at,false);
  out.report["output_format"]="waveform";
  out.report["waveform_validation"]="PASSED";
  out.report["effective_SAVE_DT"]=out.save_dt;
  out.report["replay_seconds"]=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
  return out;
}
} // namespace pulse
