#include "pulse/core.hpp"
#include <algorithm>
#include <cctype>
#include <chrono>
#include <functional>
#include <regex>
#include <sstream>
namespace pulse {
namespace {
struct Expression {
    std::string s;
    size_t p = 0;
    const std::set<std::string> *known = nullptr;
    void space() {
        while (p < s.size() && std::isspace(static_cast<unsigned char>(s[p])))
            ++p;
    }
    bool eat(char c) {
        space();
        if (p < s.size() && s[p] == c) {
            ++p;
            return true;
        }
        return false;
    }
    Affine add() {
        auto a = mul();
        for (;;) {
            if (eat('+')) {
                auto b = mul();
                a.bias += b.bias;
                for (auto &[n, v] : b.terms)
                    a.terms[n] += v;
            } else if (eat('-')) {
                auto b = mul();
                a.bias -= b.bias;
                for (auto &[n, v] : b.terms)
                    a.terms[n] -= v;
            } else
                break;
        }
        return a;
    }
    void simplify(Affine &a) {
        for (auto i = a.terms.begin(); i != a.terms.end();)
            if (i->second == 0)
                i = a.terms.erase(i);
            else
                ++i;
    }
    Affine mul() {
        auto a = atom();
        simplify(a);
        for (;;) {
            bool division = false;
            if (!eat('*')) {
                if (!eat('/'))
                    break;
                division = true;
            }
            auto b = atom();
            simplify(b);
            if (division) {
                require(b.terms.empty() && b.bias != 0, 2, "CONTINUOUS_NONAFFINE",
                        "division must have nonzero fixed denominator");
                b.bias = 1 / b.bias;
            }
            require(a.terms.empty() || b.terms.empty(), 2, "CONTINUOUS_NONAFFINE",
                    "continuous signal product is not affine");
            if (a.terms.empty()) {
                double c = a.bias;
                a = b;
                a.bias *= c;
                for (auto &[n, v] : a.terms)
                    v *= c;
            } else {
                a.bias *= b.bias;
                for (auto &[n, v] : a.terms)
                    v *= b.bias;
            }
            simplify(a);
        }
        return a;
    }
    Affine atom() {
        space();
        if (eat('+'))
            return atom();
        if (eat('-')) {
            auto a = atom();
            a.bias = -a.bias;
            for (auto &[n, v] : a.terms)
                v = -v;
            return a;
        }
        if (eat('(')) {
            auto a = add();
            require(eat(')'), 1, "EXPRESSION_SYNTAX", "missing closing parenthesis");
            return a;
        }
        space();
        size_t start = p;
        require(p < s.size(), 1, "EXPRESSION_SYNTAX", "missing operand");
        if (std::isdigit(static_cast<unsigned char>(s[p])) || s[p] == '.') {
            char *end = nullptr;
            std::strtod(s.c_str() + p, &end);
            p = size_t(end - s.c_str());
            while (p < s.size() && std::isalpha(static_cast<unsigned char>(s[p])))
                ++p;
            return {{}, number(s.substr(start, p - start))};
        }
        std::string match;
        size_t name_start = p;
        for (const std::string prefix : {"REAL::", "BOOL::", "TRIG::"})
            if (s.compare(p, prefix.size(), prefix) == 0)
                name_start = p + prefix.size();
        if (known)
            for (const auto &name : *known) {
                size_t end = name_start + name.size();
                if (s.compare(name_start, name.size(), name) == 0 &&
                    (end == s.size() ||
                     !(std::isalnum(static_cast<unsigned char>(s[end])) || s[end] == '_' || s[end] == ':')) &&
                    name.size() > match.size())
                    match = name;
            }
        if (!match.empty())
            p = name_start + match.size();
        else
            while (p < s.size() &&
                   (std::isalnum(static_cast<unsigned char>(s[p])) || s[p] == '_' || s[p] == ':'))
                ++p;
        require(p > start, 1, "EXPRESSION_SYNTAX", "invalid expression operand");
        return {{{s.substr(start, p - start), 1}}, 0};
    }
};
std::string trim_array(std::string s) {
    auto a = s.find_first_not_of(" \t\r\n"), b = s.find_last_not_of(" \t\r\n");
    return a == std::string::npos ? std::string{} : s.substr(a, b - a + 1);
}
std::vector<std::string> array_items(std::string s, char open = '[', char close = ']') {
    s = trim_array(s);
    require(s.size() >= 2 && s.front() == open && s.back() == close, 1, "ARRAY_SYNTAX",
            "expected a delimited array");
    s = s.substr(1, s.size() - 2);
    std::vector<std::string> v;
    int depth = 0;
    size_t start = 0;
    for (size_t i = 0; i <= s.size(); ++i) {
        char c = i < s.size() ? s[i] : ',';
        if (c == '[' || c == '(' || c == '{')
            ++depth;
        if (c == ']' || c == ')' || c == '}')
            --depth;
        require(depth >= 0, 1, "ARRAY_SYNTAX", "unbalanced array");
        if (c == ',' && depth == 0) {
            auto item = trim_array(s.substr(start, i - start));
            require(!item.empty(), 1, "ARRAY_SYNTAX", "empty array element");
            v.push_back(item);
            start = i + 1;
        }
    }
    require(depth == 0, 1, "ARRAY_SYNTAX", "unbalanced array");
    return v;
}
std::vector<double> array_values(const std::string &s) {
    std::vector<double> v;
    auto t = trim_array(s);
    if (!t.empty() && t.front() == '[') {
        for (auto &item : array_items(t)) {
            require(item.find('[') == std::string::npos && item.find('(') == std::string::npos, 1,
                    "ARRAY_SYNTAX", "IC requires a flat vector");
            v.push_back(number(item));
        }
    } else
        v.push_back(number(t));
    return v;
}
std::pair<std::string, std::string> port(std::string s) {
    for (char &c : s)
        if (c == '(' || c == ')' || c == ',')
            c = ' ';
    std::istringstream in(s);
    std::string a, b, c;
    in >> a >> b;
    require(!a.empty() && !b.empty() && !(in >> c), 1, "PORT_ARITY", "expected ordered two-node port");
    return {a, b};
}
std::string opt(const Primitive &p, const std::string &k, const std::string &d = "") {
    auto it = p.options.find(k);
    return it == p.options.end() ? d : it->second;
}
} // namespace
Affine affine(const std::string &s, const std::set<std::string> &known) {
    Expression e{s, 0, &known};
    auto a = e.add();
    e.space();
    require(e.p == s.size(), 1, "EXPRESSION_SYNTAX", "unexpected expression tail: " + s.substr(e.p));
    for (auto i = a.terms.begin(); i != a.terms.end();)
        if (i->second == 0)
            i = a.terms.erase(i);
        else
            ++i;
    require(std::isfinite(a.bias), 7, "NONFINITE", "nonfinite expression");
    for (auto &[n, v] : a.terms)
        require(std::isfinite(v), 7, "NONFINITE", "nonfinite affine coefficient");
    return a;
}
std::pair<double, double> Curve::segment(int i) const {
    double a = (y.at(i + 1) - y.at(i)) / (x.at(i + 1) - x.at(i));
    return {a, y.at(i) - a * x.at(i)};
}
int Curve::locate(double v, bool inverse) const {
    const auto &a = inverse ? y : x;
    require(extend || (v >= a.front() && v <= a.back()), 5, "PWA_OUT_OF_RANGE",
            "physical state outside PWA table");
    return std::clamp(int(std::upper_bound(a.begin(), a.end(), v) - a.begin()) - 1, 0, int(a.size()) - 2);
}
double Curve::value(double v, bool inv) const {
    auto [a, b] = segment(locate(v, inv));
    return inv ? (v - b) / a : a * v + b;
}
Model compile(Netlist net) {
    auto start = std::chrono::steady_clock::now();
    // Diagnostic context is local to this compilation; no shared/thread-local state.
    // Global errors without a mapped statement deliberately retain an empty Source.
    Source source_context;
    try {
        Model m;
        m.netlist = std::move(net);
        std::set<std::string> known_signals;
        for (auto &p : m.netlist.primitives)
            if ((p.kind == "SENSOR" || p.kind == "MATH" || p.kind == "CMP" || p.kind == "SEL" ||
                 p.kind == "INT" || p.kind == "REG" || p.kind == "EVENT") &&
                !p.args.empty())
                known_signals.insert(net_name(p.args[0]));
        require(Json::accept(m.netlist.layout_json), 1, "INVALID_LAYOUT_JSON",
                "Layout must contain valid JSON");
        std::sort(m.netlist.primitives.begin(), m.netlist.primitives.end(),
                  [](auto &a, auto &b) { return a.id < b.id; });
        std::map<std::string, int> masks;
        struct GenericEdge {
            std::string a, b;
            Source source;
        };
        std::vector<GenericEdge> equal;
        std::map<std::string, Source> first_reference, first_consumer, first_driver;
        auto reference_source = [&](const std::string &name) -> Source {
            if (auto found = first_consumer.find(name); found != first_consumer.end())
                return found->second;
            if (auto found = first_reference.find(name); found != first_reference.end())
                return found->second;
            return {};
        };
        auto driver_source = [&](const std::string &name) -> Source {
            if (auto found = first_driver.find(name); found != first_driver.end())
                return found->second;
            return reference_source(name);
        };
        std::map<std::string, std::vector<std::string>> deps;
        std::set<std::string> primitive_ids;
        auto constrain = [&](const std::string &raw, int bits, bool consumption = true) {
            if (is_literal(raw)) {
                double v = number(raw);
                require(bits != 4, 1, "TRIG_LITERAL", "TRIG requires a driven event");
                if (bits == 2)
                    require(v == 0 || v == 1, 1, "BOOL_LITERAL", "BOOL must be 0 or 1");
                return;
            }
            auto n = net_name(raw);
            require(std::regex_match(n, std::regex("[A-Za-z_][A-Za-z0-9_]*(/[A-Za-z_][A-Za-z0-9_]*)*")), 1,
                    "INVALID_IDENTIFIER", "invalid signal name: " + n);
            int declared = 7;
            if (raw.find("::") != std::string::npos) {
                auto t = raw.substr(0, raw.find("::"));
                declared = t == "REAL" ? 1 : t == "BOOL" ? 2 : t == "TRIG" ? 4 : 0;
            }
            first_reference.try_emplace(n, source_context);
            if (consumption)
                first_consumer.try_emplace(n, source_context);
            auto [it, fresh] = masks.emplace(n, 7);
            it->second &= bits & declared;
            require(it->second, 1, "TYPE_CONFLICT", "incompatible signal type: " + raw);
        };
        auto drive = [&](const std::string &n, const std::string &id, int bits) {
            require(!is_literal(n), 1, "INVALID_SIGNAL", "signal output cannot be literal");
            constrain(n, bits, false);
            auto key = net_name(n);
            std::string previous;
            if (auto found = first_driver.find(key); found != first_driver.end())
                previous = " (first driver at " + found->second.file + ":" +
                           std::to_string(found->second.line) + ")";
            require(!m.signals.count(key), 1, "MULTIPLE_DRIVERS", "multiple drivers: " + key + previous);
            first_driver.try_emplace(key, source_context);
            m.signals[key].driver = id;
        };
        auto unify = [&](const std::string &a, const std::string &b) {
            constrain(a, 3);
            constrain(b, 3);
            if (is_literal(a)) {
                double v = number(a);
                if (v != 0 && v != 1)
                    constrain(b, 1);
            }
            if (is_literal(b)) {
                double v = number(b);
                if (v != 0 && v != 1)
                    constrain(a, 1);
            }
            if (!is_literal(a) && !is_literal(b))
                equal.push_back({net_name(a), net_name(b), source_context});
        };
        auto positive = [&](const Primitive &p, const std::string &key) {
            require(p.options.count(key) && number(p.options.at(key)) > 0, 1, "NONPOSITIVE_PARAMETER",
                    p.id + " requires positive " + key, false, p.source);
        };
        std::map<std::string, std::set<std::string>> allowed = {
            {"R", {"R", "IV_TABLE", "RANGE"}},
            {"C", {"C", "QV_TABLE", "RANGE", "IC_V", "IC_Q"}},
            {"L", {"L", "PHII_TABLE", "L_MATRIX", "RANGE", "IC_I", "IC_PHI"}},
            {"V", {"DC"}},
            {"I", {"DC"}},
            {"SW", {"RON", "ROFF"}},
            {"SENSOR", {"PORT"}},
            {"MATH", {"OP", "EXPONENT"}},
            {"CMP", {"OP", "THRESHOLD"}},
            {"SEL", {}},
            {"INT", {"IC"}},
            {"REG", {"MODE", "SET", "RESET", "PRIORITY", "IC"}},
            {"EVENT",
             {"MODE", "PERIOD", "START", "AT", "SOURCE", "EDGE", "DELAY", "DELAY_INPUT", "POLICY",
              "CANCEL"}}};
        for (auto raw : m.netlist.primitives) {
            source_context = raw.source;
            require(primitive_ids.insert(raw.id).second, 1, "DUPLICATE_INSTANCE",
                    "duplicate instance " + raw.id, false, raw.source);
            require(allowed.count(raw.kind), 1, "UNKNOWN_PRIMITIVE", "unknown primitive " + raw.kind, false,
                    raw.source);
            for (auto &[k, v] : raw.options)
                require(allowed.at(raw.kind).count(k), 1, "UNKNOWN_OPTION",
                        raw.id + ": unsupported option " + k, false, raw.source);
            if (raw.kind == "EVENT") {
                const std::map<std::string, std::set<std::string>> by_mode = {
                    {"AT", {"MODE", "AT"}},
                    {"PERIODIC", {"MODE", "PERIOD", "START"}},
                    {"EDGE", {"MODE", "SOURCE", "EDGE"}},
                    {"DELAY", {"MODE", "SOURCE", "DELAY", "DELAY_INPUT", "POLICY", "CANCEL"}}};
                auto mode = opt(raw, "MODE");
                if (by_mode.count(mode))
                    for (auto &[key, val] : raw.options)
                        require(by_mode.at(mode).count(key), 1, "OPTION_MODE_CONFLICT",
                                raw.id + ": option " + key + " invalid for " + mode, false, raw.source);
            }
            if (raw.kind == "REG" && opt(raw, "MODE") != "SR")
                for (auto key : {"SET", "RESET", "PRIORITY"})
                    require(!raw.options.count(key), 1, "OPTION_MODE_CONFLICT", "SR options require MODE=SR",
                            false, raw.source);
            if (raw.kind == "MATH" && raw.options.count("EXPONENT"))
                require(opt(raw, "OP") == "POW", 1, "OPTION_MODE_CONFLICT", "EXPONENT requires OP=POW", false,
                        raw.source);
            if ((raw.kind == "R" || raw.kind == "C" || raw.kind == "L") && raw.options.count("RANGE"))
                require(raw.options.count("IV_TABLE") || raw.options.count("QV_TABLE") ||
                            raw.options.count("PHII_TABLE"),
                        1, "OPTION_MODE_CONFLICT", "RANGE requires PWA table", false, raw.source);
            if (raw.kind == "SENSOR" && raw.args.size() > 1 && raw.args[1] == "V")
                require(!raw.options.count("PORT"), 1, "OPTION_MODE_CONFLICT",
                        "PORT applies only to current measurement", false, raw.source);
            Part p;
            p.raw = raw;
            auto &a = p.raw.args;
            auto &k = raw.kind;
            size_t index = m.parts.size();
            auto arity = [&](size_t n) {
                require(a.size() == n, 1, "PORT_ARITY",
                        raw.id + " expects " + std::to_string(n) + " positional ports", false, raw.source);
            };
            if (k == "R" || k == "C" || k == "L" || k == "V" || k == "I" || k == "SW") {
                if (k == "L" && raw.options.count("L_MATRIX")) {
                    require(!a.empty(), 1, "PORT_ARITY", "empty inductor matrix ports");
                    for (auto &s : a)
                        p.ports.push_back(port(s));
                    auto rows = array_items(opt(raw, "L_MATRIX"));
                    int n = int(p.ports.size());
                    require(int(rows.size()) == n, 1, "L_MATRIX_SHAPE", "L_MATRIX row count mismatch");
                    std::vector<double> values;
                    for (auto &row : rows) {
                        auto items = array_items(row);
                        require(int(items.size()) == n, 1, "L_MATRIX_SHAPE",
                                "L_MATRIX column count mismatch");
                        for (auto &item : items)
                            values.push_back(number(item));
                    }
                    require(values.size() == size_t(n * n), 1, "L_MATRIX_SHAPE", "L_MATRIX shape mismatch");
                    p.inductance = Matrix(n, n);
                    for (int i = 0; i < n * n; ++i)
                        p.inductance(i / n, i % n) = values[i];
                    require(p.inductance.isApprox(p.inductance.transpose(), 1e-12) &&
                                Eigen::LLT<Matrix>(p.inductance).info() == Eigen::Success,
                            1, "L_MATRIX_NOT_SPD", "inductance matrix must be symmetric positive definite");
                    require(!raw.options.count("L") && !raw.options.count("PHII_TABLE"), 1,
                            "PARAMETER_CONFLICT", "matrix and scalar inductor parameters conflict");
                } else {
                    arity(k == "SW" ? 3 : (k == "V" || k == "I") && !raw.options.count("DC") ? 3 : 2);
                    p.ports.push_back({a[0], a[1]});
                }
                for (auto &[v, w] : p.ports) {
                    for (auto &node : {v, w})
                        require(node == "0" ||
                                    std::regex_match(
                                        node, std::regex("[A-Za-z_][A-Za-z0-9_]*(/[A-Za-z_][A-Za-z0-9_]*)*")),
                                1, "INVALID_IDENTIFIER", "invalid electrical node: " + node);
                    if (v != "0")
                        m.nodes.emplace(v, 0);
                    if (w != "0")
                        m.nodes.emplace(w, 0);
                }
                if (k == "V" || k == "I") {
                    if (!raw.options.count("DC")) {
                        constrain(a[2], 1);
                        deps[raw.id].push_back(net_name(a[2]));
                    } else
                        number(opt(raw, "DC"));
                }
                if (k == "SW") {
                    positive(raw, "RON");
                    positive(raw, "ROFF");
                    constrain(a[2], 2);
                    deps[raw.id].push_back(net_name(a[2]));
                }
                if (k == "R" || k == "C" || k == "L") {
                    auto table = k == "R" ? "IV_TABLE" : k == "C" ? "QV_TABLE" : "PHII_TABLE";
                    if (raw.options.count(table)) {
                        require(!raw.options.count(k) && !raw.options.count("L_MATRIX"), 1,
                                "PARAMETER_CONFLICT", "linear and PWA values conflict");
                        auto points = array_items(opt(raw, table));
                        std::vector<double> values;
                        for (auto &point : points) {
                            auto pair = array_items(point, '(', ')');
                            require(pair.size() == 2, 4, "INVALID_PWA_CURVE",
                                    "each PWA point requires two values");
                            for (auto &item : pair)
                                values.push_back(number(item));
                        }
                        require(values.size() >= 4, 4, "INVALID_PWA_CURVE",
                                "PWA requires at least two points");
                        for (size_t i = 0; i < values.size(); i += 2) {
                            p.curve.x.push_back(values[i]);
                            p.curve.y.push_back(values[i + 1]);
                        }
                        for (size_t i = 1; i < p.curve.x.size(); ++i)
                            require(p.curve.x[i] > p.curve.x[i - 1] && p.curve.y[i] > p.curve.y[i - 1], 4,
                                    "INVALID_PWA_CURVE", "PWA slopes must be positive");
                        auto range = opt(raw, "RANGE", "ERROR");
                        require(range == "ERROR" || range == "EXTEND", 1, "INVALID_RANGE", "unknown RANGE");
                        p.curve.extend = range == "EXTEND";
                        m.pwas.push_back(int(index));
                    } else if (!raw.options.count("L_MATRIX"))
                        positive(raw, k);
                }
                m.branches[raw.id] = int(index);
            }
            if (k == "SENSOR") {
                require(a.size() >= 3, 1, "PORT_ARITY", "invalid SENSOR");
                drive(a[0], raw.id, 1);
                require(a[1] == "V" || a[1] == "I", 1, "SENSOR_KIND", "SENSOR supports V or I");
                arity(a[1] == "V" ? 4 : 3);
                if (a[1] == "V") {
                    if (a[2] != "0")
                        m.nodes.emplace(a[2], 0);
                    if (a[3] != "0")
                        m.nodes.emplace(a[3], 0);
                }
            }
            if (k == "MATH") {
                require(!a.empty(), 1, "PORT_ARITY", "MATH needs output");
                drive(a[0], raw.id, 1);
                if (raw.options.count("OP")) {
                    auto op = opt(raw, "OP");
                    static const std::set<std::string> ops = {"MUL", "DIV", "SIN", "COS",  "SQRT",
                                                              "POW", "EXP", "LOG", "ATAN2"};
                    require(ops.count(op), 1, "MATH_OPCODE", "unknown discrete MATH opcode");
                    arity((op == "MUL" || op == "DIV" || op == "ATAN2") ? 3 : 2);
                    if (op == "POW") {
                        require(raw.options.count("EXPONENT"), 1, "MATH_ARITY", "POW needs fixed EXPONENT");
                        number(opt(raw, "EXPONENT"));
                    }
                    for (size_t j = 1; j < a.size(); ++j) {
                        constrain(a[j], 1);
                        if (!is_literal(a[j]))
                            deps[net_name(a[0])].push_back(net_name(a[j]));
                    }
                } else {
                    arity(1);
                    p.math = affine(raw.expression, known_signals);
                    for (auto &[n, v] : p.math.terms) {
                        constrain(n, 1);
                        deps[net_name(a[0])].push_back(net_name(n));
                    }
                }
            }
            if (k == "CMP") {
                arity(2);
                drive(a[0], raw.id, 2);
                constrain(a[1], 1);
                auto op = opt(raw, "OP");
                require(op == "GT" || op == "GE" || op == "LT" || op == "LE", 1, "CMP_OPCODE",
                        "CMP requires GT/GE/LT/LE");
                require(raw.options.count("THRESHOLD"), 1, "MISSING_PARAMETER", "CMP needs threshold");
                number(opt(raw, "THRESHOLD"));
                deps[net_name(a[0])].push_back(net_name(a[1]));
                m.cmps.push_back(int(index));
            }
            if (k == "SEL") {
                arity(4);
                drive(a[0], raw.id, 3);
                constrain(a[1], 2);
                unify(a[0], a[2]);
                unify(a[0], a[3]);
                for (size_t j = 1; j < a.size(); ++j)
                    if (!is_literal(a[j]))
                        deps[net_name(a[0])].push_back(net_name(a[j]));
            }
            if (k == "INT") {
                arity(2);
                drive(a[0], raw.id, 1);
                constrain(a[1], 1);
            }
            if (k == "REG") {
                number(opt(raw, "IC", "0"));
                if (opt(raw, "MODE") == "SR") {
                    arity(1);
                    drive(a[0], raw.id, 2);
                    require(raw.options.count("SET") && raw.options.count("RESET") &&
                                (opt(raw, "PRIORITY") == "SET" || opt(raw, "PRIORITY") == "RESET"),
                            1, "SR_CONFIGURATION", "SR requires SET/RESET and explicit PRIORITY");
                    constrain(opt(raw, "SET"), 4);
                    constrain(opt(raw, "RESET"), 4);
                } else {
                    require(!raw.options.count("MODE"), 1, "REG_MODE", "unsupported REG mode");
                    arity(3);
                    drive(a[0], raw.id, 3);
                    unify(a[0], a[1]);
                    constrain(a[2], 4);
                }
                m.registers.push_back(int(index));
            }
            if (k == "EVENT") {
                arity(1);
                drive(a[0], raw.id, 4);
                auto mode = opt(raw, "MODE");
                require(mode == "AT" || mode == "PERIODIC" || mode == "EDGE" || mode == "DELAY", 1,
                        "EVENT_MODE", "unknown EVENT MODE");
                if (mode == "PERIODIC") {
                    positive(raw, "PERIOD");
                    require(number(opt(raw, "START", "0")) >= 0, 1, "EVENT_TIME", "negative start");
                }
                if (mode == "AT")
                    require(raw.options.count("AT") && number(opt(raw, "AT")) >= 0, 1, "EVENT_TIME",
                            "AT needs nonnegative time");
                if (mode == "EDGE") {
                    constrain(opt(raw, "SOURCE"), 2);
                    auto edge = opt(raw, "EDGE");
                    require(edge == "RISE" || edge == "FALL" || edge == "BOTH", 1, "EVENT_EDGE",
                            "EDGE requires RISE/FALL/BOTH");
                }
                if (mode == "DELAY") {
                    constrain(opt(raw, "SOURCE"), 4);
                    require(raw.options.count("DELAY") != raw.options.count("DELAY_INPUT"), 1,
                            "DELAY_CONFIGURATION", "exactly one DELAY or DELAY_INPUT required");
                    if (raw.options.count("DELAY_INPUT"))
                        constrain(opt(raw, "DELAY_INPUT"), 1);
                    auto policy = opt(raw, "POLICY", "TRANSPORT");
                    require(policy == "TRANSPORT" || policy == "REPLACE", 1, "DELAY_POLICY",
                            "unknown delay policy");
                    if (raw.options.count("CANCEL"))
                        constrain(opt(raw, "CANCEL"), 4);
                }
                m.events.push_back(int(index));
            }
            if (k == "C" || k == "L" || k == "INT") {
                p.state = m.ns;
                int n = k == "L" ? int(p.ports.size()) : 1;
                for (int j = 0; j < n; ++j)
                    m.state_ids.push_back(raw.id + "/" +
                                          (k == "C"   ? "q"
                                           : k == "L" ? "phi"
                                                      : "eta") +
                                          (n > 1 ? std::to_string(j + 1) : ""));
                m.ns += n;
            }
            m.parts.push_back(std::move(p));
        }
        bool change = true;
        while (change) {
            change = false;
            for (auto &[a, b, source] : equal) {
                source_context = source;
                int mask = masks[a] & masks[b];
                require(mask, 1, "TYPE_CONFLICT", "generic port type mismatch");
                if (masks[a] != mask || masks[b] != mask) {
                    masks[a] = masks[b] = mask;
                    change = true;
                }
            }
        }
        for (auto &[n, mask] : masks) {
            source_context = reference_source(n);
            require(m.signals.count(n), 1, "UNDRIVEN_SIGNAL", "undriven signal: " + n);
            source_context = driver_source(n);
            require(mask == 1 || mask == 2 || mask == 4, 1, "AMBIGUOUS_TYPE",
                    "use REAL:: or BOOL:: annotation: " + n);
            m.signals[n].type = mask == 1 ? Signal::REAL : mask == 2 ? Signal::BOOL : Signal::TRIG;
            require(!m.nodes.count(n), 1, "DOMAIN_CONFLICT", "electrical and numerical net share name " + n);
        }
        for (auto &p : m.parts) {
            source_context = p.raw.source;
            auto &a = p.raw.args;
            auto k = p.raw.kind;
            // Comparator outputs are Boolean event values: constant during a
            // flow, even when their inputs cross continuously. Seed this phase
            // before SEL/MATH propagation so dependent predicates participate
            // in the same transaction without waiting for a REG update. The
            // comparator input phase still determines its continuous guard.
            if (k == "REG" || k == "CMP")
                m.signals[net_name(a[0])].held = true;
            if (k == "MATH" && p.math.terms.empty() && !p.raw.options.count("OP"))
                m.signals[net_name(a[0])].held = true;
        }
        auto held = [&](const std::string &n) { return is_literal(n) || m.signals.at(net_name(n)).held; };
        for (size_t pass = 0; pass < m.parts.size(); ++pass)
            for (auto &p : m.parts) {
                source_context = p.raw.source;
                auto &a = p.raw.args;
                auto k = p.raw.kind;
                bool h = false;
                if (k == "MATH" || k == "SEL" || k == "CMP") {
                    h = true;
                    if (k == "MATH" && !p.raw.options.count("OP")) {
                        for (auto &[n, v] : p.math.terms)
                            h = h && held(n);
                    } else
                        for (size_t j = 1; j < a.size(); ++j)
                            h = h && held(a[j]);
                    if (h)
                        m.signals[net_name(a[0])].held = true;
                }
            }
        for (auto &p : m.parts)
            if (p.raw.kind == "MATH" && p.raw.options.count("OP")) {
                source_context = p.raw.source;
                auto start = net_name(p.raw.args[0]);
                std::set<std::string> seen;
                std::function<bool(const std::string &)> cycle = [&](const std::string &n) {
                    if (!seen.insert(n).second)
                        return false;
                    for (auto &d : deps[n])
                        if (d == start || cycle(d))
                            return true;
                    return false;
                };
                require(!cycle(start), 2, "COMBINATIONAL_CYCLE", "stateless nonlinear feedback at " + start,
                        false, p.raw.source);
            }
        for (auto &p : m.parts) {
            source_context = p.raw.source;
            auto &a = p.raw.args;
            auto k = p.raw.kind;
            if (k == "MATH" && p.raw.options.count("OP"))
                for (size_t j = 1; j < a.size(); ++j)
                    require(held(a[j]), 2, "CONTINUOUS_NONAFFINE", "discrete MATH requires held REAL inputs",
                            false, p.raw.source);
            if (k == "EVENT" && p.raw.options.count("DELAY_INPUT"))
                require(held(opt(p.raw, "DELAY_INPUT")), 2, "CONTINUOUS_DELAY_INPUT",
                        "dynamic delay requires held REAL", false, p.raw.source);
            if (k == "REG" && m.signals.at(net_name(a[0])).type == Signal::BOOL) {
                double ic = number(opt(p.raw, "IC", "0"));
                require(ic == 0 || ic == 1, 1, "BOOL_IC", "BOOL IC must be 0 or 1");
            }
            if (k == "SENSOR" && a[1] == "I") {
                require(m.branches.count(a[2]), 2, "AMBIGUOUS_CURRENT_REFERENCE",
                        "unknown directed physical branch: " + a[2], false, p.raw.source);
                auto &target = m.parts[m.branches.at(a[2])];
                double pv = number(opt(p.raw, "PORT", "1"));
                require(pv >= 1 && pv <= double(target.ports.size()) && pv == std::floor(pv), 2,
                        "AMBIGUOUS_CURRENT_REFERENCE", "PORT must be an integer winding number", false,
                        p.raw.source);
                int n = int(target.ports.size()), portno = int(pv);
                require(portno >= 1 && portno <= n && (n == 1 || p.raw.options.count("PORT")), 2,
                        "AMBIGUOUS_CURRENT_REFERENCE", "multiport current requires valid PORT");
            }
        }
        // Reject discrete combinational SCCs. Continuous affine SCCs are solved jointly below.
        std::map<std::string, int> visit;
        std::function<void(std::string)> dfs = [&](std::string n) {
            if (!m.signals.count(n) || !m.signals.at(n).held)
                return;
            source_context = driver_source(n);
            require(visit[n] != 1, 2, "COMBINATIONAL_CYCLE", "stateless discrete feedback at " + n);
            if (visit[n] == 2)
                return;
            visit[n] = 1;
            for (auto &d : deps[n])
                dfs(d);
            visit[n] = 2;
        };
        for (auto &[n, s] : m.signals)
            dfs(n);
        // Conservative transitive dependency roles. Observation selection never
        // determines electrical relevance. Stateful/control roots remain critical.
        auto mark_role = [&](const std::string &raw, const std::string &role) {
            std::set<std::string> seen;
            std::function<void(std::string)> visit_dependency = [&](std::string name) {
                name=net_name(name);
                if(!m.signals.count(name)||!seen.insert(name).second)return;
                m.dependency_roles[name].insert(role);
                for(const auto &input:deps[name])visit_dependency(input);
            };
            if(!is_literal(raw))visit_dependency(raw);
        };
        std::set<std::string> task_output_names;
        for(const auto &task:m.netlist.tasks)for(const auto &output:task.outputs)task_output_names.insert(net_name(output));
        for(const auto &part:m.parts){
            const auto &args=part.raw.args;const auto &kind=part.raw.kind;
            if((kind=="V"||kind=="I")&&args.size()>2)mark_role(args[2],"electrical_excitation");
            if(kind=="SW"&&args.size()>2)mark_role(args[2],"topology");
            if(kind=="INT"&&args.size()>1)mark_role(args[1],"dynamics");
            if(kind=="CMP"&&args.size()>1)mark_role(args[1],"guard");
            if(kind=="REG")for(size_t i=1;i<args.size();++i){
                if(task_output_names.count(net_name(args[0]))&&net_name(args[i])==net_name(args[0]))continue;
                mark_role(args[i],"state_update");
            }
            if(kind=="REG"||kind=="EVENT")for(const auto &option:part.raw.options)
                if(option.first=="SOURCE"||option.first=="CANCEL"||option.first=="DELAY_INPUT"||option.first=="SET"||option.first=="RESET")mark_role(option.second,"event_control");
        }
        for(const auto &task:m.netlist.tasks){
            for(const auto &input:task.inputs)mark_role(input,"software_input");
            mark_role(task.trigger,"event_control");
        }
        // Continuous observation equations are retained in the algebraic system;
        // their held dependencies are conservatively excluded from rebinding.
        for(const auto &[name,signal]:m.signals)
            if(signal.type==Signal::REAL&&!signal.held)mark_role(name,"continuous_equation");
        for(const auto &[name,signal]:m.signals)
            if(signal.type==Signal::REAL&&signal.held&&m.dependency_roles[name].empty()){
                m.observer_signals.insert(name);
                for(const auto &part:m.parts)if(part.raw.id==signal.driver&&part.raw.kind=="REG")m.observer_regs.insert(name);
                m.dependency_roles[name].insert("observation_only");
            }
        // Every physical two-terminal port contributes connectivity. Different
        // windings are never joined merely because a constitutive law couples
        // them. Sensors and numeric control signals contribute no graph edges.
        std::map<std::string, std::string> electrical_parent;
        electrical_parent["0"] = "0";
        for (const auto &[name, index] : m.nodes)
            electrical_parent[name] = name;
        std::function<std::string(const std::string &)> electrical_find =
            [&](const std::string &name) -> std::string {
                auto &parent = electrical_parent.at(name);
                return parent == name ? name : parent = electrical_find(parent);
            };
        for (const auto &part : m.parts)
            for (const auto &[a, b] : part.ports) {
                auto ra = electrical_find(a), rb = electrical_find(b);
                if (ra != rb)
                    electrical_parent[std::max(ra, rb)] = std::min(ra, rb);
            }
        m.node_reference["0"] = "0";
        for (const auto &[name, index] : m.nodes) {
            auto reference = electrical_find(name);
            m.node_reference[name] = reference;
            if (reference != "0" && name == reference)
                m.floating_references.push_back(reference);
        }
        for (const auto &part : m.parts)
            if (part.raw.kind == "SENSOR" && part.raw.args[1] == "V") {
                const auto &a = part.raw.args[2], &b = part.raw.args[3];
                require(m.node_reference.at(a) == m.node_reference.at(b), 2,
                        "UNDEFINED_CROSS_ISLAND_VOLTAGE",
                        "voltage between independent floating electrical references is undefined: " + a + " / " + b,
                        false, part.raw.source);
            }
        size_t algebraic_size = m.nodes.size();
        for (auto &[n, i] : m.branches)
            algebraic_size += m.parts[i].ports.size();
        for (auto &[n, sig] : m.signals)
            if (sig.type == Signal::REAL)
                ++algebraic_size;
        source_context = {}; // A whole-model budget has no unique offending statement.
        require(algebraic_size <= 512 && m.ns <= 128, 2, "MODEL_SIZE_BUDGET",
                "dense compiler supports at most 512 algebraic unknowns and 128 physical states");
        int node = 0;
        for (auto &[n, i] : m.nodes)
            i = node++;
        m.initial = Vector::Zero(m.ns + 1);
        m.initial[m.ns] = 1;
        for (auto &p : m.parts) {
            source_context = p.raw.source;
            auto &raw = p.raw;
            auto k = raw.kind;
            if (p.state < 0)
                continue;
            if (k == "INT")
                m.initial[p.state] = number(opt(raw, "IC", "0"));
            else if (k == "C") {
                require(!(raw.options.count("IC_Q") && raw.options.count("IC_V")), 1, "IC_CONFLICT",
                        "C IC_Q and IC_V conflict");
                double q = 0;
                if (raw.options.count("IC_Q"))
                    q = number(opt(raw, "IC_Q"));
                else if (raw.options.count("IC_V")) {
                    double v = number(opt(raw, "IC_V"));
                    q = p.curve.x.empty() ? number(opt(raw, "C")) * v : p.curve.value(v);
                }
                if (!p.curve.x.empty())
                    p.curve.locate(q, true);
                m.initial[p.state] = q;
            } else {
                require(!(raw.options.count("IC_I") && raw.options.count("IC_PHI")), 1, "IC_CONFLICT",
                        "L IC_I and IC_PHI conflict");
                int n = int(p.ports.size());
                Vector phi = Vector::Zero(n);
                if (raw.options.count("IC_PHI")) {
                    auto v = array_values(opt(raw, "IC_PHI"));
                    require(int(v.size()) == n, 1, "IC_SHAPE", "IC_PHI shape mismatch");
                    for (int j = 0; j < n; ++j)
                        phi[j] = v[j];
                } else if (raw.options.count("IC_I")) {
                    auto v = array_values(opt(raw, "IC_I"));
                    require(int(v.size()) == n, 1, "IC_SHAPE", "IC_I shape mismatch");
                    Vector cur(n);
                    for (int j = 0; j < n; ++j)
                        cur[j] = v[j];
                    if (p.inductance.rows() > 0)
                        phi = p.inductance * cur;
                    else
                        phi[0] = p.curve.x.empty() ? number(opt(raw, "L")) * cur[0] : p.curve.value(cur[0]);
                }
                if (!p.curve.x.empty())
                    p.curve.locate(phi[0], true);
                m.initial.segment(p.state, n) = phi;
            }
        }
        for (auto &[n, i] : m.nodes)
            m.registry.push_back("V(" + n + ")");
        for (auto &[n, i] : m.branches) {
            int count = int(m.parts[i].ports.size());
            for (int j = 0; j < count; ++j)
                m.registry.push_back("I(" + n + (count > 1 ? "," + std::to_string(j + 1) : "") + ")");
        }
        for (auto &[n, s] : m.signals)
            if (s.type != Signal::TRIG)
                m.registry.push_back(n);
        for (const auto &task : m.netlist.tasks) {
            require(m.signals.count(task.trigger) && m.signals.at(task.trigger).type == Signal::TRIG,
                    1, "SOFTWARE_TRIGGER", "task requires a TRIG signal", false, task.source);
            for (const auto &input : task.inputs)
                require(is_literal(input) || (m.signals.count(net_name(input)) &&
                        m.signals.at(net_name(input)).type != Signal::TRIG),
                        1, "SOFTWARE_INPUT", "task input is not a numeric signal: " + input, false, task.source);
            for (const auto &output : task.outputs)
                require(m.software_outputs.insert(net_name(output)).second,
                        1, "SOFTWARE_OUTPUT", "duplicate software output", false, task.source);
        }
        std::sort(m.registry.begin(), m.registry.end());
        m.compile_seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
        return m;
    } catch (const Error &error) {
        if (error.source.line > 0 || source_context.line <= 0)
            throw;
        throw Error(error.code, error.subcode, error.what(), error.unresolved, source_context);
    } catch (const ParseError &error) {
        throw Error(1, error.subcode, error.what(), false,
                    error.source.line > 0 ? error.source : source_context);
    } catch (const std::runtime_error &error) {
        // fixed_value/number failures have no Source of their own. The current
        // statement was set before evaluating any of its fixed numeric options.
        throw Error(1, "INVALID_PARAMETER", error.what(), false, source_context);
    }
}
} // namespace pulse
