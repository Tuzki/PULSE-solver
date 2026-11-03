// Independent PULSE V1.15 engineering-event acceptance draft.
// Public API only; no fixture mutation, output writes, or long simulations.
// Link with pulse_core. Optional argv[1]: one exact case name.
#include "pulse/core.hpp"
#include <algorithm>
#include <cmath>
#include <functional>
#include <iostream>
#include <numbers>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using namespace pulse;
int assertions = 0, passes = 0, failures = 0;
void check(bool value, const std::string &message) {
    ++assertions;
    if (!value) throw std::runtime_error(message);
}
void near(double value, double expected, double tolerance, const std::string &label) {
    check(std::isfinite(value) && std::abs(value - expected) <= tolerance,
          label + ": actual=" + std::to_string(value) + " expected=" + std::to_string(expected));
}
std::string document(const std::string &network, const std::string &end = "1",
                     const std::string &save = ".1") {
    // Retain v1.1 input grammar as a compatibility contract, regardless of engine version.
    return "# PULSE Netlist v1.1\n\n## Parameters\n```pulse\n```\n\n## Network\n```pulse\n" +
           network + "\n```\n\n## Simulation\n```pulse\n.TRAN T_END=" + end + " SAVE_DT=" + save +
           "\n```\n\n## Layout\n```json\n{}\n```\n";
}
template<class O> void atomic_window(O &options, double seconds) {
    // This keeps the draft compilable against the old public header; V1.15 runs
    // must expose atomic_time. Never fall back silently to SAVE_DT/10^N.
    if constexpr (requires(O &o) { o.atomic_time = seconds; })
        options.atomic_time = seconds;
    else
        throw std::runtime_error("V1.15 Options.atomic_time is required by this case");
}
Result run(const std::string &network, const std::string &end = "1",
           const std::string &save = ".1", Options options = {}) {
    return simulate(compile(parse_markdown(document(network, end, save), "engineering-events-memory.md")),
                    options);
}
void complete(const Result &r) {
    check(r.status == "COMPLETED", r.status + " " + r.diagnostic.dump());
}
double value(const Result &r, const std::string &name) {
    return r.committed.mode.binding.read().maps.at(name).dot(r.committed.physical);
}
std::vector<Json> triggers(const Result &r, const std::string &source) {
    std::vector<Json> result;
    for (const auto &event : r.events)
        if (event.value("kind", "") == "TRIG" && event.value("source", "") == source)
            result.push_back(event);
    return result;
}
Time at(const Json &event) { return Time::decode(event.at("time_canonical").get<std::string>()); }
void history(const Result &r) {
    Time previous;
    bool seen = false;
    for (const auto &event : r.events) {
        Time current = at(event);
        check(!seen || current >= previous, "committed event history regressed");
        check(current <= r.committed.at, "event escaped committed prefix");
        previous = current;
        seen = true;
    }
}
void rc_analytic() {
    // Vc(t)=3*(1-exp(-t/2)); I=(3-Vc)/2, no switching guards.
    auto r = run("V1 IN 0 DC=3\nR1 IN OUT R=2\nC1 OUT 0 C=1 IC_V=0\n"
                 "SENSOR_V VC V OUT 0\nSENSOR_I IR I R1", "2", ".125");
    complete(r);
    near(value(r, "VC"), 3 * (1 - std::exp(-1.)), 2e-10, "RC endpoint");
    near(value(r, "IR"), 1.5 * std::exp(-1.), 2e-10, "RC current");
    check(!r.times.empty() && r.times.back() == 2, "RC endpoint sample absent");
    auto column = std::find(r.analog_names.begin(), r.analog_names.end(), "VC");
    check(column != r.analog_names.end(), "RC VC output absent");
    size_t index = size_t(column - r.analog_names.begin());
    check(r.analog.size() == r.times.size() * r.analog_names.size(), "analog shape");
    for (size_t row = 0; row < r.times.size(); ++row)
        near(r.analog.at(row * r.analog_names.size() + index),
             3 * (1 - std::exp(-r.times[row] / 2)), 4e-7, "RC float32 waveform");
    check(r.events.empty(), "RC generated spurious events");
}
void rlc_multiple_roots() {
    // Parallel RLC: V''+.2 V'+V=0, V(0)=1,V'(0)=-.2.
    // V=e^(-.1t)*(cos(wt)-.1/w*sin(wt)), w=sqrt(.99).
    auto r = run("C1 N 0 C=1 IC_V=1\nL1 N 0 L=1 IC_I=0\nR1 N 0 R=5\n"
                 "SENSOR_V VC V N 0\nCMP_ZERO POS VC OP=GE THRESHOLD=0\n"
                 "EVENT_ZERO Z MODE=EDGE SOURCE=POS EDGE=BOTH", "15", ".125");
    complete(r);
    const double w = std::sqrt(.99), first = std::atan(w / .1) / w;
    auto zero = triggers(r, "Z");
    check(zero.size() == 5, "RLC must retain all five crossings, including the earliest");
    for (size_t i = 0; i < zero.size(); ++i)
        near(at(zero[i]).seconds(), first + double(i) * std::numbers::pi / w,
             std::max(2e-9, 2 * r.t_atom), "RLC crossing order");
    near(value(r, "VC"), std::exp(-1.5) *
         (std::cos(15 * w) - .1 / w * std::sin(15 * w)), 2e-9, "RLC endpoint");
    history(r);
}
void buck_capacitor_commutation() {
    // Deliberately non-stiff educational Buck. Storage charge and flux cannot jump.
    const std::string network =
        ".SUBCKT DIODE A K\nSENSOR_V VD V A K\nCMP_ON ON VD OP=GE THRESHOLD=.5\n"
        "SW_PATH A K ON RON=.1 ROFF=1Meg\nMATH_ZERO ZERO = 0\nMATH_BIAS BIAS = -5\n"
        "SEL_OFFSET OFFSET ON ZERO BIAS\nI_OFFSET A K OFFSET\n.ENDS DIODE\n"
        "VDC VIN 0 DC=10\nSW_MAIN VIN SW G RON=.01 ROFF=1Meg\n"
        "C_COMM SW 0 C=.001 IC_V=10\nL1 SW OUT L=1 IC_I=1\n"
        "C_OUT OUT 0 C=.1 IC_V=1\nR_LOAD OUT 0 R=1\nX_D 0 SW DIODE\n"
        "EVENT_OFF OFF MODE=AT AT=.01\nEVENT_ON ON MODE=AT AT=.1\n"
        "REG_GATE G MODE=SR SET=ON RESET=OFF PRIORITY=RESET IC=1\n"
        "EVENT_DIODE D_ON MODE=EDGE SOURCE=X_D/ON EDGE=RISE";
    auto model = compile(parse_markdown(document(network, ".03", ".001")));
    auto r = simulate(model);
    complete(r);
    auto off = triggers(r, "OFF"), diode = triggers(r, "D_ON");
    check(off.size() == 1 && diode.size() == 1, "Buck must have exactly one OFF and one diode ON");
    check(at(diode[0]) > at(off[0]), "diode must follow a nonzero capacitor commutation interval");
    check((at(diode[0]) - at(off[0])).seconds() > 1e-4, "Buck commutation collapsed into switch OFF");
    const RunState *off_state = nullptr, *diode_state = nullptr;
    for (const auto &segment : r.segments) {
        if (segment.state.at == at(off[0])) off_state = &segment.state;
        if (segment.state.at == at(diode[0])) diode_state = &segment.state;
    }
    check(off_state && diode_state, "event states absent from segments");
    near(off_state->mode.binding.read().maps.at("V(SW)").dot(off_state->physical), 10, .05,
         "switch OFF retains charged commutation capacitor");
    near(diode_state->mode.binding.read().maps.at("V(SW)").dot(diode_state->physical), -.5,
         2e-5, "diode ON voltage threshold");
    check(diode_state->mode.binding.read().maps.at("I(L1)").dot(diode_state->physical) > .9,
          "commutation lost positive inductor current");
    // Independent preservation check at the scheduled switch instant.
    // Uses the old mode solely to locate its left limit, not as a root oracle.
    auto previous = std::find_if(r.segments.begin(), r.segments.end(), [&](const Segment &s) {
        return s.state.at == at(off[0]);
    });
    check(previous != r.segments.begin() && previous != r.segments.end(), "OFF has no left segment");
    const auto &left = (previous - 1)->state;
    Stats scratch;
    auto expected = propagate(left.mode, left.physical, (at(off[0]) - left.at).seconds(), scratch);
    check(expected.size() == off_state->physical.size(), "storage coordinate dimension changed");
    for (int i = 0; i < model.ns; ++i)
        near(off_state->physical[i], expected[i], 2e-9, "OFF storage continuity");
    history(r);
}
void near_candidate_reversed() {
    // Old-mode extrapolation predicts Y's root 1ns after X's root.
    // Switching G1 reverses Y', so that root does not exist in the actual trajectory.
    Options o; atomic_window(o, 2e-8);
    auto r = run("MATH_ONE ONE = 1\nINT_X X ONE\nCMP_X G1 X OP=GE THRESHOLD=.5\n"
                 "SEL_DY DY G1 1 -1\nINT_Y Y DY\nCMP_Y G2 Y OP=GE THRESHOLD=.500000001\n"
                 "EVENT_EX EX MODE=EDGE SOURCE=G1 EDGE=RISE\n"
                 "EVENT_EY EY MODE=EDGE SOURCE=G2 EDGE=RISE", "1", ".1", o);
    complete(r);
    check(triggers(r, "EX").size() == 1, "anchor crossing missing");
    check(triggers(r, "EY").empty(), "stale old-mode candidate wrongly triggered after derivative reversal");
    near(value(r, "Y"), 0, 4 * r.t_atom + 1e-10, "piecewise Y endpoint");
    history(r);
}
void new_mode_candidate_added() {
    // Old Y'=0 gives no predicted root. After X switches, Y'=1 gives a real new event.
    Options o; atomic_window(o, 2e-8);
    auto r = run("MATH_ONE ONE = 1\nINT_X X ONE\nCMP_X G1 X OP=GE THRESHOLD=.5\n"
                 "SEL_DY DY G1 0 1\nINT_Y Y DY\nCMP_Y G2 Y OP=GE THRESHOLD=.00000001\n"
                 "EVENT_EX EX MODE=EDGE SOURCE=G1 EDGE=RISE\n"
                 "EVENT_EY EY MODE=EDGE SOURCE=G2 EDGE=RISE", "1", ".1", o);
    complete(r);
    auto ex = triggers(r, "EX"), ey = triggers(r, "EY");
    check(ex.size() == 1 && ey.size() == 1, "new-mode crossing was lost or duplicated");
    check(at(ey[0]) >= at(ex[0]), "new-mode event preceded its cause");
    near(at(ey[0]).seconds(), .50000001, 4 * r.t_atom + 1e-10, "new derivative candidate timing");
    near(value(r, "Y"), .5, 4 * r.t_atom + 1e-10, "new-mode integrated duration");
    history(r);
}
void stationary_zero_derivative_allowed() {
    auto r = run("MATH_ZERO ZERO = 0\nINT_X X ZERO IC=-1\n"
                 "CMP_ZERO G X OP=GE THRESHOLD=0\n"
                 "EVENT_ZERO Z MODE=EDGE SOURCE=G EDGE=RISE");
    complete(r);
    check(triggers(r, "Z").empty(), "stationary inactive guard generated an event");
    near(value(r, "X"), -1, 0, "stationary state");
}
void zero_derivative_rejected() {
    // A genuine crossing with vanishing derivative: X=(t-.5)^3.
    auto r = run("MATH_SIX SIX = 6\nINT_A A SIX IC=-3\nINT_B B A IC=.75\n"
                 "INT_X X B IC=-.125\nCMP_ZERO G X OP=GE THRESHOLD=0\n"
                 "EVENT_ZERO Z MODE=EDGE SOURCE=G EDGE=RISE");
    check(r.status == "STOPPED_UNRESOLVED", "zero-derivative crossing must safely reject");
    check(r.committed.at <= Time::from(.5), "committed through an unresolved crossing");
    check(triggers(r, "Z").empty(), "unresolved trigger escaped transaction");
    check(!r.diagnostic.value("subcode", "").empty(), "unresolved stop has no reason");
}
const std::string transaction_network =
    "MATH_ONE ONE = 1\nINT_X X ONE\nEVENT_C CLK MODE=AT AT=.5\n"
    "REG_Q Q X CLK IC=0\nEVENT_D LATE MODE=DELAY SOURCE=CLK DELAY=.125 POLICY=TRANSPORT";
