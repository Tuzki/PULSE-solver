#include "pulse/core.hpp"
#include "pulse/engineering.hpp"
#include <fstream>
#include <iostream>
using namespace pulse;
int main(int argc,char **argv){try{
 std::ifstream input(argv[1]);std::string text((std::istreambuf_iterator<char>(input)),{});auto m=compile(parse_markdown(text,argv[1]));std::ifstream data(argv[2]);Json j;data>>j;
 Vector x(m.ns+1);for(int i=0;i<=m.ns;i++)x[i]=j["state"][i];const Vector original=x;
 auto regs=j["regs"].get<std::map<std::string,double>>();std::map<int,int> segments;
 for(int i:m.pwas)segments[i]=j["segments_by_name"].at(m.parts[i].raw.id);
 Stats stats;ScopedModeCache cache(m,128);
 auto check=[](bool ok,const char *why){if(!ok)throw std::runtime_error(why);};
 auto rejected=[&](auto operation,const char *code){try{operation();}catch(const Error&e){check(e.subcode==code,"unexpected rejection code");return;}throw std::runtime_error("invalid candidate was accepted");};
 rejected([&](){compile_specified(m,x,regs,stats,{},segments);},"DESCRIPTOR_RESIDUAL");
 auto candidate=compile_specified(m,x,regs,stats,{},segments,CompilePurpose::RegionClassification);
 check(candidate.classification_only,"candidate was not marked as provisional");
 rejected([&](){validate_physical(candidate,x);},"UNACCEPTED_CANDIDATE");
 rejected([&](){engineering::Flow flow(candidate,x);},"UNACCEPTED_CANDIDATE");
 rejected([&](){accept_mode_entry(m,candidate,x);},"DESCRIPTOR_RESIDUAL");
 rejected([&](){compile_specified(m,x,regs,stats,{},segments);},"DESCRIPTOR_RESIDUAL");
 auto oldregs=regs;oldregs["GATE2"]=1;RunState old;old.physical=x;old.regs=oldregs;old.mode=compile_specified(m,x,oldregs,stats,{},segments);
 for(int repeat=0;repeat<2;repeat++){
  auto final=engineering::update_mode(m,old,x,regs,{}, {},stats);
  check(!final.classification_only&&final.residual<1e-8,"consistent result did not pass unchanged entry budget");
  for(const auto &reference:m.floating_references)
   check(final.binding.read().maps.at("V("+reference+")").isZero(0),"exact zero algebraic reference retained a numerical tail");
  check((x-original).isZero(0),"charge or flux changed during algebraic closure");
  for(int i:m.pwas){const auto&p=m.parts[i];auto [a,b]=p.ports[0];double v=0;if(a!="0")v+=final.binding.read().maps.at("V("+a+")").dot(x);if(b!="0")v-=final.binding.read().maps.at("V("+b+")").dot(x);check(final.segments.at(i)==p.curve.locate(v),"final constitutive region is inconsistent");}
  check(final.binding.read().maps.at("D117_VDS").dot(x)<0,"upper body diode did not take the freewheel current");
 }
 check(stats.cache_hits>0,"cache path was not exercised");
 std::cout<<"PASS A011 deadtime closure, strict final acceptance, provisional-flow rejection, storage preservation and cache parity\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
