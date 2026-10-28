#include "pulse/core.hpp"
#include <algorithm>
#include <iostream>
#include <stdexcept>

namespace {
int checks = 0;
void check(bool value, const std::string &message) {
    ++checks;
    if (!value)
        throw std::runtime_error(message);
}
std::string document(const std::string &network) {
    return "# PULSE Netlist v1.1\n\n## Parameters\n```pulse\n```\n\n"
           "## Network\n```pulse\n" +
           network +
           "\n```\n\n## Simulation\n```pulse\n.TRAN T_END=1 SAVE_DT=.1\n```\n\n"
           "## Layout\n```json\n{}\n```\n";
}
void reject_at(const std::string &network, const std::string &id, const std::string &subcode, int code = 1) {
    auto net = pulse::parse_markdown(document(network), "compiler_source.md");
    auto primitive =
        std::find_if(net.primitives.begin(), net.primitives.end(), [&](const auto &p) { return p.id == id; });
    check(primitive != net.primitives.end(), "test's source primitive exists: " + id);
    const auto expected = primitive->source;
    check(expected.line > 0, "parser supplies a real SourceMap line");
    try {
        pulse::compile(std::move(net));
        throw std::runtime_error("expected compiler error " + subcode);
    } catch (const pulse::Error &error) {
        check(error.subcode == subcode, "subcode preserved: " + std::string(error.what()) +
                                            " got=" + error.subcode + " expected=" + subcode);
        check(error.code == code, "top-level code preserved");
        check(error.source.file == expected.file, "source filename");
        check(error.source.block == expected.block, "source Markdown block");
        check(error.source.line == expected.line, "source line got=" + std::to_string(error.source.line) +
                                                      " expected=" + std::to_string(expected.line) + " for " +
                                                      id);
        check(error.source.column == expected.column, "source column");
        check(error.source.path == expected.path, "hierarchical instance path");
        check(!error.unresolved, "static errors keep their original non-unresolved flag");
        auto json = pulse::diagnostic(error);
        check(json["source"]["line"] == expected.line, "public diagnostic retains location");
    }
}
} // namespace
int main() {
    try {
        reject_at("EVENT1 CLK MODE=AT AT=0\nREG1 Q CLK CLK", "REG1", "TYPE_CONFLICT");
        reject_at("EVENT1 CLK MODE=AT AT=0\nREG1 TRIG::Q 0 CLK", "REG1", "TYPE_CONFLICT");
        reject_at("INT1 X MISSING", "INT1", "UNDRIVEN_SIGNAL");
        reject_at("MATH1 X = 1\nMATH2 X = 2", "MATH2", "MULTIPLE_DRIVERS");
        reject_at("EVENT1 CLK MODE=AT AT=0\nREG1 Q Z CLK\nREG2 Z Q CLK", "REG1", "AMBIGUOUS_TYPE");
        // Generic masks only become contradictory during the later fixed-point
        // pass: Y is REAL, X is BOOL, and SEL1 supplied the equality edge.
        reject_at("MATH1 Y = 1\nEVENT1 CLK MODE=AT AT=0\n"
                  "REG1 X MODE=SR SET=CLK RESET=CLK PRIORITY=RESET\nSEL1 Y2 X Y X",
                  "SEL1", "TYPE_CONFLICT");
        reject_at("MATH0 X = 1\nMATH1 Y = X*X", "MATH1", "CONTINUOUS_NONAFFINE", 2);
        reject_at("MATH0 X = 1\nMATH1 Y = X^2", "MATH1", "EXPRESSION_SYNTAX");
        reject_at("L1 (A 0) (B 0) L_MATRIX=[[1,0],[0]]", "L1", "L_MATRIX_SHAPE");
        reject_at("L1 (A 0) (B 0) L_MATRIX=[[1,0],[0,1]] IC_I=[0]", "L1", "IC_SHAPE");
        reject_at("L1 A 0 L=1 IC_I=[[0]]", "L1", "ARRAY_SYNTAX");
        reject_at("C1 A 0 C=1 IC_V=0 IC_Q=1", "C1", "IC_CONFLICT");
        reject_at("C1 A 0 QV_TABLE=[(0,0),(1,1)] IC_Q=2", "C1", "PWA_OUT_OF_RANGE", 5);
        reject_at("R1 A 0 R=UNKNOWN", "R1", "INVALID_PARAMETER");
        reject_at("L1 (A 0) (B 0) L_MATRIX=[[1,UNKNOWN],[0,1]]", "L1", "INVALID_PARAMETER");
        reject_at("INT1 X 0 IC=UNKNOWN", "INT1", "INVALID_PARAMETER");
        reject_at("EVENT1 CLK MODE=AT AT=0\n"
                  "REG1 BOOL::Q 0 CLK IC=2",
                  "REG1", "BOOL_IC");
        reject_at(".SUBCKT BAD OUT\nINT1 OUT MISSING\n.ENDS BAD\nXone Y BAD", "Xone/INT1", "UNDRIVEN_SIGNAL");
        // Source selection must follow the actual use, not the last unrelated
        // primitive in canonical order or text order.
        reject_at("INT1 X MISSING\nR_LAST A 0 R=1", "INT1", "UNDRIVEN_SIGNAL");
        auto good = pulse::compile(pulse::parse_markdown(document("MATH0 X = 1\nINT1 Y X IC=0"), "good.md"));
        check(good.ns == 1 && good.signals.count("Y"), "valid compilation remains valid");
        std::cout << "PASS compiler diagnostics " << checks << " checks\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL compiler diagnostics " << error.what() << '\n';
        return 1;
    }
}
