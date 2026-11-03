#include "pulse/core.hpp"
#include <algorithm>
#include <chrono>
#include <fstream>
#include <functional>
#include <iostream>
#include <numeric>
#include <sstream>
#include <tuple>

namespace {
using namespace pulse;
using Batches = std::map<std::pair<Time, uint64_t>, std::set<std::string>>;
uint64_t checks = 0;
void check(bool condition, const std::string &message) {
    ++checks;
    if (!condition)
        throw std::runtime_error(message);
}
std::string document(const std::string &network, const std::string &end = ".5",
                     const std::string &save = ".125") {
    return "# PULSE Netlist v1.1\n## Parameters\n```pulse\n```\n## Network\n```pulse\n" + network +
           "\n```\n## Simulation\n```pulse\n.TRAN T_END=" + end + " SAVE_DT=" + save +
           "\n```\n## Layout\n```json\n{}\n```\n";
}
std::string join(const std::vector<std::string> &rows, const std::vector<int> &order) {
    std::string text;
    for (int index : order)
        text += rows.at(size_t(index)) + "\n";
    return text;
}
void completed(const Result &result) {
    check(result.status == "COMPLETED", result.status + ": " + result.diagnostic.dump());
}
double observation(const RunState &state, const std::string &name) {
    return state.mode.binding.read().maps.at(name).dot(state.physical);
}
std::string logical_name(const std::string &name, const std::map<std::string, std::string> &inverse) {
    auto found = inverse.find(name);
    return found == inverse.end() ? name : found->second;
}
Batches batches(const Result &result, const std::map<std::string, std::string> &inverse = {}) {
    Batches out;
    for (const auto &event : result.events) {
        check(event.at("kind") == "TRIG", "these models have no continuous ROOT events");
        auto time = Time::decode(event.at("time_canonical").get<std::string>());
        auto delta = event.at("delta").get<uint64_t>();
        const auto source = logical_name(event.at("source").get<std::string>(), inverse);
        check(out[{time, delta}].insert(source).second, "duplicate same-port pulse within a batch");
    }
    return out;
}
std::map<std::string, double> state_values(const Model &model, const RunState &state,
                                           const std::map<std::string, std::string> &inverse = {}) {
    std::map<std::string, double> out;
    for (const auto &[name, signal] : model.signals)
        if (signal.type != Signal::TRIG)
            out.emplace(logical_name(name, inverse), observation(state, name));
    return out;
}
std::string replace_identifiers(const std::string &input, const std::map<std::string, std::string> &rename) {
    std::string out;
    for (size_t i = 0; i < input.size();) {
        if (std::isalpha(static_cast<unsigned char>(input[i])) || input[i] == '_') {
            size_t start = i++;
            while (i < input.size() &&
                   (std::isalnum(static_cast<unsigned char>(input[i])) || input[i] == '_'))
                ++i;
            auto identifier = input.substr(start, i - start);
            auto found = rename.find(identifier);
            out += found == rename.end() ? identifier : found->second;
        } else
            out += input[i++];
    }
    return out;
}
void same_segments(const Model &reference_model, const Result &reference, const Model &model,
                   const Result &result, const std::map<std::string, std::string> &inverse) {
    check(reference.segments.size() == result.segments.size(), "committed segment count changed");
    for (size_t i = 0; i < reference.segments.size(); ++i) {
        const auto &a = reference.segments[i].state;
        const auto &b = result.segments[i].state;
        check(a.at == b.at, "authoritative committed physical time changed");
        check(state_values(reference_model, a) == state_values(model, b, inverse),
              "committed observations changed after mapping names back");
        check(a.physical.size() == b.physical.size() && (a.physical.array() == b.physical.array()).all(),
              "committed physical state changed");
    }
}
Json serialize_batches(const Batches &input) {
    Json out = Json::array();
    for (const auto &[key, sources] : input)
        out.push_back(
            {{"time_canonical", key.first.canonical()}, {"delta", key.second}, {"triggers", sources}});
    return out;
}
} // namespace

