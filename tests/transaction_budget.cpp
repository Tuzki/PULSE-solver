#define main inherited_engineering_main
#include "engineering_events.cpp"
#undef main
int main() {
  try {
    {
      auto r=run("V1 N 0 DC=1\nR1 N 0 R=1\nEVENT_C CLK MODE=PERIODIC PERIOD=.00000762939453125 START=0",
                 ".765625",".125");
      complete(r);
      check(r.stats.transactions==100353,"normal time-advancing events did not exceed the former 100k limit");
      check(r.committed.at==Time::from(.765625),"unlimited run stopped early");
      check(r.report.at("transaction_limit_policy")=="UNLIMITED_TOTAL; BOUNDED_SAME_TIME_CLOSURE","budget policy missing");
    }
    {
      Options o;o.max_transactions=3;
      auto r=run("V1 N 0 DC=1\nR1 N 0 R=1\nEVENT_C CLK MODE=PERIODIC PERIOD=.125 START=0","1",".125",o);
      check(r.status=="STOPPED_UNRESOLVED"&&r.diagnostic.value("subcode","")=="TRANSACTION_BUDGET","explicit budget is not enforced");
      check(r.stats.transactions==3&&r.committed.at==Time::from(.25),"explicit budget did not preserve committed prefix");
    }
    zero_derivative_rejected();rollback_all_boundaries();
    std::cout<<"PASS default unlimited transactions, explicit budget and failure guards, "<<assertions<<" assertions\n";
    return 0;
  }catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}
}
