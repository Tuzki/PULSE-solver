#include "exclusion.hpp"
#include <array>
#include <atomic>
namespace rfr {
void Mode::prepare() {
    if (n <= 0 || m <= 0 || A.size() != size_t(n * n) || C.size() != size_t(m * n) || b.size() != size_t(n) ||
        d.size() != size_t(m))
        throw std::runtime_error("invalid dimensions");
    for (auto *v : {&A, &b, &C, &d})
        for (double z : *v)
            if (!std::isfinite(z))
                throw std::runtime_error("nonfinite mode input");
    norm = 0;
    mu = -INFINITY;
    cnorm.assign(m, 0);
    for (int i = 0; i < n; ++i) {
        I v(A[i * n + i]);
        double s = 0;
        for (int j = 0; j < n; ++j) {
            s = add_up(s, std::abs(A[i * n + j]));
            if (i != j)
                v = v + I(std::abs(A[i * n + j]));
        }
        norm = std::max(norm, s);
        mu = std::max(mu, v.hi);
    }
    for (int j = 0; j < m; ++j)
        for (int k = 0; k < n; ++k)
            cnorm[j] = add_up(cnorm[j], std::abs(C[j * n + k]));
    static std::atomic<uint64_t> next{1};
    generation = next.fetch_add(1);
    if (!generation)
        throw std::runtime_error("mode generation overflow");
}
static IV mv(const Mode &m, const IV &x, Counts *c) {
    IV y(m.n);
    for (int i = 0; i < m.n; ++i)
        for (int j = 0; j < m.n; ++j)
            if (m.A[i * m.n + j] != 0)
                y[i] = y[i] + I(m.A[i * m.n + j]) * x[j];
    if (c)
        ++c->matvec;
    return y;
}
static I dot(const double *a, const IV &x, int n, Counts *c) {
    I y;
    for (int i = 0; i < n; ++i)
        if (a[i] != 0)
            y = y + I(a[i]) * x[i];
    if (c)
        ++c->dots;
    return y;
}
IV velocity(const Mode &m, const Input &i) {
    IV x(m.n);
    for (int k = 0; k < m.n; ++k) {
        double e = i.radius.empty() ? 0 : i.radius[k];
        x[k] = e ? I(down(i.x[k] - e), up(i.x[k] + e)) : I(i.x[k]);
    }
    auto v = mv(m, x, nullptr);
    for (int k = 0; k < m.n; ++k)
        v[k] = v[k] + I(m.b[k]);
    return v;
}
CacheEntry &Cache::get(const Mode &m, int p, Counts *c) {
    if (!m.generation)
        throw std::runtime_error("mode not finalized");
    auto key = std::pair(m.generation, p);
    auto it = entries.find(key);
    if (it != entries.end()) {
        if (c)
            ++c->cache_hits;
        return it->second;
    }
    CacheEntry e;
    e.p = p;
    e.n = m.n;
    e.m = m.m;
    e.rows.resize(size_t(p + 1) * m.m * m.n);
    for (int j = 0; j < m.m; ++j)
        for (int k = 0; k < m.n; ++k)
            e.rows[j * m.n + k] = I(m.C[j * m.n + k]); // r1=c
    for (int order = 1; order <= p; ++order)
        for (int j = 0; j < m.m; ++j) {
            for (int col = 0; col < m.n; ++col) {
                I v;
                for (int k = 0; k < m.n; ++k)
                    if (m.A[k * m.n + col] != 0)
                        v = v + e.rows[(size_t(order - 1) * m.m + j) * m.n + k] * I(m.A[k * m.n + col]);
                e.rows[(size_t(order) * m.m + j) * m.n + col] = v / I(order + 1);
            }
            if (c)
                ++c->rowvec;
        }
    if (c) {
        ++c->cache_misses;
        c->bytes += e.bytes();
    }
    return entries.emplace(key, std::move(e)).first->second;
}
std::vector<IV> coefficients(const Mode &m, const Input &i, int p, int method, Cache *cache, Counts *c,
                             Vec *tail) {
    std::vector<IV> out(m.m, IV(p + 2));
    IV x(m.n);
    for (int k = 0; k < m.n; ++k) {
        double e = i.radius.empty() ? 0 : i.radius[k];
        x[k] = e ? I(down(i.x[k] - e), up(i.x[k] + e)) : I(i.x[k]);
    }
    auto v = velocity(m, i);
    if (c)
        ++c->matvec;
    for (int j = 0; j < m.m; ++j)
        out[j][0] = dot(&m.C[j * m.n], x, m.n, c) + I(m.d[j]);
    if (method == 1) {
        auto &e = cache->get(m, p, c);
        I hp(1);
        for (int k = 1; k <= p + 1; ++k) {
            hp = hp * I(i.h);
            for (int j = 0; j < m.m; ++j) {
                I a;
                for (int s = 0; s < m.n; ++s)
                    a = a + e.rows[(size_t(k - 1) * m.m + j) * m.n + s] * v[s];
                out[j][k] = a * hp;
                if (c)
                    ++c->dots;
            }
        }
        if (tail) {
            tail->assign(m.m, 0);
            double vn = 0;
            for (auto t : v)
                vn = std::max(vn, t.absmax());
            for (int j = 0; j < m.m; ++j) {
                double rownorm = 0;
                for (int k = 0; k < m.n; ++k)
                    rownorm = add_up(rownorm, e.rows[(size_t(p) * m.m + j) * m.n + k].absmax());
                (*tail)[j] = mul_up(mul_up(rownorm, vn), hp.hi);
            }
        }
    } else {
        IV w = v;
        I hp(1), fac(1);
        for (int k = 1; k <= p + 1; ++k) {
            if (method == 2)
                for (auto &t : w)
                    t = t * I(i.h) / I(k);
            else {
                hp = hp * I(i.h);
                fac = fac * I(k);
            }
            for (int j = 0; j < m.m; ++j) {
                I a = dot(&m.C[j * m.n], w, m.n, c);
                out[j][k] = method == 2 ? a : a / fac * hp;
            }
            if (k == p + 1 && tail) {
                double wn = 0;
                for (auto t : w)
                    wn = std::max(wn, t.absmax());
                if (method == 0)
                    wn = mul_up(wn, (hp / fac).hi);
                tail->resize(m.m);
                for (int j = 0; j < m.m; ++j)
                    (*tail)[j] = mul_up(m.cnorm[j], wn);
            }
            if (k <= p)
                w = mv(m, w, c);
        }
    }
    return out;
}
// Ordinary FP coefficient-generation experiments are never used to certify exclusions.
std::vector<Vec> coefficients_fp(const Mode &m, const Input &i, int p, int method, Cache *cache) {
    std::vector<Vec> out(m.m, Vec(p + 1));
    Vec w(m.n);
    for (int a = 0; a < m.n; ++a) {
        w[a] = m.b[a];
        for (int b = 0; b < m.n; ++b)
            w[a] += m.A[a * m.n + b] * i.x[b];
    }
    for (int j = 0; j < m.m; ++j) {
        out[j][0] = m.d[j];
        for (int a = 0; a < m.n; ++a)
            out[j][0] += m.C[j * m.n + a] * i.x[a];
    }
    if (method == 1 && cache) {
        auto &e = cache->get(m, p, nullptr);
        double hp = 1;
        for (int k = 1; k <= p; ++k) {
            hp *= i.h;
            for (int j = 0; j < m.m; ++j) {
                double v = 0;
                for (int a = 0; a < m.n; ++a) {
                    auto r = e.rows[(size_t(k - 1) * m.m + j) * m.n + a];
                    v += (r.lo / 2 + r.hi / 2) * w[a];
                }
                out[j][k] = v * hp;
            }
        }
    } else if (method == 1) {
        std::vector<double> rows = m.C;
        double hp = 1;
        for (int k = 1; k <= p; ++k) {
            hp *= i.h;
            for (int j = 0; j < m.m; ++j) {
                double v = 0;
                for (int a = 0; a < m.n; ++a)
                    v += rows[j * m.n + a] * w[a];
                out[j][k] = v * hp;
            }
            Vec next(rows.size());
            for (int j = 0; j < m.m; ++j)
                for (int col = 0; col < m.n; ++col)
                    for (int a = 0; a < m.n; ++a)
                        next[j * m.n + col] += rows[j * m.n + a] * m.A[a * m.n + col] / (k + 1);
            rows.swap(next);
        }
    } else {
        double hp = 1, fac = 1;
        for (int k = 1; k <= p; ++k) {
            if (method == 2)
                for (auto &v : w)
                    v *= i.h / k;
            else {
                hp *= i.h;
                fac *= k;
            }
            for (int j = 0; j < m.m; ++j) {
                double v = 0;
                for (int a = 0; a < m.n; ++a)
                    v += m.C[j * m.n + a] * w[a];
                out[j][k] = method == 2 ? v : v / fac * hp;
            }
            Vec next(m.n);
            for (int a = 0; a < m.n; ++a)
                for (int b = 0; b < m.n; ++b)
                    next[a] += m.A[a * m.n + b] * w[b];
            w.swap(next);
        }
    }
    return out;
}
I horner(const IV &a) {
    I v = a.back();
    for (int k = int(a.size()) - 2; k >= 0; --k)
        v = v * I(0, 1) + a[k];
    return v;
}
static uint64_t choose(int n, int k) {
    uint64_t v = 1;
    for (int j = 1; j <= k; ++j)
        v = v * (n + 1 - j) / j;
    return v;
}
I bernstein(const IV &a) {
    static const auto weights = []() {
        std::array<std::vector<I>, 33> all;
        for (int p = 0; p <= 32; ++p) {
            all[p].resize((p + 1) * (p + 1));
            for (int i = 0; i <= p; ++i)
                for (int k = 0; k <= i; ++k)
                    all[p][i * (p + 1) + k] = I(double(choose(i, k))) / I(double(choose(p, k)));
        }
        return all;
    }();
    int p = int(a.size()) - 1;
    I range(INFINITY, -INFINITY);
    for (int i = 0; i <= p; ++i) {
        I v;
        for (int k = 0; k <= i; ++k)
            v = v + a[k] * weights[p][i * (p + 1) + k];
        range.lo = std::min(range.lo, v.lo);
        range.hi = std::max(range.hi, v.hi);
    }
    return range;
}
static GuardResult enclose(IV a, double error, int level, int envelope) {
    a.pop_back();
    I v;
    if (envelope == 2) {
        v = horner(a) + I(-error, error);
        if (v.finite() && (v.lo > 0 || v.hi < 0))
            return {Status::NO_EVENT_CERTIFIED, v, error, level};
        v = bernstein(a) + I(-error, error);
    } else
        v = (envelope ? bernstein(a) : horner(a)) + I(-error, error);
    if (!v.finite() || !std::isfinite(error))
        return {Status::UNRESOLVED, whole(), error, 3};
    return {v.lo > 0 || v.hi < 0 ? Status::NO_EVENT_CERTIFIED : Status::POSSIBLE_EVENT, v, error, level};
}
Result cheap_bounds(const Mode &m, const Input &i, Counts *c) {
    Result r;
    r.guards.resize(m.m);
    auto v = velocity(m, i);
    if (c)
        ++c->matvec;
    double vn = 0;
    for (auto t : v)
        vn = std::max(vn, t.absmax());
    double duration = i.h;
    if (m.mu < 0)
        duration = std::min(i.h, (I(1) / I(-m.mu)).hi);
    else
        duration = mul_up(i.h, exp_upper(mul_up(i.h, std::max(m.mu, 0.))));
    IV x(m.n);
    for (int k = 0; k < m.n; ++k) {
        double e = i.radius.empty() ? 0 : i.radius[k];
        x[k] = e ? I(down(i.x[k] - e), up(i.x[k] + e)) : I(i.x[k]);
    }
    for (int j = 0; j < m.m; ++j) {
        I g = dot(&m.C[j * m.n], x, m.n, c) + I(m.d[j]);
        double B = mul_up(mul_up(duration, m.cnorm[j]), vn);
        I env = g + I(-B, B);
        if (env.finite() && (env.lo > 0 || env.hi < 0)) {
            r.guards[j] = {Status::NO_EVENT_CERTIFIED, env, B, 1};
            if (c)
                ++c->l1;
        } else
            r.guards[j] = {env.finite() ? Status::POSSIBLE_EVENT : Status::UNRESOLVED, env, B, 3};
    }
    return r;
}
Result detect(const Mode &m, const Input &i, int algorithm, int p, Cache &cache, Counts *c, int envelope) {
    if (p < 1 || p > 32 || i.h < 0 || !std::isfinite(i.h))
        throw std::runtime_error("invalid degree or interval");
    if (i.x.size() != size_t(m.n) || (!i.radius.empty() && i.radius.size() != size_t(m.n)) ||
        (algorithm == 0 && i.y.size() != size_t(m.n)))
        throw std::runtime_error("invalid state size");
    for (double z : i.x)
        if (!std::isfinite(z))
            throw std::runtime_error("nonfinite initial state");
    for (double z : i.radius)
        if (!std::isfinite(z) || z < 0)
            throw std::runtime_error("invalid input enclosure");
    Result r;
    r.guards.resize(m.m);
    if (algorithm == 0) {
        for (int j = 0; j < m.m; ++j) {
            double a = m.d[j], b = m.d[j];
            for (int k = 0; k < m.n; ++k) {
                a += m.C[j * m.n + k] * i.x[k];
                b += m.C[j * m.n + k] * i.y[k];
            }
            bool hit = (a < 0 && b >= 0) || (a == 0 && b > 0);
            r.guards[j] = {hit ? Status::POSSIBLE_EVENT : Status::BASELINE_SKIP_UNCERTIFIED,
                           {std::min(a, b), std::max(a, b)},
                           0,
                           0};
        }
        return r;
    }
    std::vector<bool> needed(m.m, true);
    bool any = true;
    if (algorithm == 3) {
        r = cheap_bounds(m, i, c);
        any = false;
        for (int j = 0; j < m.m; ++j) {
            needed[j] = r.guards[j].status != Status::NO_EVENT_CERTIFIED;
            any |= needed[j];
        }
    }
    if (!any)
        return r;
    // Full uses normalized recurrence. Cached and hierarchical use immutable mode-row caches.
    Vec tail;
    auto a = coefficients(m, i, p, algorithm == 1 ? 2 : 1, &cache, c, &tail);
    double growth = exp_upper(mul_up(i.h, std::max(m.mu, 0.)));
    for (int j = 0; j < m.m; ++j)
        if (needed[j]) {
            // Full: c-norm times normalized vector derivative remainder.
            // Cached: cached derivative row norm, commuting A^p and exp(A t).
            double E = mul_up(tail[j], growth);
            r.guards[j] = enclose(a[j], E, 2, algorithm == 3 && envelope == 1 ? 2 : envelope);
            if (c) {
                if (r.guards[j].status == Status::NO_EVENT_CERTIFIED)
                    ++c->l2;
                else
                    ++c->l3;
            }
        }
    return r;
}
double checksum(const Result &r) {
    double s = 0;
    for (auto &g : r.guards)
        s += int(g.status) + g.level * .01;
    return s;
}
} // namespace rfr
