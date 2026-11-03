#!/usr/bin/env python3
"""Compile/run extracted D.1 C++ helper against minimal type-compatible doubles.
Not an end-to-end solver build.
"""
from __future__ import annotations
import pathlib, tempfile, subprocess
import sys

p=pathlib.Path(__file__).with_name('apply_stage_d1.py')
s=p.read_text(encoding='utf8')
start=s.index('CowValue<ModeBinding> coordinate_bound_binding(const Model &m,')
stop=s.index("\nMode settle('",start)
helper=s[start:stop]
source=r'''
#include <Eigen/Dense>
#include <map>
#include <memory>
#include <functional>
#include <deque>
#include <cstring>
#include <vector>
#include <string>
#include <iostream>
using Matrix=Eigen::MatrixXd;using Vector=Eigen::VectorXd;
template<class T>struct CowValue {
    std::shared_ptr<T> v=std::make_shared<T>();
    CowValue()=default;
    CowValue(const T&x):v(std::make_shared<T>(x)){}
    const T&read()const{return *v;}
    T&edit(){if(!v.unique())v=std::make_shared<T>(*v);return *v;}
};
struct Guard{Vector row;};
struct ModeBinding{Matrix observations,residual_map,residual_reference;
    std::map<std::string,Vector>maps;std::vector<Guard>guards;};
struct Model{};
struct ModeCacheData{
    const Model*model=nullptr;size_t capacity=512;size_t rebound_capacity=512;
    struct CoordinateEntry { CowValue<ModeBinding> physical,internal; Matrix chart_l;};
    std::map<const ModeBinding*,CoordinateEntry,std::less<const ModeBinding*>> coordinate_entries;
    std::deque<const ModeBinding*> coordinate_order;
};
static thread_local ModeCacheData*active_mode_cache=nullptr;
'''+helper+r'''
int main(){
    Model m; ModeCacheData c;c.model=&m;active_mode_cache=&c;
    CowValue<ModeBinding> p;p.edit().observations=Matrix::Identity(3,3);
    p.edit().residual_map=Matrix::Identity(3,3);
    p.edit().residual_reference=Matrix::Identity(3,3);
    p.edit().maps.emplace("foo",Vector::Ones(3));
    p.edit().guards.push_back({Vector::Ones(3)});
    Matrix L=Matrix::Identity(3,3);L(0,1)=1.;
    auto a=coordinate_bound_binding(m,p,L);
    auto b=coordinate_bound_binding(m,p,L);
    if(&a.read()!=&b.read())return 1;
    if(&a.read()==&p.read())return 2;
    if(p.read().observations(0,1)!=0.)return 3;
    if(a.read().observations(0,1)!=1.)return 4;
    Matrix N=L;N(0,1)=0.;
    auto c2=coordinate_bound_binding(m,p,N);
    if(c2.read().observations(0,1)!=0.)return 5;
    std::cout<<"PASS compiled D.1b helper C++20 synthetic smoke\n";
}
'''
with tempfile.TemporaryDirectory() as tmp:
    src=pathlib.Path(tmp)/'d1_smoke.cpp';out=pathlib.Path(tmp)/'d1_smoke';src.write_text(source)
    subprocess.run(['g++','-std=c++20','-O3','-DNDEBUG','-ffp-contract=off','-fno-fast-math','-I/opt/pyvenv/lib/python3.13/site-packages/casadi/include/eigen3',str(src),'-o',str(out)],check=True)
    subprocess.run([str(out)],check=True)
