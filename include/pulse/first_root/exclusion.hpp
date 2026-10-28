#pragma once
#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <stdexcept>
#include <vector>
namespace rfr {
// Outward enclosure for IEEE-754 binary64 basic operations, gradual underflow,
// round-to-nearest, no reassociation/FMA. No libm transcendental is used in certificates.
inline double up(double x) {
    if (std::isnan(x))
        return INFINITY;
    if (x == INFINITY)
        return x;
    if (x == 0)
        return std::numeric_limits<double>::denorm_min();
    auto b = std::bit_cast<uint64_t>(x);
    return std::bit_cast<double>(x > 0 ? b + 1 : b - 1);
}
inline double down(double x) { return -up(-x); }
struct I {
    double lo = 0, hi = 0;
    I() = default;
    I(double x) : lo(x), hi(x) {}
    I(double l, double h) : lo(l), hi(h) {}
    bool zero() const { return lo == 0 && hi == 0; }
    bool finite() const { return std::isfinite(lo) && std::isfinite(hi) && lo <= hi; }
    double absmax() const { return std::max(std::abs(lo), std::abs(hi)); }
};
inline I whole() { return {-INFINITY, INFINITY}; }
inline I operator+(I a, I b) {
    if (a.zero())
        return b;
    if (b.zero())
        return a;
    double l = a.lo + b.lo, h = a.hi + b.hi;
    if (std::isnan(l) || std::isnan(h))
        return whole();
    return {down(l), up(h)};
}
inline I operator-(I a, I b) { return a + I(-b.hi, -b.lo); }
inline I operator*(I a, I b) {
    if (a.zero() || b.zero())
        return I(0);
    double t[] = {a.lo * b.lo, a.lo * b.hi, a.hi * b.lo, a.hi * b.hi};
    for (double x : t)
        if (std::isnan(x))
            return whole();
    return {down(*std::min_element(t, t + 4)), up(*std::max_element(t, t + 4))};
}
inline I operator/(I a, I b) {
    if (b.lo <= 0 && b.hi >= 0)
        return whole();
    return a * I(down(1 / b.hi), up(1 / b.lo));
}
inline double add_up(double a, double b) { return (a == 0 && b == 0) ? 0 : up(a + b); }
inline double mul_up(double a, double b) { return (a == 0 || b == 0) ? 0 : up(a * b); }
// exp(q) <= (1-q/64)^-64 after exact dyadic scaling to q<=1.
inline double exp_upper(double q) {
    if (q <= 0)
        return 1;
    if (q > 700 || !std::isfinite(q))
        return INFINITY;
    int scale = 0;
    while (q > 1) {
        q *= .5;
        ++scale;
    }
    I v = I(1) / (I(1) - I(q) / I(64));
    for (int k = 0; k < 6 + scale; ++k)
        v = v * v;
    return v.hi;
}
using Vec = std::vector<double>;
using IV = std::vector<I>;
struct Mode {
    int n = 0, m = 0;
    uint64_t id = 0, generation = 0;
    Vec A, b, C, d; // finalize with prepare(), then immutable
    double mu = 0, norm = 0;
    Vec cnorm;
    void prepare();
};
struct Input {
    Vec x, y, radius;
    double h = 0;
}; // y is supplied by unchanged propagator, used only by baseline.
enum class Status {
    NO_EVENT_CERTIFIED = 0,
    POSSIBLE_EVENT = 1,
    UNRESOLVED = 2,
    BASELINE_SKIP_UNCERTIFIED = 3
};
struct GuardResult {
    Status status = Status::UNRESOLVED;
    I enclosure = whole();
    double remainder = INFINITY;
    int level = 3;
};
struct Result {
    std::vector<GuardResult> guards;
};
struct Counts {
    uint64_t matvec = 0, rowvec = 0, dots = 0, l1 = 0, l2 = 0, l3 = 0, cache_hits = 0, cache_misses = 0,
             bytes = 0;
};
struct CacheEntry {
    int p = 0, n = 0, m = 0;
    std::vector<I> rows;
    uint64_t bytes() const { return rows.size() * sizeof(I); }
};
struct Cache {
    std::map<std::pair<uint64_t, int>, CacheEntry> entries;
    CacheEntry &get(const Mode &, int, Counts *);
    void clear() { entries.clear(); }
    void invalidate(const Mode &m, int p) { entries.erase({m.generation, p}); }
    uint64_t bytes() const {
        uint64_t v = 0;
        for (auto &[k, e] : entries)
            v += e.bytes();
        return v;
    }
};
IV velocity(const Mode &, const Input &);
std::vector<IV> coefficients(const Mode &, const Input &, int, int, Cache *, Counts * = nullptr,
                             Vec * = nullptr);
// method 0 direct unscaled derivatives; 1 cached mode rows; 2 normalized recurrence.
std::vector<Vec> coefficients_fp(const Mode &, const Input &, int, int, Cache * = nullptr);
I horner(const IV &);
I bernstein(const IV &);
Result cheap_bounds(const Mode &, const Input &, Counts * = nullptr);
Result detect(const Mode &, const Input &, int algorithm, int p, Cache &, Counts * = nullptr,
              int envelope = 1);
double checksum(const Result &);
} // namespace rfr
