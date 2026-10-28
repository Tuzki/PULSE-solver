#include "pulse/core.hpp"
#include <bit>
#include <cmath>
#include <iomanip>
#include <sstream>
namespace pulse {
void require(bool b, int c, const std::string &s, const std::string &m, bool u, Source src) {
    if (!b)
        throw Error(c, s, m, u, std::move(src));
}
Time Time::from(double d) {
    require(std::isfinite(d) && d >= 0 && d < 0x1p62, 7, "TIME_RESOLUTION_UNRESOLVED",
            "time outside portable range", true);
    Time t;
    auto bits = std::bit_cast<uint64_t>(d);
    int exponent = int((bits >> 52) & 2047) - 1023;
    uint64_t m = (bits & 0xfffffffffffffULL) | ((bits >> 52 & 2047) ? 0x10000000000000ULL : 0);
    if (d == 0)
        return t;
    if ((bits >> 52 & 2047) == 0)
        exponent = -1022;
    int shift = exponent - 52 + 128;
    int trailing = std::countr_zero(m);
    m >>= trailing;
    shift += trailing;
    require(shift >= 0, 7, "TIME_RESOLUTION_UNRESOLVED", "binary64 deadline below 2^-128 time backend", true);
    for (int b = 0; b < 53; ++b)
        if ((m >> b) & 1) {
            int k = b + shift;
            if (k < 64)
                t.subtick |= uint64_t(1) << k;
            else if (k < 128)
                t.tick |= uint64_t(1) << (k - 64);
            else
                t.whole |= int64_t(1) << (k - 128);
        }
    return t;
}
double Time::seconds() const {
    return double(whole) + std::ldexp(double(tick), -64) + std::ldexp(double(subtick), -128);
}
std::string Time::canonical() const {
    std::ostringstream s;
    s << "T128:" << whole << ":" << std::hex << std::setw(16) << std::setfill('0') << tick << ":"
      << std::setw(16) << subtick;
    return s.str();
}
Time Time::decode(const std::string &s) {
    Time t;
    char c;
    std::istringstream in(s);
    std::string tag;
    std::getline(in, tag, ':');
    require(tag == "T128", 1, "INVALID_TIME", "unknown time encoding");
    in >> t.whole >> c >> std::hex >> t.tick >> c >> t.subtick;
    require(bool(in) && t.whole >= 0 && t.canonical() == s, 1, "INVALID_TIME",
            "malformed or noncanonical time encoding");
    return t;
}
Time Time::operator+(Time b) const {
    Time r;
    r.subtick = subtick + b.subtick;
    uint64_t carry = r.subtick < subtick;
    auto f = tick + b.tick;
    uint64_t carry2 = f < tick;
    r.tick = f + carry;
    carry2 += r.tick < f;
    require(b.whole <= INT64_MAX - whole - int64_t(carry2), 7, "TIME_OVERFLOW", "time overflow", true);
    r.whole = whole + b.whole + int64_t(carry2);
    return r;
}
Time Time::operator-(Time b) const {
    require(*this >= b, 7, "TIME_ORDER", "negative local duration", true);
    Time r;
    uint64_t borrow = subtick < b.subtick;
    r.subtick = subtick - b.subtick;
    uint64_t v = tick - b.tick;
    uint64_t borrow2 = tick < b.tick;
    r.tick = v - borrow;
    borrow2 += v < borrow;
    r.whole = whole - b.whole - int64_t(borrow2);
    return r;
}
Time Time::times(uint64_t k) const {
    Time out, term = *this;
    while (k) {
        if (k & 1)
            out = out + term;
        k >>= 1;
        if (k)
            term = term + term;
    }
    return out;
}
Time Time::ceil_tick() const {
    Time t = *this;
    if (t.subtick) {
        t.subtick = 0;
        t = t + Time{0, 1, 0};
    }
    return t;
}
std::string net_name(const std::string &s) {
    auto i = s.find("::");
    return i == std::string::npos ? s : s.substr(i + 2);
}
bool is_literal(const std::string &s) {
    if (s.empty())
        return false;
    return std::isdigit(static_cast<unsigned char>(s[0])) || s[0] == '.' || s[0] == '-' || s[0] == '+' ||
           s[0] == '{';
}
double number(const std::string &s) { return fixed_value(s); }
Vector reconstruct_physical(const Matrix &map, const Vector &z) {
    require(map.cols() == z.size(), 12, "STATE_MAP_SHAPE", "physical reconstruction dimension mismatch");
    Vector s = map * z;
    require(s.allFinite(), 7, "STATE_MAP_NONFINITE", "nonfinite physical reconstruction");
    return s;
}
Vector reduce_physical(const Matrix &map, const Vector &physical) {
    require(map.rows() == physical.size(), 12, "STATE_MAP_SHAPE", "physical reduction dimension mismatch");
    Eigen::FullPivLU<Matrix> lu(map);
    require(lu.rank() == map.cols(), 6, "STATE_MAP_NOT_UNIQUE", "local coordinate map is not injective");
    Vector z = lu.solve(physical);
    require((reconstruct_physical(map, z) - physical).norm() <= 1e-12 * std::max(1., physical.norm()), 10,
            "INCONSISTENT_MODE_TRANSITION", "physical state outside new coordinate image");
    return z;
}
Json diagnostic(const std::exception &e) {
    Json j = {{"message", e.what()}, {"code", 1}, {"subcode", "INVALID_NETLIST"}};
    if (auto p = dynamic_cast<const Error *>(&e)) {
        j["code"] = p->code;
        j["subcode"] = p->subcode;
        j["unresolved"] = p->unresolved;
        j["source"] = {{"file", p->source.file},
                       {"line", p->source.line},
                       {"column", p->source.column},
                       {"path", p->source.path}};
    } else if (auto p = dynamic_cast<const ParseError *>(&e)) {
        j["subcode"] = p->subcode;
        j["source"] = {{"file", p->source.file},
                       {"line", p->source.line},
                       {"column", p->source.column},
                       {"path", p->source.path}};
    }
    static const char *names[] = {"OK",
                                  "INVALID_NETLIST",
                                  "UNSUPPORTED_MODEL",
                                  "INCONSISTENT_INITIAL_STATE",
                                  "INVALID_PWA_CURVE",
                                  "PWA_OUT_OF_RANGE",
                                  "MODEL_SINGULAR",
                                  "NUMERICAL_ERROR",
                                  "EVENT_ROOT_FAILURE",
                                  "MODE_STABILIZATION_FAILURE",
                                  "PHYSICAL_CONSTRAINT_VIOLATION",
                                  "OUTPUT_ERROR",
                                  "INTERNAL_ERROR"};
    int c = j["code"];
    j["top_level_error"] = c >= 0 && c <= 12 ? names[c] : "INTERNAL_ERROR";
    return j;
}
} // namespace pulse
