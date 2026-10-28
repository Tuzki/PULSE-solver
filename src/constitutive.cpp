#include "pulse/constitutive.hpp"
#include <cmath>
namespace pulse::constitutive {
Vector coordinate(const Model &m, const Mode &mode, int part) {
  const auto &p=m.parts.at(part);
  Vector row=Vector::Zero(m.ns+1);
  if(p.raw.kind!="R") row[p.state]=1;
  else {
    auto [a,b]=p.ports[0];
    if(a!="0") row+=mode.maps.at("V("+a+")");
    if(b!="0") row-=mode.maps.at("V("+b+")");
  }
  return row;
}
int direction(const Model &m,const Mode &mode,const Mode::Guard &g) {
  if(g.step) return g.step;
  auto row=coordinate(m,mode,g.part);
  return g.row.head(m.ns).dot(row.head(m.ns))>0?1:-1;
}
double boundary_value(const Model &m,const Mode::Guard &g) {
  require(g.knot>=0,12,"MISSING_BREAKPOINT","constitutive boundary lacks knot identity");
  const auto &p=m.parts.at(g.part);
  return (p.raw.kind=="R"?p.curve.x:p.curve.y).at(g.knot);
}
bool arrived(const Mode::Guard &g,const Vector &x,double location_error) {
  const double roundoff=64*std::numeric_limits<double>::epsilon()*
      (g.row.cwiseAbs().dot(x.cwiseAbs())+1e-300);
  return std::abs(g.row.dot(x))<=roundoff+location_error;
}
Json transition(const Model &m,const Mode &before,const Mode &after,
                const Vector &x,const Mode::Guard &g,int from,int to) {
  auto l=coordinate(m,before,g.part),r=coordinate(m,after,g.part);
  const auto &p=m.parts.at(g.part);
  return {{"part",p.raw.id},{"event_type","CONSTITUTIVE_BREAKPOINT"},
    {"knot",g.knot},{"boundary",boundary_value(m,g)},
    {"coordinate",p.raw.kind=="R"?"voltage":p.raw.kind=="C"?"charge":"flux"},
    {"from_segment",from},{"to_segment",to},
    {"coordinate_at_event",l.dot(x)},
    {"boundary_residual",g.row.dot(x)},{"arrival_evaluation_bound",g.arrival_error},
    {"left_derivative",l.dot(before.M*x)},
    {"right_derivative",r.dot(after.M*x)}};
}
}
