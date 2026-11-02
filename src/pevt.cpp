#include "pulse/pevt.hpp"
#include "pulse/engineering.hpp"
#include "pulse/software.hpp"
#include "pulse/state_coordinates.hpp"
#include <bit>
#include <algorithm>
#include <fstream>
#include <limits>
#include <set>
#include <cstring>
#include <deque>

#include <cstdio>
#include <cstdlib>
namespace pulse {
namespace {
constexpr uint32_t none=UINT32_MAX;
constexpr uint64_t noevent=UINT64_MAX;
constexpr size_t capacity=512*1024*1024;
using Bytes=std::vector<uint8_t>;
void put(Bytes&b,uint64_t v,size_t n){for(size_t i=0;i<n;++i)b.push_back(uint8_t(v>>(8*i)));}
void real(Bytes&b,double v){put(b,std::bit_cast<uint64_t>(v),8);}
void time(Bytes&b,Time t){put(b,std::bit_cast<uint64_t>(t.whole),8);put(b,t.tick,8);put(b,t.subtick,8);}
std::string key(const Bytes&b){return b.empty()?std::string{}:std::string(reinterpret_cast<const char*>(b.data()),b.size());}
bool same(const Vector&a,const Vector&b){return a.size()==b.size()&&(!a.size()||std::memcmp(a.data(),b.data(),size_t(a.size())*8)==0);}
bool bits(double a,double b){return std::bit_cast<uint64_t>(a)==std::bit_cast<uint64_t>(b);}
struct Read {
  const Bytes&b;size_t p=0;
  uint64_t word(size_t n){require(n<=8&&p<=b.size()&&n<=b.size()-p,11,"PEVT_TRUNCATED","truncated event stream");uint64_t v=0;for(size_t i=0;i<n;++i)v|=uint64_t(b[p++])<<(8*i);return v;}
  uint32_t id(){return uint32_t(word(4));}
  double number(){double v=std::bit_cast<double>(word(8));require(std::isfinite(v),11,"PEVT_NONFINITE","nonfinite archive value");return v;}
  Time at(){Time t;t.whole=std::bit_cast<int64_t>(word(8));t.tick=word(8);t.subtick=word(8);require(t.whole>=0,11,"PEVT_TIME","negative event time");return t;}
  Vector vector(size_t n){require(n<=10000,11,"PEVT_SHAPE","oversized state");Vector x(n);for(size_t i=0;i<n;++i)x[i]=number();return x;}
  void end(){require(p==b.size(),11,"PEVT_TRAILING","trailing section bytes");}
};
Json parse(const Bytes&b){return Json::parse(b.begin(),b.end());}
Bytes text(const Json&j){auto s=j.dump();return Bytes(s.begin(),s.end());}
struct State {Vector x;uint32_t values;};
struct Instance {uint32_t definition,values;};
struct FlowRecord {uint64_t reference,origin;uint32_t state,equation;Time offset;};
struct Event {
  uint64_t id=0;Time at;uint64_t transaction=0;uint32_t micro=0,kind=1,state=0,before=0,after=0,observer=none,outgoing=none;
  std::vector<uint32_t> pre,post;std::vector<std::pair<uint32_t,uint32_t>> members;
};
struct Section {uint32_t type;uint64_t count;Bytes bytes;};
Matrix matrix(const Json&j){auto r=j.at("rows").get<size_t>(),c=j.at("cols").get<size_t>();require(r<=10000&&c<=10000&&r*c<=1000000,11,"PEVT_SHAPE","invalid matrix shape");auto a=j.at("data").get<std::vector<double>>();require(a.size()==r*c,11,"PEVT_SHAPE","matrix length differs");Matrix m(r,c);for(size_t i=0;i<a.size();++i)m.data()[i]=a[i];require(m.allFinite(),11,"PEVT_NONFINITE","nonfinite coefficient");return m;}
}

struct PevtArchive::Data {
  struct Modal {uint32_t component;int part;std::string signal;bool region;};
  size_t nx;uint64_t equation_calls=0,definition_encodes=0,definition_hits=0;Json meta,definitions=Json::array(),component_modes=Json::array();
  std::vector<Matrix> blocks;std::vector<std::vector<double>> values;std::vector<Instance> instances;
  std::vector<State> states;std::vector<FlowRecord> flows;std::vector<Event> events;
  std::vector<Modal> modals;std::vector<std::string> slots;std::map<std::string,int> real_rows;
  std::map<std::string,uint32_t> component_ids,signal_ids,block_ids,value_ids,definition_ids,instance_ids,state_ids,component_mode_ids;
  std::map<uint64_t,std::pair<uint64_t,uint32_t>> origins;
  // Bounded stable-definition cache; dynamic observation slots bind separately.
  // This is merely a shortcut to the unchanged canonical PULSEES1 encoder.
  struct RecentEquation { Mode mode; uint32_t id; uint64_t discrete_signature; };
  std::deque<RecentEquation> recent_equations_;
  uint64_t definition_candidate_checks=0,definition_signature_skips=0;
  static uint64_t discrete_signature(const Mode&m){
    uint64_t h=14695981039346656037ULL;
    auto mix=[&](uint64_t v){for(int j=0;j<8;++j){h^=uint8_t(v>>(8*j));h*=1099511628211ULL;}};
    mix(uint64_t(m.numerical_strategy));mix(m.bools.size());
    for(const auto &[name,b]:m.bools){mix(name.size());for(unsigned char c:name){h^=c;h*=1099511628211ULL;}mix(b);}
    mix(m.segments.size());for(const auto &[id,segment]:m.segments){mix(uint64_t(id));mix(uint64_t(segment));}
    return h;
  }
  static bool identical(const Matrix&a,const Matrix&b) {
    return a.rows()==b.rows() && a.cols()==b.cols() &&
           (a.size()==0 || std::memcmp(a.data(),b.data(),size_t(a.size())*sizeof(double))==0);
  }
  static bool identical(const Vector&a,const Vector&b) {
    return a.size()==b.size() &&
           (a.size()==0 || std::memcmp(a.data(),b.data(),size_t(a.size())*sizeof(double))==0);
  }
  bool same_archive_definition(const Mode&a,const Mode&b) const {
    if(a.observer_maps!=b.observer_maps || a.observer_rows!=b.observer_rows ||
       a.numerical_strategy!=b.numerical_strategy || a.bools!=b.bools ||
       a.segments!=b.segments || a.maps.size()!=b.maps.size() ||
       a.guards.size()!=b.guards.size())return false;
    if(!identical(a.M,b.M) || !identical(a.observations,b.observations) ||
       !identical(a.constraints,b.constraints) ||
       !identical(a.residual_map,b.residual_map) ||
       !same_reference(a,b) ||
       !identical(a.invariant_lift,b.invariant_lift) ||
       !identical(a.invariant_generator,b.invariant_generator) ||
       !identical(a.invariant_reduce,b.invariant_reduce))return false;
    auto x=a.maps.begin(), y=b.maps.begin();
    for(;x!=a.maps.end();++x,++y)
      if(x->first!=y->first)return false;
      else if(a.observer_maps.count(x->first)){
        if(x->second.size()!=y->second.size()||!x->second.size()||std::memcmp(x->second.data(),y->second.data(),size_t(x->second.size()-1)*sizeof(double))!=0)return false;
      }else if(!identical(x->second,y->second))return false;
    for(size_t i=0;i<a.guards.size();++i){
      const auto&g=a.guards[i];const auto&h=b.guards[i];
      if(g.part!=h.part || g.direction!=h.direction || g.kind!=h.kind ||
         g.knot!=h.knot || g.segment!=h.segment || g.step!=h.step ||
         !identical(g.row,h.row))return false;
    }
    return true;
  }
  bool same_reference(const Mode&a,const Mode&b) const {
    const auto &x=a.residual_reference,&y=b.residual_reference;
    if(x.rows()!=y.rows()||x.cols()!=y.cols())return false;
    std::vector<size_t> dynamic;
    for(const auto &name:a.observer_maps){
      auto row=real_rows.find(name);auto left=a.maps.find(name),right=b.maps.find(name);
      if(row==real_rows.end()||left==a.maps.end()||right==b.maps.end()||x.cols()!=Eigen::Index(nx)||row->second>=x.rows()||left->second.size()!=Eigen::Index(nx)||right->second.size()!=Eigen::Index(nx))return false;
      if(!left->second.head(nx-1).isZero(0)||!right->second.head(nx-1).isZero(0)||
         !bits(x(row->second,nx-1),left->second[nx-1])||!bits(y(row->second,nx-1),right->second[nx-1]))return false;
      dynamic.push_back(size_t(row->second)+size_t(x.rows())*(nx-1));
    }
    std::sort(dynamic.begin(),dynamic.end());size_t start=0;
    for(size_t skip:dynamic){if(skip>start&&std::memcmp(x.data()+start,y.data()+start,(skip-start)*sizeof(double)))return false;start=skip+1;}
    return size_t(x.size())==start||std::memcmp(x.data()+start,y.data()+start,(size_t(x.size())-start)*sizeof(double))==0;
  }
  uint32_t bind_instance(uint32_t definition,uint32_t values_id){
    Bytes b;put(b,definition,4);put(b,values_id,4);auto k=key(b);
    if(auto it=instance_ids.find(k);it!=instance_ids.end())return it->second;
    auto index=uint32_t(instances.size());instance_ids[k]=index;instances.push_back({definition,values_id});return index;
  }
  uint32_t remember_equation(const Mode&m,uint32_t id) {
    if(recent_equations_.size()>=64)recent_equations_.pop_front();
    recent_equations_.push_back({m,id,discrete_signature(m)});return id;
  }

