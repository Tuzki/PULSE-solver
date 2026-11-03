#define main engineering_original_main
#include "engineering_events.cpp"
#undef main
#include <bit>
#include <cstring>

namespace {
template <class T> bool same_bytes(const T *a, const T *b, size_t count) {
    return count == 0 || std::memcmp(a, b, count * sizeof(T)) == 0;
}
void identical(const Result &a, const Result &b) {
    complete(a); complete(b);
    check(a.events == b.events, "cache changed authoritative event log");
    check(a.times.size() == b.times.size() &&
              same_bytes(a.times.data(), b.times.data(), a.times.size()), "cache changed time bits");
    check(a.analog_names == b.analog_names && a.digital_names == b.digital_names,
          "cache changed channel registry");
    check(a.analog.size() == b.analog.size() &&
              same_bytes(a.analog.data(), b.analog.data(), a.analog.size()), "cache changed analog bits");
    check(a.digital == b.digital, "cache changed digital values");
    check(a.segments.size() == b.segments.size(), "cache changed segment count");
    for (size_t i = 0; i < a.segments.size(); ++i) {
        const auto &x = a.segments[i].state, &y = b.segments[i].state;
        check(x.at == y.at && x.mode.id == y.mode.id, "cache changed segment time/mode");
        check(same_bytes(x.physical.data(), y.physical.data(), size_t(x.physical.size())),
              "cache changed physical state bits");
        check(x.mode.definition.read().M.rows() == y.mode.definition.read().M.rows() &&
                  same_bytes(x.mode.definition.read().M.data(), y.mode.definition.read().M.data(), size_t(x.mode.definition.read().M.size())),
              "cache changed matrix bits");
        check(std::bit_cast<uint64_t>(x.mode.residual) == std::bit_cast<uint64_t>(y.mode.residual),
              "cache did not recompute entry residual identically");
    }
}
const std::string cycling =
    "V1 IN 0 DC=1\nR1 IN OUT R=1\nC1 OUT 0 C=1 IC_V=0\n"
    "SW1 OUT 0 G RON=1 ROFF=10\n"
    "EVENT_ON ON MODE=PERIODIC PERIOD=.2 START=0\n"
    "EVENT_OFF OFF MODE=DELAY SOURCE=ON DELAY=.1 POLICY=TRANSPORT\n"
    "REG_G G MODE=SR SET=ON RESET=OFF PRIORITY=RESET IC=1";
void repeated_modes_exact() {
    auto model = compile(parse_markdown(document(cycling, "2", ".025"), "cache-cycling.md"));
    Options off; off.mode_cache_capacity = 0;
    auto a = simulate(model, off), b = simulate(model);
    identical(a, b);
    // Initialization uses strategy 2; transactions explicitly use strategy 0.
    // Their cache keys must remain distinct even for this unmixed RC chart:
    // one initial template plus the two repeated strategy-0 gate templates.
    check(b.stats.cache_hits > 10 && b.stats.modes == 3, "strategy-specific repeated modes not reused");
    check(b.stats.mode_cache_peak_entries == 3, "strategy-specific cache entry count");
}
void reg_values_are_in_key() {
    const std::string network =
        "MATH_ONE ONE = 1\nINT_X X ONE\nEVENT_C CLK MODE=PERIODIC PERIOD=.2 START=0\n"
        "REG_Q Q X CLK IC=0\nV1 N 0 Q\nR1 N 0 R=2";
    auto model = compile(parse_markdown(document(network), "cache-reg.md"));
    Options off; off.mode_cache_capacity = 0;
    auto a = simulate(model, off), b = simulate(model);
    identical(a, b);
    check(b.stats.mode_cache_peak_entries > 3, "changing REG values aliased");
    near(value(b, "V(N)"), b.committed.regs.read().at("Q"), 0, "REG-controlled voltage");
}
void pwa_segments_are_in_key() {
    auto model = compile(parse_markdown(document(
        "I1 0 N DC=1\nC1 N 0 QV_TABLE=[(0,0),(1,1),(2,3)] IC_Q=.5 RANGE=EXTEND"),
        "cache-pwa.md"));
    Stats stats; ScopedModeCache scope(model, 8);
    std::map<int,int> segment{{model.pwas.at(0), 0}};
    auto x = model.initial;
    auto first = compile_specified(model, x, {}, stats, {}, segment);
    segment.begin()->second = 1; x[model.parts[model.pwas.at(0)].state] = 2;
    auto second = compile_specified(model, x, {}, stats, {}, segment);
    segment.begin()->second = 0; x = model.initial;
    auto again = compile_specified(model, x, {}, stats, {}, segment);
    check(stats.modes == 2 && stats.cache_hits == 1, "PWA segment cache identity");
    near(first.binding.read().maps.at("V(N)").dot(x), .5, 0, "first PWA segment");
    auto y = x; y[model.parts[model.pwas.at(0)].state] = 2;
    near(second.binding.read().maps.at("V(N)").dot(y), 1.5, 0, "second PWA segment");
    check(same_bytes(first.definition.read().M.data(), again.definition.read().M.data(), size_t(first.definition.read().M.size())), "PWA reuse changed matrix");
}
void recheck_storage_constraints() {
    auto model = compile(parse_markdown(document(
        "V1 IN 0 DC=1\nL1 IN MID L=1 IC_I=0\nL2 MID 0 L=2 IC_I=0"),
        "cache-constraint.md"));
    Stats stats; ScopedModeCache scope(model, 8);
    auto first = compile_specified(model, model.initial, {}, stats, {}, {});
    check(first.definition.read().constraints.rows() > 0, "fixture has no physical constraint");
    auto bad = model.initial; bad[0] = 1;
    std::string cached_error, fresh_error;
    try { compile_specified(model, bad, {}, stats, {}, {}); }
    catch (const Error &e) { cached_error = std::to_string(e.code) + ":" + e.subcode; }
    {
        ScopedModeCache disabled(model, 0);
        try { compile_specified(model, bad, {}, stats, {}, {}); }
        catch (const Error &e) { fresh_error = std::to_string(e.code) + ":" + e.subcode; }
    }
    check(cached_error == "10:INCONSISTENT_MODE_TRANSITION" && cached_error == fresh_error,
          "cached template accepted inconsistent storage or changed diagnostic");
    compile_specified(model, model.initial, {}, stats, {}, {});
    check(stats.cache_hits == 1, "failed entry poisoned the template or nested scope");
}
void returned_modes_are_independent() {
    auto model = compile(parse_markdown(document("V1 N 0 DC=2\nR1 N 0 R=4"), "cache-copy.md"));
    Stats stats; ScopedModeCache scope(model, 8);
    auto a = compile_specified(model, model.initial, {}, stats, {}, {});
    a.binding.edit().maps.at("V(N)").setZero(); a.version = 99; a.definition.edit().M.setConstant(42);
    auto b = compile_specified(model, model.initial, {}, stats, {}, {});
    near(b.binding.read().maps.at("V(N)").dot(model.initial), 2, 0, "caller mutated cached observation");
    check(b.version != 99 && b.definition.read().M.maxCoeff() != 42, "caller mutated cached mode");
}
void model_and_run_isolation() {
    auto a = run("V1 N 0 DC=2\nR1 N 0 R=4"), b = run("V1 N 0 DC=6\nR1 N 0 R=2");
    complete(a);complete(b);
    near(value(a, "I(R1)"), .5, 0, "model A"); near(value(b, "I(R1)"), 3, 0, "model B");
    check(a.stats.cache_hits == 0 && b.stats.cache_hits == 0, "cache leaked across runs");
}
void bounded_eviction_exact() {
    auto model = compile(parse_markdown(document(cycling, "2", ".025"), "cache-eviction.md"));
    Options one; one.mode_cache_capacity = 1;
    Options off; off.mode_cache_capacity = 0;
    auto a=simulate(model, off), b=simulate(model, one);
    identical(a,b);
    check(b.stats.mode_cache_peak_entries == 1 && b.stats.mode_cache_evictions > 10,
          "bounded cache did not evict");
}
void exact_reg_bit_values() {
    auto model = compile(parse_markdown(document(
        "EVENT_E E MODE=AT AT=2\nREG_Q Q 0 E IC=0\nV1 N 0 Q\nR1 N 0 R=1"), "cache-reg-bits.md"));
    Stats stats; ScopedModeCache scope(model, 8);
    std::map<std::string,double> regs{{"Q",1}};
    auto a=compile_specified(model, model.initial, regs, stats, {}, {});
    regs["Q"]=std::nextafter(1.,2.);
    auto b=compile_specified(model, model.initial, regs, stats, {}, {});
    check(std::bit_cast<uint64_t>(a.binding.read().maps.at("V(N)").dot(model.initial)) !=
              std::bit_cast<uint64_t>(b.binding.read().maps.at("V(N)").dot(model.initial)),
          "adjacent binary64 REG values aliased");
    check(stats.modes == 2, "adjacent REG values reused incorrect template");
}
}
int main() {
    for (const auto &[name, body] : std::vector<std::pair<std::string,std::function<void()>>>{
             {"repeated_modes_exact", repeated_modes_exact}, {"reg_values_are_in_key", reg_values_are_in_key},
             {"pwa_segments_are_in_key", pwa_segments_are_in_key}, {"recheck_storage_constraints", recheck_storage_constraints},
             {"returned_modes_are_independent", returned_modes_are_independent}, {"model_and_run_isolation", model_and_run_isolation},
             {"bounded_eviction_exact", bounded_eviction_exact}, {"exact_reg_bit_values", exact_reg_bit_values}}) {
        try { body(); ++passes; std::cout << "PASS " << name << '\n'; }
        catch (const std::exception &e) { ++failures; std::cout << "FAIL " << name << ": " << e.what() << '\n'; }
    }
    std::cout << passes << " PASS / " << failures << " FAIL / " << assertions << " assertions\n";
    return failures ? 1 : 0;
}
