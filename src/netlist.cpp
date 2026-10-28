#include "pulse/netlist.hpp"
#include <algorithm>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <functional>
#include <iomanip>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
namespace pulse {
namespace {
std::string trim(std::string s) {
    auto a = s.find_first_not_of(" \t\r\n");
    if (a == s.npos)
        return {};
    return s.substr(a, s.find_last_not_of(" \t\r\n") - a + 1);
}
std::string upper(std::string s) {
    for (char &c : s)
        c = char(std::toupper((unsigned char)c));
    return s;
}
bool ident(const std::string &s) {
    if (s.empty() || (!std::isalpha((unsigned char)s[0]) && s[0] != '_'))
        return false;
    return std::all_of(s.begin() + 1, s.end(), [](unsigned char c) { return std::isalnum(c) || c == '_'; });
}
[[noreturn]] void fail(const Source &s, const std::string &code, const std::string &message) {
    throw ParseError(s, code, message);
}
std::string number(double d) {
    std::ostringstream o;
    o << std::setprecision(std::numeric_limits<double>::max_digits10) << d;
    return o.str();
}
struct Fixed {
    const std::string &s;
    const std::map<std::string, double> &p;
    size_t i = 0;
    void ws() {
        while (i < s.size() && std::isspace((unsigned char)s[i]))
            ++i;
    }
    bool take(char c) {
        ws();
        if (i < s.size() && s[i] == c) {
            ++i;
            return true;
        }
        return false;
    }
    double checked(double x) {
        if (!std::isfinite(x))
            throw std::runtime_error("nonfinite fixed expression");
        return x;
    }
    double atom() {
        ws();
        if (take('+'))
            return atom();
        if (take('-'))
            return checked(-atom());
        if (take('(')) {
            double x = add();
            if (!take(')'))
                throw std::runtime_error("missing )");
            return x;
        }
        if (i < s.size() && (std::isalpha((unsigned char)s[i]) || s[i] == '_')) {
            size_t a = i++;
            while (i < s.size() && (std::isalnum((unsigned char)s[i]) || s[i] == '_'))
                ++i;
            auto it = p.find(s.substr(a, i - a));
            if (it == p.end())
                throw std::runtime_error("unknown or forward fixed parameter " + s.substr(a, i - a));
            return it->second;
        }
        if (i + 1 < s.size() && s[i] == '0' && (s[i + 1] == 'x' || s[i + 1] == 'X'))
            throw std::runtime_error("hexadecimal numbers are not in the netlist grammar");
        const char *start = s.c_str() + i;
        char *end = nullptr;
        double x = std::strtod(start, &end);
        if (end == start)
            throw std::runtime_error("expected fixed number");
        i += size_t(end - start);
        size_t a = i;
        while (i < s.size() && std::isalpha((unsigned char)s[i]))
            ++i;
        auto u = s.substr(a, i - a);
        double scale = 1;
        if (!u.empty()) {
            if (u == "T")
                scale = 1e12;
            else if (u == "G")
                scale = 1e9;
            else if (u == "Meg" || u == "meg" || u == "MEG")
                scale = 1e6;
            else if (u == "k" || u == "K")
                scale = 1e3;
            else if (u == "m")
                scale = 1e-3;
            else if (u == "u")
                scale = 1e-6;
            else if (u == "n")
                scale = 1e-9;
            else if (u == "p")
                scale = 1e-12;
            else if (u == "f")
                scale = 1e-15;
            else
                throw std::runtime_error("invalid numeric suffix " + u);
        }
        return checked(x * scale);
    }
    double mul() {
        double x = atom();
        for (;;) {
            if (take('*'))
                x = checked(x * atom());
            else if (take('/')) {
                double y = atom();
                if (y == 0)
                    throw std::runtime_error("division by zero");
                x = checked(x / y);
            } else
                return x;
        }
    }
    double sum(double x, double y) {
        double z = checked(x + y);
        if ((x != 0 && y != 0) && ((z == x) || (z == y)))
            throw std::runtime_error(
                "FIXED_PRECISION_LOSS: nonzero term erased in binary64; express time as separate DELAY");
        return z;
    }
    double add() {
        double x = mul();
        for (;;) {
            if (take('+'))
                x = sum(x, mul());
            else if (take('-'))
                x = sum(x, -mul());
            else
                return x;
        }
    }
    double run() {
        double x = add();
        ws();
        if (i != s.size())
            throw std::runtime_error("unexpected fixed-expression token");
        return checked(x);
    }
};
std::string freeze(std::string s, const std::map<std::string, double> &p, const Source &src) {
    size_t a = 0;
    while ((a = s.find('{', a)) != s.npos) {
        auto b = s.find('}', a);
        if (b == s.npos)
            fail(src, "INVALID_PARAMETER", "unclosed fixed expression");
        try {
            auto v = number(fixed_value(s.substr(a, b - a + 1), p));
            s.replace(a, b - a + 1, v);
            a += v.size();
        } catch (const std::exception &e) {
            fail(src, "INVALID_PARAMETER", e.what());
        }
    }
    if (s.find('}') != s.npos)
        fail(src, "INVALID_PARAMETER", "unmatched }");
    return s;
}
std::vector<std::string> tokens(const std::string &s, const Source &src) {
    std::vector<std::string> out;
    size_t a = 0;
    std::vector<char> stack;
    for (size_t i = 0; i <= s.size(); ++i) {
        char c = i < s.size() ? s[i] : ' ';
        if (c == '[' || c == '(' || c == '{')
            stack.push_back(c);
        if (c == ']' || c == ')' || c == '}') {
            char expected = c == ']' ? '[' : c == ')' ? '(' : '{';
            if (stack.empty() || stack.back() != expected)
                fail(src, "INVALID_NETLIST", "unbalanced delimiters");
            stack.pop_back();
        }
        if (std::isspace((unsigned char)c) && stack.empty()) {
            if (i > a)
                out.push_back(s.substr(a, i - a));
            a = i + 1;
        }
    }
    if (!stack.empty())
        fail(src, "INVALID_NETLIST", "unclosed delimiters");
    return out;
}
struct Line {
    std::string text;
    Source source;
};
// Layout is deliberately parsed independently of all mathematical semantics.
struct Json {
    const std::string &s;
    size_t i = 0;
    void ws() {
        while (i < s.size() && std::isspace((unsigned char)s[i]))
            ++i;
    }
    bool ch(char c) {
        ws();
        if (i < s.size() && s[i] == c) {
            ++i;
            return true;
        }
        return false;
    }
    void bad() { throw std::runtime_error("invalid Layout JSON"); }
    void str() {
        if (!ch('"'))
            bad();
        while (i < s.size()) {
            unsigned char c = s[i++];
            if (c == '"')
                return;
            if (c < 32)
                bad();
            if (c == '\\') {
                if (i >= s.size())
                    bad();
                char e = s[i++];
                if (e == 'u') {
                    for (int n = 0; n < 4; ++n)
                        if (i >= s.size() || !std::isxdigit((unsigned char)s[i++]))
                            bad();
                } else if (std::string("\"\\/bfnrt").find(e) == std::string::npos)
                    bad();
            }
        }
        bad();
    }
    void val() {
        ws();
        if (i == s.size())
            bad();
        if (s[i] == '"') {
            str();
            return;
        }
        if (ch('{')) {
            if (ch('}'))
                return;
            do {
                str();
                if (!ch(':'))
                    bad();
                val();
            } while (ch(','));
            if (!ch('}'))
                bad();
            return;
        }
        if (ch('[')) {
            if (ch(']'))
                return;
            do {
                val();
            } while (ch(','));
            if (!ch(']'))
                bad();
            return;
        }
        for (auto lit : {"true", "false", "null"})
            if (s.compare(i, std::string(lit).size(), lit) == 0) {
                i += std::string(lit).size();
                return;
            }
        size_t a = i;
        if (s[i] == '-')
            ++i;
        if (i == s.size())
            bad();
        if (s[i] == '0')
            ++i;
        else {
            if (!std::isdigit((unsigned char)s[i]))
                bad();
            while (i < s.size() && std::isdigit((unsigned char)s[i]))
                ++i;
        }
        if (i < s.size() && s[i] == '.') {
            ++i;
            size_t b = i;
            while (i < s.size() && std::isdigit((unsigned char)s[i]))
                ++i;
            if (i == b)
                bad();
        }
        if (i < s.size() && (s[i] == 'e' || s[i] == 'E')) {
            ++i;
            if (i < s.size() && (s[i] == '+' || s[i] == '-'))
                ++i;
            size_t b = i;
            while (i < s.size() && std::isdigit((unsigned char)s[i]))
                ++i;
            if (i == b)
                bad();
        }
        if (i == a)
            bad();
    }
    void run() {
        if (!ch('{'))
            bad();
        --i;
        val();
        ws();
        if (i != s.size())
            bad();
    }
};
std::map<std::string, std::string> options(const std::vector<std::string> &t, size_t start, const Source &src,
                                           std::vector<std::string> &args) {
    std::map<std::string, std::string> o;
    for (size_t i = start; i < t.size(); ++i) {
        auto eq = t[i].find('=');
        if (eq == std::string::npos) {
            args.push_back(t[i]);
            continue;
        }
        auto k = upper(t[i].substr(0, eq));
        auto v = t[i].substr(eq + 1);
        if (!ident(k) || v.empty() || !o.emplace(k, v).second)
            fail(src, "INVALID_NETLIST", "invalid or duplicate option " + k);
    }
    return o;
}
std::string kindof(const std::string &id, const Source &s) {
    auto u = upper(id);
    for (auto k : {"SENSOR", "EVENT", "MATH", "CMP", "SEL", "INT", "REG", "SW", "R", "C", "L", "V", "I", "X"})
        if (u.rfind(k, 0) == 0)
            return k;
    fail(s, "INVALID_PRIMITIVE", "unknown primitive " + id);
}
void validate(Primitive &p) {
    auto n = p.args.size();
    bool valid = true;
    if (p.kind == "R" || p.kind == "C")
        valid = n == 2;
    else if (p.kind == "L")
        valid = p.options.count("L_MATRIX") ? n >= 1 : n == 2;
    else if (p.kind == "V" || p.kind == "I")
        valid = n == (p.options.count("DC") ? 2 : 3);
    else if (p.kind == "SW")
        valid = n == 3;
    else if (p.kind == "SENSOR") {
        if (n >= 2)
            p.args[1] = upper(p.args[1]);
        valid = n >= 2 && ((p.args[1] == "V" && n == 4) || (p.args[1] == "I" && n == 3));
    } else if (p.kind == "INT" || p.kind == "CMP")
        valid = n == 2;
    else if (p.kind == "SEL")
        valid = n == 4;
    else if (p.kind == "EVENT")
        valid = n == 1;
    else if (p.kind == "REG")
        valid = n == (p.options.count("MODE") && upper(p.options.at("MODE")) == "SR" ? 1 : 3);
    else if (p.kind == "MATH")
        valid = p.expression.empty() ? n >= 1 : n == 1;
    if (!valid)
        fail(p.source, "INVALID_PORT_COUNT", p.id + " has invalid positional ports");
    for (auto &[k, v] : p.options)
        if (k == "MODE" || k == "OP" || k == "POLICY" || k == "EDGE" || k == "RANGE" || k == "PRIORITY")
            v = upper(v);
}
struct Def {
    std::vector<std::string> ports;
    std::vector<Line> lines;
    Source src;
};
std::string renamed(const std::string &name, const std::string &path,
                    const std::map<std::string, std::string> &ports) {
    auto colon = name.find("::");
    if (colon != name.npos)
        return upper(name.substr(0, colon)) + "::" + renamed(name.substr(colon + 2), path, ports);
    if (name == "0")
        return name;
    if (!name.empty() &&
        (std::isdigit((unsigned char)name[0]) || name[0] == '-' || name[0] == '+' || name[0] == '.'))
        return name;
    auto it = ports.find(name);
    if (it != ports.end())
        return it->second;
    return path.empty() ? name : path + "/" + name;
}
std::string rename_expr(const std::string &s, const std::string &path,
                        const std::map<std::string, std::string> &ports) {
    std::string o;
    for (size_t i = 0; i < s.size();) {
        if (std::isdigit((unsigned char)s[i]) || s[i] == '.') {
            const char *a = s.c_str() + i;
            char *b = nullptr;
            std::strtod(a, &b);
            size_t n = size_t(b - a);
            if (n == 0) {
                o += s[i++];
                continue;
            }
            o.append(a, n);
            i += n;
            while (i < s.size() && std::isalpha((unsigned char)s[i]))
                o += s[i++];
        } else if (std::isalpha((unsigned char)s[i]) || s[i] == '_') {
            size_t a = i++;
            while (i < s.size() && (std::isalnum((unsigned char)s[i]) || s[i] == '_' || s[i] == ':'))
                ++i;
            o += renamed(s.substr(a, i - a), path, ports);
        } else
            o += s[i++];
    }
    return o;
}
} // namespace

double fixed_value(const std::string &expression, const std::map<std::string, double> &parameters) {
    auto s = trim(expression);
    if (s.size() >= 2 && s.front() == '{' && s.back() == '}')
        s = s.substr(1, s.size() - 2);
    return Fixed{s, parameters}.run();
}

Netlist parse_markdown(const std::string &text, const std::string &filename) {
    if (text.find("# PULSE Netlist v1.2") != std::string::npos)
        return parse_pre_markdown(text, filename);
    auto start = std::chrono::steady_clock::now();
    Netlist net;
    std::map<std::string, std::vector<Line>> sections;
    std::map<std::string, int> counts;
    std::string section, language;
    bool fence = false, header = false;
    int section_order = 0;
    Source layout_source{filename, "LAYOUT", "", 0, 1};
    std::istringstream input(text);
    std::string raw;
    int ln = 0;
    Source last{filename, "", "", 0, 1};
    while (std::getline(input, raw)) {
        ++ln;
        auto t = trim(raw);
        Source src{filename, section, "", ln, int(raw.find_first_not_of(" \t") + 1)};
        last = src;
        if (t.rfind("```", 0) == 0) {
            if (fence) {
                fence = false;
                language.clear();
            } else {
                fence = true;
                language = upper(trim(t.substr(3)));
                if (language == "PULSE" &&
                    (section != "PARAMETERS" && section != "NETWORK" && section != "SIMULATION"))
                    fail(src, "INVALID_SECTION", "unrecognized pulse block");
            }
            continue;
        }
        if (fence) {
            if (language == "PULSE" || (section == "LAYOUT" && language == "JSON")) {
                if (section == "LAYOUT") {
                    if (layout_source.line == 0)
                        layout_source = src;
                    net.layout_json += raw + "\n";
                } else {
                    if (t.empty() || t[0] == '*')
                        continue;
                    if (t[0] == '+') {
                        auto &ls = sections[section];
                        if (ls.empty())
                            fail(src, "INVALID_CONTINUATION", "no previous statement");
                        ls.back().text += " " + trim(t.substr(1));
                    } else
                        sections[section].push_back({t, src});
                }
            }
            continue;
        }
        if (upper(t) == "# PULSE NETLIST V1.1") {
            if (header)
                fail(src, "INVALID_HEADER", "duplicate header");
            header = true;
            continue;
        }
        if (t.rfind("## ", 0) == 0) {
            section = upper(trim(t.substr(3)));
            if (section == "PARAMETERS" || section == "NETWORK" || section == "SIMULATION" ||
                section == "LAYOUT") {
                if (++counts[section] > 1)
                    fail(src, "DUPLICATE_SECTION", section);
                int order = section == "PARAMETERS"   ? 1
                            : section == "NETWORK"    ? 2
                            : section == "SIMULATION" ? 3
                                                      : 4;
                if (!header || order <= section_order)
                    fail(src, "INVALID_SECTION_ORDER", "header and sections must follow contract order");
                section_order = order;
            }
        }
    }
    if (fence)
        fail(last, "INVALID_MARKDOWN", "unclosed code fence");
    if (!header)
        fail(last, "INVALID_HEADER", "missing # PULSE Netlist v1.1");
    for (auto s : {"PARAMETERS", "NETWORK", "SIMULATION", "LAYOUT"})
        if (counts[s] != 1)
            fail(last, "MISSING_SECTION", s);
    for (const auto &l : sections["PARAMETERS"]) {
        auto space = l.text.find_first_of(" \t");
        if (upper(l.text.substr(0, space)) != ".PARAM" || space == l.text.npos)
            fail(l.source, "INVALID_PARAMETER", "only .PARAM allowed");
        auto body = trim(l.text.substr(space));
        auto eq = body.find('=');
        auto key = trim(body.substr(0, eq));
        if (eq == body.npos || !ident(key) || net.parameters.count(key))
            fail(l.source, "INVALID_PARAMETER", "invalid or duplicate parameter " + key);
        try {
            net.parameters.emplace(key, fixed_value(body.substr(eq + 1), net.parameters));
            net.parameter_text[key] = body.substr(eq + 1);
        } catch (const std::exception &e) {
            fail(l.source, "INVALID_PARAMETER", e.what());
        }
    }
    std::map<std::string, Def> defs;
    std::vector<Line> top;
    std::string active;
    for (const auto &l : sections["NETWORK"]) {
        auto t = tokens(l.text, l.source);
        auto command = upper(t[0]);
        if (command == ".SUBCKT") {
            if (!active.empty() || t.size() < 3 || !ident(t[1]) || defs.count(t[1]))
                fail(l.source, "INVALID_SUBCKT", "invalid or duplicate .SUBCKT");
            Def d;
            d.src = l.source;
            std::set<std::string> seen;
            for (size_t i = 2; i < t.size(); ++i) {
                if (!ident(t[i]) || !seen.insert(t[i]).second)
                    fail(l.source, "INVALID_SUBCKT", "invalid or duplicate port");
                d.ports.push_back(t[i]);
            }
            active = t[1];
            defs.emplace(active, std::move(d));
        } else if (command == ".ENDS") {
            if (active.empty() || t.size() != 2 || t[1] != active)
                fail(l.source, "INVALID_SUBCKT", "mismatched .ENDS");
            active.clear();
        } else {
            if (command[0] == '.')
                fail(l.source, "INVALID_NETLIST", "unknown network directive");
            if (active.empty())
                top.push_back(l);
            else
                defs.at(active).lines.push_back(l);
        }
    }
    if (!active.empty())
        fail(defs.at(active).src, "INVALID_SUBCKT", "missing .ENDS");
    std::set<std::string> ids;
    std::vector<std::string> stack;
    // Validate every definition, including library definitions never instantiated.
    std::map<std::string, int> visited;
    std::function<void(const std::string &)> visit = [&](const std::string &name) {
        if (visited[name] == 1)
            fail(defs.at(name).src, "RECURSIVE_SUBCKT", name);
        if (visited[name] == 2)
            return;
        visited[name] = 1;
        std::set<std::string> local_ids;
        for (auto l : defs.at(name).lines) {
            l.text = freeze(l.text, net.parameters, l.source);
            auto t = tokens(l.text, l.source);
            if (!ident(t[0]) || !local_ids.insert(t[0]).second)
                fail(l.source, "DUPLICATE_INSTANCE", t[0]);
            auto k = kindof(t[0], l.source);
            if (k == "X") {
                if (t.size() < 3 || !defs.count(t.back()))
                    fail(l.source, "INVALID_SUBCKT", "unknown X definition");
                if (t.size() - 2 != defs.at(t.back()).ports.size())
                    fail(l.source, "INVALID_PORT_COUNT", t[0]);
                visit(t.back());
            } else {
                Primitive p;
                p.kind = k;
                p.id = t[0];
                p.source = l.source;
                if (k == "MATH" && l.text.find('=') != std::string::npos &&
                    tokens(l.text.substr(0, l.text.find('=')), l.source).size() == 2) {
                    p.args = {tokens(l.text.substr(0, l.text.find('=')), l.source)[1]};
                    p.expression = trim(l.text.substr(l.text.find('=') + 1));
                    if (p.expression.empty())
                        fail(l.source, "INVALID_NETLIST", "empty MATH expression");
                } else
                    p.options = options(t, 1, l.source, p.args);
                validate(p);
            }
        }
        visited[name] = 2;
    };
    for (const auto &[name, definition] : defs) {
        (void)definition;
        visit(name);
    }

    std::function<void(const std::vector<Line> &, const std::string &,
                       const std::map<std::string, std::string> &)>
        expand;
    expand = [&](const std::vector<Line> &lines, const std::string &path,
                 const std::map<std::string, std::string> &portmap) {
        for (auto l : lines) {
            auto original_line = l.text;
            l.text = freeze(l.text, net.parameters, l.source);
            auto t = tokens(l.text, l.source);
            if (!ident(t[0]))
                fail(l.source, "INVALID_IDENTIFIER", t[0]);
            auto kind = kindof(t[0], l.source);
            auto id = path.empty() ? t[0] : path + "/" + t[0];
            if (!ids.insert(id).second)
                fail(l.source, "DUPLICATE_INSTANCE", id);
            if (kind == "X") {
                if (t.size() < 3)
                    fail(l.source, "INVALID_SUBCKT", "X needs ports and definition");
                auto it = defs.find(t.back());
                if (it == defs.end())
                    fail(l.source, "INVALID_SUBCKT", "unknown definition " + t.back());
                if (std::find(stack.begin(), stack.end(), t.back()) != stack.end())
                    fail(l.source, "RECURSIVE_SUBCKT", t.back());
                if (t.size() - 2 != it->second.ports.size())
                    fail(l.source, "INVALID_PORT_COUNT", id);
                std::map<std::string, std::string> next;
                for (size_t i = 0; i < it->second.ports.size(); ++i)
                    next[it->second.ports[i]] = renamed(t[i + 1], path, portmap);
                stack.push_back(t.back());
                expand(it->second.lines, id, next);
                stack.pop_back();
                continue;
            }
            Primitive p;
            p.kind = kind;
            p.id = id;
            p.source = l.source;
            p.source.path = id;
            if (kind == "EVENT") {
                std::vector<std::string> unused;
                p.option_text = options(tokens(original_line, l.source), 1, l.source, unused);
            }
            if (kind == "MATH" && l.text.find('=') != std::string::npos &&
                tokens(l.text.substr(0, l.text.find('=')), l.source).size() == 2) {
                p.args.push_back(tokens(l.text.substr(0, l.text.find('=')), l.source)[1]);
                auto eq = l.text.find('=');
                p.expression = trim(l.text.substr(eq + 1));
                if (p.expression.empty())
                    fail(l.source, "INVALID_NETLIST", "empty MATH expression");
            } else
                p.options = options(t, 1, l.source, p.args);
            validate(p);
            for (size_t i = 0; i < p.args.size(); ++i) {
                if (kind == "SENSOR" && i == 1)
                    continue;
                auto &a = p.args[i];
                if (!a.empty() && a[0] == '(') {
                    auto group = tokens(a.substr(1, a.size() - 2), l.source);
                    if (group.size() != 2)
                        fail(l.source, "INVALID_PORT_COUNT", "winding needs two nodes");
                    a = "(" + renamed(group[0], path, portmap) + " " + renamed(group[1], path, portmap) + ")";
                } else
                    a = renamed(a, path, portmap);
            }
            for (auto &[k, v] : p.options)
                if (k == "SOURCE" || k == "SET" || k == "RESET" || k == "CANCEL" || k == "DELAY_INPUT")
                    v = renamed(v, path, portmap);
            p.expression = rename_expr(p.expression, path, portmap);
            net.primitives.push_back(std::move(p));
        }
    };
    expand(top, "", {});
    bool tran = false, save = false;
    for (auto l : sections["SIMULATION"]) {
        l.text = freeze(l.text, net.parameters, l.source);
        auto t = tokens(l.text, l.source);
        auto cmd = upper(t[0]);
        if (cmd == ".TRAN") {
            if (tran)
                fail(l.source, "INVALID_SIMULATION", "duplicate .TRAN");
            tran = true;
            std::vector<std::string> args;
            auto opts = options(t, 1, l.source, args);
            if (!args.empty())
                fail(l.source, "INVALID_SIMULATION", ".TRAN accepts named values");
            for (auto &[k, v] : opts) {
                try {
                    double x = fixed_value(v, net.parameters);
                    if (x <= 0)
                        throw std::runtime_error("time must be positive");
                    if (k == "T_END")
                        net.t_end = x;
                    else if (k == "SAVE_DT")
                        net.save_dt = x;
                    else
                        fail(l.source, "INVALID_SIMULATION", "unknown .TRAN option " + k);
                } catch (const std::exception &e) {
                    fail(l.source, "INVALID_SIMULATION", e.what());
                }
            }
        } else if (cmd == ".SAVE") {
            if (save)
                fail(l.source, "INVALID_SIMULATION", "duplicate .SAVE");
            save = true;
            net.channels = std::vector<std::string>(t.begin() + 1, t.end());
        } else
            fail(l.source, "INVALID_SIMULATION", "unknown simulation directive");
    }
    net.layout_json = trim(net.layout_json);
    if (net.layout_json.empty())
        net.layout_json = "{}";
    if (!net.layout_json.empty())
        try {
            Json{net.layout_json}.run();
        } catch (const std::exception &e) {
            fail(layout_source, "INVALID_LAYOUT", e.what());
        }
    std::sort(net.primitives.begin(), net.primitives.end(),
              [](const auto &a, const auto &b) { return a.id < b.id; });
    std::ostringstream canonical;
    for (const auto &[k, v] : net.parameters)
        canonical << "P " << k << "=" << number(v) << "\n";
    for (const auto &p : net.primitives) {
        canonical << p.kind << " " << p.id;
        for (const auto &a : p.args)
            canonical << " " << a;
        for (const auto &[k, v] : p.options)
            canonical << " " << k << "=" << v;
        canonical << " =" << p.expression << "\n";
    }
    if (net.t_end)
        canonical << "T " << number(*net.t_end) << "\n";
    if (net.save_dt)
        canonical << "D " << number(*net.save_dt) << "\n";
    if (net.channels) {
        canonical << "SAVE";
        for (auto &c : *net.channels)
            canonical << " " << c;
        canonical << "\n";
    }
    net.filename = filename;
    net.canonical = canonical.str();
    net.parse_seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    return net;
}
} // namespace pulse
