#include "pulse/engineering.hpp"
#include "pulse/solver_strategy.hpp"
#include <complex>
#include <fstream>
#include <iostream>
#include <cmath>
using namespace pulse;
void check(bool b,const char*s){if(!b)throw std::runtime_error(s);}
Matrix mat(const Json&j){Matrix m(j.size(),j.at(0).size());for(int i=0;i<m.rows();i++)for(int k=0;k<m.cols();k++)m(i,k)=j[i][k];return m;}
Vector vec(const Json&j){Vector v(j.size());for(int i=0;i<v.size();i++)v[i]=j[i];return v;}
int main(int argc,char**argv){try{
 std::ifstream file(argv[1]);Json j;file>>j;Mode m;m.M=mat(j["M"]);int n=m.M.rows()-1;m.invariant_generator=mat(j["generator"]);m.invariant_lift=Matrix::Zero(n+1,n+1);m.invariant_lift.topLeftCorner(n,n)=mat(j["lift"]);m.invariant_lift(n,n)=1;m.invariant_reduce=Matrix::Zero(n+1,n+1);m.invariant_reduce.topRows(n)=mat(j["reduce"]);m.invariant_reduce(n,n)=1;Vector x=vec(j["anchor"]),row=vec(j["row"]);m.maps["U"]=row;m.guards.push_back({row,0,1,"CMP"});engineering::Flow f(m,x);double t=j["time"],oracle=-0.0000237289361951568666;
 check(std::abs(f.value(0,t)-oracle)<2e-12,"C012 fixed-M scalar oracle");check(std::abs(f.observe(row,t)-row.dot(f.state(t)))<2e-12,"observable/state mismatch");auto bound=f.bounds(0,t,t);check(bound.lo<=oracle&&oracle<=bound.hi,"point estimate excludes fixed-M oracle");check(std::isfinite(f.scale(0))&&f.scale(0)<10,"spurious huge spectral scale remains");
 double rate=std::exp2(std::ceil(std::log2(mat(j["balanced"]).cwiseAbs().rowwise().sum().maxCoeff()))),split=.5/rate,lo=split*(1-1e-4),hi=split*(1+1e-4);
 check(std::abs(f.value(0,hi)-f.value(0,lo))<2e-8,"Taylor/modal branch jump");check(std::abs(f.value(0,t,1)-row.dot(m.M*f.state(t)))<1e-7,"fixed-M derivative mismatch");
 for(double pole:{0.,1e-80,-1e-80,1e-6,-1e-6,-2.,.7}){
  Mode q;q.M=Matrix::Zero(2,2);q.M(0,0)=pole;q.M(0,1)=1.5;Vector initial(2);initial<<.2,1;Vector r(2);r<<1,0;q.guards.push_back({r,0,1,"OBSERVE"});engineering::Flow flow(q,initial);
  auto exact=[&](double time,int order){long double z=static_cast<long double>(pole)*time;long double ph=pole==0?time:std::expm1(z)/pole;long double v=.2L*std::exp(z)+1.5L*ph;if(order==0)return v;long double d=pole*v+1.5L;for(int k=1;k<order;k++)d*=pole;return d;};
  for(double at:{.01,.5,2.,5.})for(int order=0;order<=2;order++){double want=double(exact(at,order));check(std::abs(flow.value(0,at,order)-want)<2e-10*(1+std::abs(want)),"zero/slow/growing pole value or derivative");}
  for(auto span:{std::pair<double,double>{.1,.8},{1.,2.},{.2,5.}})for(int order=0;order<=1;order++){auto b=flow.bounds(0,span.first,span.second,order);for(int k=0;k<=12;k++){double at=span.first+(span.second-span.first)*k/12;double v=double(exact(at,order));check(b.lo<=v&&v<=b.hi,"affine range misses analytic sample");}}
 }
 using C=std::complex<long double>;for(long double damping:{0.L,-.1L}){
  Mode q;q.M=Matrix::Zero(3,3);q.M(0,0)=q.M(1,1)=double(damping);q.M(0,1)=-.7;q.M(1,0)=.7;q.M(0,2)=1.5;q.M(1,2)=.7;Vector initial(3);initial<<.2,-.3,1;Vector r(3);r<<1,0,0;q.guards.push_back({r,0,1,"OBSERVE"});engineering::Flow flow(q,initial);C pole(damping,.7L),start(.2L,-.3L),forcing(1.5L,.7L);auto exact=[&](double at){return (std::exp(pole*static_cast<long double>(at))*start+(std::exp(pole*static_cast<long double>(at))-C(1))/pole*forcing).real();};
  for(double at:{.5,2.,10.})check(std::abs(flow.value(0,at)-double(exact(at)))<1e-10,"oscillatory affine value");auto b=flow.bounds(0,.2,20.);for(int k=0;k<=50;k++){double at=.2+19.8*k/50;check(b.lo<=exact(at)&&exact(at)<=b.hi,"oscillatory interval misses analytic sample");}
 }
 // Exact anchored transverse root: a broad coefficient envelope can cover a
 // nearby stationary point, but must not impose a hidden root-time veto.
 Mode anchored;anchored.M=Matrix::Zero(3,3);anchored.M(0,1)=-1;anchored.M(1,0)=1;
 Vector ax(3);ax<<1,0,1;Vector ag(3);ag<<1e8,1,-1e8;
 anchored.guards.push_back({ag,0,1,"CMP"});engineering::Flow af(anchored,ax);
 check(af.modal(),"anchored oscillator must exercise scalar modal path");
 auto ar=engineering::next_events(anchored,af,1e-9,1e-14);
 check(ar.candidates.size()==1&&ar.candidates[0].time<1e-14&&ar.candidates[0].slope>0,
       "coefficient envelope became an implicit timing veto");
 check(portfolio_retryable(Error(9,"BREAKPOINT_PREDICTION_MISMATCH","test",true)),"own-root residual failure must be retryable");
 std::cout<<"PASS fixed-M oracle, branch continuity, value/state/derivative, zero and signed slow poles, forced oscillation, range samples, finite scale\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}

