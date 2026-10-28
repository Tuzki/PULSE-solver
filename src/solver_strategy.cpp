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
Mode portfolio_mode(const Model&m,const RunState&checkpoint,int algorithm,Stats&stats){
 if(algorithm==0&&!persistent_chart(m).active)return checkpoint.mode;
 std::map<int,bool>bits;for(int i:m.cmps)bits[i]=checkpoint.mode.bools.at(net_name(m.parts[i].raw.args[0]));
 if(algorithm==2)return compile_specified(m,checkpoint.internal,checkpoint.regs,stats,bits,checkpoint.mode.segments,CompilePurpose::AcceptedEntry);
 Mode mode;
 {Scope scope(algorithm);mode=compile_specified(m,physical_view(m,checkpoint.internal),checkpoint.regs,stats,bits,checkpoint.mode.segments,CompilePurpose::RegionClassification);}
 const auto&chart=persistent_chart(m);const auto&T=chart.T;const auto&L=chart.L;
 // Raw q/phi equations are eliminated first; bring their operators to the
 // authoritative checkpoint coordinates. No rounded physical view is encoded
 // back into storage, and the legacy elimination errors are not corrected here.
 mode.M=T*mode.M*L;
 if(mode.constraints.rows())mode.constraints=mode.constraints*L;
 if(mode.residual_map.rows())mode.residual_map=mode.residual_map*L;
 if(mode.residual_reference.rows())mode.residual_reference=mode.residual_reference*L;
 if(mode.invariant_lift.rows()){mode.invariant_lift=T*mode.invariant_lift;mode.invariant_reduce=mode.invariant_reduce*L;}
 for(auto&[name,row]:mode.maps)row=L.transpose()*row;
 for(auto&guard:mode.guards)guard.row=L.transpose()*guard.row;
 mode.candidate_roundoff_scale.reset();
 accept_mode_entry(m,mode,checkpoint.internal);
 return mode;
}
bool portfolio_retryable(const Error&e){
 static const std::set<std::string>retryable={"PHYSICAL_CONSTRAINT_VIOLATION","DESCRIPTOR_RESIDUAL","CANDIDATE_LINEAR_RESIDUAL","NONFINITE_CANDIDATE","NONFINITE_DESCRIPTOR","UNPREDICTED_GUARD_JUMP","ZERO_EVENT_DERIVATIVE","ENGINEERING_ROOT_BUDGET","PORTFOLIO_QR_RANK","PORTFOLIO_ORIGINAL_RESIDUAL","PORTFOLIO_DYNAMIC_RESIDUAL","INJECTED_PORTFOLIO_REJECTION","MODE_DIRECTION_CYCLE","MODE_CYCLE","INCONSISTENT_MODE_TRANSITION","ROOT_DIRECTION_UNRESOLVED","BREAKPOINT_LEFT_DIRECTION","BREAKPOINT_NOT_REACHED","NO_FORWARD_ADMISSIBLE_MODE","MODE_DIRECTION_BUDGET","INJECTED_EVENT_CLOSURE_REJECTION","TIME_ORDER_UNRESOLVED"};
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
