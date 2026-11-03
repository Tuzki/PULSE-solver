#include "pulse/engineering.hpp"
#include "pulse/state_coordinates.hpp"
#include <sstream>
#include <iomanip>
#include <bit>
#include <functional>
namespace pulse {
namespace {
thread_local const Model*owner=nullptr;
thread_local std::string model_identity;
thread_local bool enabled=false;
thread_local PersistentChart chart;
thread_local uint64_t encodes=0,views=0;
void build(const Model&m){
  int n=m.ns+1;chart=PersistentChart{};chart.weights=Vector::Ones(n);chart.mix=Matrix::Identity(n,n);chart.unmix=chart.mix;chart.T=chart.mix;chart.L=chart.mix;encodes=views=0;
  chart.selection_reason="No independent multi-storage incidence row; identity.";
  chart.coordinate_ids=m.state_ids;
  if(!m.numerical_coordinates){chart.selection_reason="Public compile API uses physical coordinates.";return;}

  auto linear_scalar=[](const Part&p){return (p.raw.kind=="C"||p.raw.kind=="L")&&p.curve.x.empty()&&p.inductance.rows()==0;};
  // A fixed, invertible coordinate chart, derived from sparse storage incidence.
  // It is not a mode-dependent projection: every original degree of freedom is
  // retained, including cutset imbalances. No assumed zero is written to state.
  Matrix inductors=Matrix::Zero(m.nodes.size(),n),caps=inductors;
  std::map<std::string,std::string> parent;parent["0"]="0";
  for(const auto&[node,index]:m.nodes)parent[node]=node;
  std::function<std::string(const std::string&)> find=[&](const std::string&node){return parent[node]==node?node:parent[node]=find(parent[node]);};
  for(const auto&p:m.parts){
    if(linear_scalar(p)){
      chart.weights[p.state]=1/number(p.raw.options.at(p.raw.kind));
      auto[a,b]=p.ports[0];auto& incidence=p.raw.kind=="L"?inductors:caps;
      if(a!="0")incidence(m.nodes.at(a),p.state)+=1;
      if(b!="0")incidence(m.nodes.at(b),p.state)-=1;
    }
    if(p.raw.kind!="L"&&p.raw.kind!="I")for(const auto&[a,b]:p.ports)parent[find(a)]=find(b);
  }
  std::vector<bool> used(n,false);
  auto add_row=[&](const Vector&original){
    int count=0;for(int j=0;j<m.ns;j++)if(original[j])++count;
    if(count<2)return;
    Vector row=chart.unmix.transpose()*original;
    int pivot=-1;for(int j=0;j<m.ns;j++)if(!used[j]&&std::abs(row[j])==1)pivot=j;
    if(pivot<0)return;
    row/=row[pivot];
    // Unit-pivot integer row operations have an exact inverse in binary64.
    // Refuse an unsafe chart instead of rounding a numerical inverse.
    if(row.cwiseAbs().maxCoeff()>1024||!row.allFinite())return;
    for(int j=0;j<n;j++)if(row[j]!=std::trunc(row[j]))return;
    Matrix next=chart.mix;next.row(pivot)=row.transpose()*chart.mix;
    Matrix inverse=chart.unmix;
    for(int j=0;j<n;j++)if(j!=pivot)inverse.col(j)-=row[j]*chart.unmix.col(pivot);
    if(!(next*inverse-Matrix::Identity(n,n)).isZero(0))return;
    chart.mix=std::move(next);chart.unmix=std::move(inverse);used[pivot]=true;
    chart.active=true;if(chart.difference_slot<0)chart.difference_slot=pivot;
  };
  // KCL cutsets may span any number of inductors and intervening voltage
  // sources/resistors/capacitors. Process these before local nodal differences.
  std::map<std::string,Vector> cuts;
  for(const auto&p:m.parts)if(p.raw.kind=="L"&&linear_scalar(p)){
    auto[a,b]=p.ports[0];if(find(a)==find(b))continue;
    for(const auto&[node,sign]:{std::pair{a,1.},std::pair{b,-1.}}){
      auto root=find(node);if(root==find("0"))continue;
      if(!cuts.count(root))cuts[root]=Vector::Zero(n);
      cuts[root][p.state]+=sign;
    }
  }
  for(const auto&[root,row]:cuts)add_row(row);
  for(int i=0;i<inductors.rows();i++)add_row(inductors.row(i).transpose());
  // Voltage differences/imbalances of capacitor networks use the same generic
  // construction. Capacitor and inductor blocks are independent; any number of
  // independent rows can be retained, not just the first eligible device pair.
  for(int i=0;i<caps.rows();i++)add_row(caps.row(i).transpose());
  if(chart.active)chart.selection_reason="Fixed unit-pivot storage incidence chart: arbitrary-size inductor cutsets, nodal current sums/differences and capacitor voltage imbalances; all degrees of freedom retained.";
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
 if(b!=mode.bools.end())return double(b->second);
 if(s.electrical_flow && s.electrical_flow->compatible(mode))
   return s.electrical_flow->observe(mode.binding.read().maps.at(n),0);
 return mode.binding.read().maps.at(n).dot(x);
}
// Identical per-signal semantics, but the input snapshot and modal view stay
// immutable throughout the batch. Flow::observe only changes derived caches.
std::vector<double> state_signals(const RunState&s,const std::vector<std::string>&names){
 std::vector<double> result;
 result.reserve(names.size());
 const Mode&mode=s.internal_mode?*s.internal_mode:s.mode;
 const Vector&x=s.internal.size()?s.internal:s.physical;
 bool checked=false,can_observe=false;
 for(const auto&name:names){
  if(is_literal(name)){result.push_back(number(name));continue;}
  const auto n=net_name(name);
  const auto b=mode.bools.find(n);
  if(b!=mode.bools.end()){result.push_back(double(b->second));continue;}
  if(!checked){
   can_observe=s.electrical_flow && s.electrical_flow->compatible(mode);
   checked=true;
  }
  const auto &row=mode.binding.read().maps.at(n);
  result.push_back(can_observe?s.electrical_flow->observe(row,0):row.dot(x));
 }
 return result;
}
std::vector<PreparedSignal> prepare_signals(const std::vector<std::string>&names){
 std::vector<PreparedSignal> result;
 result.reserve(names.size());
 for(const auto&name:names){
  PreparedSignal item;
  item.literal=is_literal(name);
  if(item.literal) item.value=number(name);
  else item.key=net_name(name);
  result.push_back(std::move(item));
 }
 return result;
}
std::vector<double> state_signals_prepared(const RunState&s,const std::vector<PreparedSignal>&selectors){
 std::vector<double> result;
 result.reserve(selectors.size());
 const Mode&mode=s.internal_mode?*s.internal_mode:s.mode;
 const Vector&x=s.internal.size()?s.internal:s.physical;
 bool checked=false,can_observe=false;
 for(const auto&item:selectors){
  if(item.literal){result.push_back(item.value);continue;}
  const auto b=mode.bools.find(item.key);
  if(b!=mode.bools.end()){result.push_back(double(b->second));continue;}
  if(!checked){
   can_observe=s.electrical_flow && s.electrical_flow->compatible(mode);
   checked=true;
  }
  const auto &row=mode.binding.read().maps.at(item.key);
  result.push_back(can_observe?s.electrical_flow->observe(row,0):row.dot(x));
 }
 return result;
}
void publish_physical_state(const Model&m,RunState&s){
 if(s.internal.size()!=m.ns+1)return;
 s.physical=physical_view(m,s.internal);const auto&c=persistent_chart(m);
 if(!c.active)return;
 s.internal_mode=std::make_shared<const Mode>(s.mode);
 s.mode.definition.edit().M=c.L*s.mode.definition.read().M*c.T;
 for(auto&[name,row]:s.mode.binding.edit().maps)row=c.T.transpose()*row;
 for(auto&guard:s.mode.binding.edit().guards)guard.row=c.T.transpose()*guard.row;
 if(s.mode.definition.read().constraints.rows())s.mode.definition.edit().constraints=s.mode.definition.read().constraints*c.T;
 if(s.mode.binding.read().residual_map.rows())s.mode.binding.edit().residual_map=s.mode.binding.read().residual_map*c.T;
 if(s.mode.binding.read().residual_reference.rows())s.mode.binding.edit().residual_reference=s.mode.binding.read().residual_reference*c.T;
 if(s.mode.definition.read().invariant_lift.rows()){s.mode.definition.edit().invariant_lift=c.L*s.mode.definition.read().invariant_lift;s.mode.definition.edit().invariant_reduce=s.mode.definition.read().invariant_reduce*c.T;}
}
}
