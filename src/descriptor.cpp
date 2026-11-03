#include "pulse/core.hpp"
#include "pulse/state_coordinates.hpp"
#include "pulse/solver_strategy.hpp"
#include "pulse/first_root/exclusion.hpp"
#include <algorithm>
#include <bit>
#include <deque>
#include <functional>
#include <iomanip>
#include <sstream>
#include <unordered_map>
#include <unordered_set>
namespace pulse {
struct ModeCacheData {
    const Model *model;
    size_t capacity;
    // Compiled template is immutable for the entire simulation. Dynamic
    // observer bindings are always materialized on a fresh instance.
    std::map<std::string, std::shared_ptr<const Mode>> entries;
    std::deque<std::string> insertion_order;
    std::map<std::string,std::shared_ptr<const Mode>> rebound_entries;
    std::deque<std::string> rebound_order;
    size_t rebound_capacity=512;
};
namespace {
thread_local ModeCacheData *active_mode_cache = nullptr;

std::string candidate_key(const std::map<int, bool> &bits,
                          const std::map<int, int> &segments,
                          const std::map<std::string, double> &regs,
                          const std::set<std::string>* observation_regs=nullptr) {
    // Exact binary values and length-prefixed fields avoid textual ambiguities.
    // Model topology/parameters are isolated by the per-simulation cache scope.
    std::string key(1,char(portfolio_variant()));
    auto word = [&](uint64_t value) {
        key.append(reinterpret_cast<const char *>(&value), sizeof(value));
    };
    word(bits.size());
    for (auto [i, value] : bits) {
        word(uint64_t(i));
        key.push_back(value ? '\1' : '\0');
    }
    word(segments.size());
    for (auto [i, value] : segments) {
        word(uint64_t(i));
        word(uint64_t(int64_t(value)));
    }
    size_t count=0;for(const auto &[name,value]:regs)if(!observation_regs||!observation_regs->count(name))++count;
    word(count);
    for (const auto &[name, value] : regs) {
        if(observation_regs&&observation_regs->count(name))continue;
        word(name.size());
        key += name;
        word(std::bit_cast<uint64_t>(value));
    }
    return key;
}

void check_candidate_reconstruction(const Mode &mode, const Vector &s, Source source) {
    // A point already meeting the unchanged physical entry check needs no
    // stronger, new per-equation relative test (e.g. on tiny leakage currents).
    // The alternate rounding check is only for large provisional algebraic
    // values while their constitutive regions are still being closed.
    const double physical = (mode.binding.read().residual_map * s).norm() /
                            std::max(1., (mode.binding.read().residual_reference * s).norm());
    if (physical < 1e-8) return;
    require(bool(mode.candidate_roundoff_scale), 12, "MISSING_CANDIDATE_SCALE",
            "candidate equations lack a reconstruction check");
    Vector error = (mode.binding.read().residual_map * s).cwiseAbs();
    Vector scale = *mode.candidate_roundoff_scale * s.cwiseAbs();
    double backward = 0;
    int worst = 0;
    for (int i = 0; i < error.size(); ++i) {
        if (scale[i]) {
            double ratio = error[i] / scale[i];
            if (ratio > backward) { backward = ratio; worst = i; }
        }
        else require(error[i] == 0, 7, "CANDIDATE_LINEAR_RESIDUAL",
                     "nonzero residual in an exactly zero candidate equation", true, source);
    }
    std::ostringstream detail;
    detail << std::setprecision(17) << "candidate point reconstruction exceeds its rounding budget; backward="
           << backward << ", equation=" << worst << ", residual=" << error[worst] << ", scale=" << scale[worst];
    require(error.allFinite() && scale.allFinite() && std::isfinite(backward) &&
                backward <= 128 * std::numeric_limits<double>::epsilon() * std::max(1, int(error.size())),
            7, "CANDIDATE_LINEAR_RESIDUAL", detail.str(), true, source);
}
Mode instantiate_cached(const Model &m, Mode mode, const Vector &s,
                        bool classification_only) {
    mode.classification_only = classification_only;
    // Repeat the original state-dependent entry checks, with identical matrix
    // expressions, order, tolerances and diagnostics. No previous accepted
    // state/residual is reused as evidence for this entry.
    if (mode.definition.read().constraints.rows()) {
        require((mode.definition.read().constraints * s).norm() <=
                    2e-10 * std::max(1., (mode.binding.read().residual_reference * s).norm()),
                10, "INCONSISTENT_MODE_TRANSITION",
                "new algebraic constraints conflict with preserved charge/flux/INT");
        require((mode.definition.read().invariant_lift * mode.definition.read().invariant_reduce * s - s).norm() <=
                    1e-10 * std::max(1., s.norm()),
                10, "INCONSISTENT_MODE_TRANSITION",
                "physical state cannot be reconstructed in new descriptor coordinates");
    }
    if (mode.binding.read().residual_map.rows()) {
        mode.residual = (mode.binding.read().residual_map * s).norm() /
                        std::max(1., (mode.binding.read().residual_reference * s).norm());
        Source matrix_source;
        if (!m.parts.empty())
            matrix_source = {m.parts.front().raw.source.file, "Network", "@descriptor", 0, 0};
        require(classification_only || mode.residual < 1e-8, 7, "DESCRIPTOR_RESIDUAL",
                "physical entry algebraic residual exceeds budget", true, matrix_source);
        if (classification_only) check_candidate_reconstruction(mode, s, matrix_source);
    }
    if (!classification_only) mode.candidate_roundoff_scale.reset();
    return mode;
}
std::string option(const Primitive &p, const std::string &k, const std::string &d = "") {
    auto it = p.options.find(k);
    return it == p.options.end() ? d : it->second;
}
double function(const Part &p, const std::vector<double> &x) {
    auto op = option(p.raw, "OP");
    double a = x.at(0), v = 0, b = x.size() > 1 ? x[1] : 0;
    if (op == "MUL")
        v = a * b;
    else if (op == "DIV") {
        require(b != 0, 7, "MATH_DOMAIN", "DIV by zero", false, p.raw.source);
        v = a / b;
    } else if (op == "SIN")
        v = std::sin(a);
    else if (op == "COS")
        v = std::cos(a);
    else if (op == "SQRT") {
        require(a >= 0, 7, "MATH_DOMAIN", "SQRT negative", false, p.raw.source);
        v = std::sqrt(a);
    } else if (op == "POW")
        v = std::pow(a, number(option(p.raw, "EXPONENT")));
    else if (op == "EXP")
        v = std::exp(a);
    else if (op == "LOG") {
        require(a > 0, 7, "MATH_DOMAIN", "LOG nonpositive", false, p.raw.source);
        v = std::log(a);
    } else if (op == "ATAN2") {
        require(a != 0 || b != 0, 7, "MATH_DOMAIN", "ATAN2(0,0)", false, p.raw.source);
        v = std::atan2(a, b);
    }
    require(std::isfinite(v), 7, "MATH_DOMAIN", "nonfinite discrete MATH result", false, p.raw.source);
    return v;
}
bool predicate(const Part &p, double g) {
    auto op = option(p.raw, "OP");
    return op == "GE" ? g >= 0 : op == "GT" ? g > 0 : op == "LE" ? g <= 0 : g < 0;
}
struct Assembler {
    const Model &m;
    const std::map<std::string, double> &regs;
    std::map<int, bool> bits;
    std::map<int, int> segments;
    std::map<std::string, int> realcol;
    std::map<std::string, std::vector<int>> branchcol;
    std::map<std::string, std::vector<int>> branchrow;
    const std::map<std::string, int> &partidx;
    std::unordered_map<std::string, double> memo;
    std::unordered_set<std::string> visiting;
    Matrix A, B, F, D;
    int na = 0, row = 0;
    Assembler(const Model &mm, const std::map<std::string, double> &rr, std::map<int, bool> bb,
              std::map<int, int> ss, bool equations=true)
        : m(mm), regs(rr), bits(std::move(bb)), segments(std::move(ss)),
          partidx(mm.compiled_part_index) {
        if (!equations) return;
        na = int(m.nodes.size());
        for (auto &[n, i] : m.branches) {
            auto &p = m.parts[i];
            for (size_t j = 0; j < p.ports.size(); ++j)
                branchcol[n].push_back(na++);
        }
        for (auto &[n, s] : m.signals)
            if (s.type == Signal::REAL)
                realcol[n] = na++;
        A = Matrix::Zero(na, na);
        B = Matrix::Zero(na, m.ns + 1);
        F = Matrix::Zero(m.ns, na);
        D = Matrix::Zero(m.ns, m.ns + 1);
        // partidx is already compiled into the frozen Model.
    }
    double held(const std::string &raw) {
        if (is_literal(raw))
            return number(raw);
        auto n = net_name(raw);
        if (memo.count(n))
            return memo[n];
        require(visiting.insert(n).second, 2, "COMBINATIONAL_CYCLE", "discrete combinational cycle at " + n);
        auto &p = m.parts.at(partidx.at(m.signals.at(n).driver));
        auto &a = p.raw.args;
        double v = 0;
        if (p.raw.kind == "REG")
            v = regs.at(n);
        else if (p.raw.kind == "CMP")
            v = bits.at(partidx.at(p.raw.id));
        else if (p.raw.kind == "SEL")
            v = held(a[held(a[1]) ? 3 : 2]);
        else if (p.raw.kind == "MATH") {
            if (p.raw.options.count("OP")) {
                std::vector<double> x;
                for (size_t j = 1; j < a.size(); ++j)
                    x.push_back(held(a[j]));
                v = function(p, x);
            } else {
                v = p.math.bias;
                for (auto &[n, c] : p.math.terms)
                    v += c * held(n);
            }
        } else
            throw Error(2, "CONTINUOUS_AS_HELD", "signal is not held: " + n);
        visiting.erase(n);
        return memo[n] = v;
    }
    void node_coeff(Matrix &mat, int r, const std::string &node, double v) {
        if (node != "0")
            mat(r, m.nodes.at(node)) += v;
    }
    void signal_eq(int r, const std::string &s, double coeff) {
        if (is_literal(s))
            B(r, m.ns) -= coeff * number(s);
        else if (m.signals.at(net_name(s)).type == Signal::REAL)
            A(r, realcol.at(net_name(s))) += coeff;
        else
            B(r, m.ns) -= coeff * held(s);
    }
    void stamp() {
        row = int(m.nodes.size());
        for (auto &[name, i] : m.branches) {
            auto &p = m.parts[i];
            auto &raw = p.raw;
            auto k = raw.kind;
            auto &a = raw.args;
            for (size_t j = 0; j < p.ports.size(); ++j) {
                branchrow[name].push_back(row);
                auto [v, w] = p.ports[j];
                int current = branchcol.at(name)[j];
                if (v != "0")
                    A(m.nodes.at(v), current) += 1;
                if (w != "0")
                    A(m.nodes.at(w), current) -= 1;
                if (k == "R" || k == "SW") {
                    double g = 0, b = 0;
                    if (k == "SW")
                        g = 1 / number(option(raw, held(a[2]) ? "RON" : "ROFF"));
                    else if (p.curve.x.empty())
                        g = 1 / number(option(raw, "R"));
                    else
                        std::tie(g, b) = p.curve.segment(segments.at(i));
                    A(row, current) = 1;
                    node_coeff(A, row, v, -g);
                    node_coeff(A, row, w, g);
                    B(row, m.ns) = b;
                } else if (k == "C") {
                    double c = 0, b = 0;
                    if (p.curve.x.empty())
                        c = number(option(raw, "C"));
                    else
                        std::tie(c, b) = p.curve.segment(segments.at(i));
                    node_coeff(A, row, v, 1);
                    node_coeff(A, row, w, -1);
                    B(row, p.state) = 1 / c;
                    B(row, m.ns) = -b / c;
                    F(p.state, current) = 1;
                } else if (k == "L") {
                    A(row, current) = 1;
                    if (p.inductance.rows() > 0) {
                        Matrix inv = p.inductance.inverse();
                        for (size_t l = 0; l < p.ports.size(); ++l)
                            B(row, p.state + int(l)) = inv(int(j), int(l));
                    } else {
                        double l = 0, b = 0;
                        if (p.curve.x.empty())
                            l = number(option(raw, "L"));
                        else
                            std::tie(l, b) = p.curve.segment(segments.at(i));
                        B(row, p.state) = 1 / l;
                        B(row, m.ns) = -b / l;
                    }
                    node_coeff(F, p.state + int(j), v, 1);
                    node_coeff(F, p.state + int(j), w, -1);
                } else if (k == "V") {
                    node_coeff(A, row, v, 1);
                    node_coeff(A, row, w, -1);
                    if (raw.options.count("DC"))
                        B(row, m.ns) = number(option(raw, "DC"));
                    else
                        signal_eq(row, a[2], -1);
                } else if (k == "I") {
                    A(row, current) = 1;
                    if (raw.options.count("DC"))
                        B(row, m.ns) = number(option(raw, "DC"));
                    else
                        signal_eq(row, a[2], -1);
                }
                ++row;
            }
        }
        for (auto &[name, col] : realcol) {
            auto &p = m.parts.at(partidx.at(m.signals.at(name).driver));
            auto &raw = p.raw;
            auto &a = raw.args;
            auto k = raw.kind;
            A(row, col) = 1;
            if (k == "REG")
                B(row, m.ns) = regs.at(name);
            else if (k == "INT") {
                B(row, p.state) = 1;
                if (is_literal(a[1]))
                    D(p.state, m.ns) = number(a[1]);
                else
                    F(p.state, realcol.at(net_name(a[1]))) = 1;
            } else if (k == "SENSOR") {
                if (a[1] == "V") {
                    node_coeff(A, row, a[2], -1);
                    node_coeff(A, row, a[3], 1);
                } else {
                    int j = int(number(option(raw, "PORT", "1"))) - 1;
                    A(row, branchcol.at(a[2]).at(j)) = -1;
                }
            } else if (k == "MATH") {
                if (m.signals.at(name).held)
                    B(row, m.ns) = held(name);
                else {
                    B(row, m.ns) = p.math.bias;
                    for (auto &[n, c] : p.math.terms)
                        signal_eq(row, n, -c);
                }
            } else if (k == "SEL") {
                if (m.signals.at(name).held)
                    B(row, m.ns) = held(name);
                else
                    signal_eq(row, a[held(a[1]) ? 3 : 2], -1);
            } else
                throw Error(12, "INTERNAL_ERROR", "unstamped signal " + name);
            ++row;
        }
        require(row == na, 12, "INTERNAL_ERROR", "descriptor row mismatch");
        if(portfolio_variant()==2)persistent_stamp(m,B,F,D);
    }
    Mode solve(const Vector &s, bool classification_only = false) {
        stamp();
        Matrix physical_A, physical_B;
        if (!m.floating_references.empty()) {
            physical_A = A;
            physical_B = B;
            for (const auto &reference : m.floating_references) {
                Vector gauge = Vector::Zero(na), kcl = Vector::Zero(na);
                for (const auto &[node, index] : m.nodes)
                    if (m.node_reference.at(node) == reference) {
                        gauge[index] = 1;
                        kcl += physical_A.row(index).transpose();
                    }
                // Only remove a proven common-potential freedom. A redundant
                // KCL row exists because every physical port stays in its island.
                require((physical_A * gauge).isZero(0) && (F * gauge).isZero(0) && kcl.isZero(0),
                        2, "UNSUPPORTED_REFERENCE_COUPLING",
                        "floating reference is not a pure common-potential freedom: " + reference);
                int index = m.nodes.at(reference);
                A.row(index).setZero();
                A(index, index) = 1;
                B.row(index).setZero();
            }
        }
        // A global residual has no unique responsible primitive.
        Source matrix_source;
        if (!m.parts.empty())
            matrix_source = {m.parts.front().raw.source.file, "Network", "@descriptor", 0, 0};
        Mode mode;
        mode.classification_only = classification_only;
        mode.segments = segments;
        Matrix N = Matrix::Zero(na, m.ns + 1);
        mode.definition.edit().M = Matrix::Zero(m.ns + 1, m.ns + 1);
        mode.definition.edit().constraints.resize(0, m.ns + 1);
        if (na) {
            Vector ar = Vector::Ones(na), ac = Vector::Ones(na);
            for (int j = 0; j < na; ++j) {
                double scale = A.row(j).cwiseAbs().maxCoeff();
                if (scale)
                    ar[j] = 1 / scale;
            }
            Matrix scaled = ar.asDiagonal() * A;
            for (int j = 0; j < na; ++j) {
                double scale = scaled.col(j).cwiseAbs().maxCoeff();
                if (scale)
                    ac[j] = 1 / scale;
            }
            scaled = scaled * ac.asDiagonal();
            Eigen::FullPivLU<Matrix> lu(scaled);
            lu.setThreshold(64 * std::numeric_limits<double>::epsilon() * std::max(1, na));
            if (lu.isInvertible()) {
                if(portfolio_variant()==1){
                    mode.elimination_path="ALGEBRAIC_QR";
                    Eigen::ColPivHouseholderQR<Matrix> qr(scaled);
                    qr.setThreshold(64*std::numeric_limits<double>::epsilon()*std::max(1,na));
                    require(qr.rank()==na,7,"PORTFOLIO_QR_RANK","QR cannot certify full rank under the existing rank threshold",true);
                    N=ac.asDiagonal()*qr.solve(ar.asDiagonal()*B);
                }else if (lu.rcond() < 1e-7) {
                    mode.elimination_path="ALGEBRAIC_WIDE_LU";
                    // Finite off-state conductances can leave nearly floating
                    // algebraic coordinates. Factor in extended precision so
                    // cancellation does not create spurious cross-coupling in
                    // threshold rows. Rank policy and physical state are unchanged.
                    using Wide = Eigen::Matrix<long double, Eigen::Dynamic, Eigen::Dynamic>;
                    Wide wa = ar.cast<long double>().asDiagonal() *
                              A.cast<long double>() * ac.cast<long double>().asDiagonal();
                    Eigen::PartialPivLU<Wide> wide_lu(wa);
                    Wide answer = ac.cast<long double>().asDiagonal() *
                        wide_lu.solve(ar.cast<long double>().asDiagonal() * B.cast<long double>());
                    N = answer.cast<double>();
                } else {
                    mode.elimination_path="ALGEBRAIC_LU";
                    N = ac.asDiagonal() * lu.solve(ar.asDiagonal() * B);
                }
            } else {
                // A rank-revealing transpose factorization selects independent
                // original equations. Its nullspace preserves structural zeros;
                // an orthogonal mixing of every row can contaminate a sparse
                // storage constraint with unrelated, differently scaled rows.
                Eigen::FullPivLU<Matrix> transpose_lu(scaled.transpose());
                transpose_lu.setThreshold(64 * std::numeric_limits<double>::epsilon() * std::max(1, na));
                int rank = int(transpose_lu.rank()), r = na - rank;
                require(rank == lu.rank(), 7, "DESCRIPTOR_RANK_UNRESOLVED",
                        "row and transpose rank decisions disagree", true);
                Matrix left_null = ar.asDiagonal() * transpose_lu.kernel();
                // Exact KCL cutsets of prescribed-current branches are common
                // in series/coupled inductors. Construct them from incidence
                // rather than approximate dense null vectors. Use this basis
                // only when it spans the entire defect and annihilates A exactly.
                std::map<std::string, std::string> parent;
                parent["0"] = "0";
                for (auto &[n, index] : m.nodes)
                    parent[n] = n;
                std::function<std::string(const std::string &)> find = [&](const std::string &n) {
                    return parent[n] == n ? n : parent[n] = find(parent[n]);
                };
                for (auto &[name, index] : m.branches) {
                    const auto &p = m.parts[index];
                    if (p.raw.kind != "L" && p.raw.kind != "I")
                        for (auto &[v, w] : p.ports)
                            parent[find(v)] = find(w);
                }
                std::map<std::string, Vector> cuts;
                const auto grounded = find("0");
                for (auto &[n, index] : m.nodes)
                    if (find(n) != grounded) {
                        auto [it, inserted] = cuts.try_emplace(find(n), Vector::Zero(na));
                        it->second[index] = 1;
                    }
                std::vector<Vector> exact_cuts;
                for (auto &[component, cut] : cuts) {
                    for (auto &[name, index] : m.branches) {
                        const auto &p = m.parts[index];
                        for (size_t j = 0; j < p.ports.size(); ++j) {
                            auto &[v, w] = p.ports[j];
                            int direction = int(find(v) == component) - int(find(w) == component);
                            if (direction)
                                cut[branchrow.at(name)[j]] -= direction;
                        }
                    }
                    bool annihilates = true;
                    for (int j = 0; j < na && annihilates; ++j) {
                        rfr::I coefficient;
                        for (int i = 0; i < na; ++i)
                            coefficient = coefficient + rfr::I(cut[i]) * rfr::I(A(i, j));
                        annihilates = coefficient.zero();
                    }
                    if (annihilates)
                        exact_cuts.push_back(cut);
                }
                if (int(exact_cuts.size()) >= r) {
                    Matrix topology(na, exact_cuts.size());
                    for (size_t j = 0; j < exact_cuts.size(); ++j)
                        topology.col(j) = exact_cuts[j];
                    Eigen::FullPivLU<Matrix> topology_lu(topology);
                    topology_lu.setThreshold(64 * std::numeric_limits<double>::epsilon() * std::max(1, na));
                    if (topology_lu.rank() == r)
                        for (int j = 0; j < r; ++j)
                            left_null.col(j) = topology.col(topology_lu.permutationQ().indices()[j]);
                }
                mode.definition.edit().constraints = left_null.transpose() * B;
                require((mode.definition.read().constraints * s).norm() <= 2e-10 * std::max(1., (B * s).norm()), 10,
                        "INCONSISTENT_MODE_TRANSITION",
                        "new algebraic constraints conflict with preserved charge/flux/INT");
                Matrix K = Matrix::Zero(m.ns + na, m.ns + na), R = Matrix::Zero(m.ns + na, m.ns + 1);
                K.topLeftCorner(m.ns, m.ns).setIdentity();
                K.topRightCorner(m.ns, na) = -F;
                R.topRows(m.ns) = D;
                for (int j = 0; j < rank; ++j) {
                    int original = transpose_lu.permutationQ().indices()[j];
                    K.block(m.ns + j, m.ns, 1, na) = A.row(original);
                    R.row(m.ns + j) = B.row(original);
                }
                K.bottomLeftCorner(r, m.ns) = mode.definition.read().constraints.leftCols(m.ns);
                Vector rs = Vector::Ones(K.rows()), cs = Vector::Ones(K.cols());
                for (int j = 0; j < K.rows(); ++j) {
                    double v = K.row(j).cwiseAbs().maxCoeff();
                    if (v)
                        rs[j] = 1 / v;
                }
                Matrix balanced = rs.asDiagonal() * K;
                for (int j = 0; j < K.cols(); ++j) {
                    double v = balanced.col(j).cwiseAbs().maxCoeff();
                    if (v)
                        cs[j] = 1 / v;
                }
                balanced = balanced * cs.asDiagonal();
                Eigen::FullPivLU<Matrix> reduction(balanced);
                reduction.setThreshold(128 * std::numeric_limits<double>::epsilon() *
                                       std::max(1, int(K.rows())));
                require(reduction.isInvertible(), 6, "MODEL_SINGULAR",
                        "descriptor has nonunique or unsupported higher-index dynamics");
                // Compile only the admissible affine physical subspace. Solving
                // arbitrary off-manifold storage columns amplifies unphysical directions.
                // This reduction changes coordinates, never the authoritative physical state.
                Eigen::FullPivLU<Matrix> state_lu(mode.definition.read().constraints.leftCols(m.ns));
                state_lu.setThreshold(128 * std::numeric_limits<double>::epsilon() * std::max(1, m.ns));
                int state_rank = int(state_lu.rank()), free = m.ns - state_rank;
                Matrix basis = free ? Matrix(state_lu.kernel()) : Matrix(m.ns, 0);
                Vector offset = state_lu.solve(-mode.definition.read().constraints.col(m.ns));
                Matrix lift = Matrix::Zero(m.ns + 1, free + 1), reduce = Matrix::Zero(free + 1, m.ns + 1);
                lift.topLeftCorner(m.ns, free) = basis;
                lift.topRightCorner(m.ns, 1) = offset;
                lift(m.ns, free) = 1;
                for (int j = 0; j < free; ++j) {
                    int original = state_lu.permutationQ().indices()[state_rank + j];
                    reduce(j, original) = 1;
                    reduce(j, m.ns) = -offset[original];
                }
                reduce(free, m.ns) = 1;
                require((lift * reduce * s - s).norm() <= 1e-10 * std::max(1., s.norm()), 10,
                        "INCONSISTENT_MODE_TRANSITION",
                        "physical state cannot be reconstructed in new descriptor coordinates");
                Matrix allowed = R * lift;
                // QR must cover the constrained descriptor branch too. Rank
                // policy, physical constraints and acceptance budgets are shared.
                Eigen::ColPivHouseholderQR<Matrix> descriptor_qr;
                if(portfolio_variant()==1){
                    descriptor_qr.compute(balanced);
                    descriptor_qr.setThreshold(128*std::numeric_limits<double>::epsilon()*std::max(1,int(K.rows())));
                    require(descriptor_qr.rank()==K.rows(),7,"PORTFOLIO_QR_RANK","QR cannot certify constrained descriptor rank",true);
                }
                auto solve_descriptor=[&](const Matrix&rhs)->Matrix{
                    if(portfolio_variant()==1)return cs.asDiagonal()*descriptor_qr.solve(rs.asDiagonal()*rhs);
                    return cs.asDiagonal()*reduction.solve(rs.asDiagonal()*rhs);
                };
                mode.elimination_path=portfolio_variant()==1?"CONSTRAINED_QR":"CONSTRAINED_LU";
                Matrix local = solve_descriptor(allowed);
                // Retain exact scalar assignments present in the original
                // equations, including structural zero currents. Dense pivoting
                // and refinement can otherwise leave meaningless tiny values in
                // x=0 rows, for which componentwise relative error is always one.
                Matrix assigned = Matrix::Zero(local.rows(), local.cols());
                std::vector<bool> known(size_t(K.cols()), false);
                for (int pass = 0; pass < K.cols(); ++pass) {
                    bool changed = false;
                    for (int i = 0; i < K.rows(); ++i) {
                        int target = -1;
                        for (int j = 0; j < K.cols(); ++j)
                            if (K(i, j) != 0 && !known[size_t(j)]) {
                                if (target >= 0) {
                                    target = -2;
                                    break;
                                }
                                target = j;
                            }
                        if (target >= 0) {
                            assigned.row(target) = allowed.row(i);
                            for (int j = 0; j < K.cols(); ++j)
                                if (known[size_t(j)] && K(i, j) != 0)
                                    assigned.row(target) -= K(i, j) * assigned.row(j);
                            assigned.row(target) /= K(i, target);
                            known[size_t(target)] = true;
                            changed = true;
                        }
                    }
                    if (!changed)
                        break;
                }
                auto scalar_assignments = [&]() {
                    for (int j = 0; j < K.cols(); ++j)
                        if (known[size_t(j)])
                            local.row(j) = assigned.row(j);
                };
                scalar_assignments();
                for (int refinement = 0; refinement < 2; ++refinement) {
                    local += solve_descriptor(allowed - K * local);
                    scalar_assignments();
                }
                Matrix error = (K * local - allowed).cwiseAbs(),
                       denominator = K.cwiseAbs() * local.cwiseAbs() + allowed.cwiseAbs();
                // A componentwise ratio is meaningless when a structurally zero
                // row has only roundoff noise in the denominator.  Add the FP
                // resolution scale of this row against this solution column.
                const double eps = std::numeric_limits<double>::epsilon();
                for (int i = 0; i < denominator.rows(); ++i)
                    for (int j = 0; j < denominator.cols(); ++j) {
                        const double col_scale =
                            K.row(i).lpNorm<1>() * local.col(j).lpNorm<Eigen::Infinity>() +
                            allowed.row(i).lpNorm<1>();
                        const double floor = eps * col_scale;
                        if (denominator(i, j) < floor)
                            denominator(i, j) = floor;
                    }
                double backward = 0;
                int worst_row = 0, worst_column = 0;
                for (int i = 0; i < error.rows(); ++i)
                    for (int j = 0; j < error.cols(); ++j) {
                        if (denominator(i, j) > 0) {
                            double ratio = error(i, j) / denominator(i, j);
                            if (ratio > backward) {
                                backward = ratio;
                                worst_row = i;
                                worst_column = j;
                            }
                        } else
                            require(error(i, j) == 0, 7, "DESCRIPTOR_RESIDUAL",
                                    "nonzero residual in an exactly zero equation", true, matrix_source);
                    }
                std::ostringstream backward_detail;
                backward_detail << std::setprecision(17) << "componentwise descriptor backward error "
                                << backward << " exceeds rounding budget; equation=" << worst_row
                                << ", column=" << worst_column
                                << ", residual=" << error(worst_row, worst_column)
                                << ", scale=" << denominator(worst_row, worst_column);
                require(backward <= 128 * std::numeric_limits<double>::epsilon() * std::max(1, int(K.rows())),
                        7, "DESCRIPTOR_RESIDUAL", backward_detail.str(), true, matrix_source);
                Matrix X = local * reduce;
                mode.definition.edit().M.topRows(m.ns) = X.topRows(m.ns);
                mode.definition.edit().invariant_lift = lift;
                mode.definition.edit().invariant_reduce = reduce;
                Matrix physical_derivative = Matrix::Zero(m.ns + 1, free + 1);
                physical_derivative.topRows(m.ns) = local.topRows(m.ns);
                mode.definition.edit().invariant_generator = reduce * physical_derivative;
                N = X.bottomRows(na);
            }
            // These are exact algebraic coordinate assignments (Vref=0), not
            // storage-state constraints. Retain their structural zero after
            // factorization, rather than interpreting a tiny gauge tail as
            // relative error one during provisional reconstruction checks.
            for (const auto &reference : m.floating_references)
                N.row(m.nodes.at(reference)).setZero();
            require(N.allFinite() && mode.definition.read().M.allFinite(), 7, "NONFINITE_CANDIDATE",
                    "compiled candidate equations are nonfinite", true, matrix_source);
            if (m.floating_references.empty()) {
                mode.binding.edit().residual_map = A * N - B;
                mode.binding.edit().residual_reference = B;
            } else {
                // Check every original physical equation, including each KCL
                // row replaced by a coordinate equation, plus local references.
                int extra = int(m.floating_references.size());
                mode.binding.edit().residual_map = Matrix::Zero(na + extra, m.ns + 1);
                mode.binding.edit().residual_reference = Matrix::Zero(na + extra, m.ns + 1);
                mode.binding.edit().residual_map.topRows(na) = physical_A * N - physical_B;
                mode.binding.edit().residual_reference.topRows(na) = physical_B;
                for (int j = 0; j < extra; ++j)
                    mode.binding.edit().residual_map.row(na + j) = N.row(m.nodes.at(m.floating_references[j]));
            }
            // Retain the original descriptor shape and factorization ordering.
            // Only structurally isolated held observations may be rebound.
            if(!m.observer_regs.empty()){
                auto binding=std::make_shared<ObserverBinding>();bool isolated=true;
                for(const auto &name:m.observer_signals){
                    int col=realcol.at(name);int r=col;
                    if(A(r,col)!=1||A.row(r).cwiseAbs().sum()!=1||A.col(col).cwiseAbs().sum()!=1||!F.col(col).isZero(0))isolated=false;
                    if(!N.row(col).head(m.ns).isZero(0)||std::bit_cast<uint64_t>(N(col,m.ns))!=std::bit_cast<uint64_t>(held(name)))isolated=false;
                    binding->rows[name]=r;
                }
                if(isolated){
                    binding->A=m.floating_references.empty()?A:physical_A;
                    binding->B=m.floating_references.empty()?B:physical_B;binding->N=N;
                    mode.observer_binding=binding;
                    for(const auto &[name,r]:binding->rows){mode.observer_maps.insert(name);mode.observer_rows.push_back(r);}
                }
            }
            // Classification uses only this physical point, not arbitrary
            // independent coefficient columns. Cache the operation scale, not
            // a previous point's validation result; recheck every cache hit.
            const Matrix &check_A = m.floating_references.empty() ? A : physical_A;
            const Matrix &check_B = m.floating_references.empty() ? B : physical_B;
            Matrix scale = Matrix::Zero(mode.binding.read().residual_map.rows(), m.ns + 1);
            scale.topRows(na) = check_A.cwiseAbs() * N.cwiseAbs() + check_B.cwiseAbs();
            for (int i = 0; i < na; ++i)
                for (int j = 0; j <= m.ns; ++j) {
                    double floor = std::numeric_limits<double>::epsilon() *
                        (check_A.row(i).lpNorm<1>() * N.col(j).lpNorm<Eigen::Infinity>() + check_B.row(i).lpNorm<1>());
                    scale(i,j) = std::max(scale(i,j), floor);
                }
            for (size_t j = 0; j < m.floating_references.size(); ++j)
                scale.row(na + j) = N.row(m.nodes.at(m.floating_references[j])).cwiseAbs();
            mode.candidate_roundoff_scale = std::make_shared<const Matrix>(std::move(scale));
            if (classification_only) check_candidate_reconstruction(mode, s, matrix_source);
            mode.residual = (mode.binding.read().residual_map * s).norm() /
                            std::max(1., (mode.binding.read().residual_reference * s).norm());
            require(
                classification_only || mode.residual < 1e-8, 7, "DESCRIPTOR_RESIDUAL",
                "physical entry algebraic residual exceeds budget", true,
                matrix_source); // constrained maps only satisfy algebraic equations on constraint manifold

            if (!mode.definition.read().constraints.rows())
                mode.definition.edit().M.topRows(m.ns) = F * N + D;
        }
        require(mode.definition.read().M.allFinite() && N.allFinite(), 7, "NONFINITE_DESCRIPTOR",
                "descriptor elimination is nonfinite");
        for (auto &[n, i] : m.nodes)
            mode.binding.edit().maps["V(" + n + ")"] = N.row(i).transpose();
        for (auto &[n, cols] : branchcol)
            for (size_t j = 0; j < cols.size(); ++j)
                mode.binding.edit().maps["I(" + n + (cols.size() > 1 ? "," + std::to_string(j + 1) : "") + ")"] =
                    N.row(cols[j]).transpose();
        for (auto &[n, sig] : m.signals)
            if (sig.type == Signal::REAL) {
                if (sig.held) {
                    Vector x = Vector::Zero(m.ns + 1);
                    x[m.ns] = held(n);
                    mode.binding.edit().maps[n] = x;
                } else
                    mode.binding.edit().maps[n] = N.row(realcol.at(n)).transpose();
            } else if (sig.type == Signal::BOOL) {
                double v = held(n);
                mode.bools[n] = v != 0;
                Vector x = Vector::Zero(m.ns + 1);
                x[m.ns] = v;
                mode.binding.edit().maps[n] = x;
            }
        std::ostringstream id;
        id << std::setprecision(17);
        for (auto &[i, b] : bits)
            id << m.parts[i].raw.id << '=' << b << ';';
        for (auto &[i, seg] : segments)
            id << m.parts[i].raw.id << '=' << seg << ';';
        for (auto &[n, v] : regs)
            id << n << '=' << v << ';';
        mode.id = id.str();
        return mode;
    }
};
Mode bind_observations(const Model&m,const Mode&stored,const std::map<std::string,double>&regs,
                       const std::map<int,bool>&bits,const std::map<int,int>&segments,
                       bool classification_only){
    Mode mode=stored;if(!stored.observer_binding)return mode;
    const auto &binding=*stored.observer_binding;
    // D: Per-thread scratch is entirely overwritten before every use.
    // It is not shared with a Mode, transaction or persistent cache.
    struct BindingScratch { Matrix N, B, scale; };
    static thread_local BindingScratch scratch;
    Matrix &N=scratch.N, &B=scratch.B;
    N=binding.N; B=binding.B;
    Assembler values(m,regs,bits,segments,false);
    for(const auto &[name,row]:binding.rows){
        double value=values.held(name);N(row,m.ns)=value;B(row,m.ns)=value;
        mode.binding.edit().maps.at(name).setZero();mode.binding.edit().maps.at(name)[m.ns]=value;
    }
    int na=int(N.rows());mode.binding.edit().residual_map.topRows(na)=binding.A*N-B;
    mode.binding.edit().residual_reference.topRows(na)=B;
    if(classification_only) {
    Matrix &scale=scratch.scale;
    scale=Matrix::Zero(mode.binding.read().residual_map.rows(),m.ns+1);
    scale.topRows(na)=binding.A.cwiseAbs()*N.cwiseAbs()+B.cwiseAbs();
    // Norms depend on only one loop index. Evaluate each only once per bind;
    // keep the original expression and floating-point reduction order intact.
    std::vector<double> a_row_norm(static_cast<size_t>(na)), b_row_norm(static_cast<size_t>(na));
    std::vector<double> n_col_norm(static_cast<size_t>(m.ns + 1));
    for(int i=0;i<na;++i){
        a_row_norm[size_t(i)]=binding.A.row(i).lpNorm<1>();
        b_row_norm[size_t(i)]=B.row(i).lpNorm<1>();
    }
    for(int j=0;j<=m.ns;++j)
        n_col_norm[size_t(j)]=N.col(j).lpNorm<Eigen::Infinity>();
    for(int i=0;i<na;++i)for(int j=0;j<=m.ns;++j){
        double floor=std::numeric_limits<double>::epsilon()*(a_row_norm[size_t(i)]*n_col_norm[size_t(j)]+b_row_norm[size_t(i)]);
        scale(i,j)=std::max(scale(i,j),floor);
    }
    for(size_t j=0;j<m.floating_references.size();++j){
        mode.binding.edit().residual_map.row(na+j)=N.row(m.nodes.at(m.floating_references[j]));
        scale.row(na+j)=N.row(m.nodes.at(m.floating_references[j])).cwiseAbs();
    }
    mode.candidate_roundoff_scale=std::make_shared<const Matrix>(scale);
    } else {
      // Floating reference rows remain checked for accepted entries.
      for(size_t j=0;j<m.floating_references.size();++j)
        mode.binding.edit().residual_map.row(na+j)=
            N.row(m.nodes.at(m.floating_references[j]));
      mode.candidate_roundoff_scale.reset();
    }
    std::ostringstream id;id<<std::setprecision(17);
    for(const auto &[i,b]:bits)id<<m.parts[i].raw.id<<'='<<b<<';';
    for(const auto &[i,seg]:segments)id<<m.parts[i].raw.id<<'='<<seg<<';';
    for(const auto &[name,v]:regs)id<<name<<'='<<v<<';';
    mode.id=id.str();
    return mode;
}
Vector input_map(const Model &m, const Mode &mode, const std::string &name) {
    if (is_literal(name)) {
        Vector v = Vector::Zero(m.ns + 1);
        v[m.ns] = number(name);
        return v;
    }
    return mode.binding.read().maps.at(net_name(name));
}
// Right-side Taylor jet at a boundary. Exact zero tests avoid turning a small
// derivative into an identity proof. This remains a numerical compiler check.
int right_sign(const Mode &mode, Vector row, const Vector &s) {
    std::vector<rfr::I> jet(size_t(row.size()));
    for (int j = 0; j < row.size(); ++j)
        jet[j] = rfr::I(row[j]);
    for (int order = 0; order < s.size() + 1; ++order) {
        std::vector<rfr::I> next(jet.size());
        for (int j = 0; j < row.size(); ++j)
            for (int i = 0; i < row.size(); ++i)
                next[j] = next[j] + jet[i] * rfr::I(mode.definition.read().M(i, j));
        jet = std::move(next);
        rfr::I value;
        bool zero = true;
        for (int j = 0; j < s.size(); ++j) {
            value = value + jet[j] * rfr::I(s[j]);
            zero = zero && jet[j].zero();
        }
        if (value.lo > 0)
            return 1;
        if (value.hi < 0)
            return -1;
        if (zero)
            return 0;
        if (!value.zero())
            throw Error(9, "FORWARD_JET_UNRESOLVED", "outward boundary derivative cannot determine a side",
                        true);
    }
    throw Error(9, "FORWARD_JET_UNRESOLVED", "cannot prove forward boundary side", true);
}

} // namespace
ScopedModeCache::ScopedModeCache(const Model &model, size_t capacity)
    : data_(std::make_unique<ModeCacheData>(ModeCacheData{&model, capacity, {}, {}})),
      previous_(active_mode_cache) {
    active_mode_cache = data_.get();
}
ScopedModeCache::~ScopedModeCache() {
    active_mode_cache = previous_;
}
Mode settle(const Model &m, const Vector &s, const std::map<std::string, double> &regs, Stats &stats,
            const std::set<int> &crossed, bool initial) {
    Source matrix_source;
    if (!m.parts.empty())
        matrix_source = {m.parts.front().raw.source.file, "Network", "@descriptor", 0, 0};
    size_t count = 1;
    require(m.cmps.size() <= 12, 9, "MODE_UNRESOLVED", "CMP candidate budget exceeds 12", true);
    count <<= m.cmps.size();
    for (int i : m.pwas) {
        size_t n = m.parts[i].curve.x.size() - 1;
        require(count <= 4096 / n, 9, "MODE_UNRESOLVED", "mixed mode enumeration budget exceeded", true);
        count *= n;
    }
    std::vector<Mode> accepted;
    bool physical_conflict = false, forward_conflict = false, range_conflict = false;
    std::optional<Error> singular;
    for (size_t candidate = 0; candidate < count; ++candidate) {
        size_t code = candidate;
        std::map<int, bool> bits;
        std::map<int, int> segs;
        for (int i : m.cmps) {
            bits[i] = code % 2;
            code /= 2;
        }
        for (int i : m.pwas) {
            int n = int(m.parts[i].curve.x.size()) - 1;
            segs[i] = int(code % size_t(n));
            code /= size_t(n);
        }
        try {
            Assembler a(m, regs, bits, segs);
            Mode mode = a.solve(s);
            ++stats.modes;
            bool valid = true;
            for (int i : m.cmps) {
                auto &p = m.parts[i];
                Vector g = input_map(m, mode, p.raw.args[1]);
                g[m.ns] -= number(option(p.raw, "THRESHOLD"));
                double v = g.dot(s);
                bool actual = predicate(p, v);
                bool isheld = is_literal(p.raw.args[1]) || m.signals.at(net_name(p.raw.args[1])).held;
                bool boundary = v == 0;
                if (!isheld && (boundary || crossed.count(i))) {
                    int sign = right_sign(mode, g, s);
                    actual = sign ? ((option(p.raw, "OP") == "GT" || option(p.raw, "OP") == "GE") ? sign > 0
                                                                                                  : sign < 0)
                                  : predicate(p, 0);
                    if (actual != bits[i]) {
                        valid = false;
                        forward_conflict = true;
                    }
                } else if (actual != bits[i])
                    valid = false;
                if (!isheld) {
                    bool greater = option(p.raw, "OP") == "GT" || option(p.raw, "OP") == "GE";
                    double oriented = (bits[i] == greater) ? -1 : 1;
                    g *= oriented;
                    if (!(g.head(m.ns).isZero(0))) {
                        mode.binding.edit().guards.push_back({g, i, 1, "CMP"});
                    }
                }
            }
            bool logic_valid = valid;
            for (int i : m.pwas) {
                auto &p = m.parts[i];
                int seg = segs[i];
                auto &curve = p.curve;
                Vector x = Vector::Zero(m.ns + 1);
                bool physical = p.raw.kind != "R";
                if (physical)
                    x[p.state] = 1;
                else {
                    auto [v, w] = p.ports[0];
                    if (v != "0")
                        x += mode.binding.read().maps.at("V(" + v + ")");
                    if (w != "0")
                        x -= mode.binding.read().maps.at("V(" + w + ")");
                }
                const auto &bounds = physical ? curve.y : curve.x;
                double value = x.dot(s), tol = 0;
                bool lower = seg > 0 || !curve.extend, upper = seg + 2 < int(bounds.size()) || !curve.extend;
                if ((lower && value < bounds[seg] - tol) || (upper && value > bounds[seg + 1] + tol)) {
                    if (logic_valid && !curve.extend && (value < bounds.front() || value > bounds.back()))
                        range_conflict = true;
                    valid = false;
                    continue;
                }
                if (lower) {
                    Vector g = -x;
                    g[m.ns] += bounds[seg];
                    if (std::abs(value - bounds[seg]) <= tol && right_sign(mode, g, s) > 0) {
                        valid = false;
                        forward_conflict = true;
                        if (logic_valid && seg == 0 && !curve.extend)
                            range_conflict = true;
                    }
                    mode.binding.edit().guards.push_back({g, i, 1, seg == 0 ? "RANGE" : "PWA", seg, seg, -1});
                }
                if (upper) {
                    Vector g = x;
                    g[m.ns] -= bounds[seg + 1];
                    if (std::abs(value - bounds[seg + 1]) <= tol) {
                        int sign = right_sign(mode, g, s);
                        if (sign > 0) {
                            valid = false;
                            forward_conflict = true;
                            if (logic_valid && seg + 2 == int(bounds.size()) && !curve.extend)
                                range_conflict = true;
                        } else if (sign == 0 && seg + 2 < int(bounds.size()))
                            valid = false;
                    }
                    mode.binding.edit().guards.push_back({g, i, 1, seg + 2 == int(bounds.size()) ? "RANGE" : "PWA", seg + 1, seg, 1});
                }
            }
            if (valid) {
                stats.max_residual = std::max(stats.max_residual, mode.residual);
                accepted.push_back(std::move(mode));
            }
        } catch (const Error &e) {
            if (e.subcode == "INCONSISTENT_MODE_TRANSITION")
                physical_conflict = true;
            else if (e.code == 6)
                singular = e;
            else
                throw;
        }
    }
    require(accepted.size() <= 1, 9, "MULTIPLE_STABLE_MODES", "more than one stable forward mode");
    if (accepted.empty()) {
        if (physical_conflict)
            throw Error(initial ? 3 : 10,
                        initial ? "INCONSISTENT_INITIAL_STATE" : "INCONSISTENT_MODE_TRANSITION",
                        "preserved physical state violates new source constraints", false, matrix_source);
        if (singular)
            throw *singular;
        if (range_conflict)
            throw Error(5, "PWA_OUT_OF_RANGE", "no supported forward mode within PWA table range", false,
                        m.parts[m.pwas.front()].raw.source);
        if (forward_conflict)
            throw Error(9, "NO_FORWARD_ADMISSIBLE_MODE",
                        "boundary has no supported ordinary forward continuation", true,
                        m.parts[!crossed.empty()  ? *crossed.begin()
                                : !m.cmps.empty() ? m.cmps.front()
                                                  : m.pwas.front()]
                            .raw.source);
        throw Error(9, "NO_STABLE_MODE", "no algebraically consistent stable mode");
    }
    if (singular)
        throw Error(9, "MODE_UNRESOLVED", "a competing candidate has unresolved singular dynamics", true,
                    singular->source);
    return std::move(accepted.front());
}

void accept_mode_entry(const Model &m, Mode &mode, const Vector &s) {
    // Repeat exactly the accepted-entry checks at the final, consistent region.
    // No storage projection or tolerance change is part of candidate closure.
    Source source;
    if (!m.parts.empty()) source = {m.parts.front().raw.source.file, "Network", "@descriptor", 0, 0};
    if (mode.definition.read().constraints.rows()) {
        require((mode.definition.read().constraints * s).norm() <= 2e-10 * std::max(1., (mode.binding.read().residual_reference * s).norm()),
                10, "INCONSISTENT_MODE_TRANSITION", "new algebraic constraints conflict with preserved charge/flux/INT");
        require((mode.definition.read().invariant_lift * mode.definition.read().invariant_reduce * s - s).norm() <= 1e-10 * std::max(1., s.norm()),
                10, "INCONSISTENT_MODE_TRANSITION", "physical state cannot be reconstructed in new descriptor coordinates");
    }
    if (mode.binding.read().residual_map.rows()) {
        mode.residual = (mode.binding.read().residual_map * s).norm() / std::max(1., (mode.binding.read().residual_reference * s).norm());
        require(mode.residual < 1e-8, 7, "DESCRIPTOR_RESIDUAL",
                "physical entry algebraic residual exceeds budget after region closure", true, source);
    }
    mode.classification_only = false;
    mode.candidate_roundoff_scale.reset();
}
Mode compile_specified(const Model &m, const Vector &s, const std::map<std::string, double> &regs,
                       Stats &stats, const std::map<int, bool> &bits, const std::map<int, int> &segments,
                       CompilePurpose purpose) {
    const bool classification_only = purpose == CompilePurpose::RegionClassification;
    ModeCacheData *cache = active_mode_cache && active_mode_cache->model == &m &&
                                  active_mode_cache->capacity
                              ? active_mode_cache
                              : nullptr;
    std::string key;
    if (cache) {
        key = candidate_key(bits, segments, regs, &m.observer_regs);
        auto it=cache->entries.find(key);
        if(it==cache->entries.end())it=cache->entries.find(candidate_key(bits,segments,regs));
        if (it != cache->entries.end()) {
            if(it->second->observer_binding) {
                const std::string full_key=candidate_key(bits,segments,regs);
                if(auto hit=cache->rebound_entries.find(full_key);
                   hit!=cache->rebound_entries.end()) {
                    ++stats.stage_d_rebound_hits;
                    Mode mode=instantiate_cached(m,*hit->second,s,classification_only);
                    ++stats.cache_hits;
                    return mode;
                }
                ++stats.stage_d_rebound_misses;
                // Construct a classification-capable template exactly once
                // per full dynamic key. Accepted-entry checks still run below.
                Mode bound=bind_observations(m,*it->second,regs,bits,segments,true);
                if(cache->rebound_entries.size()>=cache->rebound_capacity) {
                    cache->rebound_entries.erase(cache->rebound_order.front());
                    cache->rebound_order.pop_front();
                }
                cache->rebound_entries.emplace(full_key,std::make_shared<const Mode>(bound));
                cache->rebound_order.push_back(full_key);
                Mode mode=instantiate_cached(m,std::move(bound),s,classification_only);
                ++stats.cache_hits;
                return mode;
            }
            Mode mode=instantiate_cached(m,*it->second,s,classification_only);
            ++stats.cache_hits;
            return mode;
        }
    }
    ++stats.mode_cache_misses;
    Assembler a(m, regs, bits, segments);
    Mode mode = a.solve(s, classification_only);
    ++stats.modes;
    for (int i : m.cmps) {
        auto &p = m.parts[i];
        Vector g = input_map(m, mode, p.raw.args[1]);
        g[m.ns] -= number(option(p.raw, "THRESHOLD"));
        bool isheld = is_literal(p.raw.args[1]) || m.signals.at(net_name(p.raw.args[1])).held;
        if (!isheld) {
            bool greater = option(p.raw, "OP") == "GT" || option(p.raw, "OP") == "GE";
            double oriented = (bits.at(i) == greater) ? -1 : 1;
            g *= oriented;
            if (!(g.head(m.ns).isZero(0)))
                mode.binding.edit().guards.push_back({g, i, 1, "CMP"});
        }
    }
    for (int i : m.pwas) {
        auto &p = m.parts[i];
        int seg = segments.at(i);
        auto &curve = p.curve;
        Vector x = Vector::Zero(m.ns + 1);
        bool physical = p.raw.kind != "R";
        if (physical)
            x[p.state] = 1;
        else {
            auto [v, w] = p.ports[0];
            if (v != "0")
                x += mode.binding.read().maps.at("V(" + v + ")");
            if (w != "0")
                x -= mode.binding.read().maps.at("V(" + w + ")");
        }
        const auto &bounds = physical ? curve.y : curve.x;
        bool lower = seg > 0 || !curve.extend, upper = seg + 2 < int(bounds.size()) || !curve.extend;
        if (lower) {
            Vector g = -x;
            g[m.ns] += bounds[seg];
            mode.binding.edit().guards.push_back({g, i, 1, seg == 0 ? "RANGE" : "PWA", seg, seg, -1});
        }
        if (upper) {
            Vector g = x;
            g[m.ns] -= bounds[seg + 1];
            mode.binding.edit().guards.push_back({g, i, 1, seg + 2 == int(bounds.size()) ? "RANGE" : "PWA", seg + 1, seg, 1});
        }
    }
    if (cache) {
        if(!mode.observer_binding)key=candidate_key(bits,segments,regs);
        if (cache->entries.size() >= cache->capacity) {
            cache->entries.erase(cache->insertion_order.front());
            cache->insertion_order.pop_front();
            ++stats.mode_cache_evictions;
        }
        cache->entries.emplace(key, std::make_shared<const Mode>(mode));
        cache->insertion_order.push_back(std::move(key));
        stats.mode_cache_peak_entries =
            std::max(stats.mode_cache_peak_entries, uint64_t(cache->entries.size()));
    }
    if (!classification_only) mode.candidate_roundoff_scale.reset();
    return mode;
}
} // namespace pulse

