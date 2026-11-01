#include "pulse/core.hpp"
#include <chrono>
#include <fstream>
#include <iostream>
#include <limits>
#include <sstream>
int main(int argc, char **argv) {
  try {
    pulse::Options options;options.retain_history=false;
    std::string input, dest = "out";
    bool ir = false, atomic_override = false;
    for (int i = 1; i < argc; ++i) {
      std::string a = argv[i];
      auto value = [&]() {
        pulse::require(i + 1 < argc, 1, "CLI_USAGE", "missing value for " + a);
        return std::string(argv[++i]);
      };
      if (a == "--help") {
        std::cout << "pulse-solver MODEL.md [--out DIR] [--t-end N] [--save-dt "
                     "N] [--channels LIST] [--output-format waveform|trajectory] "
                     "[--atomic-time N] [--atom-exponent N] [--max-transactions N(0=unlimited)] [--no-mode-cache] [--ir]\n";
        return 0;
      } else if (a == "--version") {
        std::cout << "PULSE Solver 1.2.0-pre\n";
        return 0;
      } else if (a == "--out")
        dest = value();
      else if (a == "--output-format") {
        auto format=value();
        pulse::require(format=="waveform"||format=="trajectory",1,"CLI_USAGE","output format must be waveform or trajectory");
        options.trajectory_output=format=="trajectory";
      }
      else if (a == "--t-end")
        options.t_end = pulse::number(value());
      else if (a == "--save-dt")
        options.save_dt = pulse::number(value());
      else if (a == "--atomic-time") {
        options.atomic_time = pulse::number(value());
        atomic_override = true;
        options.atom_exponent = -1;
      } else if (a == "--atom-exponent")
        options.atom_exponent = std::stoi(value());
      else if (a == "--max-transactions") {
        const auto text = value();
        size_t consumed = 0;
        const auto budget = std::stoull(text, &consumed);
        pulse::require(!text.empty() && text.front() != '-' &&
                           consumed == text.size() &&
                           budget <= std::numeric_limits<size_t>::max(),
                       1, "CLI_USAGE", "max-transactions must be a nonnegative integer; 0 means unlimited");
        options.max_transactions = size_t(budget);
      } else if (a == "--no-mode-cache")
        options.mode_cache_capacity = 0;
      else if (a == "--fault")
        options.fault = value();
      else if (a == "--channels") {
        auto v = value();
        {
          options.channels = std::vector<std::string>{};
          std::stringstream ss(v);
          std::string n;
          while (std::getline(ss, n, ','))
            if (!n.empty())
              options.channels->push_back(n);
        }
      } else if (a == "--ir")
        ir = true;
      else if (a == "--netlist")
        input = value();
      else {
        pulse::require(input.empty() && !a.starts_with('-'), 1, "CLI_USAGE",
                       "unknown argument " + a);
        input = a;
      }
    }
    pulse::require(!input.empty() &&
                       std::filesystem::path(input).extension() == ".md",
                   1, "CLI_USAGE", "provide a Markdown .md netlist");
    std::ifstream f(input);
    pulse::require(bool(f), 1, "INPUT_IO", "cannot open " + input);
    std::string text((std::istreambuf_iterator<char>(f)), {});
    auto start = std::chrono::steady_clock::now();
    auto model = pulse::compile(pulse::parse_markdown(text, input));
    if (atomic_override) model.netlist.atomic_time.reset();
    double compile_seconds =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - start)
            .count();
    if (ir) {
      std::cout << model.netlist.canonical << '\n';
      return 0;
    }
    auto result = pulse::simulate(model, options);
    result.report["parse_and_compile_seconds"] = compile_seconds;
    result.report["max_transactions"] = options.max_transactions;
    pulse::write_result(model, result, dest);
    std::cout << result.report.dump(2) << '\n';
    return result.status == "COMPLETED"            ? 0
           : result.status == "STOPPED_UNRESOLVED" ? 2
                                                   : 1;
  } catch (const std::exception &e) {
    std::cerr << pulse::diagnostic(e).dump(2) << '\n';
    return 1;
  }
}
