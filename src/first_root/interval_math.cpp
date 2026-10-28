#include "first_root.hpp"
#include <numbers>
namespace fri {
using namespace rfr;
static I pi() { return {0x1.921fb54442d18p+1, 0x1.921fb54442d19p+1}; }
I exp_interval(I a) {
    if (!a.finite())
        return whole();
    auto point = [](double x) -> I {
        if (x == 0)
            return I(1);
        if (x < -2048)
            return I(0, std::numeric_limits<double>::denorm_min());
        if (x > 709)
            return whole();
        bool neg = x < 0;
        double q = std::abs(x);
        int s = 0;
        while (q > .5) {
            q *= .5;
            ++s;
        }
        I term(1), sum(1);
        for (int k = 1; k <= 20; ++k) {
            term = term * I(q) / I(k);
            sum = sum + term;
        }
        I next = term * I(q) / I(21);
        double err = (next / (I(1) - I(q) / I(22))).hi;
        sum = sum + I(0, err);
        for (int k = 0; k < s; ++k)
            sum = sum * sum;
        if (neg)
            sum = I(1) / sum;
        return sum;
    };
    I l = point(a.lo), h = point(a.hi);
    return {std::max(0., l.lo), h.hi};
}
static I trig_point(I x, bool cosine) {
    if (!x.finite() || x.hi - x.lo >= 6.28 || std::max(std::abs(x.lo), std::abs(x.hi)) > 1e13)
        return {-1, 1};
    double mid = x.lo * .5 + x.hi * .5;
    double k = std::nearbyint(mid / (2 * std::numbers::pi));
    x = x - I(k) * I(2) * pi();
    if (x.absmax() > 7)
        return {-1, 1};
    // Taylor remainder bounded by |x|^(N+1)/(N+1)! since all real trig derivatives <=1.
    I term(1), sum(cosine ? 1 : 0);
    for (int j = 1; j <= 48; ++j) {
        term = term * x / I(j);
        if ((j % 2 == 0) == cosine) {
            int sign = cosine ? ((j / 2) % 2 ? -1 : 1) : (((j - 1) / 2) % 2 ? -1 : 1);
            sum = sum + term * I(sign);
        }
    }
    I absx(x.absmax()), tail(1);
    for (int j = 1; j <= 49; ++j)
        tail = tail * absx / I(j);
    sum = sum + I(-tail.hi, tail.hi);
    return {std::max(-1., sum.lo), std::min(1., sum.hi)};
}
static I trig(I x, bool cosine) {
    if (!x.finite() || x.hi - x.lo >= 6.28 || x.absmax() > 1e13)
        return {-1, 1};
    auto a = trig_point(I(x.lo), cosine), b = trig_point(I(x.hi), cosine);
    I out(std::min(a.lo, b.lo), std::max(a.hi, b.hi));
    double phase = cosine ? 0 : std::numbers::pi / 2;
    int64_t first = int64_t(std::floor((x.lo - phase) / std::numbers::pi)) - 2,
            last = int64_t(std::ceil((x.hi - phase) / std::numbers::pi)) + 2;
    for (int64_t k = first; k <= last; ++k) {
        I critical = I(double(k)) * pi() + (cosine ? I(0) : pi() / I(2));
        if (critical.lo <= x.hi && critical.hi >= x.lo) {
            double v = k % 2 ? -1. : 1.;
            out.lo = std::min(out.lo, v);
            out.hi = std::max(out.hi, v);
        }
    }
    return out;
}
I sin_interval(I a) { return trig(a, false); }
I cos_interval(I a) { return trig(a, true); }
static IV matvec(const Mode &m, const IV &x, Statistics *s) {
    IV y(m.n);
    for (int i = 0; i < m.n; ++i)
        for (int j = 0; j < m.n; ++j)
            if (m.A[i * m.n + j] != 0)
                y[i] = y[i] + I(m.A[i * m.n + j]) * x[j];
    if (s)
        ++s->matvecs;
    return y;
}
IV exponential_action(const Mode &m, const IV &initial, double t, Statistics *s, size_t max_steps) {
    if (s)
        ++s->state_calls;
    if (t == 0)
        return initial;
    double demand = std::ceil(m.norm * t / 1.5);
    if (!std::isfinite(demand) || demand > max_steps)
        return IV(m.n, whole());
    int steps = std::max(1, int(demand));
    double delta = t / steps; // use exact interval duration so steps*delta covers exact t
    I dt = I(t) / I(steps);
    IV x = initial;
    for (int z = 0; z < steps; ++z) {
        auto v = matvec(m, x, s);
        for (int j = 0; j < m.n; ++j)
            v[j] = v[j] + I(m.b[j]);
        IV term = v, out = x;
        for (int k = 1; k <= 24; ++k) {
            for (auto &a : term)
                a = a * dt / I(k);
            for (int j = 0; j < m.n; ++j)
                out[j] = out[j] + term[j];
            term = matvec(m, term, s);
        }
        // term now A*w24; multiply dt/25 for first omitted vector.
        double tail = 0;
        for (auto &a : term)
            tail = std::max(tail, (a * dt / I(25)).absmax());
        tail = mul_up(tail, exp_upper(mul_up(std::max(m.mu, 0.), dt.hi)));
        for (auto &a : out)
            a = a + I(-tail, tail);
        x.swap(out);
    }
    (void)delta;
    return x;
}
static uint64_t choose(int n, int k) {
    uint64_t x = 1;
    for (int i = 1; i <= k; ++i)
        x = x * (n + 1 - i) / i;
    return x;
}
IV ca_transform(const IV &q, double a, double b) {
    int p = int(q.size()) - 1;
    IV scaled(p + 1), z(p + 1);
    if (a == 0 && b == 1) {
        for (int j = 0; j <= p; ++j)
            for (int k = 0; k <= j; ++k)
                z[j] = z[j] + q[k] * I(double(choose(p - k, j - k)));
        return z;
    } // translation/rescaling P(a+(b-a)s), then reverse/translate.
    for (int j = 0; j <= p; ++j)
        for (int k = j; k <= p; ++k) {
            I ap(1), bp(1);
            for (int v = 0; v < k - j; ++v)
                ap = ap * I(a);
            for (int v = 0; v < j; ++v)
                bp = bp * (I(b) - I(a));
            scaled[j] = scaled[j] + q[k] * I(double(choose(k, j))) * ap * bp;
        }
    for (int j = 0; j <= p; ++j)
        for (int k = 0; k <= j; ++k)
            z[j] = z[j] + scaled[k] * I(double(choose(p - k, j - k)));
    return z;
}
int sign_variations(const IV &a) {
    int prior = 0, v = 0;
    for (I x : a) {
        if (x.zero())
            continue;
        int k = x.lo > 0 ? 1 : (x.hi < 0 ? -1 : 0);
        if (!k)
            return -1;
        if (prior && prior != k)
            ++v;
        prior = k;
    }
    return v;
}
} // namespace fri
