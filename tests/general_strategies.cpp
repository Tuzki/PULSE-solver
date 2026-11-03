#include "pulse/core.hpp"
#include "pulse/state_coordinates.hpp"
#include "pulse/solver_strategy.hpp"
#include "pulse/engineering.hpp"
#include <iostream>
#include <sstream>
#include <cmath>
using namespace pulse;
void check(bool c,const std::string&s){if(!c)throw std::runtime_error(s);}
std::string doc(const std::string&s){return "# PULSE Netlist v1.1\n\n## Parameters\n```pulse\n```\n\n## Network\n```pulse\n"+s+"\n```\n\n## Simulation\n```pulse\n.TRAN T_END=10u SAVE_DT=1u\n```\n\n## Layout\n```json\n{}\n```\n";}
void star(int n){
 std::ostringstream net;net<<"R_BUS BUS 0 R=2\n";
 double numerator=0,denominator=0;
 for(int i=0;i<n;i++){
  double inductance=.001*(i+1),v=i+1; numerator+=v/inductance;denominator+=1/inductance;
  net<<"V"<<i<<" A"<<i<<" AC DC="<<v<<"\nL"<<i<<" A"<<i<<" BUS L="<<inductance<<" IC_I=0\n";
 }
 auto m=compile(parse_markdown(doc(net.str()),"n_inductor.md"));m.numerical_coordinates=true;
 const auto&chart=persistent_chart(m);check(chart.active,"arbitrary-size cutset chart was not selected");
 check((chart.mix*chart.unmix-Matrix::Identity(m.ns+1,m.ns+1)).isZero(0),"chart inverse is not exact");
 RunState state;state.internal=persistent_encode(m,m.initial);state.physical=m.initial;Stats stats;
 ScopedModeCache cache(m,128);portfolio_reset_equations();
 state.mode=engineering::initial_mode(m,state.internal,{},stats);
 auto untouched=state.internal;
 for(int algorithm=0;algorithm<3;algorithm++){
  auto mode=portfolio_mode(m,state,algorithm,stats);
  check(mode.elimination_path==(algorithm==1?"CONSTRAINED_QR":"CONSTRAINED_LU"),"wrong actual constrained factorization");
  portfolio_original_check(m,state,mode,state.internal);
  Vector derivative=physical_increment(m,(mode.definition.read().M*state.internal).head(m.ns));
  for(const auto&p:m.parts)if(p.raw.kind=="L"){
   int i=std::stoi(p.raw.id.substr(1));double expected=i+1-numerator/denominator;
   check(std::abs(derivative[p.state]-expected)<1e-9,"derivative disagrees with analytical star solution");
  }
  check((state.internal-untouched).isZero(0),"strategy mutated checkpoint");
 }
 auto result=simulate(m,Options{});check(result.status=="COMPLETED",result.diagnostic.dump());
}
void multiple_blocks(){
 std::string net="V1 IN 0 DC=1\nR1 IN A R=2\nC1 A B C=1u IC_V=0\nC2 B C C=2u IC_V=0\nC3 C 0 C=3u IC_V=0\nR2 B 0 R=3\nR3 C 0 R=4\nL1 IN D L=.001 IC_I=0\nL2 D E L=.002 IC_I=0\nL3 E 0 L=.003 IC_I=0\nR4 D 0 R=5\nR5 E 0 R=6";
 auto m=compile(parse_markdown(doc(net),"multiple_rows.md"));m.numerical_coordinates=true;
 const auto&chart=persistent_chart(m);int changed=0;
 for(int i=0;i<m.ns;i++)if(!(chart.mix.row(i)-Matrix::Identity(m.ns+1,m.ns+1).row(i)).isZero(0))++changed;
 check(changed>=4,"only one row/device pair was transformed");
 auto result=simulate(m,Options{});check(result.status=="COMPLETED",result.diagnostic.dump());
 auto plain=compile(parse_markdown(doc(net),"physical_reference.md"));Stats stats;
 auto mode=engineering::initial_mode(plain,plain.initial,{},stats);engineering::Flow reference(mode,plain.initial);
 auto expected=reference.state(1e-5);
 check((result.committed.physical-expected).norm()<1e-10,"mixed RLC physical solution changed");
}
int main(){try{for(int n:{2,3,5,11})star(n);multiple_blocks();std::cout<<"PASS 2/3/5/11 unequal inductors, constrained LU/QR paths, analytical derivatives, multiple independent RLC coordinates, immutable checkpoints\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
