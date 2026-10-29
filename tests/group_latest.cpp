#include "pulse/core.hpp"
#include <cstdlib>
#include <iostream>
#include <algorithm>
using namespace pulse;
void check(bool b,const std::string&s){if(!b)throw std::runtime_error(s);}
Result run(const std::string&network){std::string doc="# PULSE Netlist v1.1\n\n## Parameters\n```pulse\n```\n\n## Network\n```pulse\nMATH_ONE ONE = 1\nINT_X X ONE IC=-1e-6\n"+network+"\n```\n\n## Simulation\n```pulse\n.TRAN T_END=2e-6 SAVE_DT=2e-7\n```\n\n## Layout\n```json\n{}\n```\n";Options o;o.atomic_time=1e-14;return simulate(compile(parse_markdown(doc,"latest-group-test.md")),o);}
int main(){try{
 auto a=run("CMP_A A X OP=GT THRESHOLD=0\nCMP_B B X OP=GT THRESHOLD=8e-15\nCMP_C C X OP=GT THRESHOLD=16e-15");check(a.status=="COMPLETED",a.diagnostic.dump());std::vector<Json>roots;for(auto&e:a.events)if(e["kind"]=="ROOT")roots.push_back(e);check(roots.size()==2,"expected two non-chained groups");auto ids=roots[0]["candidate_members"].get<std::vector<std::string>>();check(ids.size()==2 && std::find(ids.begin(),ids.end(),"CMP_C")==ids.end(),"+16fs leaked into first 10fs window");double latest=0;for(auto&e:roots[0]["predicted_events"])latest=std::max(latest,e["old_mode_local_time"].get<double>());check(roots[0]["execution_local_time"].get<double>()==latest,"execution must use latest selected root");check(roots[0]["execution_delay_from_first"].get<double>()>7e-15,"group was executed at earliest root");check(Time::decode(roots[0]["time_canonical"].get<std::string>())==Time::from(latest),"committed timestamp not latest root");
 std::cout<<"PASS comparator group: first+8fs included, +16fs excluded, state/time advanced to latest\n";
 auto b=run("V_DRIVE IN 0 X\nR_KNOT IN 0 IV_TABLE=[(-1,-1),(0,0),(1,2)] RANGE=EXTEND\nCMP_B B X OP=GT THRESHOLD=8e-15");check(b.status=="COMPLETED",b.diagnostic.dump());bool saw=false;for(auto&e:b.events)if(e["kind"]=="ROOT"){auto ids=e["candidate_members"].get<std::vector<std::string>>();if(std::find(ids.begin(),ids.end(),"R_KNOT")!=ids.end()){check(ids.size()==2,"PWA/CMP not grouped");check(e["execution_delay_from_first"].get<double>()>7e-15,"PWA group not delayed to latest");saw=true;}}check(saw,"PWA test has no knot event");check(std::abs(b.committed.physical[0]-1e-6)<1e-19,"storage integrator was reset/projected during group commit");
 std::cout<<"PASS PWA group: own predicted knot checked; earlier knot may be crossed at latest commit; state preserved\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}

