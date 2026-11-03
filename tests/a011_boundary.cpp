#include "pulse/core.hpp"
#include "pulse/engineering.hpp"
#include <fstream>
#include <iostream>
using namespace pulse;
int main(int argc,char **argv) {
 try {
  std::ifstream in(argv[1]);Json fixture;in>>fixture;
  const int n=int(fixture["state"].size());Mode mode;mode.definition.edit().M=Matrix(n,n);Vector x(n);
  for(int i=0;i<n;i++){x[i]=fixture["state"][i];for(int j=0;j<n;j++)mode.definition.edit().M(i,j)=fixture["matrix"][i][j];}
  for(const auto &j:fixture["guards"])if(j["part"]=="R_D133"){
   Mode::Guard g;g.row=Vector(n);for(int i=0;i<n;i++)g.row[i]=j["row"][i];g.kind="PWA";g.part=0;g.knot=1;g.segment=1;g.step=-1;mode.binding.edit().guards.push_back(g);
  }
  engineering::Flow flow(mode,x);
  auto check=[](bool ok,const char *text){if(!ok)throw std::runtime_error(text);};
  const double slope=flow.value(0,0,1);
  check(std::abs(slope-(-3.6697581181288326e-6))<1e-12,"small outgoing derivative has wrong sign or magnitude");
  check(std::abs(flow.value(0,1e-8)-(-1.9523653546273622e-10))<5e-16,"guard increment differs from independent 80-digit reference");
  check(flow.bounds(0,0,1e-7,1).hi<0,"outgoing derivative enclosure invents an outward crossing");
  check(engineering::next_events(mode,flow,1e-7,1e-14).candidates.empty(),"arrived knot is spuriously crossed again");
  check((flow.state(0)-x).isZero(0),"entry state was projected");
  for(double h:{1e-12,1e-10,1e-8,1e-7})
   check(std::abs(mode.binding.read().guards[0].row.dot(flow.state(h))-flow.value(0,h))<1e-20,
         "root prediction and propagated physical state use inconsistent flows");
  // A later genuine exit must survive the inward-at-entry pruning: g=t^2-t.
  Mode later;later.definition.edit().M=Matrix::Zero(3,3);later.definition.edit().M(0,2)=1;later.definition.edit().M(1,0)=2;
  Vector initial(3);initial<<0,0,1;Mode::Guard g;g.row=Vector(3);g.row<<-1,1,0;g.kind="PWA";g.part=0;later.binding.edit().guards.push_back(g);
  engineering::Flow curve(later,initial);auto roots=engineering::next_events(later,curve,1.5,1e-14);
  check(roots.candidates.size()==1&&std::abs(roots.candidates[0].time-1)<1e-12,"real later exit was discarded");
  std::cout<<"PASS A011 boundary derivative, independent guard value, enclosure, no false re-entry, state preservation and later exit\n";return 0;
 } catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
}
