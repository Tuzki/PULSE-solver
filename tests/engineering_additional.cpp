// Small independent additions; public API only. Link pulse_core.
#define main engineering_original_main
#include "engineering_events.cpp"
#undef main
namespace {
void save_grid_independence() {
    const std::string net="MATH_ONE ONE = 1\nINT_X X ONE\nCMP_X G X OP=GE THRESHOLD=.3\n"
                          "SEL_DY DY G 1 2\nINT_Y Y DY\nEVENT_E E MODE=EDGE SOURCE=G EDGE=RISE";
    Options o; atomic_window(o,2e-8);
    auto a=run(net,"1",".1",o),b=run(net,"1",".125",o);
    complete(a);complete(b);
    check(a.t_atom==2e-8 && b.t_atom==2e-8,"SAVE_DT changed fixed engineering window");
    check(a.events==b.events,"SAVE_DT changed event decision/provenance");
    check(a.committed.mode.id==b.committed.mode.id,"SAVE_DT changed final mode");
    check(a.committed.physical.isApprox(b.committed.physical,1e-13),"SAVE_DT changed final storage state");
}
void pwa_capacitor() {
    auto r=run("I1 0 N DC=1\nC1 N 0 QV_TABLE=[(0,1),(1,3),(2,6)] IC_Q=1 RANGE=EXTEND","3",".125");
    complete(r);
    near(r.committed.physical[0],4,2e-12,"PWA capacitor charge");
    near(value(r,"V(N)"),4./3,2e-10,"PWA capacitor intercept");
    check(r.committed.mode.segments.begin()->second==1,"PWA capacitor segment not advanced");
}
void pwa_resistor() {
    auto r=run("MATH_ONE ONE = 1\nINT_X X ONE\nI1 0 N X\n"
               "R1 N 0 IV_TABLE=[(0,0),(1,1),(2,3)] RANGE=EXTEND","2",".125");
    complete(r);
    near(value(r,"V(N)"),1.5,2e-9,"PWA resistor voltage inverse");
    near(value(r,"I(R1)"),2,2e-9,"PWA resistor current");
    check(r.committed.mode.segments.begin()->second==1,"PWA resistor segment not advanced");
}
void held_comparator() {
    auto r=run("MATH_ONE ONE = 1\nEVENT_C CLK MODE=AT AT=.5\nREG_Q Q ONE CLK IC=0\n"
               "CMP_G G Q OP=GE THRESHOLD=.5\nEVENT_E E MODE=EDGE SOURCE=G EDGE=RISE");
    complete(r);near(value(r,"G"),1,0,"held comparator reclassification");
    auto e=triggers(r,"E");check(e.size()==1 && at(e[0])==Time::from(.5),"held comparator edge missing");
}
void held_pwa_resistor() {
    auto r=run("MATH_V VALUE = 1.5\nEVENT_C CLK MODE=AT AT=.5\nREG_Q Q VALUE CLK IC=0\n"
               "V1 N 0 Q\nR1 N 0 IV_TABLE=[(0,0),(1,1),(2,3)] RANGE=EXTEND");
    if(r.status=="COMPLETED") {
        near(value(r,"I(R1)"),2,2e-12,"held voltage step left PWA R in wrong segment");
        check(r.committed.mode.segments.begin()->second==1,"held R step did not select segment1");
    } else {
        check(r.status=="STOPPED_UNRESOLVED" && r.committed.at<Time::from(.5),
              "R jump stop: "+r.status+" at "+r.committed.at.canonical()+" "+r.diagnostic.dump());
    }
}
void mixed_held_comparator() {
    auto r=run("MATH_ZERO ZERO = 0\nINT_X X ZERO IC=0\nMATH_ONE ONE = 1\n"
               "EVENT_C CLK MODE=AT AT=.5\nREG_Q Q ONE CLK IC=0\nMATH_SUM SUM = X+Q\n"
               "CMP_G G SUM OP=GE THRESHOLD=.5\nEVENT_E E MODE=EDGE SOURCE=G EDGE=RISE");
    // Either support the discrete crossing or reject before publishing the inconsistent mode.
    if(r.status=="COMPLETED") {
        near(value(r,"G"),1,0,"mixed held+INT comparator stale after REG jump");
        auto e=triggers(r,"E");check(e.size()==1 && at(e[0])==Time::from(.5),"mixed comparator EDGE missing");
    } else {
        check(r.status=="STOPPED_UNRESOLVED","mixed jump failed without unresolved diagnosis");
        check(r.committed.at<Time::from(.5),"unresolved jump committed stale mode");
        check(triggers(r,"E").empty(),"unresolved jump leaked EDGE");
    }
}

void continuous_boolean_closure() {
    // Check multiple combinational levels, with and without unrelated clocks.
    for (const auto &period : {std::string(), std::string(".25"), std::string(".125")}) {
        std::string net =
            "MATH_ONE ONE = 1\nINT_X X ONE IC=0\n"
            "CMP_A A X OP=GE THRESHOLD=.3125\n"
            "SEL_REAL R A -1 1\nCMP_B B R OP=LT THRESHOLD=0\n"
            "SEL_SECOND S B 5 -5\nCMP_C C S OP=GT THRESHOLD=0\n"
            "EVENT_A EA MODE=EDGE SOURCE=A EDGE=BOTH\n"
            "EVENT_B EB MODE=EDGE SOURCE=B EDGE=BOTH\n"
            "EVENT_C EC MODE=EDGE SOURCE=C EDGE=BOTH\n";
        if (!period.empty())
            net += "EVENT_T T MODE=PERIODIC PERIOD=" + period + " START=0\n"
                   "MATH_INC INC = COUNT+1\nREG_COUNT COUNT INC T IC=0\n";
        auto model = compile(parse_markdown(document(net, "1", ".0625")));
        check(!model.signals.at("X").held, "continuous ramp was classified held");
        check(model.signals.at("R").held, "Boolean-selected REAL must be event-held");
        auto r = simulate(model);complete(r);
        auto a = triggers(r, "EA"), b = triggers(r, "EB"), c = triggers(r, "EC");
        check(a.size()==1 && b.size()==1 && c.size()==1, "cascade lost or duplicated an edge");
        near(at(a[0]).seconds(), .3125, 2*r.t_atom+1e-12, "continuous source edge");
        check(at(a[0])==at(b[0]) && at(a[0])==at(c[0]),
              "Boolean cascade waited for a later physical time");
        for (const auto &segment : r.segments) {
            auto eval=[&](const std::string &name) {
                return segment.state.mode.maps.at(name).dot(segment.state.physical);
            };
            near(eval("B"),eval("A")==0 ? 1 : 0,0,"stale first Boolean decode");
            near(eval("C"),eval("A"),0,"stale second Boolean decode");
        }
        history(r);
    }
}


void comparator_switch_diode_closure() {
    const std::string power =
        "V_BUS OUT 0 DC=100\nI_IN 0 SW DC=1\n"
        "SW_M SW 0 G RON=.1 ROFF=1G\n"
        "R_D SW OUT IV_TABLE=[(-1000,-.000001001),(1,0),(1000,9990)] RANGE=EXTEND\n";
    auto a=run(power+"MATH_ONE ONE = 1\nINT_T T ONE IC=0\n"
                     "CMP_OFF OFF T OP=GE THRESHOLD=.25\nSEL_G BOOL::G OFF 1 0",
               ".5",".01");
    auto b=run(power+"EVENT_OFF OFF MODE=AT AT=.25\nEVENT_NEVER NEVER MODE=AT AT=1\n"
                     "REG_G G MODE=SR SET=NEVER RESET=OFF PRIORITY=RESET IC=1",
               ".5",".01");
    complete(a);complete(b);
    near(value(a,"V(SW)"),101.1,2e-7,"diode clamp after comparator switch OFF");
    near(value(a,"V(SW)"),value(b,"V(SW)"),1e-12,"CMP/REG topology closure disagree");
    near(value(a,"I(R_D)"),1.,2e-7,"diode carries preserved source current");
    near(value(a,"T"),.5,1e-12,"topology closure changed integrator state");
    check(a.committed.mode.segments.begin()->second==1,"diode old segment retained");
    history(a);history(b);
}


void leaky_bridge_algebraic_precision() {
    // An all-off bridge fixes its common mode through four 1 nS leaks.
    // Symmetry makes each diagonal voltage depend only on Vin and Cin;
    // downstream bus charge and inductor flux must not contaminate it.
    const std::string diode=" IV_TABLE=[(-1000000,-.0010000006),(.6,0),(1000000,49999970)] RANGE=EXTEND\n";
    const std::string net=
        "MATH_ZERO ZERO = 0\nINT_SIN SIN ZERO IC=.007174745819907179\n"
        "MATH_AC AC = 141.42135623730951*SIN\nV_AC NA REF1 AC\nV_PROBE NA NB DC=0\n"
        "R_D002 NB P"+diode+"R_D003 N NB"+diode+
        "R_D004 REF1 P"+diode+"R_D005 N REF1"+diode+
        "L_IN P LNODE L=.001 IC_I=.004442025715321977\n"
        "C_IN P N C=1e-7 IC_V=-.18533771549075333\n"
        "C_BUS OUT N C=.001 IC_V=478.7326759668174\n"
        "R_BOOST SW OUT IV_TABLE=[(-1000000,-.0010000009385),(.9385,0),(1000000,53269360.047942467)] RANGE=EXTEND\n"
        "CMP_GATE G 0 OP=GT THRESHOLD=1\nSW_M SW N G RON=.065 ROFF=1G\n"
        "R_LOAD OUT N R=500\nR_WIRE LNODE SW R=.001\n";
    auto m=compile(parse_markdown(document(net)));
    std::map<int,bool> bits;for(int i:m.cmps)bits[i]=false;
    std::map<int,int> segments;for(int i:m.pwas)segments[i]=0;
    Stats stats;auto mode=compile_specified(m,m.initial,{},stats,bits,segments);
    int bus=-1,flux=-1;
    for(int i=0;i<m.ns;++i){if(m.state_ids[i]=="C_BUS/q")bus=i;if(m.state_ids[i]=="L_IN/phi")flux=i;}
    check(bus>=0 && flux>=0,"bridge state identifiers");
    int checked=0;
    for(const auto &g:mode.guards)
        if(m.parts[g.part].raw.id=="R_D002" || m.parts[g.part].raw.id=="R_D005") {
            near(g.row[bus],0.,1e-13,"off-bridge spurious bus coupling");
            near(g.row[flux],0.,1e-10,"off-bridge spurious flux coupling");
            near(g.row.dot(m.initial),0.,2e-13,"off-bridge boundary residual");
            ++checked;
        }
    check(checked==2,"missing diagonal bridge guards");
}

}
int main() {
    std::cout<<std::unitbuf;
    for(const auto &[name,body]:std::vector<std::pair<std::string,std::function<void()>>>{
        {"save_grid_independence",save_grid_independence},{"pwa_capacitor",pwa_capacitor},
        {"pwa_resistor",pwa_resistor},{"held_comparator",held_comparator},
        {"mixed_held_comparator",mixed_held_comparator},{"held_pwa_resistor",held_pwa_resistor},
        {"continuous_boolean_closure",continuous_boolean_closure},
        {"comparator_switch_diode_closure",comparator_switch_diode_closure},
        {"leaky_bridge_algebraic_precision",leaky_bridge_algebraic_precision}}) {
        std::cout<<"RUN "<<name<<'\n';
        try{body();++passes;std::cout<<"PASS "<<name<<'\n';}
        catch(const std::exception&e){++failures;std::cout<<"FAIL "<<name<<": "<<e.what()<<'\n';}
    }
    std::cout<<passes<<" PASS / "<<failures<<" FAIL / "<<assertions<<" assertions\n";
    return failures?1:0;
}
