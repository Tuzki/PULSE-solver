#include "pulse/engineering.hpp"
#include <iostream>
#include <iomanip>
using namespace pulse;
int main(){try{
 auto check=[](bool b,const char*m){if(!b)throw std::runtime_error(m);};
 // Fixed binary64 A2 circuit operator; reference values obtained by evaluating
 // THIS operator at 80 digits, independently of the runtime evaluator.
 Mode m;m.definition.edit().M=Matrix::Zero(5,5);
 m.definition.edit().M << -413.1377816506659,0,0,9.227252531791527e-17,0,
 0,0,1e7,1e7,0,
 -4.8789097761847706e-14,0,0,1.3500000000027002e15,0,
 2.9273458657108726e-13,-83333.33333333333,-41666666666833.32,-8141666666683034,33333333.333333332,
 0,0,0,0,0;
 Vector x(5);x<<50,0,0,0,1;
 Vector g=Vector::Zero(5);g[3]=-9; m.binding.edit().guards.push_back({g,0,1,"CMP"});m.binding.edit().maps["current"]=g;
 engineering::Flow f(m,x);
 double lo=4e-12,hi=6e-12;for(int j=0;j<80;j++){double mid=(lo+hi)*.5;if(mid==lo||mid==hi)break;if(f.value(0,mid)<0)lo=mid;else hi=mid;}
 double root=(lo+hi)*.5;
 // The reference of this standalone matrix differs slightly from the actual
 // assembled guard (which also has a tiny nonzero output-capacitor coefficient).
 check(std::abs(root-4.841472829939087185678383484561e-12)<1e-24,"fixed operator root oracle");
 check(std::abs(f.value(0,root,1)-7.374638201851120770075414003501e-10)<1e-22,"fixed operator direction oracle");
 Mode opposite=m;opposite.binding.edit().guards[0].row=-g;
 auto h=f.continued(opposite,root);
 for(double dt:{0.,1e-17,1e-14,1e-12,1e-9}){
   check(h.observe(g,dt)==f.observe(g,root+dt),"observable anchor lost");
   check(h.observe(g,dt,1)==f.observe(g,root+dt,1),"derivative anchor lost");
   check((h.state(dt)-f.state(root+dt)).isZero(0),"storage anchor lost");
   check(h.value(0,dt)==-f.value(0,root+dt),"guard orientation lost");
 }
 check(f.observe(g,root,1)>0,"incoming direction");
 auto chain=f;Time elapsed;
 for(int j=0;j<10000;j++){chain=chain.continued(m,1e-15);elapsed=elapsed+Time::from(1e-15);}
 check(chain.value(0,0)==f.value(0,elapsed.seconds()),"continuation clock accumulation");
 check(std::abs(g.dot(f.state(root))-f.value(0,root))<1e-35,"state observable mismatch");
 Mode changed=m;changed.definition.edit().M(3,4)*=2;
 check(!f.compatible(changed),"changed electrical source incorrectly reused");
 engineering::Flow right(changed,f.state(root));
 check(right.observe(g,0,1)*f.observe(g,root,1)<0,"right derivative must be independent");
 Mode changed_map=m;changed_map.binding.edit().maps["current"]=-g;
 check(!f.compatible(changed_map),"changed algebraic map incorrectly reused");
 // Singular affine generator: integrator remains an integrator.
 Mode integrator;integrator.definition.edit().M=Matrix::Zero(2,2);integrator.definition.edit().M(0,1)=2;
 Vector y(2);y<<3,1;Vector row(2);row<<1,0;
 integrator.binding.edit().guards.push_back({row,0,1,"OBSERVE"});
 engineering::Flow q(integrator,y);
 check(std::abs(q.value(0,4)-11)<1e-12,"singular affine fallback");
 check(std::abs(q.state(4)[0]-11)<1e-12,"singular storage fallback");
 std::cout<<"trajectory tests passed; fixed-operator root="<<std::setprecision(17)<<root<<"\n";
 return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
