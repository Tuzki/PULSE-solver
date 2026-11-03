// Stage D.1 regression: no COW aliasing, exact chart math, +0/-0 behavior.
// This test has real runtime checks even when NDEBUG is set.
#include "pulse/core.hpp"
#include "pulse/solver_strategy.hpp"
#include "pulse/engineering.hpp"
#include <cmath>
#include <cstring>
#include <iostream>
#include <stdexcept>

using namespace pulse;
static void check(bool cond, const char *reason) {
    if (!cond) throw std::runtime_error(reason);
}
static bool identical(const Matrix &a, const Matrix &b) {
    return a.rows()==b.rows() && a.cols()==b.cols() &&
           (a.size()==0 || std::memcmp(a.data(),b.data(),size_t(a.size())*sizeof(double))==0);
}
static bool identical(const Vector &a, const Vector &b) {
    return a.size()==b.size() &&
           (a.size()==0 || std::memcmp(a.data(),b.data(),size_t(a.size())*sizeof(double))==0);
}

// Before D.1: the exact original expression order and math, on one Mode.
static CowValue<ModeBinding> old_coordinate_transform(CowValue<ModeBinding> binding,const Matrix &L) {
    if(binding.read().observations.cols()==L.rows())
        binding.edit().observations=binding.read().observations*L;
    if(binding.read().residual_map.rows())
        binding.edit().residual_map=binding.read().residual_map*L;
    if(binding.read().residual_reference.rows())
        binding.edit().residual_reference=binding.read().residual_reference*L;
    for(auto &[name,row]:binding.edit().maps) row=L.transpose()*row;
    for(auto &guard:binding.edit().guards) guard.row=L.transpose()*guard.row;
    return binding;
}

static void check_binding(const ModeBinding &a, const ModeBinding &b) {
    check(identical(a.observations,b.observations),"observations changed");
    check(identical(a.residual_map,b.residual_map),"residual map changed");
    check(identical(a.residual_reference,b.residual_reference),"residual reference changed");
    check(a.maps.size()==b.maps.size(),"maps count changed");
    for(const auto &[name,row]:a.maps) {
        auto it=b.maps.find(name);
        check(it!=b.maps.end() && identical(row,it->second),"map data changed");
    }
    check(a.guards.size()==b.guards.size(),"guard count changed");
    for(size_t i=0;i<a.guards.size();++i)
        check(identical(a.guards[i].row,b.guards[i].row),"guard row changed");
}

