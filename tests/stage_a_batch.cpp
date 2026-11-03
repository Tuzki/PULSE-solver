#define main engineering_original_main
#include "engineering_events.cpp"
#undef main
#include "pulse/engineering.hpp"
#include "pulse/state_coordinates.hpp"
#include <cstring>

int main(){try{
    auto model=compile(parse_markdown(document("V1 IN 0 DC=1\nR1 IN OUT R=1\nC1 OUT 0 C=1 IC_V=0", ".1", ".01"),"stage-a.md"));
    Stats stats;RunState state;state.internal=model.initial;state.physical=model.initial;
    state.mode=engineering::initial_mode(model,state.internal,{},stats);
    state.mode.bools["FLAG"]=true;
    auto original=state.mode;
    const std::vector<std::string> names={"1.5","FLAG","V(OUT)","V(IN)","V(OUT)","0"};
    for(int condition=0;condition<8;++condition){
        state.mode=original;state.internal_mode.reset();state.electrical_flow.reset();
        if(condition&1)state.electrical_flow=std::make_shared<engineering::Flow>(original,state.internal);
        if(condition&2)state.mode.definition.edit().M(0,model.ns)+=1; // Incompatible views must use original fallback.
        if(condition&4)state.internal_mode=std::make_shared<const Mode>(state.mode);
        std::vector<double> scalar;for(auto &name:names)scalar.push_back(state_signal(state,name));
        auto batch=state_signals(state,names);
        check(batch.size()==scalar.size()&&!std::memcmp(batch.data(),scalar.data(),batch.size()*sizeof(double)),"batch changed signal values or order");
        check(state_signals(state,{}).empty(),"empty batch");
    }
    for(auto fault:std::vector<std::string>{"","retry_after_closure"}){
        Options full;full.fault=fault;auto retained=simulate(model,full);
        Options compact=full;compact.retain_history=false;auto streamed=simulate(model,compact);
        check(retained.status==streamed.status&&retained.events==streamed.events,"compact history changed event/retry semantics");
        check(retained.committed.at==streamed.committed.at&&(retained.committed.internal-streamed.committed.internal).isZero(0),"compact history changed committed prefix");
        check(streamed.segments.size()==1&&streamed.segments.back().state.at==streamed.committed.at,"final compact segment missing");
    }
    Options bad;bad.t_end=-1;bad.retain_history=false;
    auto failed=simulate(model,bad);
    check(failed.status=="STOPPED_ERROR"&&failed.segments.empty(),"pre-initialization failure fabricated a segment");
    std::cout<<"PASS: actual scalar/batch snapshots, incompatible fallback, compact history, retries and early failure\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
