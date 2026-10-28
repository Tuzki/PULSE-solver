#include "pulse/state_coordinates.hpp"
#include <sstream>
#include <iomanip>
#include <bit>
namespace pulse {
namespace {
thread_local const Model*owner=nullptr;
thread_local std::string model_identity;
thread_local bool enabled=false;
thread_local PersistentChart chart;
thread_local uint64_t encodes=0,views=0;
void build(const Model&m){
  int n=m.ns+1;chart=PersistentChart{};chart.weights=Vector::Ones(n);chart.mix=Matrix::Identity(n,n);chart.unmix=chart.mix;chart.T=chart.mix;chart.L=chart.mix;encodes=views=0;
  chart.selection_reason="No eligible linear two-inductor KCL difference; identity.";
  chart.coordinate_ids=m.state_ids;
  if(!m.numerical_coordinates){chart.selection_reason="Public compile API uses physical coordinates.";return;}

  for(const auto&p:m.parts)if((p.raw.kind=="C"||p.raw.kind=="L")&&(!p.curve.x.empty()||p.inductance.rows()>0)){chart.selection_reason="Nonlinear/coupled storage is outside this fixed-chart prototype; identity.";return;}
  Matrix injection=Matrix::Zero(m.nodes.size(),n);
  for(const auto&p:m.parts)if(p.raw.kind=="C"||p.raw.kind=="L"){
    double w=1/number(p.raw.options.at(p.raw.kind));chart.weights[p.state]=w;
    if(p.raw.kind=="L"){auto[a,b]=p.ports[0];if(a!="0")injection(m.nodes.at(a),p.state)+=1;if(b!="0")injection(m.nodes.at(b),p.state)-=1;}
  }
  for(int i=0;i<injection.rows();i++){
    std::vector<int> columns;for(int j=0;j<m.ns;j++)if(injection(i,j))columns.push_back(j);
    if(columns.size()!=2||injection(i,columns[0])*injection(i,columns[1])>=0)continue;
    const int pivot=columns.back();chart.mix.row(pivot)=injection.row(i)/injection(i,pivot);
    chart.unmix.row(pivot)=-chart.mix.row(pivot);chart.unmix(pivot,pivot)=1;
    require((chart.mix*chart.unmix-Matrix::Identity(n,n)).isZero(0),12,"PERSISTENT_CHART_INVERSE","integer mix is not exactly invertible");
    chart.active=true;chart.difference_slot=pivot;chart.selection_reason="Fixed graph-derived two-inductor KCL difference; compiler-owned physical state ordinals and exact binary coefficients identify rows.";break;
  }
  if(!chart.active){chart.weights.setOnes();chart.mix.setIdentity();chart.unmix.setIdentity();}
  chart.T=chart.mix*chart.weights.asDiagonal();chart.L=chart.weights.cwiseInverse().asDiagonal()*chart.unmix;
  chart.coordinate_ids.clear();
  for(int i=0;i<m.ns;i++){
    std::ostringstream id;id<<"affine[";for(int j=0;j<m.ns;j++)if(chart.mix(i,j)){id<<j<<":"<<m.state_ids[j]<<":"<<std::hexfloat<<chart.mix(i,j)*chart.weights[j]<<";";}id<<"]+0";
    chart.coordinate_ids.push_back(id.str());
  }
}
}
const PersistentChart& persistent_chart(const Model&m){if(owner!=&m||model_identity!=m.netlist.canonical||enabled!=m.numerical_coordinates){owner=&m;model_identity=m.netlist.canonical;enabled=m.numerical_coordinates;build(m);}return chart;}
Vector persistent_encode(const Model&m,const Vector&x){const auto&c=persistent_chart(m);++encodes;return c.T*x;}
Vector physical_view(const Model&m,const Vector&xi){const auto&c=persistent_chart(m);++views;return c.L*xi;}
Vector physical_increment(const Model&m,const Vector&dxi){return persistent_chart(m).L.topLeftCorner(m.ns,m.ns)*dxi;}
void persistent_stamp(const Model&m,Matrix&B,Matrix&F,Matrix&D){
  const auto&c=persistent_chart(m);if(!c.active)return;int n=m.ns;
  Matrix right=B;
  // Divide before mixing: an original i=w*phi constraint becomes i=(im+delta),
  // with exact unit coefficients, instead of multiplying rounded inverse weights.
  for(int j=0;j<=n;j++)right.col(j)/=c.weights[j];
  B=right*c.unmix;
  Matrix weighted=F;for(int i=0;i<n;i++)weighted.row(i)*=c.weights[i];F=c.mix.topLeftCorner(n,n)*weighted;
  Matrix dynamic=D;for(int i=0;i<n;i++)for(int j=0;j<=n;j++)dynamic(i,j)=dynamic(i,j)*c.weights[i]/c.weights[j];
  D=c.mix.topLeftCorner(n,n)*dynamic*c.unmix;
}
Json persistent_description(const Model&m){
  const auto&c=persistent_chart(m);auto mat=[](const Matrix&a){Json j=Json::array();for(int i=0;i<a.rows();i++){Json row=Json::array();for(int k=0;k<a.cols();k++)row.push_back(a(i,k));j.push_back(row);}return j;};
  return{{"enabled",c.active},{"reason",c.selection_reason},{"difference_slot",c.difference_slot},{"internal_coordinate_ids",c.coordinate_ids},{"T",mat(c.T)},{"physical_view_L",mat(c.L)},{"physical_state_ids",m.state_ids},{"initial_encodes",encodes},{"physical_views_for_diagnostics",views},{"cross_event_policy","Same fixed chart: RunState vector copied directly; no physical-view roundtrip."},{"scope","Linear scalar storage; graph-derived fixed KCL difference, not arbitrary chart selection."}};
}
}


namespace pulse {
double state_signal(const RunState&s,const std::string&name){
 if(is_literal(name))return number(name);
 const Mode&mode=s.internal_mode?*s.internal_mode:s.mode;
 const Vector&x=s.internal.size()?s.internal:s.physical;
 const auto n=net_name(name);auto b=mode.bools.find(n);
 return b!=mode.bools.end()?double(b->second):mode.maps.at(n).dot(x);
}
void publish_physical_state(const Model&m,RunState&s){
 if(s.internal.size()!=m.ns+1)return;
 s.physical=physical_view(m,s.internal);const auto&c=persistent_chart(m);
 if(!c.active)return;
 s.internal_mode=std::make_shared<const Mode>(s.mode);
 s.mode.M=c.L*s.mode.M*c.T;
 for(auto&[name,row]:s.mode.maps)row=c.T.transpose()*row;
 for(auto&guard:s.mode.guards)guard.row=c.T.transpose()*guard.row;
 if(s.mode.constraints.rows())s.mode.constraints=s.mode.constraints*c.T;
 if(s.mode.residual_map.rows())s.mode.residual_map=s.mode.residual_map*c.T;
 if(s.mode.residual_reference.rows())s.mode.residual_reference=s.mode.residual_reference*c.T;
 if(s.mode.invariant_lift.rows()){s.mode.invariant_lift=c.L*s.mode.invariant_lift;s.mode.invariant_reduce=s.mode.invariant_reduce*c.T;}
}
}
