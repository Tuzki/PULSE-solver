#include "pulse/core.hpp"
#include "pulse/engineering.hpp"
#include <fstream>
#include <iostream>
using namespace pulse;
Json matrix(const Matrix&m){Json a=Json::array();for(int i=0;i<m.rows();++i){Json r=Json::array();for(int j=0;j<m.cols();++j)r.push_back(m(i,j));a.push_back(r);}return a;}
Json vector(const Vector&v){Json a=Json::array();for(double x:v)a.push_back(x);return a;}
int main(int argc,char**argv){
 if(argc<2)return 2;std::ifstream f(argv[1]);std::string text((std::istreambuf_iterator<char>(f)),{});
 auto m=compile(parse_markdown(text,argv[1]));Options o;if(argc>2)o.t_end=number(argv[2]);
 auto r=simulate(m,o);Json out={{"report",r.report},{"events",r.events},{"segments",Json::array()}};
 for(auto&s:r.segments){const auto&st=s.state;out["segments"].push_back({{"at",st.at.canonical()},{"physical",vector(st.physical)},{"matrix",matrix(st.mode.M)},
 {"lift",matrix(st.mode.invariant_lift)},{"generator",matrix(st.mode.invariant_generator)},{"reduce",matrix(st.mode.invariant_reduce)},{"mode",st.mode.id},{"guards",Json::array()}});
 for(const auto&g:st.mode.guards)out["segments"].back()["guards"].push_back({{"part",m.parts[g.part].raw.id},{"row",vector(g.row)},{"kind",g.kind}});}
 if(r.status!="COMPLETED"){
  const auto&s=r.committed;double h=r.t_end-s.at.seconds();for(const auto&a:s.agenda)if(a.at>s.at)h=std::min(h,(a.at-s.at).seconds());
  out["probe"]=Json::array();
  for(auto&g:s.mode.guards){Mode one=s.mode;one.guards={g};engineering::Flow flow(one,s.physical);Json p={{"part",m.parts[g.part].raw.id},{"value",flow.value(0,0)},{"slope",flow.value(0,0,1)},{"horizon",h},{"modal",flow.modal()},{"samples",Json::array()}};
   for(double t:{0.,h*1e-6,h*.001,h*.1,h}){auto b=flow.bounds(0,t,t);auto d=flow.bounds(0,t,t,1);p["samples"].push_back({{"t",t},{"value",flow.value(0,t)},{"bounds",{b.lo,b.hi}},{"derivative",{d.lo,d.hi}}});}
   try{auto roots=engineering::next_events(one,flow,h,r.t_atom);p["nodes"]=roots.nodes;p["roots"]=roots.candidates.size();}catch(const std::exception&e){p["error"]=diagnostic(e);}out["probe"].push_back(p);
  }
 }
 std::cout<<out.dump(2)<<'\n';return 0;
}
