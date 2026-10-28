#pragma once
#include "pulse/core.hpp"
#include <array>
namespace pulse {
int portfolio_variant();
struct PortfolioStats {
 std::array<uint64_t,3>attempts{},accepted{},failed{};uint64_t restores=0,journal_records=0;
 Json failures=Json::array();
 std::array<std::map<std::string,uint64_t>,3> executed_paths;
 void record_failure(int algorithm,const RunState&checkpoint,Time target,const Error&error);
 Json description()const;
};
Mode portfolio_mode(const Model&,const RunState&,int,Stats&);
void portfolio_original_check(const Model&,const RunState&,const Mode&,const Vector&);
bool portfolio_retryable(const Error&);
void portfolio_reset_equations();
}
