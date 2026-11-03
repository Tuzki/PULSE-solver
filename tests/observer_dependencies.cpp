#define main engineering_original_main
#include "engineering_events.cpp"
#undef main
#include "pulse/engineering.hpp"
#include "pulse/trajectory.hpp"
#include <cstring>

namespace {
bool exact(const Matrix&a,const Matrix&b){return a.rows()==b.rows()&&a.cols()==b.cols()&&(!a.size()||std::memcmp(a.data(),b.data(),size_t(a.size())*sizeof(double))==0);}
const std::string base="V1 IN 0 DC=1\nR1 IN OUT R=1\nC1 OUT 0 C=1 IC_V=0\nEVENT_E E MODE=AT AT=0\nREG_Q Q 0 E IC=0\n";
void observation_binding(){
    auto model=compile(parse_markdown(document(base+"MATH_VIEW VIEW = 2*Q"),"observer.md"));
    check(model.observer_regs.count("Q")&&model.observer_signals.count("VIEW"),"transitive observation classification");
    Stats stats;ScopedModeCache cache(model,8);std::map<std::string,double> regs{{"Q",0}};
    auto first=compile_specified(model,model.initial,regs,stats,{},{});
    check(bool(first.observer_binding),"isolated observation not certified");
    for(int i=1;i<=100;++i){
        regs["Q"]=double(i)/8;
        auto hit=compile_specified(model,model.initial,regs,stats,{},{});
        Stats fresh_stats;Mode fresh;
        {ScopedModeCache disabled(model,0);fresh=compile_specified(model,model.initial,regs,fresh_stats,{},{});}
        check(exact(hit.definition.read().M,fresh.definition.read().M)&&exact(hit.binding.read().residual_map,fresh.binding.read().residual_map)&&exact(hit.binding.read().residual_reference,fresh.binding.read().residual_reference),"rebound equations differ from original complete compilation");
        for(const auto &[name,row]:fresh.binding.read().maps)check(exact(hit.binding.read().maps.at(name),row),"rebound observation differs: "+name);
        near(hit.binding.read().maps.at("VIEW").dot(model.initial),2*regs["Q"],0,"derived observation");
    }
    check(stats.modes==1&&stats.cache_hits==100,"pure observation caused electrical recompilation");
    auto last=compile_specified(model,model.initial,regs,stats,{},{});
    engineering::Flow flow(first,model.initial);
    check(flow.compatible(last),"pure observation invalidated dynamics");
    auto next=flow.continued(last,.125);
    check(exact(flow.state(.25),next.state(.125)),"continuation changed anchored state");
    near(next.observe(last.binding.read().maps.at("VIEW"),0),25,0,"continued observation view");
    check(next.archive_mode().binding.read().maps.at("Q")[model.ns]==12.5,"archive lost new observation binding");
    auto wrong=last;wrong.definition.edit().M(0,model.ns)+=1;check(!flow.compatible(wrong),"changed affine forcing reused flow");
    wrong=last;++wrong.numerical_strategy;check(!flow.compatible(wrong),"different strategy reused flow");
}
void critical_dependencies(){
    for(const auto &network:std::vector<std::string>{
        "EVENT_E E MODE=AT AT=0\nREG_Q Q 0 E IC=0\nMATH_X X = 2*Q\nV1 IN 0 X\nR1 IN OUT R=1\nC1 OUT 0 C=1 IC_V=0",
        base+"MATH_X X = 2*Q\nCMP_G G X OP=GT THRESHOLD=1\nSW1 OUT 0 G RON=1 ROFF=10",
        base+"REG_F REAL::F Q E IC=0"}){
        auto model=compile(parse_markdown(document(network),"critical-observer.md"));
        check(!model.observer_regs.count("Q"),"critical transitive REAL dependency omitted from key");
    }
    auto model=compile(parse_markdown(document("EVENT_E E MODE=AT AT=0\nREG_Q Q 0 E IC=0\nMATH_X X = 2*Q\nV1 IN 0 X\nR1 IN OUT R=1\nC1 OUT 0 C=1 IC_V=0"),"forcing.md"));
    Stats stats;ScopedModeCache cache(model,8);
    auto a=compile_specified(model,model.initial,{{"Q",1}},stats,{},{});
    auto b=compile_specified(model,model.initial,{{"Q",2}},stats,{},{});
    check(stats.modes==2&&!exact(a.definition.read().M,b.definition.read().M),"dynamic electrical forcing was frozen");
}
void complete_observation_archive(){
    auto model=compile(parse_markdown(document(
        "V1 IN 0 DC=1\nR1 IN OUT R=1\nC1 OUT 0 C=1 IC_V=0\n"
        "MATH_ONE ONE = 1\nINT_T T ONE\nEVENT_E E MODE=PERIODIC PERIOD=.1 START=0\n"
        "REG_Q Q T E IC=0\nMATH_VIEW VIEW = 2*Q", "1", ".025"),"changing-monitor.md"));
    auto wave=simulate(model);Options options;options.trajectory_output=true;
    auto trace=simulate(model,options);
    check(wave.status=="COMPLETED"&&trace.status=="COMPLETED","monitor simulation failed");
    check(wave.events==trace.events,"archive changed authoritative events");
    trace.trajectory->write("observer-archive-test",trace);
    auto replay=replay_trajectory("observer-archive-test");
    check(wave.analog_names==replay.analog_names&&wave.digital_names==replay.digital_names,"monitor channels missing in reconstruction");
    check(wave.times==replay.times&&wave.analog==replay.analog&&wave.digital==replay.digital,"changing monitor archive reconstruction differs");
    check(trace.stats.modes<10,"monitor-only sampling compiled repeatedly");
}
}
int main(){
    try{observation_binding();critical_dependencies();complete_observation_archive();std::cout<<"Observation rebinding, transitive critical dependencies and anchored Flow reuse passed\n";return 0;}
    catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
