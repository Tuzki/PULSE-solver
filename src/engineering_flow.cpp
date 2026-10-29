#include "pulse/engineering.hpp"
#include <Eigen/Eigenvalues>
#include <algorithm>
#include <array>
#include <bit>
#include <complex>
#include <cstdlib>
#include <functional>
#include <numbers>
#include <sstream>
#include <unsupported/Eigen/MatrixFunctions>
namespace pulse::engineering {
namespace {
using Complex = std::complex<double>;
using CMatrix = Eigen::MatrixXcd;
using CVector = Eigen::VectorXcd;
struct Basis {
  Matrix generator, lift, reduce, balanced;
  Vector scaling;
  CMatrix vectors, inverse;
  CVector poles;
  bool modal = false;
  bool centered = false;
  Vector center, center_defect, center_residual;
};
std::string key(const Mode &m) {
  std::string s;
  for (const Matrix *a :
       {&m.M, &m.invariant_lift, &m.invariant_generator, &m.invariant_reduce}) {
    auto rows = a->rows(), cols = a->cols();
    s.append(reinterpret_cast<const char *>(&rows), sizeof(rows));
    s.append(reinterpret_cast<const char *>(&cols), sizeof(cols));
    s.append(reinterpret_cast<const char *>(a->data()),
             size_t(a->size()) * sizeof(double));
  }
  return s;
}

// Refine the computed eigenpairs against the original balanced generator.
// Row/column equilibration prevents a finite fast pole from hiding residuals
// in the slower equations. No pole or physical storage coordinate is removed.
void refine_eigenpairs(const Matrix&a,CVector&poles,CMatrix&vectors){
 const int n=a.rows();
 auto residual=[&](const CVector&v,Complex pole){
  CVector r(n);using W=std::complex<long double>;
  for(int i=0;i<n;i++){
   W sum=-W(pole.real(),pole.imag())*W(v[i].real(),v[i].imag());
   for(int j=0;j<n;j++)sum+=static_cast<long double>(a(i,j))*W(v[j].real(),v[j].imag());
   r[i]=Complex(double(sum.real()),double(sum.imag()));
  }return r;
 };
 auto error=[&](const CVector&v,Complex pole,const CVector&r)->double{
  double worst=0;for(int i=0;i<n;i++){
   long double scale=std::abs(pole)*std::abs(v[i]);for(int j=0;j<n;j++)scale+=std::abs(a(i,j))*std::abs(v[j]);
   if(scale>0)worst=std::max(worst,double(std::abs(r[i])/scale));else if(r[i]!=Complex(0))return INFINITY;
  }return worst;
 };
 for(int k=0;k<n;k++){
  CVector v=vectors.col(k);Complex pole=poles[k];int pivot=0;v.cwiseAbs().maxCoeff(&pivot);
  for(int iteration=0;iteration<5;iteration++){
   CVector r=residual(v,pole);double before=error(v,pole,r);
   CMatrix K=CMatrix::Zero(n+1,n+1);K.topLeftCorner(n,n)=a.cast<Complex>();K.topLeftCorner(n,n).diagonal().array()-=pole;
   K.topRightCorner(n,1)=-v;K(n,pivot)=1;CVector rhs=CVector::Zero(n+1);rhs.head(n)=-r;
   Vector rows=Vector::Ones(n+1),cols=rows;
   for(int i=0;i<=n;i++){double z=K.row(i).cwiseAbs().maxCoeff();if(z)rows[i]=1/z;}
   CMatrix scaled=rows.asDiagonal()*K;
   for(int j=0;j<=n;j++){double z=scaled.col(j).cwiseAbs().maxCoeff();if(z)cols[j]=1/z;}
   scaled=scaled*cols.asDiagonal();Eigen::PartialPivLU<CMatrix>factor(scaled);
   CVector correction=cols.asDiagonal()*factor.solve(rows.asDiagonal()*rhs);
   if(!correction.allFinite())break;
   CVector next=v+correction.head(n);Complex next_pole=pole+correction[n];
   if(!next.allFinite()||!std::isfinite(std::abs(next_pole)))break;
   double after=error(next,next_pole,residual(next,next_pole));
   if(!(after<=before))break;
   v=next;pole=next_pole;
   if(correction.head(n).norm()<=4*std::numeric_limits<double>::epsilon()*v.norm()&&std::abs(correction[n])<=4*std::numeric_limits<double>::epsilon()*std::max(1.,std::abs(pole)))break;
  }
  vectors.col(k)=v;poles[k]=pole;
 }
}
std::shared_ptr<Basis> basis(const Mode &mode) {
  static thread_local std::map<std::string, std::shared_ptr<Basis>> cache;
  auto id = key(mode);
  if (auto it = cache.find(id); it != cache.end())
    return it->second;
  auto b = std::make_shared<Basis>();
  const int physical = int(mode.M.rows()) - 1;
  if (mode.invariant_generator.size()) {
    b->generator = mode.invariant_generator;
    const int free = int(b->generator.rows()) - 1;
    b->lift = mode.invariant_lift.topLeftCorner(physical, free);
    b->reduce = mode.invariant_reduce.topRows(free);
  } else {
    b->generator = mode.M;
    b->lift = Matrix::Identity(physical, physical);
    b->reduce = Matrix::Zero(physical, physical + 1);
    b->reduce.leftCols(physical).setIdentity();
  }
  const int n = int(b->generator.rows()) - 1;
  b->balanced = b->generator;
  b->scaling = Vector::Ones(n + 1);
  // Power-of-two Osborne balancing keeps physical units out of the spectral
  // conditioning. The homogeneous coordinate is not rescaled.
  for (int pass = 0; pass < 32; ++pass) {
    bool changed = false;
    for (int i = 0; i < n; ++i) {
      double row = 0, col = 0;
      for (int j = 0; j < n; ++j)
        if (i != j) {
          row += std::abs(b->balanced(i, j));
          col += std::abs(b->balanced(j, i));
        }
      if (!(row > 0 && col > 0))
        continue;
      int shift =
          std::clamp(int(std::round(.5 * std::log2(row / col))), -32, 32);
      double f = std::ldexp(1., shift);
      if (shift && row / f + col * f < .95 * (row + col) &&
          std::abs(std::log2(b->scaling[i])) + std::abs(shift) < 200) {
        b->balanced.row(i) /= f;
        b->balanced.col(i) *= f;
        b->scaling[i] *= f;
        changed = true;
      }
    }
    if (!changed)
      break;
  }
  if (n > 0) {
    Matrix a = b->balanced.topLeftCorner(n, n);
    // A particular affine state is computed independently of modal residues.
    // Equilibrating equations/unknowns avoids a rank decision based on the
    // ratio of the fastest and slowest poles. Singular systems retain the
    // existing phi/integrator path; no inverse or steady state is presumed.
    Vector rs=Vector::Ones(n),cs=Vector::Ones(n);
    for(int i=0;i<n;i++){double q=a.row(i).cwiseAbs().maxCoeff();if(q)rs[i]=1/q;}
    Matrix equilibrated=rs.asDiagonal()*a;
    for(int j=0;j<n;j++){double q=equilibrated.col(j).cwiseAbs().maxCoeff();if(q)cs[j]=1/q;}
    equilibrated=equilibrated*cs.asDiagonal();
    Eigen::FullPivLU<Matrix> affine_lu(equilibrated);
    affine_lu.setThreshold(64*std::numeric_limits<double>::epsilon()*std::max(1,n));
    if(affine_lu.isInvertible()){
      const Vector forcing=b->balanced.topRightCorner(n,1);
      b->center=cs.asDiagonal()*affine_lu.solve(rs.asDiagonal()*(-forcing));
      Vector defect(n);
      for(int i=0;i<n;i++){
        long double v=forcing[i];for(int j=0;j<n;j++)v+=static_cast<long double>(a(i,j))*b->center[j];defect[i]=double(v);
      }
      b->center_residual=defect;
      b->center_defect=cs.asDiagonal()*affine_lu.solve(rs.asDiagonal()*defect);
      Vector scale=a.cwiseAbs()*b->center.cwiseAbs()+forcing.cwiseAbs();
      double backward=0;for(int i=0;i<n;i++)backward=std::max(backward,std::abs(defect[i])/std::max(1e-300,scale[i]));
      b->centered=b->center.allFinite()&&b->center_defect.allFinite()&&backward<=64*std::numeric_limits<double>::epsilon()*std::max(1,n);
    }
    Eigen::ComplexEigenSolver<Matrix> eig(a);
    if (eig.info() == Eigen::Success) {
      b->poles = eig.eigenvalues();
      if((b->poles.array()==Complex(0)).any())b->centered=false;
      b->vectors = eig.eigenvectors();
      refine_eigenpairs(a,b->poles,b->vectors);
      Eigen::FullPivLU<CMatrix> lu(b->vectors);
      if (lu.isInvertible() && lu.rcond() > 1e-11) {
        b->inverse = lu.inverse();
        double residual = (a.cast<Complex>() * b->vectors -
                           b->vectors * b->poles.asDiagonal())
                              .norm() /
                          std::max(1., a.norm());
        b->modal = std::isfinite(residual) && residual < 1e-10;
      }
    }
  } else
    b->modal = true;
  if (cache.size() >= 128)
    cache.erase(cache.begin());
  cache.emplace(std::move(id), b);
  return b;
}
Complex phi(Complex pole, double t) {
  Complex z = pole * t;
  if (std::abs(z) < 1e-4) {
    Complex term(1), sum(1);
    for (int k = 1; k < 20; ++k) {
      term *= z / double(k + 1);
      sum += term;
    }
    return t * sum;
  }
  return (std::exp(z) - Complex(1)) / pole;
}
Range add(Range a, Range b) { return {a.lo + b.lo, a.hi + b.hi}; }
Range multiply(Range a, Range b) {
  double v[] = {a.lo * b.lo, a.lo * b.hi, a.hi * b.lo, a.hi * b.hi};
  return {*std::min_element(v, v + 4), *std::max_element(v, v + 4)};
}
Range trig(double a, double b, bool cosine) {
  if (a > b)
    std::swap(a, b);
  constexpr double pi = std::numbers::pi;
  if (b - a >= 2 * pi || std::max(std::abs(a), std::abs(b)) > 1e14)
    return {-1, 1};
  if (cosine) {
    a += pi / 2;
    b += pi / 2;
  }
  double lo = std::min(std::sin(a), std::sin(b)),
         hi = std::max(std::sin(a), std::sin(b));
  if (std::ceil((a - pi / 2) / (2 * pi)) <= std::floor((b - pi / 2) / (2 * pi)))
    hi = 1;
  if (std::ceil((a + pi / 2) / (2 * pi)) <= std::floor((b + pi / 2) / (2 * pi)))
    lo = -1;
  return {lo, hi};
}
struct Term {
  Complex pole, coefficient;
  Complex forcing = Complex(0);
  bool affine_increment = false;
};
struct Functional {
  double constant = 0, linear = 0;
  bool increment_form = false;
  std::vector<Term> terms;
};
} // namespace
struct FlowData {
  Mode mode;
  Vector initial, reduced, scaled;
  std::shared_ptr<Basis> basis;
  CVector y, forcing, center_shift;
  std::vector<Functional> guards;
  mutable std::map<std::string,std::shared_ptr<FlowData>> observable_cache;
  // Local scalar Taylor evaluation is anchored at the committed physical
  // point. It avoids subtracting nearly cancelling spectral residues when
  // deciding the direction immediately after a constitutive knot.
  static constexpr int local_degree = 24;
  double local_rate = 1;
  mutable bool local_ready = false;
  mutable std::vector<std::array<long double, local_degree + 1>> local;
  mutable std::vector<std::array<long double, local_degree + 1>> local_absolute;
  mutable std::vector<long double> local_scale;
  mutable std::vector<Eigen::Matrix<long double, Eigen::Dynamic, 1>> local_state;
  mutable std::map<double, Vector> points;
};
namespace {
void prepare_local(FlowData &d) {
  if (d.local_ready) return;
  using Wide = long double;
  using WMatrix = Eigen::Matrix<Wide, Eigen::Dynamic, Eigen::Dynamic>;
  using WVector = Eigen::Matrix<Wide, Eigen::Dynamic, 1>;
  const auto &b = *d.basis;
  const int n = int(b.generator.rows()) - 1;
  WVector z = WVector::Ones(n + 1);
  if (n) z.head(n) = (b.reduce.cast<Wide>() * d.initial.cast<Wide>()).cwiseQuotient(b.scaling.head(n).cast<Wide>());
  WMatrix a = b.balanced.cast<Wide>() / Wide(d.local_rate);
  WVector absolute_z = z.cwiseAbs();
  std::vector<WVector> projected;
  d.local.resize(d.mode.guards.size());
  d.local_state.resize(FlowData::local_degree + 1);
  d.local_state[0] = z;
  d.local_absolute.resize(d.mode.guards.size());
  d.local_scale.resize(d.mode.guards.size());
  for (size_t k = 0; k < d.mode.guards.size(); ++k) {
    const auto &g = d.mode.guards[k];
    WVector p = WVector::Zero(n + 1);
    if (n) p.head(n) = (b.lift.cast<Wide>().transpose() * g.row.head(d.initial.size() - 1).cast<Wide>()).cwiseProduct(b.scaling.head(n).cast<Wide>());
    projected.push_back(p);
    d.local[k][0] = Wide(g.row.dot(d.initial));
    d.local_absolute[k][0] = g.row.cast<Wide>().cwiseAbs().dot(d.initial.cast<Wide>().cwiseAbs());
    d.local_scale[k] = p.cwiseAbs().sum() * z.cwiseAbs().maxCoeff();
  }
  for (int j = 1; j <= FlowData::local_degree; ++j) {
    z = (a * z / Wide(j)).eval();
    d.local_state[j] = z;
    absolute_z = (a.cwiseAbs() * absolute_z / Wide(j)).eval();
    for (size_t k = 0; k < projected.size(); ++k) {
      d.local[k][j] = projected[k].dot(z);
      d.local_absolute[k][j] = projected[k].cwiseAbs().dot(absolute_z);
    }
  }
  d.local_ready = true;
}
std::array<long double, FlowData::local_degree + 1>
local_coefficients(FlowData &d, size_t k, int order) {
  prepare_local(d);
  std::array<long double, FlowData::local_degree + 1> out{};
  for (int j = order; j <= FlowData::local_degree; ++j) {
    long double c = d.local[k][j];
    for (int r = 0; r < order; ++r) c *= (j - r) * static_cast<long double>(d.local_rate);
    out[j - order] = c;
  }
  return out;
}
long double local_tail(const FlowData &d, size_t k, long double q, int order) {
  long double tail = d.local_scale[k] * std::exp(q);
  for (int j = 1; j <= FlowData::local_degree + 1 - order; ++j) tail *= q / j;
  for (int j = 0; j < order; ++j) tail *= d.local_rate;
  return tail;
}
} // namespace
Flow::Flow(const Mode &mode, const Vector &initial)
    : data_(std::make_shared<FlowData>()) {
  require(!mode.classification_only, 12, "UNACCEPTED_CANDIDATE",
          "region-classification candidate cannot be propagated");
  auto &d = *data_;
  d.mode = mode;
  d.initial = initial;
  d.basis = basis(mode);
  auto &b = *d.basis;
  double rate = b.balanced.cwiseAbs().rowwise().sum().maxCoeff();
  if (rate > 0 && std::isfinite(rate))
    d.local_rate = std::exp2(std::ceil(std::log2(rate)));
  int n = int(b.generator.rows()) - 1;
  d.reduced = b.reduce * initial;
  d.scaled = Vector::Ones(n + 1);
  d.scaled.head(n) = d.reduced.cwiseQuotient(b.scaling.head(n));
  if (b.modal && n) {
    d.y = b.inverse * d.scaled.head(n).cast<Complex>();
    d.forcing = b.inverse * b.balanced.topRightCorner(n, 1).cast<Complex>();
    if(b.centered){
      d.center_shift=b.inverse*b.center_residual.cast<Complex>();
      for(int j=0;j<n;j++){
        require(b.poles[j]!=Complex(0),7,"AFFINE_PARTICULAR_UNRESOLVED","nonsingular particular decomposition produced an unresolved zero pole",true);
        d.center_shift[j]/=b.poles[j];
      }
    }
  }
  for (auto &guard : mode.guards) {
    Functional g;
    g.constant = guard.row.dot(initial);
    if (b.modal && n) {
      auto projected = (guard.row.head(initial.size() - 1).transpose() *
                        b.lift * b.scaling.head(n).asDiagonal())
                           .eval();
      Eigen::RowVectorXcd row = projected.cast<Complex>() * b.vectors;
      if(b.centered){
        Vector center_state=initial;
        center_state.head(initial.size()-1)+=b.lift*(b.center.cwiseProduct(b.scaling.head(n))-d.reduced);
        Functional centered;
        centered.constant=guard.row.dot(center_state)-(row*d.center_shift).value().real();
        const CVector amplitude=(b.inverse*(d.scaled.head(n)-b.center).cast<Complex>()+d.center_shift).eval();
        double centered_cost=guard.row.cwiseAbs().dot(center_state.cwiseAbs())+std::abs((row*d.center_shift).value());
        double increment_cost=std::abs(g.constant);
        for(int j=0;j<n;j++){
          const Complex c=row[j]*amplitude[j];centered.terms.push_back({b.poles[j],c});centered_cost+=std::abs(c);
          increment_cost+=std::abs(row[j]*d.y[j])+std::abs(row[j]*d.forcing[j])/d.local_rate;
        }
        // Keep the established low-cancellation centered path when well scaled.
        // A remote equilibrium of a genuine near-zero pole must not manufacture
        // huge coefficients: select the equivalent affine increment instead.
        if(std::isfinite(centered_cost)&&centered_cost<=8*std::max(1e-300,increment_cost)){
          d.guards.push_back(std::move(centered));continue;
        }
      }
      // Keep well-scaled exponential residues to retain their accurate small
      // decaying tails. Only unsafe affine quotients use the phi increment.
      // Both forms retain the complete pole and forcing contribution.
      g.increment_form = true;
      double reference_cost=std::abs(g.constant);
      for(int j=0;j<n;j++)reference_cost+=std::abs(row[j]*d.y[j])+std::abs(row[j]*d.forcing[j])/d.local_rate;
      g.constant-=(row*d.y).value().real();
      for(int j=0;j<n;j++){
        const Complex a=row[j]*d.y[j],forcing=row[j]*d.forcing[j];
        const long double pole=std::abs(b.poles[j]);
        const long double projected_shift=pole>0?std::abs(forcing)/pole:INFINITY;
        const long double raw_shift=pole>0?std::abs(d.forcing[j])/pole:INFINITY;
        if(pole==0 || projected_shift>8*std::max(1e-300,reference_cost) || raw_shift>std::numeric_limits<double>::max()/4){
          g.constant+=a.real();
          g.terms.push_back({b.poles[j],a,forcing,true});
        }else{
          Complex shift=d.forcing[j]/b.poles[j];
          g.constant-=(row[j]*shift).real();
          g.terms.push_back({b.poles[j],row[j]*(d.y[j]+shift)});
        }
      }

    }
    d.guards.push_back(std::move(g));
  }
  d.points.emplace(0, initial);
}
Vector Flow::state(double t) const {
  t += offset_.seconds();
  require(t >= 0 && std::isfinite(t), 7, "TIME_ORDER",
          "invalid engineering propagation time", true);
  auto &d = *data_;
  if (auto it = d.points.find(t); it != d.points.end())
    return it->second;
  auto &b = *d.basis;
  const int n = int(b.generator.rows()) - 1;
  if (t * d.local_rate <= .5) {
    prepare_local(d);
    using WVector = Eigen::Matrix<long double, Eigen::Dynamic, 1>;
    const long double q = static_cast<long double>(t) * d.local_rate;
    WVector increment = WVector::Zero(n);
    for (int j = FlowData::local_degree; j >= 1; --j)
      increment = (increment * q + d.local_state[j].head(n)).eval();
    increment *= q;
    WVector physical = b.lift.cast<long double>() * increment.cwiseProduct(b.scaling.head(n).cast<long double>());
    Vector out = d.initial;
    for (int i = 0; i < out.size() - 1; ++i)
      out[i] = double(static_cast<long double>(d.initial[i]) + physical[i]);
    out[out.size() - 1] = 1;
    require(out.allFinite(), 7, "NONFINITE_PROPAGATION", "local affine flow is nonfinite", true);
    if (d.points.size() < 4096) d.points.emplace(t, out);
    return out;
  }
  Vector out = d.initial;
  if (b.modal && b.centered) {
    // Compute each physical storage coordinate from the original anchor.
    // Use the lower-operation-scale form (absolute or expm1 increment).
    const CVector amp=(b.inverse*(d.scaled.head(n)-b.center).cast<Complex>() +
                       d.center_shift).eval();
    for(int i=0;i<out.size()-1;i++){
      const Eigen::RowVectorXd projected=b.lift.row(i)*b.scaling.head(n).asDiagonal();
      const Eigen::RowVectorXcd row=projected.cast<Complex>()*b.vectors;
      long double absolute=static_cast<long double>(d.initial[i]);
      long double increment=absolute, abs_scale=std::abs(absolute), inc_scale=abs_scale;
      for(int j=0;j<n;j++) absolute+=static_cast<long double>(b.lift(i,j))*(
        static_cast<long double>(b.scaling[j])*b.center[j]-d.reduced[j]);
      absolute-=(row*d.center_shift).value().real();abs_scale=std::abs(absolute);
      for(int j=0;j<n;j++){
        Complex c=row[j]*amp[j], e=std::exp(b.poles[j]*t);
        Complex delta=b.poles[j]*phi(b.poles[j],t);
        absolute+=(c*e).real(); increment+=(c*delta).real();
        abs_scale+=std::abs(c*e);inc_scale+=std::abs(c*delta);
      }
      out[i]=double(inc_scale<abs_scale?increment:absolute);
    }
  } else {
    Vector z(n);
    if(b.modal){
      CVector y(n);for(int j=0;j<n;j++)y[j]=std::exp(b.poles[j]*t)*d.y[j]+phi(b.poles[j],t)*d.forcing[j];
      CVector answer=b.vectors*y;z=answer.real().cwiseProduct(b.scaling.head(n));
      require(answer.imag().norm()<=1e-7*std::max(1.,answer.real().norm()),7,
        "MODAL_COMPLEX_RESIDUAL","engineering flow has excessive imaginary residual",true);
    } else {Vector a=(b.balanced*t).exp()*d.scaled;z=a.head(n).cwiseProduct(b.scaling.head(n));}
    out.head(out.size()-1)+=b.lift*(z-d.reduced);
  }
  out[out.size() - 1] = 1;
  require(out.allFinite(), 7, "NONFINITE_PROPAGATION",
          "engineering matrix exponential is nonfinite", true);
  if (d.points.size() < 4096)
    d.points.emplace(t, out);
  return out;
}
double Flow::value(size_t k, double t, int order) const {
  t += offset_.seconds();
  auto &d = *data_;
  if (t == 0 && order == 0)
    return d.mode.guards.at(k).row.dot(d.initial);
  if (order <= 1 && t * d.local_rate <= .5) {
    const auto coefficients = local_coefficients(d, k, order);
    const long double q = static_cast<long double>(t) * d.local_rate;
    long double value = 0;
    for (int j = FlowData::local_degree - order; j >= 0; --j)
      value = value * q + coefficients[j];
    return double(value);
  }
  if (!d.basis->modal) {
    Vector row = d.mode.guards.at(k).row;
    for (int j = 0; j < order; ++j)
      row = (row.transpose() * d.mode.M).transpose();
    return row.dot(state(t - offset_.seconds()));
  }
  const auto &g = d.guards.at(k);
  if(g.increment_form){
    using W=std::complex<long double>;
    long double value=order==0?g.constant:0;
    for(const auto &term:g.terms){
      if(!term.affine_increment){
        Complex c=term.coefficient;for(int j=0;j<order;j++)c*=term.pole;
        value+=(c*std::exp(term.pole*t)).real();continue;
      }
      W pole(term.pole.real(),term.pole.imag()),a(term.coefficient.real(),term.coefficient.imag()),forcing(term.forcing.real(),term.forcing.imag());
      W rate=pole*a+forcing;
      if(order==0){auto ph=phi(term.pole,t);value+=(rate*W(ph.real(),ph.imag())).real();}
      else {for(int j=1;j<order;j++)rate*=pole;value+=(rate*std::exp(pole*static_cast<long double>(t))).real();}
    }
    return double(value);
  }
  long double value = order == 0   ? g.constant + g.linear * t
                      : order == 1 ? g.linear
                                   : 0;
  for (auto &term : g.terms) {
    Complex c = term.coefficient;
    for (int j = 0; j < order; ++j)
      c *= term.pole;
    value += (c * std::exp(term.pole * t)).real();
  }
  return double(value);
}
Range Flow::bounds(size_t k, double a, double b, int order) const {
  a += offset_.seconds(); b += offset_.seconds();
  auto &d = *data_;
  if (order <= 1 && b * d.local_rate <= .5) {
    const auto coefficients = local_coefficients(d, k, order);
    const int degree = FlowData::local_degree - order;
    const long double mid = (static_cast<long double>(a) + b) * .5L * d.local_rate;
    const long double half = (static_cast<long double>(b) - a) * .5L * d.local_rate;
    // Horner translation to powers of u in [-1,1], combining coefficients
    // before bounding them. All values and derivative bounds use one flow.
    std::array<long double, FlowData::local_degree + 1> centered{};
    for (int j = degree; j >= 0; --j) {
      for (int r = degree; r >= 1; --r)
        centered[r] = centered[r] * mid + centered[r - 1] * half;
      centered[0] = centered[0] * mid + coefficients[j];
    }
    long double lo = centered[0], hi = lo, magnitude = std::abs(lo);
    for (int j = 1; j <= degree; ++j) {
      const long double c = centered[j];
      lo += j % 2 ? -std::abs(c) : std::min(0.L, c);
      hi += j % 2 ? std::abs(c) : std::max(0.L, c);
      magnitude += std::abs(c);
    }
    // Componentwise operation scale, not ||row||*||state||: the latter can
    // invent order-one slope uncertainty after harmless unit balancing.
    long double operation_scale = 0;
    const long double q = static_cast<long double>(b) * d.local_rate;
    for (int j = FlowData::local_degree; j >= order; --j) {
      long double c = d.local_absolute[k][j];
      for (int r = 0; r < order; ++r) c *= (j - r) * static_cast<long double>(d.local_rate);
      operation_scale = operation_scale * q + c;
    }
    const long double pad =
        64 * (FlowData::local_degree + 1) * d.basis->balanced.rows() *
            std::numeric_limits<long double>::epsilon() * operation_scale +
        64 * std::numeric_limits<double>::epsilon() * magnitude +
        local_tail(d, k, static_cast<long double>(b) * d.local_rate, order);
    return {double(lo - pad), double(hi + pad)};
  }
  if (!d.basis->modal) {
    // Taylor enclosure of the numerical point trajectory around the middle.
    // Nilpotent INT chains terminate exactly; other cases subdivide when
    // the scaled generator is too large. No output-grid integration occurs.
    double mid = (a + b) * .5, h = (b - a) * .5;
    Vector row = d.mode.guards.at(k).row;
    for (int j = 0; j < order; ++j)
      row = (row.transpose() * d.mode.M).transpose();
    Vector x = state(mid - offset_.seconds()), term = x;
    Range result{row.dot(x), row.dot(x)};
    double q = d.basis->balanced.cwiseAbs().rowwise().sum().maxCoeff() * h;
    if (q > 16)
      return {-INFINITY, INFINITY};
    bool terminated = false;
    for (int j = 1; j <= 64; ++j) {
      term = d.mode.M * term * (h / j);
      if (term.isZero(0)) {
        terminated = true;
        break;
      }
      double c = row.dot(term);
      result = add(result, j % 2 ? Range{-std::abs(c), std::abs(c)}
                                 : Range{std::min(0., c), std::max(0., c)});
    }
    if (!terminated) {
      double tail = std::exp(q);
      for (int j = 1; j <= 65; ++j)
        tail *= q / j;
      double error = tail * (1 + std::abs(row.dot(x)));
      result.lo -= error;
      result.hi += error;
    }
    // The reconstructed midpoint is itself rounded. Enclose its arithmetic
    // scale as well as interval variation; a zero-width interval must not
    // pretend that a cancelling nilpotent polynomial was evaluated exactly.
    Vector absolute=d.initial.cwiseAbs(), absolute_term=absolute;
    const Matrix absolute_generator=d.mode.M.cwiseAbs();
    for(int j=1;j<=64;j++){
      absolute_term=absolute_generator*absolute_term*(mid/j);
      absolute+=absolute_term;
      if(absolute_term.isZero(0))break;
    }
    const double evaluation_pad=64*(d.mode.M.rows()+1)*std::numeric_limits<double>::epsilon()*
                                row.cwiseAbs().dot(absolute);
    result.lo-=evaluation_pad;result.hi+=evaluation_pad;
    return result;
  }
  const auto &g = d.guards.at(k);
  if(g.increment_form){
    using W=std::complex<long double>;
    std::array<long double,25> coefficients{};
    coefficients[0]=order==0?g.constant:0;
    const double mid=a+(b-a)*.5,h=(b-a)*.5;
    Range result{};long double magnitude=std::abs(coefficients[0]),tail=0;
    for(const auto &term:g.terms){
      W pole(term.pole.real(),term.pole.imag()),amp(term.coefficient.real(),term.coefficient.imag()),forcing(term.forcing.real(),term.forcing.imag());
      const bool integral=term.affine_increment;
      W rate=integral?pole*amp+forcing:amp;
      if(integral){if(order>0)for(int j=1;j<order;j++)rate*=pole;}
      else for(int j=0;j<order;j++)rate*=pole;
      double q=std::abs(term.pole)*h;
      const long double expmax=std::exp(std::max(pole.real()*a,pole.real()*b));
      if(q<=2){
        W coefficient=rate*std::exp(pole*static_cast<long double>(mid));
        if(order==0 && integral){
          auto ph=phi(term.pole,mid);coefficients[0]+=(rate*W(ph.real(),ph.imag())).real();
          const double absolute_integral=phi(Complex(term.pole.real(),0),mid).real();
          magnitude+=(std::abs(pole*amp)+std::abs(forcing))*absolute_integral;
          coefficient*=static_cast<long double>(h);
          for(size_t j=1;j<coefficients.size();j++){
            coefficients[j]+=coefficient.real();coefficient*=pole*static_cast<long double>(h)/static_cast<long double>(j+1);
          }
          long double rem=std::abs(rate)*expmax*h;
          for(int j=2;j<=25;j++)rem*=q/j;
          tail+=rem;
        }else{
          magnitude+=std::abs(rate)*expmax;
          for(size_t j=0;j<coefficients.size();j++){
            coefficients[j]+=coefficient.real();coefficient*=pole*static_cast<long double>(h)/static_cast<long double>(j+1);
          }
          long double rem=std::abs(rate)*expmax;
          for(int j=1;j<=25;j++)rem*=q/j;
          tail+=rem;
        }
        continue;
      }
      // A nonzero pole is used as an exponential quotient only when its
      // variation across this interval is large; never in the near-zero branch.
      W c=(order==0&&integral)?rate/pole:rate;
      auto cosine=trig(term.pole.imag()*a,term.pole.imag()*b,true);
      auto sine=trig(term.pole.imag()*a,term.pole.imag()*b,false);
      Range wave=add(multiply({double(c.real()),double(c.real())},cosine),multiply({double(-c.imag()),double(-c.imag())},sine));
      double e1=std::exp(term.pole.real()*a),e2=std::exp(term.pole.real()*b);
      Range component=multiply({std::min(e1,e2),std::max(e1,e2)},wave);
      if(order==0&&integral)component=add(component,{double(-c.real()),double(-c.real())});
      result=add(result,component);magnitude+=std::abs(c)*(expmax+(order==0&&integral?1:0));
    }
    result=add(result,{double(coefficients[0]),double(coefficients[0])});
    for(size_t j=1;j<coefficients.size();j++){
      double c=double(coefficients[j]);magnitude+=std::abs(coefficients[j]);
      result=add(result,j%2?Range{-std::abs(c),std::abs(c)}:Range{std::min(0.,c),std::max(0.,c)});
    }
    const long double pad=64*std::numeric_limits<double>::epsilon()*magnitude+tail;
    return {double(result.lo-pad),double(result.hi+pad)};
  }
  Range result = order == 0   ? Range{g.constant, g.constant}
                 : order == 1 ? Range{g.linear, g.linear}
                              : Range{};
  if (order == 0)
    result = add(result, multiply({g.linear, g.linear}, {a, b}));
  double magnitude = std::max(std::abs(result.lo), std::abs(result.hi));
  std::array<long double, 25> coefficients{};
  double mid = a + (b - a) * .5, h = (b - a) * .5, tail = 0;
  for (auto &term : g.terms) {
    Complex c = term.coefficient;
    for (int j = 0; j < order; ++j)
      c *= term.pole;
    double q = std::abs(term.pole) * h;
    if (q <= 2) {
      // Combine scalar Taylor coefficients before taking absolute values.
      // Closely spaced poles often have large, cancelling residues; bounding
      // each exponential independently would invent a huge guard variation.
      using Wide = std::complex<long double>;
      Wide pole(term.pole.real(), term.pole.imag());
      Wide coefficient(c.real(), c.imag());
      coefficient *= std::exp(pole * static_cast<long double>(mid));
      for (size_t j = 0; j < coefficients.size(); ++j) {
        coefficients[j] += coefficient.real();
        coefficient *= pole * static_cast<long double>(h) /
                       static_cast<long double>(j + 1);
      }
      double remainder = std::abs(c) * std::exp(std::max(term.pole.real() * a,
                                                         term.pole.real() * b));
      magnitude += remainder;
      for (int j = 1; j <= 25; ++j)
        remainder *= q / j;
      tail += remainder * std::exp(q);
      continue;
    }
    auto cosine = trig(term.pole.imag() * a, term.pole.imag() * b, true);
    auto sine = trig(term.pole.imag() * a, term.pole.imag() * b, false);
    Range wave = add(multiply({c.real(), c.real()}, cosine),
                     multiply({-c.imag(), -c.imag()}, sine));
    double e1 = std::exp(term.pole.real() * a),
           e2 = std::exp(term.pole.real() * b);
    Range component = multiply({std::min(e1, e2), std::max(e1, e2)}, wave);
    result = add(result, component);
    magnitude += std::max(std::abs(component.lo), std::abs(component.hi));
  }
  result = add(result, {double(coefficients[0]), double(coefficients[0])});
  for (size_t j = 1; j < coefficients.size(); ++j) {
    double c = double(coefficients[j]);
    result = add(result, j % 2 ? Range{-std::abs(c), std::abs(c)}
                               : Range{std::min(0., c), std::max(0., c)});
  }
  double pad = 64 * std::numeric_limits<double>::epsilon() * magnitude;
  return {result.lo - pad - tail, result.hi + pad + tail};
}
double Flow::tangent(const Mode &mode,const Vector &initial,const Vector &row){
  auto b=basis(mode);const int n=int(b->generator.rows())-1;
  using WVector=Eigen::Matrix<long double,Eigen::Dynamic,1>;
  WVector z=WVector::Ones(n+1);
  if(n)z.head(n)=(b->reduce.cast<long double>()*initial.cast<long double>()).cwiseQuotient(b->scaling.head(n).cast<long double>());
  WVector dz=b->balanced.cast<long double>()*z;
  WVector projected=(b->lift.cast<long double>().transpose()*row.head(initial.size()-1).cast<long double>()).cwiseProduct(b->scaling.head(n).cast<long double>());
  return double(projected.dot(dz.head(n)));
}
bool Flow::compatible(const Mode &m) const {
  const auto &old=data_->mode;
  auto same=[](const Matrix&a,const Matrix&b){return a.rows()==b.rows()&&a.cols()==b.cols()&&(a.array()==b.array()).all();};
  if(m.numerical_strategy!=old.numerical_strategy||key(m)!=key(old)||m.segments!=old.segments||
     !same(m.constraints,old.constraints)||!same(m.residual_map,old.residual_map)||
     !same(m.residual_reference,old.residual_reference)||m.maps.size()!=old.maps.size())return false;
  for(const auto &[name,row]:old.maps){
    auto it=m.maps.find(name);
    if(it==m.maps.end())return false;
    // BOOL projections are control snapshots, not electrical observations.
    // All real-valued maps (including source values) still require equality.
    if(old.bools.count(name)&&m.bools.count(name))continue;
    if(!same(row,it->second))return false;
  }
  return true;
}
Flow Flow::continued(const Mode &m,double elapsed) const {
  require(compatible(m)&&elapsed>=0,12,"FLOW_INCOMPATIBLE","electrical trajectory cannot continue across incompatible equations or maps");
  // Reproject guards from the ORIGINAL anchor, never from a public snapshot.
  Flow next(m,data_->initial);next.offset_=offset_+Time::from(elapsed);return next;
}
double Flow::observe(const Vector &row,double t,int derivative) const {
  // Project an arbitrary observable on this same continuous trajectory.
  for(size_t k=0;k<data_->mode.guards.size();k++){
    const auto &g=data_->mode.guards[k].row;
    if(g.size()==row.size()&&(g.array()==row.array()).all())return value(k,t,derivative);
    if(g.size()==row.size()&&(g.array()==-row.array()).all())return -value(k,t,derivative);
  }
  std::string id(reinterpret_cast<const char*>(row.data()),size_t(row.size())*sizeof(double));
  auto found=data_->observable_cache.find(id);
  if(found==data_->observable_cache.end()){
    Mode view=data_->mode;view.maps.clear();view.bools.clear();
    view.guards.clear();view.guards.push_back({row,0,1,"OBSERVE"});
    Flow projection(view,data_->initial);
    found=data_->observable_cache.emplace(std::move(id),projection.data_).first;
  }
  Flow projection=*this;projection.data_=found->second;
  return projection.value(0,t,derivative);
}
double Flow::scale(size_t k) const {
  const auto &g = data_->guards.at(k);
  double sum = std::abs(g.constant);
  for (auto &term : g.terms){
    sum += std::abs(term.coefficient);
    if(g.increment_form && term.affine_increment){
      // Engineering anchor/elapsed scale, not a strict all-history certificate.
      // Preserve time units without a forcing/near-zero-pole coefficient.
      const double horizon=std::max(offset_.seconds(),1/data_->local_rate);
      sum += std::abs(term.forcing)*phi(Complex(term.pole.real(),0),horizon).real();
    }
  }
  return std::max(1e-300, sum);
}
bool Flow::stationary(size_t k) const {
  Vector row =
      (data_->mode.guards.at(k).row.transpose() * data_->mode.M).transpose();
  return row.isZero(0);
}
bool Flow::modal() const { return data_->basis->modal; }
// Resolve incoming direction on the same trajectory, without a root-time veto.
void validate_event_timing(const Flow &flow, const Crossing &root, double atom) {
 require(std::isfinite(root.slope)&&root.slope>0&&std::isfinite(atom)&&atom>0,
         8,"ROOT_DIRECTION_UNRESOLVED","located root needs a finite directed slope",true);
 const auto direction=flow.bounds(root.guard,root.time,root.time,1);
 require(std::isfinite(direction.lo)&&direction.lo>0,8,"ROOT_DIRECTION_UNRESOLVED",
         "incoming derivative is not resolved above its evaluation roundoff",true);
 // The nonmodal path evaluates guards through a rounded reconstructed state,
 // while the modal path evaluates value and slope directly on one scalar
 // expression. This additional reconstruction-risk check applies to the
 // former path; a broad modal coefficient envelope is not a timing certificate
 // and must not become an implicit veto of the user's point-event policy.
 if(flow.modal())return;
 // A rounded value can create a false transverse root near a flat crossing.
 // Resolve direction over the local value-roundoff neighborhood, not just at
 // the rounded point. This neither changes atomic membership nor compares the
 // neighborhood's width to T_atom; it is not an absolute timing-accuracy veto.
 const double value=flow.value(root.guard,root.time);
 const auto evaluated=flow.bounds(root.guard,root.time,root.time);
 const double radius=std::max(std::abs(value-evaluated.lo),std::abs(evaluated.hi-value));
 const double neighborhood=radius/direction.lo;
 require(std::isfinite(neighborhood),8,"ROOT_DIRECTION_UNRESOLVED",
         "root value roundoff has no finite direction neighborhood",true);
 const auto incoming=flow.bounds(root.guard,std::max(0.,root.lower-neighborhood),
                                 root.upper+neighborhood,1);
 require(std::isfinite(incoming.lo)&&incoming.lo>0,8,"ROOT_DIRECTION_UNRESOLVED",
         "incoming direction is unresolved across local value roundoff",true);

}
SearchResult next_events(const Mode &mode, const Flow &flow, double horizon,
                         double atom, size_t budget) {
  SearchResult result;
  const double tolerance =
      std::max(atom / 64, std::numeric_limits<double>::denorm_min());
  for (size_t k = 0; k < mode.guards.size(); ++k) {
    double initial = flow.value(k, 0), slope = flow.value(k, 0, 1);
    const double initial_roundoff =
        64 * std::numeric_limits<double>::epsilon() * flow.scale(k);
    require(initial <= initial_roundoff ||
                (slope < 0 && initial / -slope <= atom),
            8, "UNPREDICTED_GUARD_JUMP",
            "a noncandidate threshold is already beyond its legal side; "
            "explicit transition dynamics are required",
            true);
    if (flow.stationary(k))
      continue;
    bool found = false;
    Crossing root;
    std::function<void(double, double, int)> visit = [&](double a, double b,
                                                         int depth) {
      require(++result.nodes <= budget && depth <= 160, 8,
              "ENGINEERING_ROOT_BUDGET",
              "engineering first-event search exhausted its budget", true);
      if (found)
        return;
      Range range = flow.bounds(k, a, b);
      if (range.hi < 0)
        return;
      double ga = flow.value(k, a), gb = flow.value(k, b);
      auto derivative = flow.bounds(k, a, b, 1);
      if (derivative.hi < 0 &&
          (ga <= 0 || (a == 0 && (ga <= initial_roundoff || ga / -flow.value(k, 0, 1) <= atom))))
        return;
      if (derivative.lo > 0 && gb < 0)
        return;
      if (derivative.lo > 0 && ga <= 0 && gb >= 0) {
        double lo = a, hi = b;
        for (int iter = 0; iter < 100 && hi - lo >
             (mode.guards[k].kind == "PWA" ?
              std::max(std::numeric_limits<double>::denorm_min(),
                       2 * std::numeric_limits<double>::epsilon() * std::max(std::abs(lo), std::abs(hi))) : tolerance); ++iter) {
          double mid = lo + (hi - lo) * .5;
          if (mid == lo || mid == hi)
            break;
          if (flow.value(k, mid) < 0)
            lo = mid;
          else
            hi = mid;
        }
        double at = lo + (hi - lo) * .5;
        root = {k, at, lo, hi, flow.value(k, at, 1)};
        found = true;
        return;
      }
      if (a == 0 && ga >= 0 && derivative.lo > 0) {
        double slope = flow.value(k, 0, 1);
        require(ga <= initial_roundoff || ga / slope <= atom, 8, "UNPREDICTED_GUARD_JUMP",
                "a threshold jumped beyond the supported event window; model "
                "needs explicit transition dynamics",
                true);
        root = {k, 0, 0, 0, slope};
        found = true;
        return;
      }
      double mid = a + (b - a) * .5;
      if (mid == a || mid == b || b - a <= tolerance) {
        double slope = flow.value(k, mid, 1), value = flow.value(k, mid);
        if (slope > 0 && std::abs(value / slope) <= atom) {
          root = {k, mid, a, b, slope};
          found = true;
          return;
        }
        if (slope == 0 ||
            std::abs(value) <=
                64 * std::numeric_limits<double>::epsilon() * flow.scale(k))
          throw Error(8, "ZERO_EVENT_DERIVATIVE",
                      "located threshold has zero or numerically unresolved "
                      "crossing derivative",
                      true);
        throw Error(
            8, "ENGINEERING_ROOT_UNRESOLVED",
            "first event cannot be resolved within the engineering window",
            true);
      }
      visit(a, mid, depth + 1);
      if (!found)
        visit(mid, b, depth + 1);
    };
    visit(0, horizon, 0);
    if (found) {
      validate_event_timing(flow, root, atom);
      result.candidates.push_back(root);
    }
  }
  std::sort(result.candidates.begin(), result.candidates.end(),
            [](auto &a, auto &b) { return a.time < b.time; });
  if (!result.candidates.empty()) {
    double first = result.candidates.front().time;
    std::erase_if(result.candidates,
                  [&](auto &r) { return r.time > first + atom; });
  }
  return result;
}
} // namespace pulse::engineering