namespace pulse {
namespace {
struct OriginalEquations {
 Matrix A,B,F,D;
 std::map<std::string,std::vector<int>> branches;
 std::map<std::string,int> reals;
 struct ObserverValue {std::string name;int row;double reference;};
 std::vector<ObserverValue> observer_values;
 bool certified_observer_independence=false;
 mutable Matrix current_rhs_matrix;
 OriginalEquations(const Model&m,const RunState&s){
  std::map<int,bool>bits;for(int i:m.cmps)bits[i]=s.mode.bools.at(net_name(m.parts[i].raw.args[0]));
  Assembler stamp(m,s.regs.read(),bits,s.mode.segments);stamp.stamp();
  A=stamp.A;B=stamp.B;F=stamp.F;D=stamp.D;branches=stamp.branchcol;reals=stamp.realcol;
  current_rhs_matrix=B;
  // A reduced key is permitted only for an independent held-REG subsystem.
  // Derived held expressions can affect additional B rows and are conservatively
  // excluded. Never infer this certificate from signal names or SAVE lists.
  bool safe=!m.observer_regs.empty() &&
            m.observer_signals.size()==m.observer_regs.size();
  for(const auto &name:m.observer_regs){
   auto col=reals.find(name);auto value=s.regs.read().find(name);
   if(!safe||col==reals.end()||value==s.regs.read().end()){safe=false;break;}
   const int row=col->second;
   if(row<0||row>=A.rows()||row>=B.rows()||A(row,row)!=1.){safe=false;break;}
   for(int i=0;i<A.rows();++i){
    if(i!=row && A(i,row)!=0.){safe=false;break;}
    if(i!=row && A(row,i)!=0.){safe=false;break;}
   }
   if(!safe)break;
   for(int j=0;j<B.cols()-1;++j)if(B(row,j)!=0.){safe=false;break;}
   if(!safe || !F.col(row).isZero(0)){safe=false;break;}
   if(B(row,B.cols()-1)!=value->second){safe=false;break;}
   observer_values.push_back({name,row,value->second});
  }
  certified_observer_independence=safe;
  if(!safe)observer_values.clear();
 }
 Vector anchored_rhs(const RunState &s,const Vector &xi)const {
  if(!certified_observer_independence)return B*xi;
  // Rebind certified held observations only, preserving full B*xi arithmetic.
  // This cache is thread-local; its equation objects are not shared across threads.
  for(const auto &o:observer_values)
   current_rhs_matrix(o.row,current_rhs_matrix.cols()-1)=s.regs.read().at(o.name);
  return current_rhs_matrix*xi;
 }
};
thread_local std::map<std::string,std::shared_ptr<OriginalEquations>> original_cache;
thread_local std::deque<std::string> original_order;
thread_local uint64_t original_hits=0,original_builds=0,original_rebound_hits=0,
                     original_certified_builds=0,original_verifications=0;
}
void portfolio_reset_equations(){
 original_cache.clear();original_order.clear();
 original_hits=original_builds=original_rebound_hits=original_certified_builds=original_verifications=0;
}
Json portfolio_original_diagnostics(){
 return {{"checks",original_verifications},{"cache_hits",original_hits},
         {"equation_builds",original_builds},{"certified_builds",original_certified_builds},
         {"rebound_hits",original_rebound_hits}};
}
void portfolio_original_check(const Model&m,const RunState&entry,const Mode&mode,const Vector&xi){
 require(portfolio_variant()==2,12,"STRATEGY_SCOPE","original-equation check requires canonical stamp");
 std::map<int,bool>bits;for(int i:m.cmps)bits[i]=entry.mode.bools.at(net_name(m.parts[i].raw.args[0]));
 ++original_verifications;
 auto full_key=candidate_key(bits,entry.mode.segments,entry.regs.read());
 auto reduced_key=candidate_key(bits,entry.mode.segments,entry.regs.read(),&m.observer_regs);
 auto found=original_cache.find(reduced_key);
 if(found==original_cache.end())found=original_cache.find(full_key);
 std::shared_ptr<OriginalEquations>system;
 if(found!=original_cache.end()){
  system=found->second;++original_hits;
  if(system->certified_observer_independence)++original_rebound_hits;
 }else{
  system=std::make_shared<OriginalEquations>(m,entry);++original_builds;
  if(system->certified_observer_independence)++original_certified_builds;
  const std::string &key=system->certified_observer_independence?reduced_key:full_key;
  if(original_cache.size()>=64){original_cache.erase(original_order.front());original_order.pop_front();}
  original_cache[key]=system;original_order.push_back(key);
 }
 Vector u=Vector::Zero(system->A.cols());
 for(auto&[name,i]:m.nodes)u[i]=mode.binding.read().maps.at("V("+name+")").dot(xi);
 for(auto&[name,cols]:system->branches)for(size_t j=0;j<cols.size();j++)u[cols[j]]=mode.binding.read().maps.at("I("+name+(cols.size()>1?","+std::to_string(j+1):"")+")").dot(xi);
 for(auto&[name,col]:system->reals)u[col]=mode.binding.read().maps.at(name).dot(xi);
 Vector rhs=system->anchored_rhs(entry,xi);
 Vector r=system->A*u-rhs;
 double residual=r.norm()/std::max(1.,rhs.norm());
 require(u.allFinite()&&std::isfinite(residual)&&residual<=1e-8,7,"PORTFOLIO_ORIGINAL_RESIDUAL","original circuit equations exceed unchanged residual budget",true);
 Vector expected=system->F*u+system->D*xi;
 Vector error=physical_increment(m,(mode.definition.read().M*xi).head(m.ns)-expected),scale=physical_increment(m,expected);
 require(error.allFinite()&&error.norm()<=1e-10*std::max(1.,scale.norm()),7,"PORTFOLIO_DYNAMIC_RESIDUAL","original physical derivatives exceed residual budget",true);
}
}