void rollback_all_boundaries() {
    for (const auto *fault : {"after_propagation", "after_reg", "after_queue", "after_mode", "before_output"}) {
        Options o; o.fault = fault;
        auto r = run(transaction_network, "1", ".1", o);
        check(r.status == "STOPPED_ERROR" && r.diagnostic.value("subcode", "") == "INJECTED_FAULT",
              std::string("fault not reached: ") + fault);
        check(r.committed.at == Time{}, "fault leaked candidate time");
        near(value(r, "X"), 0, 0, "fault leaked integrated state");
        near(value(r, "Q"), 0, 0, "fault leaked sampled register");
        check(r.events.empty(), "fault leaked event log");
        check(r.committed.agenda.read().size() == 1 && r.committed.agenda.read()[0].at == Time::from(.5) &&
              r.committed.agenda.read()[0].trigger == "CLK", "fault leaked or removed queued deadline");
        check(r.stats.rollbacks == 1, "rollback accounting missing");
    }
}
void transport_delay() {
    auto r = run(transaction_network);
    complete(r);
    auto clk = triggers(r, "CLK"), late = triggers(r, "LATE");
    check(clk.size() == 1 && late.size() == 1, "transport trigger count");
    check(at(clk[0]) == Time::from(.5) && at(late[0]) == Time::from(.625), "exact delayed deadline");
    near(value(r, "Q"), .5, 1e-12, "REG samples at source, not delayed endpoint");
    check(r.committed.agenda.read().empty(), "consumed delay remained pending");
    history(r);
}
}
int main(int argc, char **argv) {
    std::cout << std::unitbuf;
    const std::vector<std::pair<std::string, std::function<void()>>> tests = {
        {"rc_analytic", rc_analytic}, {"rlc_multiple_roots", rlc_multiple_roots},
        {"buck_capacitor_commutation", buck_capacitor_commutation},
        {"near_candidate_reversed", near_candidate_reversed},
        {"new_mode_candidate_added", new_mode_candidate_added},
        {"stationary_zero_derivative_allowed", stationary_zero_derivative_allowed},
        {"zero_derivative_rejected", zero_derivative_rejected},
        {"rollback_all_boundaries", rollback_all_boundaries}, {"transport_delay", transport_delay}};
    for (const auto &[name, body] : tests) {
        if (argc > 1 && name != argv[1]) continue;
        std::cout << "RUN " << name << '\n';
        try { body(); ++passes; std::cout << "PASS " << name << '\n'; }
        catch (const std::exception &e) { ++failures; std::cout << "FAIL " << name << ": " << e.what() << '\n'; }
    }
    if (passes + failures == 0) { std::cerr << "No matching case\n"; return 2; }
    std::cout << passes << " PASS / " << failures << " FAIL / " << assertions << " assertions\n";
    return failures ? 1 : 0;
}