int main(int argc, char **argv) {
    using namespace pulse;
    const auto root = argc > 1 ? std::filesystem::path(argv[1]) : std::filesystem::current_path();
    Json ledger = {{"schema", "pulse-event-invariance-1.1"},
                   {"cases", Json::array()},
                   {"comparison", "exact authoritative Time/delta with each trigger batch treated as a set; "
                                  "exact dyadic state/sample oracles"}};
    size_t failures = 0;
    auto scenario = [&](const std::string &id, const std::function<void(Json &)> &body) {
        Json entry = {{"id", id}, {"status", "FAIL"}, {"execution", "EXECUTED"}};
        const auto start = std::chrono::steady_clock::now();
        try {
            body(entry);
            entry["status"] = "PASS";
        } catch (const std::exception &error) {
            entry["failure"] = error.what();
            ++failures;
        }
        entry["wall_seconds"] =
            std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
        std::cout << entry["status"].get<std::string>() << ' ' << id;
        if (entry.contains("failure"))
            std::cout << ' ' << entry["failure"].get<std::string>();
        std::cout << '\n';
        ledger["cases"].push_back(std::move(entry));
    };

    scenario("N06_all_six_declaration_permutations", [&](Json &entry) {
        const std::vector<std::string> rows = {"MATH_ONE ONE = 1",           "MATH_NEXT NEXT = A+ONE",
                                               "EVENT_C CLK MODE=AT AT=.25", "REG_A A NEXT CLK IC=0",
                                               "REG_B B A CLK IC=7",         "REG_C C B CLK IC=9"};
        std::vector<int> order(rows.size());
        std::iota(order.begin(), order.end(), 0);
        auto baseline_model = compile(parse_markdown(document(join(rows, order)), "N06_permutation.md"));
        auto baseline = simulate(baseline_model);
        completed(baseline);
        const Batches expected = {{{Time::from(.25), 0}, {"CLK"}}};
        check(batches(baseline) == expected, "baseline trigger time/delta is not the oracle");
        entry["expected_permutation_count"] = 720;
        entry["declaration_count"] = 6;
        entry["permutations_attempted"] = 0;
        entry["permutations_verified"] = 0;
        entry["oracle"] = "At .25 all REG read A=0,B=7: A=1,B=0,C=7. NEXT becomes 2 only after atomic "
                          "commit. Before .25 A=0,B=7,C=9.";
        do {
            entry["permutations_attempted"] = entry["permutations_attempted"].get<size_t>() + 1;
            auto model = compile(parse_markdown(document(join(rows, order)), "N06_permutation.md"));
            auto result = simulate(model);
            completed(result);
            check(observation(result.committed, "A") == 1, "REG A did not read old A");
            check(observation(result.committed, "B") == 0, "REG B read new A");
            check(observation(result.committed, "C") == 7, "REG C read new B");
            check(observation(result.committed, "NEXT") == 2, "post-commit MATH did not recompute");
            check(batches(result) == expected, "permutation changed authoritative trigger sequence");
            same_segments(baseline_model, baseline, model, result, {});
            check(result.times == std::vector<double>({0, .125, .25, .375, .5}), "sample grid changed");
            for (size_t sample = 0; sample < result.times.size(); ++sample) {
                for (const auto &[channel, before, after] :
                     std::vector<std::tuple<std::string, float, float>>{
                         {"A", 0, 1}, {"B", 7, 0}, {"C", 9, 7}}) {
                    auto column = std::find(result.analog_names.begin(), result.analog_names.end(), channel);
                    check(column != result.analog_names.end(), "missing REG observation");
                    const auto index = size_t(column - result.analog_names.begin());
                    const float expected_value = result.times[sample] < .25 ? before : after;
                    check(result.analog.at(sample * result.analog_names.size() + index) == expected_value,
                          "permutation changed sampled old/atomic-held value");
                }
            }
            entry["permutations_verified"] = entry["permutations_verified"].get<size_t>() + 1;
        } while (std::next_permutation(order.begin(), order.end()));
        check(entry["permutations_verified"] == 720, "did not execute every 6! permutation");
        entry["trigger_oracle"] = serialize_batches(expected);
    });

    scenario("agenda_order_and_irrelevant_renaming", [&](Json &entry) {
        const std::vector<std::string> rows = {"MATH_ONE ONE = 1",
                                               "EVENT_A A MODE=AT AT=.25",
                                               "EVENT_Z Z MODE=AT AT=.25",
                                               "EVENT_D D MODE=DELAY SOURCE=A DELAY=0",
                                               "EVENT_E E MODE=DELAY SOURCE=Z DELAY=.125",
                                               "REG_X X ONE A IC=0",
                                               "REG_Y Y X D IC=0",
                                               "REG_Q Q Y E IC=0",
                                               "REG_R R X Z IC=0"};
        std::vector<int> text_order(rows.size());
        std::iota(text_order.begin(), text_order.end(), 0);
        const auto base_text = join(rows, text_order);
        auto baseline_model = compile(parse_markdown(document(base_text), "agenda_baseline.md"));
        auto baseline = simulate(baseline_model);
        completed(baseline);
        const Batches expected = {{{Time::from(.25), 0}, {"A", "Z"}},
                                  {{Time::from(.25), 1}, {"D"}},
                                  {{Time::from(.375), 0}, {"E"}}};
        check(batches(baseline) == expected, "baseline agenda causal sequence violates oracle");
        const std::vector<std::map<std::string, std::string>> plans = {{},
                                                                       {{"EVENT_A", "EVENT_zz"},
                                                                        {"EVENT_Z", "EVENT_aa"},
                                                                        {"EVENT_D", "EVENT_mm"},
                                                                        {"EVENT_E", "EVENT_bb"},
                                                                        {"REG_X", "REG_zz"},
                                                                        {"REG_Y", "REG_aa"},
                                                                        {"REG_Q", "REG_mm"},
                                                                        {"REG_R", "REG_bb"},
                                                                        {"MATH_ONE", "MATH_renamed"},
                                                                        {"A", "zPulse"},
                                                                        {"Z", "aPulse"},
                                                                        {"D", "mPulse"},
                                                                        {"E", "bPulse"},
                                                                        {"X", "stateZ"},
                                                                        {"Y", "stateA"},
                                                                        {"Q", "stateM"},
                                                                        {"R", "stateB"},
                                                                        {"ONE", "unitValue"}}};
        entry["renaming_plan_count"] = plans.size();
        entry["agenda_permutations_per_plan"] = 24;
        entry["text_orders_per_plan"] = 2;
        entry["expected_run_count"] = 96;
        entry["runs_attempted"] = 0;
        entry["runs_verified"] = 0;
        entry["oracle"] = "At .25 delta0 A/Z sample old X=0; X=1,R=0. D at delta1 sees X=1, Y=1. E at .375 "
                          "samples Y=1 into Q.";
        for (const auto &rename : plans) {
            std::map<std::string, std::string> inverse;
            for (const auto &[original, replacement] : rename)
                inverse.emplace(replacement, original);
            for (bool reverse_text : {false, true}) {
                auto order = text_order;
                if (reverse_text)
                    std::reverse(order.begin(), order.end());
                auto text = replace_identifiers(join(rows, order), rename);
                auto model = compile(parse_markdown(document(text), "agenda_renamed.md"));
                const auto original_events = model.events;
                check(original_events.size() == 4, "test must permute all four EVENT entries");
                std::vector<int> event_order(4);
                std::iota(event_order.begin(), event_order.end(), 0);
                do {
                    entry["runs_attempted"] = entry["runs_attempted"].get<size_t>() + 1;
                    // This deliberately changes actual EVENT enumeration order,
                    // hence initial agenda insertion and per-delta scheduling order.
                    for (size_t i = 0; i < event_order.size(); ++i)
                        model.events[i] = original_events.at(size_t(event_order[i]));
                    auto result = simulate(model);
                    completed(result);
                    check(batches(result, inverse) == expected,
                          "agenda order/renaming changed trigger batches");
                    same_segments(baseline_model, baseline, model, result, inverse);
                    const std::map<std::string, double> final = {
                        {"ONE", 1}, {"X", 1}, {"Y", 1}, {"Q", 1}, {"R", 0}};
                    check(state_values(model, result.committed, inverse) == final,
                          "agenda order/renaming changed atomic chain final state");
                    check(result.times == baseline.times, "agenda order/renaming changed sample instants");
                    entry["runs_verified"] = entry["runs_verified"].get<size_t>() + 1;
                } while (std::next_permutation(event_order.begin(), event_order.end()));
            }
        }
        check(entry["runs_verified"] == 96, "incomplete agenda/rename permutations");
        entry["trigger_oracle"] = serialize_batches(expected);
    });

    scenario("N05_periodic_full_sample_and_hold_oracle", [&](Json &entry) {
        const auto text = document("MATH_D DX = 2\nINT_X X DX IC=3\n"
                                   "EVENT_C CLK MODE=PERIODIC START=.125 PERIOD=.25\nREG_Q Q X CLK IC=7",
                                   "1", ".0625");
        auto model = compile(parse_markdown(text, "N05_full_hold.md"));
        auto result = simulate(model);
        completed(result);
        Batches expected;
        Json sampled = Json::array();
        for (int k = 0; k < 4; ++k) {
            const double time = .125 + .25 * k;
            expected[{Time::from(time), 0}] = {"CLK"};
            sampled.push_back(
                {{"time_canonical", Time::from(time).canonical()}, {"sample_value", 3 + 2 * time}});
            const auto segment = std::find_if(result.segments.begin(), result.segments.end(),
                                              [&](const auto &s) { return s.state.at == Time::from(time); });
            check(segment != result.segments.end(), "missing committed clock segment");
            check(observation(segment->state, "Q") == 3 + 2 * time,
                  "sampled Q differs from analytic X(t_clk)");
        }
        check(batches(result) == expected, "periodic clock sequence/delta differs from exact schedule");
        check(result.times.size() == 17, "expected all 17 dyadic output samples including endpoints");
        const auto xcol = std::find(result.analog_names.begin(), result.analog_names.end(), "X");
        const auto qcol = std::find(result.analog_names.begin(), result.analog_names.end(), "Q");
        check(xcol != result.analog_names.end() && qcol != result.analog_names.end(),
              "missing X or Q waveform");
        for (size_t i = 0; i < result.times.size(); ++i) {
            const double t = double(i) / 16;
            check(result.times[i] == t, "non-oracle output sample time");
            double q = 7;
            for (int k = 0; k < 4; ++k) {
                const double clock = .125 + .25 * k;
                if (clock <= t)
                    q = 3 + 2 * clock;
            }
            const auto width = result.analog_names.size();
            check(result.analog.at(i * width + size_t(xcol - result.analog_names.begin())) ==
                      float(3 + 2 * t),
                  "continuous X waveform differs from 3+2t");
            check(result.analog.at(i * width + size_t(qcol - result.analog_names.begin())) == float(q),
                  "held Q waveform differs from last clock sample / IC=7");
        }
        check(observation(result.committed, "Q") == 4.75, "last sample must remain held through T_END=1");
        entry["waveform_sample_count"] = result.times.size();
        entry["periodic_sample_count"] = 4;
        entry["register_initial_value"] = 7;
        entry["sample_sequence_oracle"] = std::move(sampled);
        entry["trigger_oracle"] = serialize_batches(expected);
        entry["oracle"] = "X(t)=3+2t; clocks=.125+.25*k, k=0..3; Q=7 before first clock, then Q=X(last "
                          "clock) including right-sided clock samples.";
        entry["tolerance"] =
            "exact: all times, oracle values and float32 samples are dyadic and exactly representable";
    });

    ledger["checks"] = checks;
    ledger["failures"] = failures;
    ledger["reproduce"] = "build/event_invariance_tests <project-root>";
    try {
        std::filesystem::create_directories(root / "reports");
        std::ofstream output(root / "reports/event_invariance_ledger.json");
        output.exceptions(std::ios::failbit | std::ios::badbit);
        output << ledger.dump(2) << '\n';
        output.close();
    } catch (const std::exception &error) {
        std::cerr << "ledger write failed: " << error.what() << '\n';
        return 1;
    }
    std::cout << "TOTAL checks=" << checks << " failures=" << failures << '\n';
    return failures ? 1 : 0;
}
