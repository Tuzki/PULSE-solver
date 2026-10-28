#include "pulse/netlist.hpp"
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace pulse;
namespace {
int checks = 0;
void check(bool x, const std::string &msg) {
    ++checks;
    if (!x)
        throw std::runtime_error(msg);
}
std::string doc(std::string network, std::string params = "", std::string sim = ".TRAN T_END=1m SAVE_DT=1u",
                std::string layout = "{}") {
    return "# PULSE Netlist v1.1\n## Parameters\n```pulse\n" + params + "\n```\n## Network\n```pulse\n" +
           network + "\n```\n## Simulation\n```pulse\n" + sim + "\n```\n## Layout\n```json\n" + layout +
           "\n```\n";
}
void rejects(const std::string &s, const std::string &code) {
    try {
        parse_markdown(s, "bad.md");
        throw std::runtime_error("unexpected accept: " + code);
    } catch (const std::exception &e) {
        check(std::string(e.what()).find(code + ": bad.md:") != std::string::npos, e.what());
    }
}
const Primitive &byid(const Netlist &n, const std::string &id) {
    auto it =
        std::find_if(n.primitives.begin(), n.primitives.end(), [&](const auto &p) { return p.id == id; });
    if (it == n.primitives.end())
        throw std::runtime_error("missing " + id);
    return *it;
}
} // namespace
int main() {
    try {
        check(std::abs(fixed_value("{-(1k+2k)/3}") + 1000) < 1e-12, "four operations");
        check(fixed_value("1Meg") == 1e6, "Meg");
        check(fixed_value("1m") == .001, "milli");
        for (auto s : {"1M", "0x1p2", "sin(1)", "1/0", "1e999", "PI", "1+"}) {
            bool threw = false;
            try {
                fixed_value(s);
            } catch (...) {
                threw = true;
            }
            check(threw, std::string("bad fixed: ") + s);
        }
        auto n = parse_markdown(
            doc("R1 A 0 R={B}\nC1 A 0 C=1u\nMATH1 Y = {B}*A", ".PARAM A=2k\n.PARAM B={A/2}"), "ok.md");
        check(n.primitives.size() == 3, "three primitives");
        check(n.parameters.at("B") == 1000, "parameter order");
        check(byid(n, "R1").options.at("R") == "1000", "freeze");
        check(byid(n, "R1").source.line == 9, "source line");
        check(byid(n, "R1").source.block == "NETWORK", "source block");
        check(byid(n, "MATH1").expression == "1000*A", "MATH freeze");
        check(!n.channels, "omitted SAVE");
        check(byid(parse_markdown(doc("MATH1 Y={K}+1", ".PARAM K=2")), "MATH1").expression == "2+1",
              "compact assignment");
        auto empty = parse_markdown(doc("R1 A 0 R=1", "", ".SAVE"));
        check(empty.channels && empty.channels->empty(), "explicit empty SAVE");
        auto selected = parse_markdown(doc("R1 A 0 R=1", "", ".SAVE A R1 CLK"));
        check(selected.channels->size() == 3, "selected channels");
        check(parse_markdown(doc("C1 A 0 C=1u\nR1 A 0 R={B}\nMATH1 Y = {B}*A", ".PARAM A=2k\n.PARAM B={A/2}",
                                 ".TRAN T_END=1m SAVE_DT=1u", "{\"x\":42}"))
                      .canonical == n.canonical,
              "order/layout invariant");
        auto h = parse_markdown(
            doc(".SUBCKT LOW IN OUT\nR1 IN MID R=1\nC1 MID 0 C=1u\nMATH1 OUT = IN-MID\nSENSOR1 S I "
                "R1\nEVENT1 CLK MODE=DELAY SOURCE=TR DELAY_INPUT=OUT CANCEL=OFF\nREG1 Q MODE=SR SET=CLK "
                "RESET=OFF PRIORITY=RESET\n.ENDS LOW\n.SUBCKT HIGH A B\nXlow A B LOW\n.ENDS HIGH\nXone U V "
                "HIGH\nXtwo W Z HIGH"));
        check(byid(h, "Xone/Xlow/R1").args[0] == "U", "nested port mapping");
        check(byid(h, "Xone/Xlow/R1").args[1] == "Xone/Xlow/MID", "private net");
        check(byid(h, "Xtwo/Xlow/R1").args[0] == "W", "instance isolation");
        check(byid(h, "Xone/Xlow/SENSOR1").args[2] == "Xone/Xlow/R1", "branch mapping");
        check(byid(h, "Xone/Xlow/EVENT1").options.at("DELAY_INPUT") == "V", "option port map");
        check(byid(h, "Xone/Xlow/MATH1").expression == "U-Xone/Xlow/MID", "expression map");
        check(byid(h, "Xone/Xlow/C1").args[1] == "0", "global ground");
        auto all = parse_markdown(
            doc("R1 A 0 IV_TABLE=[(-1,-1m), (0,0), (1,1m)]\nC1 A 0 C=1u\nL1 (A 0) (B 0) L_MATRIX=[[1, 0], "
                "[0, 1]]\nV1 A 0 DC=1\nI1 A 0 CTRL\nSW1 A B ON RON=1 ROFF=1Meg\nSENSOR1 VS V A 0\nMATH1 Y = "
                "2*VS\nCMP1 G Y OP=GE THRESHOLD=1\nSEL1 Z G Y VS\nINT1 X Z IC=0\nREG1 Q X CLK\nEVENT1 CLK "
                "MODE=PERIODIC PERIOD=1m\n+ START=0"));
        check(all.primitives.size() == 13, "all kinds");
        check(byid(all, "L1").options.at("L_MATRIX") == "[[1, 0], [0, 1]]", "matrix grouping");
        check(byid(all, "EVENT1").options.at("START") == "0", "continuation");
        rejects(doc("R1 A 0 R=1", ".PARAM B={A}\n.PARAM A=1"), "INVALID_PARAMETER");
        rejects(doc("R1 A 0 R=1", ".PARAM A=1\n.PARAM A=2"), "INVALID_PARAMETER");
        rejects(doc("R1 A 0 R=1\nR1 B 0 R=1"), "DUPLICATE_INSTANCE");
        rejects(doc("D1 A 0 V=1"), "INVALID_PRIMITIVE");
        rejects(doc("R1 A R=1"), "INVALID_PORT_COUNT");
        rejects(doc("SENSOR1 X T A B"), "INVALID_PORT_COUNT");
        rejects(doc("R1 A 0 R=[1,2"), "INVALID_NETLIST");
        rejects(doc(".SUBCKT A P\nX1 P A\n.ENDS A\nX1 X A"), "RECURSIVE_SUBCKT");
        rejects(doc(".SUBCKT A P P\n.ENDS A"), "INVALID_SUBCKT");
        rejects(doc("X1 A MISSING"), "INVALID_SUBCKT");
        rejects(doc("R1 A 0 R=1", "", "", "{\"a\":}"), "INVALID_LAYOUT");
        rejects(doc("R1 A 0 R=1") + "## Network\n", "DUPLICATE_SECTION");
        rejects(doc("R1 A 0 R=1") + "## Other\n```pulse\nR2 A 0 R=2\n```\n", "INVALID_SECTION");
        rejects(doc(".SUBCKT A P\nX1 P A\n.ENDS A"), "RECURSIVE_SUBCKT");
        auto fixtures = std::filesystem::path(__FILE__).parent_path() / "fixtures" / "parser";
        for (const auto &entry : std::filesystem::directory_iterator(fixtures)) {
            std::ifstream f(entry.path());
            std::string contents((std::istreambuf_iterator<char>(f)), {});
            auto filename = entry.path().filename().string();
            bool expected_reject = filename.rfind("invalid_", 0) == 0;
            bool rejected = false;
            try {
                parse_markdown(contents, entry.path().string());
            } catch (...) {
                rejected = true;
            }
            check(rejected == expected_reject, "fixture " + filename);
        }
        std::cout << "PASS parser " << checks << " checks\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "FAIL " << e.what() << "\n";
        return 1;
    }
}