  explicit Data(const Model&m,const RunState&s):nx(size_t(s.internal.size())) {
    require(nx>0&&nx<=10000,11,"PEVT_SHAPE","invalid state dimension");
    meta={{"state_dimension",nx},{"value_slot_count",0},{"modal_component_count",0},{"state_layout",Json::array()},
      {"components",Json::array()},{"signals",Json::array()},{"modal_components",Json::array()},
      {"component_modes",Json::array()},{"value_slots",Json::array()},
      {"numerical_context",{{"implementation","PULSE-native-flow"},{"version","1.2pre"},{"double_digits",std::numeric_limits<double>::digits},{"long_double_digits",std::numeric_limits<long double>::digits},{"long_double_max_exponent",std::numeric_limits<long double>::max_exponent}}},
      {"atomic_time",0.0},{"boundary_rule","POST_MODE"},{"initial_event_id",0},{"default_save_dt",0.0},{"provenance",Json::object()}};
    for(size_t i=0;i<m.parts.size();++i){auto id=add_component(m.parts[i].raw.id,m.parts[i].raw.kind,int(i));meta["components"][id]["ports"]=m.parts[i].ports;meta["components"][id]["arguments"]=m.parts[i].raw.args;meta["components"][id]["parameters"]=m.parts[i].raw.options;meta["components"][id]["curve_x"]=m.parts[i].curve.x;meta["components"][id]["curve_y"]=m.parts[i].curve.y;}
    for(auto&t:m.netlist.tasks)add_component(t.name,"SOFTWARE_TASK",-1);
    for(size_t i=0;i<nx;++i) {
      std::string name=i<m.state_ids.size()?m.state_ids[i]:(i+1==nx?"1":"x"+std::to_string(i));
      meta["state_layout"].push_back({{"index",i},{"component_id",none},{"name",name},{"unit",i+1==nx?"1":"internal"},{"meaning","original fixed internal coordinate"}});
    }
    meta["provenance"]["dependency_roles"]=m.dependency_roles;
    if(!m.parts.empty()){auto chart=persistent_description(m);meta["provenance"]["persistent_chart"]=chart;for(size_t i=0;i<chart["internal_coordinate_ids"].size();++i)meta["state_layout"][i]["name"]=chart["internal_coordinate_ids"][i];}
    int row=int(m.nodes.size());for(auto&[name,index]:m.branches)row+=int(m.parts.at(index).ports.size());
    for(auto&[name,signal]:m.signals)if(signal.type==Signal::REAL)real_rows[name]=row++;
    for(auto&[name,v]:s.mode.maps) {
      uint32_t owner=none;std::string unit="unspecified";
      if(auto i=m.signals.find(name);i!=m.signals.end())if(auto c=component_ids.find(i->second.driver);c!=component_ids.end())owner=c->second;
      if(name.starts_with("V("))unit="V";
      if(name.starts_with("I("))unit="A";
      if(owner!=none&&owner<m.parts.size()){const auto&p=m.parts.at(owner);if(p.raw.kind=="SENSOR"&&p.raw.args.size()>1)unit=p.raw.args[1]=="V"?"V":p.raw.args[1]=="I"?"A":"unspecified";}
      signal_ids[name]=uint32_t(meta["signals"].size());meta["signals"].push_back({{"signal_id",signal_ids[name]},{"component_id",owner},{"name",name},{"unit",unit}});
      auto source=m.signals.find(name);
      if(source!=m.signals.end()&&source->second.held) {
        slots.push_back(name);meta["value_slots"].push_back({{"slot_id",slots.size()-1},{"name",name},{"unit",unit},{"role",m.software_outputs.count(name)?"HELD_OUTPUT":"INPUT"}});
      }
    }
    for(auto&[part,region]:s.mode.segments){uint32_t id=part>=0&&size_t(part)<m.parts.size()?uint32_t(part):add_component("region_"+std::to_string(part),"REGION",part);modals.push_back({id,part,"",true});}
    std::set<uint32_t> modal_ids;for(auto&modal:modals)modal_ids.insert(modal.component);
    for(auto&[name,value]:s.mode.bools) {
      auto it=m.signals.find(name);uint32_t id=it!=m.signals.end()&&component_ids.count(it->second.driver)?component_ids.at(it->second.driver):add_component(name,"BOOL",-1);
      if(modal_ids.count(id))id=add_component(name+"@bool","BOOL",-1);
      modals.push_back({id,-1,name,false});modal_ids.insert(id);
    }
    for(size_t i=0;i<m.parts.size();++i)if(m.parts[i].raw.kind=="SW"&&!modal_ids.count(uint32_t(i))) {
      auto gate=m.parts[i].raw.args.at(2);modals.push_back({uint32_t(i),int(i),gate,false});modal_ids.insert(uint32_t(i));
    }
    for(auto&modal:modals)meta["modal_components"].push_back(modal.component);
    meta["value_slot_count"]=slots.size();meta["modal_component_count"]=modals.size();
    auto eq=equation(s.mode);Event first;first.at=s.at;first.state=state(s.internal,instances.at(eq).values);first.before=first.after=eq;first.pre=first.post=modes(s.mode);
    events.push_back(first);events.back().observer=flow(s,0);
  }
  uint32_t add_component(const std::string&name,const std::string&type,int part) {
    if(component_ids.count(name))return component_ids.at(name);
    auto id=uint32_t(meta["components"].size());component_ids[name]=id;
    meta["components"].push_back({{"component_id",id},{"name",name},{"type",type},{"source_part_index",part}});return id;
  }
  std::vector<uint32_t> modes(const Mode&m) {
    std::vector<uint32_t> result;
    for(auto&modal:modals) {
      int value=modal.region?m.segments.at(modal.part):m.bools.count(modal.signal)?int(m.bools.at(modal.signal)):is_literal(modal.signal)?int(number(modal.signal)!=0):0;
      auto k=std::to_string(modal.component)+":"+std::to_string(value);auto it=component_mode_ids.find(k);
      if(it==component_mode_ids.end()) {
        auto id=uint32_t(component_modes.size());component_mode_ids[k]=id;
        component_modes.push_back({{"component_id",modal.component},{"mode_id",id},{"definition",{{"kind",modal.region?"REGION":"BOOL"},{"source_part_index",modal.part},{"signal",modal.signal},{"value",value}}}});result.push_back(id);
      }else result.push_back(it->second);
    }return result;
  }
  uint32_t value_set(const Mode&m) {
    std::vector<double> v;Bytes b;
    for(auto&name:slots){auto&row=m.maps.at(name);require(row.size()==Eigen::Index(nx),11,"PEVT_SHAPE","held value row differs");double value=row[row.size()-1];v.push_back(value);real(b,value);}
    auto k=key(b);if(value_ids.count(k))return value_ids.at(k);auto id=uint32_t(values.size());value_ids[k]=id;values.push_back(std::move(v));return id;
  }
  uint32_t block(const Matrix&m,const std::vector<std::pair<uint32_t,uint32_t>>&bindings) {
    Bytes b;put(b,m.rows(),4);put(b,m.cols(),4);for(Eigen::Index i=0;i<m.size();++i)real(b,m.data()[i]);
    for(auto[index,slot]:bindings){put(b,index,4);put(b,slot,4);}auto k=key(b);
    if(block_ids.count(k))return block_ids.at(k);
    auto id=uint32_t(blocks.size());block_ids[k]=id;blocks.push_back(m);return id;
  }
  uint32_t equation(const Mode&m) {
    ++equation_calls;
    const auto signature=discrete_signature(m);
    for(const auto&entry:recent_equations_){
      if(entry.discrete_signature!=signature){++definition_signature_skips;continue;}
      ++definition_candidate_checks;
      if(same_archive_definition(m,entry.mode)){
        ++definition_hits;return bind_instance(instances.at(entry.id).definition,value_set(m));
      }
    }
    ++definition_encodes;
    auto vs=value_set(m);auto encoded=archive_encode_mode(m);Json definition={{"definition_id",0},{"observation_rows",Json::array()},{"guards",Json::array()},{"dynamic_bindings",Json::array()},{"numerical_strategy",m.numerical_strategy},{"component_mode_ids",modes(m)},{"observer_maps",m.observer_maps},{"observer_rows",m.observer_rows}};
    std::map<std::string,std::vector<std::pair<uint32_t,uint32_t>>> binding;
    for(size_t slot=0;slot<slots.size();++slot) {
      const auto&name=slots[slot];auto&source=encoded["maps"][name];
      bool constant=source["data"].size()==nx;for(size_t i=0;i+1<nx&&constant;++i)constant=source["data"][i].get<double>()==0;
      if(constant&&!m.bools.count(name))binding["map:"+name].push_back({uint32_t(nx-1),uint32_t(slot)});
      auto row=real_rows.find(name);auto&reference=encoded["residual_reference"];
      if(row!=real_rows.end()&&row->second>=0&&uint32_t(row->second)<reference["rows"].get<uint32_t>()&&reference["cols"].get<size_t>()==nx&&!m.bools.count(name)) {
        auto index=uint32_t(row->second)+reference["rows"].get<uint32_t>()*uint32_t(nx-1);
        if(bits(reference["data"][index].get<double>(),values[vs][slot]))binding["residual_reference"].push_back({index,uint32_t(slot)});
      }
    }
    auto add=[&](const std::string&name,Json value){
      auto rows=value["rows"].get<uint32_t>();auto binds=binding[name];for(auto[index,slot]:binds)value["data"][index]=0.0;
      auto id=block(matrix(value),binds);for(auto[index,slot]:binds)definition["dynamic_bindings"].push_back({{"slot_id",slot},{"target_block_id",id},{"row",index%rows},{"col",index/rows}});return id;
    };
    for(auto [old_name,new_name]:{std::pair{"M","state_matrix"},{"lift","invariant_lift"},{"generator","invariant_generator"},{"reduce","invariant_reduce"},{"constraints","constraints"},{"residual_map","residual_map"},{"residual_reference","residual_reference"}})definition[new_name]=add(old_name,encoded[old_name]);
    for(auto it=encoded["maps"].begin();it!=encoded["maps"].end();++it){require(signal_ids.count(it.key()),11,"PEVT_SCHEMA","signal registry changed");definition["observation_rows"].push_back({{"signal_id",signal_ids.at(it.key())},{"row_block_id",add("map:"+it.key(),it.value())}});}
    for(auto guard:encoded["guards"]) {
      int part=guard["part"];uint32_t component=part>=0&&size_t(part)<meta["components"].size()?uint32_t(part):none;
      guard["component_id"]=component;guard["row_block_id"]=add("guard",guard["row"]);guard.erase("row");guard.erase("part");definition["guards"].push_back(std::move(guard));
    }
    auto dkey=definition.dump();uint32_t id;
    if(auto i=definition_ids.find(dkey);i!=definition_ids.end())id=i->second;
    else {require(definitions.size()<100000,11,"PEVT_LIMIT","too many equation definitions");id=uint32_t(definitions.size());definition_ids[dkey]=id;definition["definition_id"]=id;definitions.push_back(std::move(definition));}
    return remember_equation(m,bind_instance(id,vs));
  }
  uint32_t state(const Vector&x,uint32_t vs) {
    require(size_t(x.size())==nx&&x.allFinite(),11,"PEVT_SHAPE","invalid event state");Bytes b;put(b,vs,4);for(Eigen::Index i=0;i<x.size();++i)real(b,x[i]);auto k=key(b);
    if(state_ids.count(k))return state_ids.at(k);
    auto id=uint32_t(states.size());state_ids[k]=id;states.push_back({x,vs});return id;
  }
  uint32_t flow(const RunState&s,uint64_t reference) {
    if(!s.electrical_flow)return none;
    auto&f=*s.electrical_flow;auto token=f.archive_origin_id();auto origin=origins.find(token);
    if(origin==origins.end()) {
      require(f.archive_offset()==Time{}&&same(f.archive_anchor(),states.at(events.at(reference).state).x),11,"PEVT_ORIGIN","unresolved original Flow anchor");
      origin=origins.emplace(token,std::pair{reference,events.at(reference).state}).first;
    }
    require(same(f.archive_anchor(),states.at(origin->second.second).x),11,"PEVT_ORIGIN","Flow anchor changed within lineage");
    auto id=uint32_t(flows.size());flows.push_back({reference,origin->second.first,origin->second.second,equation(f.archive_mode()),f.archive_offset()});return id;
  }
  void append(const RunState&a,const RunState&b,const std::vector<Json>&logs,uint64_t transaction) {
    require(a.at==events.back().at&&same(a.internal,states.at(events.back().state).x)&&b.at>=a.at,11,"PEVT_CONTINUITY","event slice continuity differs");
    auto previous=events.size()-1;auto outgoing=flow(a,previous);auto after=equation(b.mode);auto before=equation(a.mode);
    Event e;e.id=events.size();e.at=b.at;e.transaction=transaction?transaction:events.size();e.micro=b.at==a.at?events.back().micro+1:0;
    e.state=state(b.internal,instances[after].values);e.before=before;e.after=after;e.pre=modes(a.mode);e.post=modes(b.mode);
    bool control=false,gate=false,region=false;
    for(size_t i=0;i<e.pre.size();++i)if(e.pre[i]!=e.post[i]){if(modals[i].region)region=true;else gate=true;}
    for(auto&log:logs) {
      auto kind=log.value("kind","");if(kind=="SOFTWARE_TASK"||kind=="TRIG")control=true;
      if(log.contains("source")&&log["source"].is_string()){auto name=log["source"].get<std::string>();e.members.push_back({add_component(name,"EVENT_SOURCE",-1),kind=="SOFTWARE_TASK"||kind=="TRIG"?2u:4u});}
      if(log.contains("members")&&log["members"].is_array())for(auto&member:log["members"])if(member.is_string()){auto name=member.get<std::string>();e.members.push_back({add_component(name,"EVENT_SOURCE",-1),4});}
    }
    if(e.members.empty())for(size_t i=0;i<e.pre.size();++i)if(e.pre[i]!=e.post[i])e.members.push_back({modals[i].component,modals[i].region?4u:3u});
    std::sort(e.members.begin(),e.members.end());e.members.erase(std::unique(e.members.begin(),e.members.end()),e.members.end());
    e.kind=int(control)+int(gate)+int(region)>1||e.members.size()>1?5:region?4:gate?3:2;
    events.push_back(std::move(e));events.back().observer=flow(b,events.size()-1);events[previous].outgoing=outgoing;
  }
};

PevtArchive::PevtArchive(const Model&m,const RunState&s):data_(std::make_shared<Data>(m,s)){}
void PevtArchive::append(const RunState&a,const RunState&b,const std::vector<Json>&logs,uint64_t transaction){data_->append(a,b,logs,transaction);}

void PevtArchive::write(const std::filesystem::path&path,const Result&r)const {
  auto&d=*data_;auto events=d.events;auto flow_records=d.flows;Event end=events.back();end.id=events.size();end.kind=6;end.before=end.after;end.pre=end.post;end.members.clear();end.outgoing=none;++end.micro;
  if(end.observer!=none){auto f=flow_records.at(end.observer);f.reference=end.id;end.observer=uint32_t(flow_records.size());flow_records.push_back(f);}
  events.push_back(end);
  auto meta=d.meta;meta["provenance"]["archive_counts"]={{"equation_calls",d.equation_calls},{"definition_encodes",d.definition_encodes},{"definition_hits",d.definition_hits},{"definition_candidate_checks",d.definition_candidate_checks},{"definition_signature_skips",d.definition_signature_skips}};meta["component_modes"]=d.component_modes;meta["atomic_time"]=r.t_atom;meta["default_save_dt"]=r.save_dt;
  meta["provenance"]["simulation_report"]=r.report;meta["provenance"]["simulation_report"]["analog_channels"]=r.analog_names;meta["provenance"]["simulation_report"]["digital_channels"]=r.digital_names;meta["provenance"]["solver_source_sha256"]=r.report.value("source_sha256","");
  std::vector<Section> sections;sections.push_back({1,1,text(meta)});Bytes b;
  for(size_t i=0;i<d.blocks.size();++i){auto&m=d.blocks[i];put(b,i,4);put(b,m.rows(),4);put(b,m.cols(),4);for(Eigen::Index j=0;j<m.size();++j)real(b,m.data()[j]);}
  sections.push_back({2,d.blocks.size(),std::move(b)});sections.push_back({3,1,text(d.definitions)});b.clear();
  for(size_t i=0;i<d.values.size();++i){put(b,i,4);for(auto v:d.values[i])real(b,v);}sections.push_back({4,d.values.size(),std::move(b)});b.clear();
  for(size_t i=0;i<d.instances.size();++i){put(b,i,4);put(b,d.instances[i].definition,4);put(b,d.instances[i].values,4);}sections.push_back({5,d.instances.size(),std::move(b)});b.clear();
  for(size_t i=0;i<d.states.size();++i){put(b,i,4);for(Eigen::Index j=0;j<d.states[i].x.size();++j)real(b,d.states[i].x[j]);put(b,d.states[i].values,4);}sections.push_back({6,d.states.size(),std::move(b)});b.clear();
  for(auto&e:events){put(b,e.id,8);time(b,e.at);put(b,e.transaction,8);put(b,e.micro,4);put(b,e.kind,4);put(b,e.state,4);put(b,e.before,4);put(b,e.after,4);put(b,e.observer,4);put(b,e.outgoing,4);
    for(auto id:e.pre)put(b,id,4);
    for(auto id:e.post)put(b,id,4);
    put(b,e.members.size(),4);for(auto [id,kind]:e.members){put(b,id,4);put(b,kind,4);}}
  sections.push_back({7,events.size(),std::move(b)});b.clear();
  for(size_t i=0;i<flow_records.size();++i){auto&f=flow_records[i];put(b,i,4);put(b,f.reference,8);put(b,f.origin,8);put(b,f.state,4);put(b,f.equation,4);time(b,f.offset);}sections.push_back({8,flow_records.size(),std::move(b)});
  sections.push_back({9,1,text({{"status",r.status},{"last_event_id",end.id},{"diagnostic",r.diagnostic}})});b.clear();
  for(auto&e:r.events){auto line=e.dump()+"\n";b.insert(b.end(),line.begin(),line.end());}sections.push_back({10,r.events.size(),std::move(b)});
  size_t total=16;for(auto&s:sections){require(s.bytes.size()<=capacity-total-64,11,"PEVT_LIMIT","event stream exceeds 512 MiB");total+=64+s.bytes.size();}
  if(std::getenv("PULSE_PROFILE_PHASES")){
    for(const auto &section:sections)
      std::fprintf(stderr,"PULSE_PEVT_SECTION type=%u count=%zu bytes=%zu\n",
                   section.type,size_t(section.count),section.bytes.size());
  }
  auto tmp=path;tmp+=".tmp";std::ofstream f(tmp,std::ios::binary);f.exceptions(std::ios::failbit|std::ios::badbit);
  Bytes header;for(char c:std::string("PULSEES1"))header.push_back(uint8_t(c));put(header,1,2);put(header,sections.size(),2);put(header,0,4);f.write(reinterpret_cast<const char*>(header.data()),header.size());
  for(auto&s:sections){Bytes h;put(h,s.type,4);put(h,0,4);put(h,s.bytes.size(),8);put(h,s.bytes.size(),8);put(h,s.count,8);auto sha=software::buffer_sha256(s.bytes);h.insert(h.end(),sha.begin(),sha.end());
    f.write(reinterpret_cast<const char*>(h.data()),h.size());f.write(reinterpret_cast<const char*>(s.bytes.data()),std::streamsize(s.bytes.size()));}
  f.close();if(std::filesystem::exists(path))std::filesystem::remove(path);std::filesystem::rename(tmp,path);
}

Result PevtArchive::read(const std::filesystem::path&path,const std::function<void(Result&,const RunState&,const RunState&,bool)>&emit) {
  require(std::filesystem::file_size(path)<=capacity,11,"PEVT_LIMIT","event stream exceeds 512 MiB");std::ifstream file(path,std::ios::binary);require(bool(file),11,"PEVT_IO","cannot read event stream");
  Bytes all((std::istreambuf_iterator<char>(file)),{});Read whole{all};require(all.size()>=16&&std::string(all.begin(),all.begin()+8)=="PULSEES1",11,"PEVT_VERSION","invalid event stream magic");whole.p=8;
  require(whole.word(2)==1,11,"PEVT_VERSION","unsupported event stream version");auto count=whole.word(2);require(count>=9&&count<=10&&whole.word(4)==0,11,"PEVT_SCHEMA","invalid file header");
  std::map<uint32_t,Section> sections;
  for(size_t i=0;i<count;++i){auto type=whole.id(),codec=whole.id();auto stored=whole.word(8),decoded=whole.word(8),records=whole.word(8);std::array<uint8_t,32> expected{};for(auto&v:expected)v=uint8_t(whole.word(1));
    require(type>=1&&type<=10&&!sections.count(type),11,"PEVT_SCHEMA","duplicate or invalid section");require(codec==0,11,"PEVT_CODEC","this native reader accepts codec 0");
    require(stored==decoded&&stored<=capacity&&whole.p<=all.size()&&stored<=all.size()-whole.p&&records<=10000000,11,"PEVT_TRUNCATED","invalid section length/count");
    Bytes payload(all.begin()+whole.p,all.begin()+whole.p+size_t(stored));whole.p+=size_t(stored);require(software::buffer_sha256(payload)==expected,11,"PEVT_HASH","section SHA256 mismatch");sections.emplace(type,Section{type,records,std::move(payload)});
  }whole.end();for(uint32_t i=1;i<=9;++i)require(sections.count(i),11,"PEVT_SCHEMA","missing required section");
  auto meta=parse(sections.at(1).bytes),defs=parse(sections.at(3).bytes),ending=parse(sections.at(9).bytes);
  require(sections.at(1).count==1&&sections.at(3).count==1&&sections.at(9).count==1&&meta.is_object()&&defs.is_array(),11,"PEVT_SCHEMA","invalid JSON section");
  auto nx=meta.at("state_dimension").get<size_t>(),np=meta.at("value_slot_count").get<size_t>(),nm=meta.at("modal_component_count").get<size_t>();
  require(nx>0&&nx<=10000&&np<=10000&&nm<=10000&&meta.at("state_layout").size()==nx&&meta.at("value_slots").size()==np&&meta.at("modal_components").size()==nm,11,"PEVT_SHAPE","invalid state schema");
  auto context=meta.at("numerical_context");require(context.at("double_digits")==std::numeric_limits<double>::digits&&context.at("long_double_digits")==std::numeric_limits<long double>::digits&&context.at("long_double_max_exponent")==std::numeric_limits<long double>::max_exponent,11,"TRAJECTORY_PRECISION","replay precision differs");
  require(meta.at("boundary_rule")=="POST_MODE",11,"PEVT_SCHEMA","unsupported boundary rule");
  std::vector<Matrix> blocks;Read r{sections.at(2).bytes};for(size_t i=0;i<sections.at(2).count;++i){require(r.id()==i,11,"PEVT_ID","matrix ID order differs");auto rows=r.id(),cols=r.id();require(rows<=10000&&cols<=10000&&uint64_t(rows)*cols<=1000000,11,"PEVT_SHAPE","invalid matrix shape");Matrix m(rows,cols);for(Eigen::Index j=0;j<m.size();++j)m.data()[j]=r.number();blocks.push_back(std::move(m));}r.end();
  std::vector<std::vector<double>> values;Read vr{sections.at(4).bytes};for(size_t i=0;i<sections.at(4).count;++i){require(vr.id()==i,11,"PEVT_ID","value ID order differs");std::vector<double>v;for(size_t j=0;j<np;++j)v.push_back(vr.number());values.push_back(std::move(v));}vr.end();
  std::vector<Instance> instances;Read ir{sections.at(5).bytes};for(size_t i=0;i<sections.at(5).count;++i){require(ir.id()==i,11,"PEVT_ID","equation ID order differs");Instance v{ir.id(),ir.id()};require(v.definition<defs.size()&&v.values<values.size(),11,"PEVT_REFERENCE","invalid equation reference");instances.push_back(v);}ir.end();
  std::vector<State> states;Read sr{sections.at(6).bytes};for(size_t i=0;i<sections.at(6).count;++i){require(sr.id()==i,11,"PEVT_ID","state ID order differs");auto x=sr.vector(nx);auto vs=sr.id();require(vs<values.size(),11,"PEVT_REFERENCE","invalid state values");states.push_back({std::move(x),vs});}sr.end();
  std::vector<Event> events;Read er{sections.at(7).bytes};auto cms=meta.at("component_modes");
  for(size_t i=0;i<sections.at(7).count;++i){Event e;e.id=er.word(8);e.at=er.at();e.transaction=er.word(8);e.micro=er.id();e.kind=er.id();e.state=er.id();e.before=er.id();e.after=er.id();e.observer=er.id();e.outgoing=er.id();
    require(e.id==i&&e.kind>=1&&e.kind<=6&&e.state<states.size()&&e.before<instances.size()&&e.after<instances.size(),11,"PEVT_REFERENCE","invalid event reference");
    for(size_t j=0;j<nm;++j)e.pre.push_back(er.id());
    for(size_t j=0;j<nm;++j)e.post.push_back(er.id());
    for(auto*v:{&e.pre,&e.post})for(size_t j=0;j<nm;++j)require(v->at(j)<cms.size()&&cms[v->at(j)].at("component_id")==meta["modal_components"][j],11,"PEVT_REFERENCE","invalid component mode");
    require(defs.at(instances[e.before].definition).at("component_mode_ids")==e.pre&&defs.at(instances[e.after].definition).at("component_mode_ids")==e.post&&states[e.state].values==instances[e.after].values,11,"PEVT_REFERENCE","event slice/mode definition differs");
    auto n=er.id();require(n<=100000,11,"PEVT_LIMIT","oversized event group");for(size_t j=0;j<n;++j){auto cid=er.id(),kind=er.id();require(cid<meta["components"].size()&&kind>=1&&kind<=6,11,"PEVT_REFERENCE","invalid event member");e.members.push_back({cid,kind});}
    require(events.empty()||e.at>events.back().at||(e.at==events.back().at&&e.transaction>=events.back().transaction&&(e.transaction!=events.back().transaction||e.micro>=events.back().micro)),11,"PEVT_TIME","unordered event slices");events.push_back(std::move(e));}er.end();
  require(!events.empty()&&events.front().kind==1&&events.back().kind==6&&meta.at("initial_event_id")==0&&ending.at("last_event_id")==events.back().id,11,"PEVT_SCHEMA","initial/end event differs");
  std::vector<FlowRecord> flows;Read fr{sections.at(8).bytes};for(size_t i=0;i<sections.at(8).count;++i){require(fr.id()==i,11,"PEVT_ID","Flow ID order differs");FlowRecord f;f.reference=fr.word(8);f.origin=fr.word(8);f.state=fr.id();f.equation=fr.id();f.offset=fr.at();require(f.reference<events.size()&&f.origin<=f.reference&&f.state<states.size()&&f.equation<instances.size(),11,"PEVT_REFERENCE","invalid Flow reference");require(events[f.origin].state==f.state,11,"PEVT_ORIGIN","Flow origin state differs");flows.push_back(f);}fr.end();
  auto decode_equation=[&](uint32_t id){
    require(id<instances.size(),11,"PEVT_REFERENCE","invalid equation ID");auto instance=instances[id];const auto&d=defs.at(instance.definition);require(d.at("definition_id")==instance.definition,11,"PEVT_ID","definition ID order differs");std::map<uint32_t,Matrix> copies;
    auto get=[&](uint32_t block)->Matrix {require(block<blocks.size(),11,"PEVT_REFERENCE","invalid coefficient block");if(auto i=copies.find(block);i!=copies.end())return i->second;return blocks[block];};
    for(auto&binding:d.at("dynamic_bindings")){uint32_t block=binding.at("target_block_id"),slot=binding.at("slot_id"),row=binding.at("row"),col=binding.at("col");require(block<blocks.size()&&slot<np&&row<uint32_t(blocks[block].rows())&&col<uint32_t(blocks[block].cols()),11,"PEVT_REFERENCE","invalid coefficient binding");if(!copies.count(block))copies[block]=blocks[block];copies[block](row,col)=values[instance.values][slot];}
    Mode m;m.M=get(d.at("state_matrix"));m.invariant_lift=get(d.at("invariant_lift"));m.invariant_generator=get(d.at("invariant_generator"));m.invariant_reduce=get(d.at("invariant_reduce"));m.constraints=get(d.at("constraints"));m.residual_map=get(d.at("residual_map"));m.residual_reference=get(d.at("residual_reference"));m.numerical_strategy=d.at("numerical_strategy");m.observer_maps=d.value("observer_maps",std::set<std::string>{});m.observer_rows=d.value("observer_rows",std::vector<int>{});
    require(size_t(m.M.rows())==nx&&size_t(m.M.cols())==nx,11,"PEVT_SHAPE","state matrix dimension differs");
    for(auto&entry:d.at("observation_rows")){uint32_t signal=entry.at("signal_id");require(signal<meta["signals"].size(),11,"PEVT_REFERENCE","invalid observation signal");auto row=get(entry.at("row_block_id"));require(size_t(row.rows())==nx&&row.cols()==1,11,"PEVT_SHAPE","observation shape differs");m.maps[meta["signals"][signal].at("name").get<std::string>()]=row;}
    for(auto mode_id:d.at("component_mode_ids")){uint32_t cm=mode_id;require(cm<cms.size(),11,"PEVT_REFERENCE","invalid equation component mode");auto def=cms[cm].at("definition");if(def.at("kind")=="REGION")m.segments[def.at("source_part_index").get<int>()]=def.at("value");else if(!def.at("signal").get<std::string>().empty()&&!is_literal(def.at("signal").get<std::string>()))m.bools[def.at("signal").get<std::string>()]=def.at("value").get<int>()!=0;}
    for(auto&g:d.at("guards")){Mode::Guard guard;guard.row=get(g.at("row_block_id"));uint32_t cid=g.at("component_id");require(cid<meta["components"].size(),11,"PEVT_REFERENCE","invalid guard component");guard.part=meta["components"][cid].at("source_part_index");guard.direction=g.at("direction");guard.kind=g.at("kind").get<std::string>();guard.knot=g.at("knot");guard.segment=g.at("segment");guard.step=g.at("step");m.guards.push_back(std::move(guard));}
    return m;
  };
  // Bounded reconstruction cache: instances carry their full dynamic bindings.
  std::map<uint32_t,Mode> cache;auto eq=[&](uint32_t id)->const Mode&{if(auto i=cache.find(id);i!=cache.end())return i->second;if(cache.size()>=128)cache.erase(cache.begin());return cache.emplace(id,decode_equation(id)).first->second;};
  auto attach=[&](RunState&s,uint32_t id,uint64_t reference){if(id==none)return;require(id<flows.size()&&flows[id].reference==reference,11,"PEVT_REFERENCE","Flow reference event differs");auto&f=flows[id];s.electrical_flow=std::make_shared<engineering::Flow>(engineering::Flow::restore_archive(eq(f.equation),states[f.state].x,f.offset));};
  auto snapshot=[&](const Event&e){RunState s;s.at=e.at;s.internal=states[e.state].x;s.mode=eq(e.after);attach(s,e.observer,e.id);return s;};
  Result out;out.report=meta.at("provenance").at("simulation_report");out.status=ending.at("status").get<std::string>();out.diagnostic=ending.at("diagnostic");out.evidence=out.report.value("evidence","ENGINEERING_POINT_TRAJECTORY");out.save_dt=meta.at("default_save_dt");out.t_atom=meta.at("atomic_time");out.t_end=events.back().at.seconds();out.analog_names=out.report.value("analog_channels",std::vector<std::string>{});out.digital_names=out.report.value("digital_channels",std::vector<std::string>{});
  auto initial=snapshot(events.front());out.committed=initial;emit(out,initial,initial,true);
  for(size_t i=1;i<events.size();++i){auto old=snapshot(events[i-1]);old.mode=eq(events[i].before);old.electrical_flow.reset();attach(old,events[i-1].outgoing,events[i-1].id);auto next=snapshot(events[i]);emit(out,old,next,false);out.committed=std::move(next);}
  if(sections.count(10)){std::string logs=key(sections.at(10).bytes);std::istringstream in(logs);std::string line;while(std::getline(in,line))if(!line.empty())out.events.push_back(Json::parse(line));require(out.events.size()==sections.at(10).count,11,"PEVT_SCHEMA","diagnostic count differs");}
  return out;
}
}
