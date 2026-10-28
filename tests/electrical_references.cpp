#include "pulse/core.hpp"
#include <cmath>
#include <iostream>
using namespace pulse;
namespace {
void check(bool v,const std::string &s){if(!v)throw std::runtime_error(s);}
std::string document(const std::string &network){return
    "# PULSE Netlist v1.1\n\n## Parameters\n```pulse\n```\n\n## Network\n```pulse\n"+network+
    "\n```\n\n## Simulation\n```pulse\n.TRAN T_END=20u SAVE_DT=1u\n```\n\n## Layout\n```json\n{}\n```\n";}
Model model(const std::string &s){return compile(parse_markdown(document(s),"electrical-references.md"));}
Result run(const Model &m, bool cache=true){Options o;if(!cache)o.mode_cache_capacity=0;return simulate(m,o);}
void complete(const Result &r){check(r.status=="COMPLETED",r.status+" "+r.diagnostic.dump());}
double value(const Result&r,const std::string&n){return r.committed.mode.maps.at(n).dot(r.committed.physical);}
void near(double a,double b){check(std::abs(a-b)<=1e-10*std::max(1.,std::abs(b)),"value mismatch");}
}
int main(){try{
    auto a=model("V1 P 0 DC=1\nR1 P 0 R=1\nV2 SPLUS SREF DC=2\nR2 SPLUS SREF R=1\nSENSOR1 VB V SPLUS SREF");
    check(a.floating_references.size()==1,"floating loop not detected");
    auto ra=run(a);complete(ra);near(value(ra,"VB"),2);near(value(ra,"I(R2)"),2);
    auto b=model("V1 AP AREF DC=1\nR1 AP AREF R=1\nV2 BP BREF DC=2\nR2 BP BREF R=1\nSENSOR1 VB V BP BREF");
    check(b.floating_references.size()==2,"independent references merged");
    auto rb=run(b);complete(rb);near(value(rb,"VB"),2);
    auto rc=model("V1 IN REF1 DC=10\nR1 IN OUT R=2\nC1 OUT REF1 C=1u IC_V=0\nSENSOR1 VO V OUT REF1");
    auto grounded=model("V1 IN 0 DC=10\nR1 IN OUT R=2\nC1 OUT 0 C=1u IC_V=0\nSENSOR1 VO V OUT 0");
    auto rrc=run(rc),rg=run(grounded);complete(rrc);complete(rg);
    near(value(rrc,"VO"),value(rg,"VO"));
    check(rrc.committed.physical.isApprox(rg.committed.physical,1e-12),"reference changed charge");
    auto coupled=model("V1 P REF1 DC=1\nR1 P A R=1\nL_COUP (A REF1) (B REF2) L_MATRIX=[[2u,1u],[1u,2u]] IC_I=[0,0]\nR2 B REF2 R=2\nSENSOR1 VS V B REF2");
    check(coupled.node_reference.at("REF1")!=coupled.node_reference.at("REF2"),"magnetic coupling merged references");
    complete(run(coupled));
    auto bridge=model("V1 AP AREF DC=1\nR1 AP AREF R=1\nV2 BP BREF DC=2\nR2 BP BREF R=1\nC1 AREF BREF C=1u IC_V=3\nSENSOR1 VAB V AREF BREF");
    check(bridge.floating_references.size()==1,"real cross-island capacitor ignored");
    auto rbridge=run(bridge);complete(rbridge);near(value(rbridge,"VAB"),3);
    bool rejected=false;
    try {model("V1 P 0 DC=1\nR1 P 0 R=1\nV2 SPLUS SREF DC=2\nR2 SPLUS SREF R=1\nSENSOR1 BAD V P SPLUS");}
    catch(const Error&e){rejected=e.subcode=="UNDEFINED_CROSS_ISLAND_VOLTAGE";}
    check(rejected,"undefined cross-reference measurement accepted");
    auto cycle=model("V1 P REF DC=1\nEVENT_C CLK MODE=PERIODIC PERIOD=2u START=0\nEVENT_O OFF MODE=DELAY SOURCE=CLK DELAY=1u POLICY=TRANSPORT\nREG_G G MODE=SR SET=CLK RESET=OFF PRIORITY=RESET IC=0\nSW1 P OUT G RON=1 ROFF=100\nC1 OUT REF C=1u IC_V=0\nR1 OUT REF R=10\nSENSOR1 VO V OUT REF");
    auto on=run(cycle),off=run(cycle,false);complete(on);complete(off);
    check(on.stats.cache_hits>0,"floating cache not exercised");
    check(on.events==off.events && on.committed.physical.isApprox(off.committed.physical,1e-13),"cache changed floating trajectory");
    auto bad=run(model("V1 N REF DC=1\nV2 N REF DC=2\nR1 N REF R=1"));
    check(bad.status!="COMPLETED","reference fix hid inconsistent physical sources");
    std::cout<<"Independent references, storage, coupled windings, physical bridge, undefined measurement, cache, and inconsistent-source checks passed\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
