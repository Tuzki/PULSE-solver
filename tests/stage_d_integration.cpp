// Public-API tests for exact dynamic keys, COW isolation and shared projections.
#define main stage_d_engineering_fixture_main
#include "engineering_events.cpp"
#undef main
#include "pulse/engineering.hpp"
#include <bit>
#include <cstring>

namespace {
bool bytes(const Matrix& a,const Matrix& b) {
  return a.rows()==b.rows() && a.cols()==b.cols() &&
      (!a.size() || std::memcmp(a.data(),b.data(),size_t(a.size())*sizeof(double))==0);
}
void bound_cache() {
  auto model=compile(parse_markdown(document(
      "V1 IN 0 DC=1\nR1 IN OUT R=1\nC1 OUT 0 C=1 IC_V=0\n"
      "EVENT_E E MODE=AT AT=0\nREG_Q Q 0 E IC=0\nMATH_VIEW VIEW = 2*Q"),
      "stage-d-cache.md"));
  check(model.compiled_part_index.size()==model.parts.size(),"frozen index incomplete");
  for(size_t i=0;i<model.parts.size();++i)
    check(model.compiled_part_index.at(model.parts[i].raw.id)==int(i),"frozen part identity");
  Stats stats;ScopedModeCache scope(model,8);
  auto compile_at=[&](double q,const Vector& x) {
    return compile_specified(model,x,{{"Q",q}},stats,{},{});
  };
  auto original=compile_at(0,model.initial);
  check(bool(original.observer_binding),"fixture lacks certified observer binding");
  auto first=compile_at(.125,model.initial);
  auto hit=compile_at(.125,model.initial);
  check(stats.stage_d_rebound_misses==1 && stats.stage_d_rebound_hits==1,"exact-key hit absent");
  check(bytes(first.binding.read().residual_map,hit.binding.read().residual_map),"cached residual changed");
  hit.binding.edit().maps.at("VIEW").setConstant(99);
  auto isolated=compile_at(.125,model.initial);
  check(bytes(first.binding.read().maps.at("VIEW"),isolated.binding.read().maps.at("VIEW")),"COW cache polluted");
  auto plus=compile_at(+0.,model.initial),minus=compile_at(-0.,model.initial);
  check(std::bit_cast<uint64_t>(plus.binding.read().maps.at("Q")[model.ns])!=
        std::bit_cast<uint64_t>(minus.binding.read().maps.at("Q")[model.ns]),"signed-zero keys aliased");
  for(int i=1;i<=520;++i)compile_at(double(i),model.initial);
  const auto misses=stats.stage_d_rebound_misses;
  auto evicted=compile_at(.125,model.initial);
  check(stats.stage_d_rebound_misses==misses+1,"bounded cache did not evict oldest key");
  check(bytes(evicted.binding.read().maps.at("VIEW"),first.binding.read().maps.at("VIEW")),"evicted rebound changed");
  // Same immutable bound template, new physical state: residual must be evaluated again.
  auto x=model.initial;x[0]=.25;
  auto changed=compile_at(.125,x);
  Stats fresh_stats;Mode fresh;
  {ScopedModeCache disabled(model,0);
   fresh=compile_specified(model,x,{{"Q",.125}},fresh_stats,{},{});}
  check(std::bit_cast<uint64_t>(changed.residual)==std::bit_cast<uint64_t>(fresh.residual),"entry residual not rechecked");
  check(bytes(changed.binding.read().residual_map,fresh.binding.read().residual_map),"cache changed state equation");
  auto candidate=compile_specified(model,x,{{"Q",.125}},stats,{}, {},CompilePurpose::RegionClassification);
  check(candidate.classification_only && bool(candidate.candidate_roundoff_scale),"classification capability lost");
  bool refused=false;
  try { engineering::Flow invalid(candidate,x); }
  catch(const Error& e) {refused=e.subcode=="UNACCEPTED_CANDIDATE";}
  check(refused,"classification candidate propagated");
}
void projected_taylor() {
  for(double pole:{0.,1e-80,-1e-80,-2.,1e6}) {
    Mode mode;mode.definition.edit().M=Matrix::Zero(3,3);
    mode.definition.edit().M(0,0)=pole;
    mode.definition.edit().M(0,1)=1;
    mode.definition.edit().M(1,2)=1.5;
    Vector x(3);x<<.2,-.3,1;
    Vector guard(3);guard<<1,0,0;
    mode.binding.edit().guards.push_back({guard,0,1,"CMP"});
    engineering::Flow flow(mode,x);
    for(double t:{0.,1e-9,1e-8}) {
      for(double constant:{+0.,-0.,.7}) {
        Vector row(3);row<<.25,-.75,constant;
        auto reference_mode=mode;
        reference_mode.binding.edit().guards={{row,0,1,"OBSERVE"}};
        engineering::Flow reference(reference_mode,x);
        for(int order=0;order<=2;++order) {
          auto actual=flow.observe(row,t,order),expected=reference.value(0,t,order);
          check(std::bit_cast<uint64_t>(actual)==std::bit_cast<uint64_t>(expected),"shared projection changed value bits");
        }
      }
      check(bytes(flow.state(t),engineering::Flow(mode,x).state(t)),"shared Taylor changed state bits");
    }
    auto next_mode=mode;
    next_mode.binding.edit().guards[0].row[2]=.125;
    check(flow.compatible(next_mode),"guard-only change rejected continuation");
    auto next=flow.continued(next_mode,1e-9);
    Vector row(3);row<<.25,-.75,.7;
    check(next.observe(row,1e-9)==flow.observe(row,2e-9),"reprojection lost original anchor");
    auto other_x=x;other_x[0]=std::nextafter(other_x[0],1.);
    engineering::Flow other(mode,other_x);
    auto separate=next_mode;separate.binding.edit().guards={{row,0,1,"OBSERVE"}};
    check(other.observe(row,1e-9)==engineering::Flow(separate,other_x).value(0,1e-9),"different anchors aliased");
  }
}
}
int main() {try {
  bound_cache();projected_taylor();
  std::cout<<"PASS Stage D exact keys, eviction, COW, entry checks and Taylor projection bits\n";
  return 0;
} catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}}
