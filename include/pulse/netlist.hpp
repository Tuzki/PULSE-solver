#pragma once
#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>
namespace pulse {
struct Source {
    std::string file, block, path;
    int line = 0, column = 1;
};
struct ParseError : std::runtime_error {
    Source source;
    std::string subcode;
    ParseError(Source s, std::string c, std::string message)
        : std::runtime_error(c + ": " + s.file + ":" + std::to_string(s.line) + ": " + message),
          source(std::move(s)), subcode(std::move(c)) {}
};
struct Primitive {
    std::string kind, id;
    std::vector<std::string> args;
    std::map<std::string, std::string> options;
    std::string expression;
    Source source;
    std::map<std::string, std::string> option_text;
};
struct Netlist {
    struct Program {
        std::string name, binary;
        std::vector<std::string> sources;
        std::string inline_source;
        Source source;
    };
    struct Task {
        std::string name, mcu, program, entry, init, trigger, wake_trigger;
        std::vector<std::string> inputs, outputs;
        std::vector<double> initial_outputs, parameters;
        bool self_trigger = false;
        Source source;
    };
    std::vector<Primitive> primitives;
    std::map<std::string, double> parameters;
    std::map<std::string, std::string> parameter_text;
    std::optional<double> t_end, save_dt;
    std::optional<std::vector<std::string>> channels;
    std::string layout_json;
    std::string canonical;
    std::string filename, format = "1.1";
    std::optional<double> atomic_time;
    std::map<std::string, Program> programs;
    std::vector<Task> tasks;
    double parse_seconds = 0;
};
Netlist parse_markdown(const std::string &text, const std::string &filename = "<memory>");
Netlist parse_pre_markdown(const std::string &text, const std::string &filename);
double fixed_value(const std::string &, const std::map<std::string, double> &parameters = {});
} // namespace pulse
