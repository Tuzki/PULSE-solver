#include "first_root.hpp"
#include <bit>
#include <ctime>
#include <functional>
#include <numeric>
namespace fri {
using namespace rfr;
const char *name(Status s) {
    switch (s) {
    case Status::FOUND_CERTIFIED:
        return "FOUND_CERTIFIED";
    case Status::FOUND_NUMERICAL:
        return "FOUND_NUMERICAL";
    case Status::FOUND_ENGINEERING:
        return "FOUND_ENGINEERING";
    case Status::NO_EVENT_CERTIFIED:
        return "NO_EVENT_CERTIFIED";
    case Status::UNRESOLVED:
        return "UNRESOLVED";
    default:
        return "UNSUPPORTED";
    }
}
size_t ModelCache::bytes() const {
    size_t b = 0;
    for (auto &[k, m] : modes)
        b += 8 * (m.A.size() + m.b.size() + m.C.size() + m.d.size() + m.cnorm.size());
    return b;
}
Mode &ModelCache::get(const Mode &m) {
    auto it = modes.find(m.generation);
    if (it != modes.end()) {
        ++hits;
        return it->second;
    }
    ++misses;
    size_t need = 8 * (m.A.size() + m.b.size() + m.C.size() + m.d.size() + m.cnorm.size());
    if (need > capacity)
        throw std::runtime_error("MODE_CACHE_CAPACITY");
    while (bytes() + need > capacity && !modes.empty()) {
        modes.erase(modes.begin());
        ++evictions;
    }
    Mode c = m;
    c.prepare();
    c.generation = m.generation;
    return modes.emplace(m.generation, std::move(c)).first->second;
}
static I dot(const double *c, const IV &x) {
    I v;
    for (size_t i = 0; i < x.size(); ++i)
        if (c[i] != 0)
            v = v + I(c[i]) * x[i];
    return v;
}
static IV mv(const Mode &m, const IV &x, Statistics &s) {
    ++s.matvecs;
    IV v(m.n);
    for (int i = 0; i < m.n; ++i)
        for (int j = 0; j < m.n; ++j)
            if (m.A[i * m.n + j] != 0)
                v[i] = v[i] + I(m.A[i * m.n + j]) * x[j];
    return v;
}
static double norm(const IV &v) {
    double x = 0;
    for (I a : v)
        x = std::max(x, a.absmax());
    return x;
}
static double middle(I x) { return x.lo * .5 + x.hi * .5; }
static I isqrt(I x) {
    if (x.lo < 0 || !x.finite())
        return whole();
    return {std::max(0., down(std::sqrt(x.lo))), up(std::sqrt(x.hi))};
}
// Portable bounded exact-dyadic shortcut. Overflow disables the shortcut;
// interval root isolation remains available. No compiler-specific integer ABI.
struct Dy {
    int64_t v = 0;
    int e = 0;
    bool ok = true;
    Dy() = default;
    Dy(double d) {
        if (!std::isfinite(d)) {
            ok = false;
            return;
        }
        auto z = std::bit_cast<uint64_t>(d);
        int f = int((z >> 52) & 2047);
        v = int64_t((z & ((1ULL << 52) - 1)) | (f ? 1ULL << 52 : 0));
        e = f ? f - 1023 - 52 : -1074;
        if (z >> 63)
            v = -v;
        trim();
    }
    void trim() {
        if (v == 0) {
            e = 0;
            return;
        }
        while (v % 2 == 0) {
            v /= 2;
            ++e;
        }
    }
};
static constexpr int64_t dy_limit = int64_t(1) << 60;
static bool dy_mul(int64_t a, int64_t b, int64_t &out) {
    if (a > dy_limit || a < -dy_limit || b > dy_limit || b < -dy_limit)
        return false;
    auto aa = uint64_t(a < 0 ? -a : a), bb = uint64_t(b < 0 ? -b : b);
    if (bb && aa > uint64_t(dy_limit) / bb)
        return false;
    out = a * b;
    return true;
}
static Dy operator+(Dy a, Dy b) {
    if (!a.ok || !b.ok) {
        a.ok = false;
        return a;
    }
    if (a.v == 0)
        return b;
    if (b.v == 0)
        return a;
    int e = std::min(a.e, b.e), sa = a.e - e, sb = b.e - e;
    int64_t av = 0, bv = 0;
    if (sa > 60 || sb > 60 || !dy_mul(a.v, int64_t(1) << sa, av) || !dy_mul(b.v, int64_t(1) << sb, bv)) {
        a.ok = false;
        return a;
    }
    a.v = av + bv;
    if (a.v > dy_limit || a.v < -dy_limit) {
        a.ok = false;
        return a;
    }
    a.e = e;
    a.trim();
    return a;
}
static Dy operator*(Dy a, Dy b) {
    int64_t v = 0;
    if (!a.ok || !b.ok || !dy_mul(a.v, b.v, v)) {
        a.ok = false;
        return a;
    }
    a.v = v;
    a.e += b.e;
    a.trim();
    return a;
}
static Dy half(Dy a) {
    --a.e;
    return a;
}
struct Analytic {
    bool valid = false, scalar = false, real = false;
    I alpha, w;
    IV eq, z, nz;
    // Real distinct eigenvalues: x = eq + 0.5*(p*exp(lp*t) + q*exp(lm*t)).
    IV p, q;
    I lp, lm;
};
struct NodeData {
    I g, der;
    int variation = -2;
};
struct Context {
    const Mode &m;
    const Input &in;
    Options o;
    Statistics s;
    IV initial;
    Analytic an;
    std::map<double, IV> points;
    double horizon, tol;
    int guard = 0;
    double current_right = NAN;
    int current_depth = 0;
    int current_guard = 0;
    std::string failure;
    using Clock = std::chrono::steady_clock;
    double now() { return std::chrono::duration<double>(Clock::now().time_since_epoch()).count(); }
    Context(const Mode &mm, const Input &ii, const Options &oo) : m(mm), in(ii), o(oo) {
        horizon = std::min(ii.h, oo.scheduled);
        tol = std::max(oo.abs_tol, oo.rel_tol * horizon);
        initial.resize(m.n);
        for (int i = 0; i < m.n; ++i) {
            double r = ii.radius.empty() ? 0 : ii.radius[i];
            initial[i] = r ? I(down(ii.x[i] - r), up(ii.x[i] + r)) : I(ii.x[i]);
        }
        points.emplace(0, initial);
        setup();
    }
    void setup() {
        if (m.n == 1) {
            an.valid = true;
            an.scalar = true;
            if (m.A[0] != 0)
                an.eq = {I(-m.b[0]) / I(m.A[0])};
            return;
        }
        if (m.n != 2)
            return;
        I a(m.A[0]), b(m.A[1]), c(m.A[2]), d(m.A[3]);
        I det = a * d - b * c;
        an.alpha = (I(0) - a - d) / I(2);
        I w2 = det - an.alpha * an.alpha;
        if (det.lo <= 0 || det.hi <= 0)
            return;
        if (w2.hi < 0) {
            // Overdamped real distinct eigenvalues.  Use the stable
            // two-exponential form; cosh/sinh overflows for the stiff DCM modes.
            an.real = true;
            an.w = isqrt(I(-w2.hi, -w2.lo));
        } else if (w2.lo > 0) {
            an.w = isqrt(w2);
        } else {
            return;
        }
        if (an.w.lo <= 0)
            return;
        an.eq = {(b * I(m.b[1]) - d * I(m.b[0])) / det, (c * I(m.b[0]) - a * I(m.b[1])) / det};
        an.z = {initial[0] - an.eq[0], initial[1] - an.eq[1]};
        an.nz = {(a + an.alpha) * an.z[0] + b * an.z[1], c * an.z[0] + (d + an.alpha) * an.z[1]};
        if (an.real) {
            an.p = {an.z[0] + an.nz[0] / an.w, an.z[1] + an.nz[1] / an.w};
            an.q = {an.z[0] - an.nz[0] / an.w, an.z[1] - an.nz[1] / an.w};
            an.lp = I(0) - an.alpha + an.w;
            an.lm = I(0) - an.alpha - an.w;
        }
        an.valid = true;
    }
    struct ScalarFlow {
        int idx = -1;
        double a = 0, b = 0, c = 0, d = 0;
    };
    bool scalar_flow(ScalarFlow &f) const {
        int idx = -1, count = 0;
        for (int i = 0; i < m.n; ++i)
            if (m.C[guard * m.n + i] != 0) {
                idx = i;
                ++count;
            }
        if (count != 1)
            return false;
        for (int j = 0; j < m.n; ++j)
            if (j != idx && m.A[idx * m.n + j] != 0)
                return false;
        f.idx = idx;
        f.a = m.A[idx * m.n + idx];
        f.b = m.b[idx];
        f.c = m.C[guard * m.n + idx];
        f.d = m.d[guard];
        return true;
    }
    I scalar_value(const ScalarFlow &f, I t) const {
        I x;
        if (f.a == 0)
            x = initial[f.idx] + I(f.b) * t;
        else {
            I eq = I(-f.b) / I(f.a);
            x = eq + exp_interval(I(f.a) * t) * (initial[f.idx] - eq);
        }
        return I(f.c) * x + I(f.d);
    }
    I scalar_derivative(const ScalarFlow &f, I t) const {
        I x;
        if (f.a == 0)
            x = initial[f.idx] + I(f.b) * t;
        else {
            I eq = I(-f.b) / I(f.a);
            x = eq + exp_interval(I(f.a) * t) * (initial[f.idx] - eq);
        }
        return I(f.c) * (I(f.a) * x + I(f.b));
    }
    IV analytic_state(I t) {
        if (an.scalar) {
            I a(m.A[0]);
            if (a.zero())
                return {initial[0] + I(m.b[0]) * t};
            return {an.eq[0] + exp_interval(a * t) * (initial[0] - an.eq[0])};
        }
        if (an.real) {
            I e1 = exp_interval(an.lp * t), e2 = exp_interval(an.lm * t);
            return {an.eq[0] + (an.p[0] * e1 + an.q[0] * e2) / I(2),
                    an.eq[1] + (an.p[1] * e1 + an.q[1] * e2) / I(2)};
        }
        I co = cos_interval(an.w * t), si = sin_interval(an.w * t), ex = exp_interval((I(0) - an.alpha) * t);
        return {an.eq[0] + ex * (an.z[0] * co + an.nz[0] / an.w * si),
                an.eq[1] + ex * (an.z[1] * co + an.nz[1] / an.w * si)};
    }
    const IV &state(double t) {
        auto it = points.find(t);
        if (it != points.end())
            return it->second;
        size_t need = (points.size() + 1) * size_t(m.n) * sizeof(I) +
                      size_t(o.max_depth + 1) * size_t(m.n + o.p + 1) * sizeof(I);
        if (need > o.memory_budget) {
            failure = "QUERY_MEMORY_BUDGET";
            static const IV empty;
            return empty;
        }
        IV x;
        bool diagonal = true;
        for (int a = 0; a < m.n; ++a)
            for (int b = 0; b < m.n; ++b)
                if (a != b && m.A[a * m.n + b] != 0)
                    diagonal = false;
        if (diagonal && !an.valid) {
            x.resize(m.n);
            for (int k = 0; k < m.n; ++k) {
                I a(m.A[k * m.n + k]);
                if (a.zero())
                    x[k] = initial[k] + I(m.b[k]) * I(t);
                else {
                    I eq = I(-m.b[k]) / a;
                    x[k] = eq + exp_interval(a * I(t)) * (initial[k] - eq);
                }
            }
            ++s.state_calls;
        } else if (an.valid) {
            x = analytic_state(I(t));
            ++s.state_calls;
        } else {
            x = exponential_action(m, initial, t, &s, 4096);
        }
        s.peak_bytes = std::max<uint64_t>(s.peak_bytes, need);
        return points.emplace(t, std::move(x)).first->second;
    }
    int exact_sign(double t) { // exact point-state proof for degree <=2 nilpotent affine flows
        if (!in.radius.empty() &&
            std::any_of(in.radius.begin(), in.radius.end(), [](double z) { return z != 0; }))
            return 2;
        std::vector<Dy> x(m.n), v(m.n), av(m.n), aav(m.n);
        for (int i = 0; i < m.n; ++i)
            x[i] = Dy(in.x[i]);
        for (int i = 0; i < m.n; ++i) {
            v[i] = Dy(m.b[i]);
            for (int j = 0; j < m.n; ++j)
                v[i] = v[i] + Dy(m.A[i * m.n + j]) * x[j];
        }
        if (t != 0) {
            for (int i = 0; i < m.n; ++i)
                for (int j = 0; j < m.n; ++j)
                    av[i] = av[i] + Dy(m.A[i * m.n + j]) * v[j];
            for (int i = 0; i < m.n; ++i)
                for (int j = 0; j < m.n; ++j)
                    aav[i] = aav[i] + Dy(m.A[i * m.n + j]) * av[j];
            for (auto z : aav)
                if (!z.ok || z.v != 0)
                    return 2;
            for (int i = 0; i < m.n; ++i)
                x[i] = x[i] + v[i] * Dy(t) + half(av[i] * Dy(t) * Dy(t));
        }
        Dy g(m.d[guard]);
        for (int i = 0; i < m.n; ++i)
            g = g + Dy(m.C[guard * m.n + i]) * x[i];
        return g.ok ? (g.v > 0 ? 1 : (g.v < 0 ? -1 : 0)) : 2;
    }
    I direct_guard_taylor(double t, int N = 52) {
        const int n = int(m.n);
        IV terms(n + 1), next(n + 1);
        for (int j = 0; j < n; ++j) terms[j] = initial[j];
        terms[n] = I(1);
        I ans(0), tt(t);
        for (int k = 0; k <= N; ++k) {
            if (k == 0) ans = ans + I(m.d[guard]);
            for (int j = 0; j < n; ++j)
                if (m.C[guard * n + j] != 0)
                    ans = ans + I(m.C[guard * n + j]) * terms[j];
            if (k == N) break;
            next.assign(n + 1, I(0));
            for (int i = 0; i < n; ++i) {
                for (int j = 0; j < n; ++j)
                    if (m.A[i * n + j] != 0)
                        next[i] = next[i] + I(m.A[i * n + j]) * terms[j];
                next[i] = next[i] + I(m.b[i]) * terms[n];
                next[i] = next[i] * tt / I(k + 1);
            }
            terms.swap(next);
        }
        double z = 0, cn = std::abs(m.d[guard]);
        for (int i = 0; i < n; ++i) {
            double row = 0;
            for (int j = 0; j < n; ++j)
                row = add_up(row, mul_up(std::abs(m.A[i * n + j]), std::abs(t)));
            row = add_up(row, mul_up(std::abs(m.b[i]), std::abs(t)));
            z = std::max(z, row);
            cn = add_up(cn, std::abs(m.C[guard * n + i]));
        }
        double snorm = 1;
        for (int j = 0; j < n; ++j) snorm = std::max(snorm, initial[j].absmax());
        I p(1);
        for (int k = 1; k <= N + 1; ++k) p = p * I(z) / I(k);
        I tail = p * I(exp_upper(z)) * I(cn) * I(snorm);
        if (!std::isfinite(tail.hi) || !std::isfinite(tail.lo)) return whole();
        return ans + I(-tail.hi, tail.hi);
    }
    I point(double t) {
        ++s.evaluations;
        ScalarFlow sf;
        I normal;
        if (scalar_flow(sf))
            normal = scalar_value(sf, I(t));
        else {
            const auto &x = state(t);
            normal = x.empty() ? whole() : dot(&m.C[guard * m.n], x) + I(m.d[guard]);
        }
        if (normal.finite() && !(normal.lo <= 0 && normal.hi >= 0)) return normal;
        I direct = direct_guard_taylor(t);
        if (!direct.finite()) return normal;
        I both(std::max(normal.lo, direct.lo), std::min(normal.hi, direct.hi));
        return both.lo <= both.hi ? both : whole();
    }
    int sign(I a, double t) {
        if (a.lo > 0)
            return 1;
        if (a.hi < 0)
            return -1;
        return exact_sign(t);
    }
    NodeData bounds(double l, double r, int algorithm) {
        double start = o.profile ? now() : 0;
        NodeData out;
        I ti(l, r);
        ScalarFlow sf;
        if (scalar_flow(sf)) {
            ++s.evaluations;
            out.g = scalar_value(sf, ti);
            out.der = scalar_derivative(sf, ti);
            return out;
        }
        if (algorithm == 0) {
            ++s.evaluations;
            if (an.scalar) {
                auto xs = analytic_state(ti);
                out.g = dot(&m.C[guard * m.n], xs) + I(m.d[guard]);
                out.der = I(m.C[guard]) * (I(m.A[0]) * xs[0] + I(m.b[0]));
            } else if (an.real) {
                I ap = dot(&m.C[guard * m.n], an.p), aq = dot(&m.C[guard * m.n], an.q),
                  off = dot(&m.C[guard * m.n], an.eq) + I(m.d[guard]);
                I e1 = exp_interval(an.lp * ti), e2 = exp_interval(an.lm * ti);
                out.g = off + (ap * e1 + aq * e2) / I(2);
                out.der = (ap * an.lp * e1 + aq * an.lm * e2) / I(2);
            } else {
                I B = dot(&m.C[guard * m.n], an.z), C = dot(&m.C[guard * m.n], an.nz) / an.w,
                  off = dot(&m.C[guard * m.n], an.eq) + I(m.d[guard]);
                I cs = cos_interval(an.w * ti), sn = sin_interval(an.w * ti),
                  ex = exp_interval((I(0) - an.alpha) * ti);
                out.g = off + ex * (B * cs + C * sn);
                out.der = ex * ((C * an.w - an.alpha * B) * cs - (B * an.w + an.alpha * C) * sn);
            }
        } else {
            const IV &x = state(l);
            if (x.empty())
                return {whole(), whole()};
            I duration = I(r) - I(l);
            double dt = duration.hi;
            int p = algorithm == 1 ? o.p : 4;
            double gen = o.profile ? now() : 0;
            IV v = mv(m, x, s);
            for (int i = 0; i < m.n; ++i)
                v[i] = v[i] + I(m.b[i]);
            IV w = v;
            IV q(p + 1);
            q[0] = dot(&m.C[guard * m.n], x) + I(m.d[guard]);
            double growth = exp_upper(mul_up(std::max(m.mu, 0.), dt));
            for (int k = 1; k <= p + 1; ++k) {
                for (I &a : w)
                    a = a * duration / I(k);
                if (k <= p)
                    q[k] = dot(&m.C[guard * m.n], w);
                if (k <= p)
                    w = mv(m, w, s);
            }
            double e = mul_up(mul_up(m.cnorm[guard], norm(w)), growth);
            double ed = dt > 0 ? mul_up(e, (I(p + 1) / I(dt)).hi) : INFINITY;
            if (o.profile)
                s.taylor_s += now() - gen;
            out.g = horner(q) + I(-e, e);
            IV dq(p);
            for (int k = 1; k <= p; ++k)
                dq[k - 1] = q[k] * I(k) / duration;
            out.der = horner(dq) + I(-ed, ed);
            if (algorithm == 1) {
                double tm = o.profile ? now() : 0;
                auto trans = ca_transform(q);
                out.variation = sign_variations(trans);
                ++s.ca_transforms;
                if (out.variation == 0)
                    ++s.ca_zero;
                else if (out.variation == 1)
                    ++s.ca_one;
                else if (out.variation < 0)
                    ++s.ca_ambiguous;
                // Descartes candidates are never an absence certificate for the original function.
                if (out.g.lo <= 0 && out.g.hi >= 0)
                    out.g = bernstein(q) + I(-e, e);
                if (o.profile)
                    s.transform_s += now() - tm;
            }
        }
        if (o.profile)
            s.bounds_s += now() - start;
        return out;
    }
    Result unresolved(double l, const std::string &why) {
        Result r;
        r.status = Status::UNRESOLVED;
        r.reason = why;
        r.unresolved_frontier = l;
        r.failed_bracket = I(l, std::isfinite(current_right) ? std::max(l, current_right) : l);
        r.failed_guard = current_guard;
        r.failed_depth = current_depth;
        r.failed_nodes = s.nodes;
        r.stats = s;
        return r;
    }
    Result refine(double l, double r, I der, int direction, int algorithm) {
        double tm = o.profile ? now() : 0;
        double orig = l;
        int it = 0;
        while (r - l > tol && it++ < o.max_iterations) {
            ++s.iterations;
            double mid = std::midpoint(l, r);
            if (it == 1 && algorithm == 0 && !an.scalar && !an.real && m.d[guard] == 0 &&
                std::all_of(m.b.begin(), m.b.end(), [](double z) { return z == 0; })) {
                I B = dot(&m.C[guard * m.n], an.z), C = dot(&m.C[guard * m.n], an.nz) / an.w;
                double w = middle(an.w), phase = std::atan2(-middle(B), middle(C)), pi = std::acos(-1.);
                double k = std::ceil((l * w - phase) / pi), candidate = (phase + k * pi) / w;
                if (candidate > l && candidate < r)
                    mid = candidate;
            }
            if (mid == l || mid == r)
                break;
            I g = point(mid);
            if (exact_sign(mid) == 0) {
                l = r = mid;
                break;
            }
            I ni = I(mid) - g / der;
            double nl = std::max(l, ni.lo), nr = std::min(r, ni.hi);
            if (nl > nr)
                return unresolved(orig, "INTERVAL_NEWTON_EMPTY_INTERNAL_CHECK");
            if (nr - nl < .8 * (r - l)) {
                l = nl;
                r = nr;
                auto bb = bounds(l, r, algorithm);
                if (bb.der.lo > 0 || bb.der.hi < 0)
                    der = bb.der;
                continue;
            }
            int sg = sign(g, mid);
            if (sg == 2)
                break;
            if (sg * direction > 0)
                r = mid;
            else if (sg * direction < 0)
                l = mid;
            else {
                l = r = mid;
                break;
            }
        }
        if (o.profile)
            s.refinement_s += now() - tm;
        if (r - l > tol)
            return unresolved(orig, "ROOT_PRECISION_FLOOR_OR_ITERATION_LIMIT");
        Result z;
        z.status = Status::FOUND_CERTIFIED;
        z.event_id = guard;
        z.direction = direction;
        z.bracket = I(l, r);
        z.time = std::midpoint(l, r);
        z.residual = bounds(l, r, algorithm).g;
        z.reason = "chronological exclusion + strict original derivative + IVT + interval Newton enclosure";
        return z;
    }
    Result search(double l, double r, int depth, int algorithm) {
        if (++s.nodes > uint64_t(o.max_nodes))
            return unresolved(l, "NODE_BUDGET");
        if (!failure.empty())
            return unresolved(l, failure);
        NodeData b = bounds(l, r, algorithm);
        if (!failure.empty())
            return unresolved(l, failure);
        if (b.g.finite() && (b.g.lo > 0 || b.g.hi < 0)) {
            Result z;
            z.status = Status::NO_EVENT_CERTIFIED;
            return z;
        }
        int dr = b.der.lo > 0 ? 1 : (b.der.hi < 0 ? -1 : 0);
        int want = o.directions.empty() ? 1 : o.directions[guard];
        if (algorithm == 1 && b.variation > 1)
            dr = 0; // CA requires further polynomial isolation before accepting an interior candidate.
        if (dr) {
            if (want != 0 && want != dr) {
                Result z;
                z.status = Status::NO_EVENT_CERTIFIED;
                return z;
            }
            I gl = point(l), gr = point(r);
            int sl = sign(gl, l), sr = sign(gr, r);
            if (sl != 2)
                sl *= dr;
            if (sr != 2)
                sr *= dr;
            if (l == 0 && o.include_left && sl == 0) {
                Result z;
                z.status = Status::FOUND_CERTIFIED;
                z.event_id = guard;
                z.direction = dr;
                z.time = 0;
                z.bracket = I(0);
                z.residual = gl;
                z.reason = "exact left boundary + strict original derivative; stabilization contract";
                return z;
            }
            if ((sl != 2 && sl >= 0) || (sr != 2 && sr < 0)) {
                Result z;
                z.status = Status::NO_EVENT_CERTIFIED;
                return z;
            }
            if (sl == -1 && (sr == 1 || sr == 0)) {
                if (sr == 0) {
                    Result z;
                    z.status = Status::FOUND_CERTIFIED;
                    z.event_id = guard;
                    z.direction = dr;
                    z.time = r;
                    z.bracket = I(r);
                    z.residual = gr;
                    z.reason = "exact right boundary + strict monotonicity";
                    return z;
                }
                return refine(l, r, b.der, dr, algorithm);
            }
        }
        if (depth >= o.max_depth || r - l <= std::max(tol * .25, std::numeric_limits<double>::denorm_min()))
            return unresolved(l, "NONMONOTONE_OR_BOUNDARY_AMBIGUITY");
        double mid = std::midpoint(l, r);
        if (algorithm == 0 && !an.scalar) {
            I B = dot(&m.C[guard * m.n], an.z), C = dot(&m.C[guard * m.n], an.nz) / an.w;
            double u = middle(C * an.w - an.alpha * B), v = middle(I(0) - B * an.w - an.alpha * C),
                   w = middle(an.w);
            double phase = std::atan2(-u, v);
            double k = std::nearbyint((mid * w - phase) / std::acos(-1.));
            double critical = (phase + k * std::acos(-1.)) / w;
            if (critical > l + .15 * (r - l) && critical < r - .15 * (r - l))
                mid = critical;
        }
        if (mid == l || mid == r)
            return unresolved(l, "TIME_REPRESENTATION_LIMIT");
        ++s.subdivisions;
        current_right = r;
        current_depth = depth;
        current_guard = guard;
        auto left = search(l, mid, depth + 1, algorithm);
        if (left.status != Status::NO_EVENT_CERTIFIED)
            return left;
        return search(mid, r, depth + 1, algorithm);
    }
    bool identical(int a, int b) {
        if ((o.directions.empty() ? 1 : o.directions[a]) != (o.directions.empty() ? 1 : o.directions[b]) ||
            m.d[a] != m.d[b])
            return false;
        bool same = true;
        for (int i = 0; i < m.n; ++i)
            if (m.C[a * m.n + i] != m.C[b * m.n + i])
                same = false;
        if (same)
            return true;
        int ia = -1, ib = -1;
        for (int i = 0; i < m.n; ++i) {
            if (m.C[a * m.n + i] != 0) {
                if (ia != -1)
                    return false;
                ia = i;
            }
            if (m.C[b * m.n + i] != 0) {
                if (ib != -1)
                    return false;
                ib = i;
            }
        }
        if (ia < 0 || ib < 0 || m.C[a * m.n + ia] != m.C[b * m.n + ib] || in.x[ia] != in.x[ib] ||
            m.b[ia] != m.b[ib] || m.A[ia * m.n + ia] != m.A[ib * m.n + ib])
            return false;
        if (!in.radius.empty() && (in.radius[ia] != 0 || in.radius[ib] != 0))
            return false;
        for (int j = 0; j < m.n; ++j)
            if ((j != ia && m.A[ia * m.n + j] != 0) || (j != ib && m.A[ib * m.n + j] != 0))
                return false;
        return true; // equal decoupled scalar IVPs prove simultaneous times, without an overlap tolerance.
    }
    Result run() {
        if (o.algorithm == 0 && !an.valid) {
            Result z;
            z.status = Status::UNSUPPORTED;
            z.reason = "analytic fast path requires scalar or provably underdamped nonsingular 2x2";
            return z;
        }
        if (horizon < 0 || !std::isfinite(horizon) || o.p < 2 || o.p > 32 || o.memory_budget < 1024 ||
            o.abs_tol < 0 || o.rel_tol < 0 || !std::isfinite(tol) || tol <= 0)
            return unresolved(0, "INVALID_OPTIONS_OR_MEMORY_BUDGET");
        if (horizon == 0 && !o.include_left) {
            Result z;
            z.status = Status::NO_EVENT_CERTIFIED;
            z.reason = "empty open-left window";
            return z;
        }
        int algorithm = o.algorithm == 3 ? (an.valid && (an.scalar || an.real) ? 0 : 2) : o.algorithm;
        std::vector<Result> roots;
        double frontier = INFINITY;
        int frontier_guard = 0;
        std::string why;
        std::vector<bool> skip(m.m, false);
        if (o.algorithm == 3) {
            double bt = o.profile ? now() : 0;
            Input ii = in;
            ii.h = horizon;
            auto z = cheap_bounds(m, ii);
            for (int j = 0; j < m.m; ++j)
                if (z.guards[j].status == rfr::Status::NO_EVENT_CERTIFIED) {
                    skip[j] = true;
                    ++s.l1_excluded;
                }
            if (o.profile)
                s.bounds_s += now() - bt;
        }
        for (guard = 0; guard < m.m; ++guard) {
            if (skip[guard])
                continue;
            bool duplicate = false;
            for (auto &v : roots)
                if (identical(guard, v.event_id)) {
                    v.simultaneous.push_back(guard);
                    duplicate = true;
                    break;
                }
            if (duplicate)
                continue;
            double end = horizon;
            for (auto &known : roots)
                end = std::min(end, known.bracket.hi);
            auto z = search(0, end, 0, algorithm);
            if (z.status == Status::UNRESOLVED) {
                if (z.unresolved_frontier <= frontier) {
                    frontier = z.unresolved_frontier;
                    frontier_guard = guard;
                }
                why = z.reason;
            } else if (z.status == Status::FOUND_CERTIFIED) {
                z.simultaneous = {guard};
                roots.push_back(z);
            }
        }
        if (roots.empty()) {
            if (std::isfinite(frontier)) {
                current_guard = frontier_guard;
                return unresolved(frontier, why);
            }
            Result z;
            z.status = Status::NO_EVENT_CERTIFIED;
            z.reason = "every guard chronologically excluded or wrong crossing direction";
            return z;
        }
        std::sort(roots.begin(), roots.end(), [](auto &a, auto &b) { return a.bracket.lo < b.bracket.lo; });
        auto best = roots.front();
        if (frontier <= best.bracket.hi) {
            current_guard = frontier_guard;
            return unresolved(frontier, "EARLIER_UNRESOLVED_PREFIX: " + why);
        }
        for (size_t i = 1; i < roots.size(); ++i) {
            if (roots[i].bracket.lo <= best.bracket.hi) {
                if (o.engineering_window > 0) {
                    // All overlapping roots have certified evidence.  Return a
                    // representative engineering first root only when every
                    // overlapping interval fits inside the fixed window and no
                    // earlier unresolved prefix exists.
                    double lo = best.bracket.lo, hi = best.bracket.hi;
                    for (size_t j = 1; j < roots.size(); ++j)
                        if (roots[j].bracket.lo <= best.bracket.hi)
                            hi = std::max(hi, roots[j].bracket.hi);
                    if (frontier <= lo || hi - lo > o.engineering_window)
                        return unresolved(best.bracket.lo, "ROOT_ORDER_UNRESOLVED_NOT_PROVEN_SIMULTANEOUS");
                    best.status = Status::FOUND_ENGINEERING;
                    best.engineering_representative = true;
                    best.time_uncertainty = hi - lo;
                    best.reason = "ENGINEERING_FIRST_ROOT: overlapping certified roots inside fixed window; "
                                  "representative is not proven strictly earliest";
                    if (an.valid)
                        best.state = analytic_state(best.bracket);
                    else {
                        best.state = state(best.bracket.lo);
                        if (!best.state.empty()) {
                            auto v = mv(m, best.state, s);
                            for (int k = 0; k < m.n; ++k)
                                v[k] = v[k] + I(m.b[k]);
                            I width = I(best.bracket.hi) - I(best.bracket.lo);
                            double change = mul_up(mul_up(norm(v), width.hi),
                                                   exp_upper(mul_up(std::max(m.mu, 0.), width.hi)));
                            for (auto &x : best.state)
                                x = x + I(-change, change);
                        }
                    }
                    return best;
                }
                return unresolved(best.bracket.lo, "ROOT_ORDER_UNRESOLVED_NOT_PROVEN_SIMULTANEOUS");
            }
            if (o.require_tick_order &&
                std::ceil(roots[i].bracket.lo / 0x1p-64) <= std::ceil(best.bracket.hi / 0x1p-64))
                return unresolved(best.bracket.lo, "TIME_QUANTIZATION_COLLISION");
        }
        if (an.valid)
            best.state = analytic_state(best.bracket);
        else {
            best.state = state(best.bracket.lo);
            if (!best.state.empty()) {
                auto v = mv(m, best.state, s);
                for (int k = 0; k < m.n; ++k)
                    v[k] = v[k] + I(m.b[k]);
                I width = I(best.bracket.hi) - I(best.bracket.lo);
                double change =
                    mul_up(mul_up(norm(v), width.hi), exp_upper(mul_up(std::max(m.mu, 0.), width.hi)));
                for (auto &x : best.state)
                    x = x + I(-change, change);
            }
        }
        return best;
    }
};
Result find_first_event(const Mode &m, const Input &i, const Options &o, ModelCache *cache) {
    auto wall = o.profile ? std::chrono::steady_clock::now() : std::chrono::steady_clock::time_point{};
    auto cpu = o.profile ? std::clock() : 0;
    Result z;
    if (m.generation == 0) {
        z.reason = "MODE_NOT_PREPARED";
        return z;
    }
    if (i.x.size() != size_t(m.n) || (!i.radius.empty() && i.radius.size() != size_t(m.n)) ||
        (!o.directions.empty() && o.directions.size() != size_t(m.m))) {
        z.reason = "INVALID_DIMENSIONS";
        return z;
    }
    for (int d : o.directions)
        if (d < -1 || d > 1) {
            z.reason = "INVALID_DIRECTION";
            return z;
        }
    for (double v : i.x)
        if (!std::isfinite(v)) {
            z.reason = "NONFINITE_INITIAL_STATE";
            return z;
        }
    for (double v : i.radius)
        if (v < 0 || !std::isfinite(v)) {
            z.reason = "INVALID_INITIAL_RADIUS";
            return z;
        }
    uint64_t ch = cache ? cache->hits : 0, cm = cache ? cache->misses : 0, ce = cache ? cache->evictions : 0;
    const Mode *mp = &m;
    double prep = 0;
    try {
        if (cache) {
            auto t = o.profile ? std::chrono::steady_clock::now() : std::chrono::steady_clock::time_point{};
            mp = &cache->get(m);
            if (o.profile)
                prep = std::chrono::duration<double>(std::chrono::steady_clock::now() - t).count();
        }
        Context ctx(*mp, i, o);
        z = ctx.run();
        z.stats = ctx.s;
    } catch (const std::exception &e) {
        z.reason = e.what();
        z.status = Status::UNRESOLVED;
    }
    z.stats.cache_prepare_s = prep;
    if (cache) {
        z.stats.cache_hits = cache->hits - ch;
        z.stats.cache_misses = cache->misses - cm;
        z.stats.cache_evictions = cache->evictions - ce;
        z.stats.peak_bytes += cache->bytes();
    }
    if (o.profile) {
        z.stats.isolation_s = std::chrono::duration<double>(std::chrono::steady_clock::now() - wall).count() -
                              z.stats.refinement_s;
        z.stats.cpu_s = double(std::clock() - cpu) / CLOCKS_PER_SEC;
    }
    return z;
}
} // namespace fri