static void coordinate_cache() {
    Model model; // Scoped cache only reads its identity here.
    ModeBinding physical;
    physical.observations=Matrix::Identity(3,3);
    physical.residual_map=Matrix::Zero(2,3);
    physical.residual_map<<1.,-2.,+0.,-0.,3.,4.;
    physical.residual_reference=Matrix::Zero(2,3);
    physical.residual_reference<<1.,2.,-0.,-3.,+0.,5.;
    Vector v(3);v<<1.,-0.,2.;
    physical.maps.emplace("sig",v);
    Vector g(3);g<<-2.,0.,3.;
    physical.guards.push_back({g,0,1,"CMP"});
    CowValue<ModeBinding> source(std::move(physical));
    Matrix L=Matrix::Identity(3,3);
    L(0,1)=-1.;L(1,0)=1.;L(2,2)=2.;

    const auto expected=old_coordinate_transform(source,L);
    CowValue<ModeBinding> saved_first_scope;
    {
        ScopedModeCache scope(model,4);
        auto actual=coordinate_bound_binding(model,source,L);
        saved_first_scope=actual;
        check_binding(actual.read(),expected.read());
        auto repeat=coordinate_bound_binding(model,source,L);
        check(repeat.shares_storage_with(actual),"repeated source did not reuse binding");
        repeat.edit().maps.at("sig")[0]=99.;
        check_binding(actual.read(),expected.read());
        check_binding(source.read(),source.read());
        check(source.read().maps.at("sig")[0]==1.,"physical binding mutated");

        Matrix other=L;other(0,1)=0.;
        auto other_out=coordinate_bound_binding(model,source,other);
        check_binding(other_out.read(),old_coordinate_transform(source,other).read());
        check(!other_out.shares_storage_with(actual),"changed chart reused stale binding");
        auto back=coordinate_bound_binding(model,source,L);
        check_binding(back.read(),expected.read());

        // The existing cache-off option and nested simulation ownership remain
        // authoritative, including when the same source object is supplied.
        {
            ScopedModeCache disabled(model,0);
            auto a=coordinate_bound_binding(model,source,L);
            auto b=coordinate_bound_binding(model,source,L);
            check_binding(a.read(),expected.read());
            check(!a.shares_storage_with(b),"disabled cache reused coordinate binding");
        }
        check(coordinate_bound_binding(model,source,L).shares_storage_with(back),
              "nested disabled scope did not restore outer cache");
        Model other_model;
        auto other_model_a=coordinate_bound_binding(other_model,source,L);
        auto other_model_b=coordinate_bound_binding(other_model,source,L);
        check(!other_model_a.shares_storage_with(other_model_b),
              "foreign Model reused active Model cache");
        {
            ScopedModeCache nested(other_model,4);
            auto a=coordinate_bound_binding(other_model,source,L);
            auto b=coordinate_bound_binding(other_model,source,L);
            check(a.shares_storage_with(b),"nested Model cache did not reuse source");
            check(!a.shares_storage_with(back),"nested Model shared outer derived storage");
        }
        check(coordinate_bound_binding(model,source,L).shares_storage_with(back),
              "nested Model scope did not restore outer cache");

        CowValue<ModeBinding> physically_mutated=source;
        physically_mutated.edit().maps.at("sig")[0]=101.;
        auto mutated=coordinate_bound_binding(model,physically_mutated,L);
        check(!mutated.shares_storage_with(back),"modified source reused stale coordinate cache");
        check_binding(mutated.read(),old_coordinate_transform(physically_mutated,L).read());

        // FIFO eviction must not alias a released physical-object address.
        // The first source binding remains alive in the caller.
        for(int i=0;i<520;++i) {
            CowValue<ModeBinding> extra;
            extra.edit().observations=Matrix::Identity(3,3);
            extra.edit().residual_map=Matrix::Zero(2,3);
            extra.edit().maps.emplace("idx",Vector::Constant(3,double(i)));
            (void)coordinate_bound_binding(model,extra,L);
        }
        auto after_evict=coordinate_bound_binding(model,source,L);
        check_binding(after_evict.read(),expected.read());
        check(!after_evict.shares_storage_with(actual),"FIFO eviction did not release transformed entry");
    }
    // A different simulation scope must not share a transformed Binding.
    {
        ScopedModeCache second(model,4);
        auto next=coordinate_bound_binding(model,source,L);
        check_binding(next.read(),expected.read());
        check(!next.shares_storage_with(expected),"raw transform unexpectedly aliased original object");
        check(!next.shares_storage_with(saved_first_scope),"scoped cache survived its scope");
    }
}

static void vector_comparison() {
    // Flow::compatible must retain ordinary numeric equality, not memcmp.
    Mode mode;
    mode.definition.edit().M=Matrix::Zero(3,3);
    mode.definition.edit().M(0,0)=-2.;
    Vector row(3);row<<+0.,1.,0.;
    mode.binding.edit().maps.emplace("signal",row);
    Vector initial(3);initial<<1.,2.,1.;
    engineering::Flow flow(mode,initial);
    Mode signed_zero=mode;
    signed_zero.binding.edit().maps.at("signal")[0]=-0.;
    check(flow.compatible(signed_zero),"numeric +0/-0 compatibility changed");
    Mode changed=mode;
    changed.binding.edit().maps.at("signal")[1]=3.;
    check(!flow.compatible(changed),"incompatible flow incorrectly reused");
}

static void immutable_norms() {
    Matrix A(2,3);A<<+0.,-1.,3.,4.,-0.,1.e-100;
    ObserverBinding observer;
    observer.A=A;
    observer.a_row_norm.resize(A.rows());
    for(int i=0;i<A.rows();++i)
        observer.a_row_norm[i]=observer.A.row(i).lpNorm<1>();
    for(int i=0;i<A.rows();++i)
        check(observer.a_row_norm[i]==A.row(i).lpNorm<1>(),"immutable A norm changed");
}

int main() {
    try {coordinate_cache();vector_comparison();immutable_norms();}
    catch(const std::exception &e) {std::cerr<<"Stage D.1 FAILED: "<<e.what()<<'\n';return 1;}
    std::cout<<"PASS Stage D.1 scoped coordinate cache, COW, chart, vector equality\n";
    return 0;
}
