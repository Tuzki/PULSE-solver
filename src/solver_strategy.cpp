#include "pulse/solver_strategy.hpp"
#include "pulse/state_coordinates.hpp"
#include <fstream>
#include <sstream>
#include <iomanip>
namespace pulse {
namespace {thread_local int variant=2;
struct Scope{int before;Scope(int v):before(variant){variant=v;}~Scope(){variant=before;}};
const std::array<std::string,3>names={"RAW_QPHI_ELIMINATION_LU","RAW_QPHI_ELIMINATION_QR","PERSISTENT_DIFFERENCE_LU"};
}
int portfolio_variant(){return variant;}
Mode portfolio_compile(const Model&m,const Vector&internal,
 const std::map<std::string,double>&regs,Stats&stats,
 const std::map<int,bool>&bits,const std::map<int,int>&segments,
 int algorithm,CompilePurpose purpose){
 require(algorithm>=0&&algorithm<3,12,"STRATEGY_SCOPE","invalid numerical strategy");
 Mode mode;
 if(algorithm==2){
  Scope scope(2);mode=compile_specified(m,internal,regs,stats,bits,segments,purpose);
 }else{
  // Raw strategies compile in physical coordinates, but candidates and accepted
  // modes are BOTH returned in the authoritative internal chart. Keep every
  // mode-construction iteration on the attempt's explicitly selected strategy.
  {Scope scope(algorithm);mode=compile_specified(m,physical_view(m,internal),regs,stats,bits,segments,CompilePurpose::RegionClassification);}
  const auto&chart=persistent_chart(m);const auto&T=chart.T;const auto&L=chart.L;
  mode.definition.edit().M=T*mode.definition.read().M*L;
  if(mode.definition.read().constraints.rows())mode.definition.edit().constraints=mode.definition.read().constraints*L;
  if(mode.definition.read().invariant_lift.rows()){mode.definition.edit().invariant_lift=T*mode.definition.read().invariant_lift;mode.definition.edit().invariant_reduce=mode.definition.read().invariant_reduce*L;}
  // A cache hit skips only repeated chart materialization. Original
  // compile_specified() entry checks and all definition transforms ran.
  mode.binding=coordinate_bound_binding(m,mode.binding,L);
  if(mode.candidate_roundoff_scale)
   mode.candidate_roundoff_scale=std::make_shared<const Matrix>((*mode.candidate_roundoff_scale)*L.cwiseAbs());
  if(purpose==CompilePurpose::AcceptedEntry)accept_mode_entry(m,mode,internal);
 }
 mode.numerical_strategy=algorithm;
 return mode;
}
// All numerical strategies remain unchanged. Runtime profiling surrounds
// portfolio_mode() rather than weakening the canonical verification contract.
Mode portfolio_mode(const Model&m,const RunState&checkpoint,int algorithm,Stats&stats){
 std::map<int,bool>bits;for(int i:m.cmps)bits[i]=checkpoint.mode.bools.at(net_name(m.parts[i].raw.args[0]));
 return portfolio_compile(m,checkpoint.internal,checkpoint.regs.read(),stats,bits,checkpoint.mode.segments,algorithm);
}
bool portfolio_retryable(const Error&e){
 static const std::set<std::string>retryable={"PHYSICAL_CONSTRAINT_VIOLATION","DESCRIPTOR_RESIDUAL","CANDIDATE_LINEAR_RESIDUAL","NONFINITE_CANDIDATE","NONFINITE_DESCRIPTOR","UNPREDICTED_GUARD_JUMP","ZERO_EVENT_DERIVATIVE","ENGINEERING_ROOT_BUDGET","ENGINEERING_ROOT_UNRESOLVED","PORTFOLIO_QR_RANK","PORTFOLIO_ORIGINAL_RESIDUAL","PORTFOLIO_DYNAMIC_RESIDUAL","INJECTED_PORTFOLIO_REJECTION","MODE_DIRECTION_CYCLE","MODE_CYCLE","INCONSISTENT_MODE_TRANSITION","ROOT_DIRECTION_UNRESOLVED","BREAKPOINT_LEFT_DIRECTION","BREAKPOINT_NOT_REACHED","BREAKPOINT_PREDICTION_MISMATCH","NO_FORWARD_ADMISSIBLE_MODE","MODE_DIRECTION_BUDGET","INJECTED_EVENT_CLOSURE_REJECTION","TIME_ORDER_UNRESOLVED"};
 return retryable.count(e.subcode);
}
void PortfolioStats::record_failure(int algorithm,const RunState&checkpoint,Time target,const Error&error){
 ++failed[algorithm];++restores;
 if(failures.size()<64)failures.push_back({{"algorithm",algorithm},{"checkpoint_seconds",checkpoint.at.seconds()},{"checkpoint_version",checkpoint.version},{"candidate_seconds",target.seconds()},{"diagnostic",diagnostic(error)}});
}
Json PortfolioStats::description()const{
 Json rows=Json::array();for(int i=0;i<3;i++)rows.push_back({{"algorithm",i},{"name",names[i]},{"attempts",attempts[i]},{"committed",accepted[i]},{"failed",failed[i]},{"executed_paths",executed_paths[i]}});
 return{{"methods",rows},{"checkpoint_restores",restores},{"failures",failures},{"journal_records",journal_records},{"checkpoint_policy","Same immutable post-event RunState for every attempt; canonical difference state retained. MCU writes, invocation counters and queued events are staged in each candidate and only committed once; failed event closure also restores the checkpoint."},{"validation","Inherited entry/endpoint checks plus original unstatically-eliminated algebraic equations and physical q/phi derivatives at start, midpoint, endpoint; engineering sampled checks, not a continuous-time certificate."},{"exhaustion_policy","Stop at last committed event; no SPICE fallback, no 1 ns rounding, no tolerance relaxation."},{"scope","Three registered candidates only; raw equation elimination operators evaluated in canonical checkpoint coordinates, not an exact replay of the historical raw-state solver."}};
}
}
