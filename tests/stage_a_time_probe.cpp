#include "pulse/time_origin.hpp"
#include <iostream>
int main(){
    int64_t whole;uint64_t tick,subtick;
    while(std::cin>>whole>>tick>>subtick){
        auto result=pulse::decimal_origin_from_binary_time(whole,tick,subtick);
        if(result.value)std::cout<<result.value->digits<<'|'<<result.value->exponent<<'\n';
        else std::cout<<pulse::origin_issue_name(result.issue)<<'\n';
    }
}
