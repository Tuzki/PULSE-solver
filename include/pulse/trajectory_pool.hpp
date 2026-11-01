#pragma once
#include "pulse/core.hpp"
#include <bit>
#include <fstream>
#include <unordered_map>

namespace pulse {
// Exact, typed, little-endian content sharing for archive data only. No numeric
// approximation: double keys include every bit, including the sign of zero.
class TrajectoryPool {
  static constexpr size_t capacity=128*1024*1024;
  std::unordered_map<std::string,uint32_t> ids_;
  std::vector<std::string> nodes_;
  size_t bytes_=0;
  static void word(std::string& s,uint64_t v,size_t n) {
    for(size_t i=0;i<n;++i)s.push_back(char(v>>(8*i)));
  }
  static uint64_t read_word(const std::string&s,size_t&pos,size_t n) {
    require(pos+n<=s.size(),11,"TRAJECTORY_TRUNCATED","truncated shared block");
    uint64_t v=0;for(size_t i=0;i<n;++i)v|=uint64_t(uint8_t(s[pos++]))<<(8*i);return v;
  }
  uint32_t intern(std::string s) {
    if(auto it=ids_.find(s);it!=ids_.end())return it->second;
    require(nodes_.size()<4000000&&bytes_+4+s.size()<=capacity-400024,
            11,"TRAJECTORY_LIMIT","shared template pool exceeds resource limit");
    auto id=uint32_t(nodes_.size());bytes_+=4+s.size();
    ids_.emplace(s,id);nodes_.push_back(std::move(s));return id;
  }
  uint32_t group(char tag,const std::vector<uint32_t>&v,size_t first,size_t last) {
    std::string s(1,tag);word(s,last-first,4);
    for(size_t i=first;i<last;++i)word(s,v[i],4);
    return intern(std::move(s));
  }
  uint32_t array(const std::vector<uint32_t>&values) {
    if(values.size()<=32)return group('a',values,0,values.size());
    std::vector<uint32_t> level;
    for(size_t i=0;i<values.size();i+=32)level.push_back(group('a',values,i,std::min(i+32,values.size())));
    while(level.size()>32) {
      std::vector<uint32_t> next;
      for(size_t i=0;i<level.size();i+=32)next.push_back(group('A',level,i,std::min(i+32,level.size())));
      level=std::move(next);
    }
    return group('A',level,0,level.size());
  }
  Json expand(uint32_t id,size_t depth,size_t&budget)const {
    require(id<nodes_.size()&&depth<64&&budget>0,11,"TRAJECTORY_TEMPLATE","invalid shared block reference or expansion");
    --budget;const auto&s=nodes_[id];size_t p=1;Json result;
    require(!s.empty(),11,"TRAJECTORY_TEMPLATE","empty shared block");
    auto child=[&](){auto index=read_word(s,p,4);require(index<id,11,"TRAJECTORY_TEMPLATE","forward/cyclic shared block reference");return expand(uint32_t(index),depth+1,budget);};
    switch(s[0]) {
      case 'n':result=nullptr;break;
      case 'b':{auto b=read_word(s,p,1);require(b<=1,11,"TRAJECTORY_TEMPLATE","invalid boolean");result=bool(b);break;}
      case 'i':result=std::bit_cast<int64_t>(read_word(s,p,8));break;
      case 'u':result=read_word(s,p,8);break;
      case 'f':{auto v=std::bit_cast<double>(read_word(s,p,8));require(std::isfinite(v),11,"TRAJECTORY_NONFINITE","nonfinite shared value");result=v;break;}
      case 's':result=s.substr(1);p=s.size();break;
      case 'a':case 'A':{
        auto count=read_word(s,p,4);require(count<=32,11,"TRAJECTORY_SHAPE","oversized shared array block");result=Json::array();
        for(size_t i=0;i<count;++i){auto v=child();if(s[0]=='a')result.push_back(std::move(v));else {
          require(v.is_array()&&result.size()+v.size()<=1000000,11,"TRAJECTORY_SHAPE","invalid shared array expansion");
          for(auto&value:v)result.push_back(std::move(value));
        }}break;
      }
      case 'o':{
        auto pairs=child();require(pairs.is_array(),11,"TRAJECTORY_SHAPE","invalid shared object");result=Json::object();
        for(auto&entry:pairs){require(entry.is_array()&&entry.size()==2&&entry[0].is_string(),11,"TRAJECTORY_SHAPE","invalid shared member");
          auto name=entry[0].get<std::string>();require(!result.contains(name),11,"TRAJECTORY_SHAPE","duplicate shared member");result[name]=std::move(entry[1]);}break;
      }
      default:throw Error(11,"TRAJECTORY_TEMPLATE","unknown shared block type");
    }
    require(p==s.size(),11,"TRAJECTORY_TRAILING","trailing shared block bytes");return result;
  }
public:
  uint32_t encode(const Json&j) {
    std::string s;
    if(j.is_null())return intern("n");
    if(j.is_boolean()){s="b";word(s,j.get<bool>(),1);}
    else if(j.is_number_unsigned()){s="u";word(s,j.get<uint64_t>(),8);}
    else if(j.is_number_integer()){s="i";word(s,std::bit_cast<uint64_t>(j.get<int64_t>()),8);}
    else if(j.is_number_float()){double v=j.get<double>();require(std::isfinite(v),11,"TRAJECTORY_NONFINITE","nonfinite archived value");s="f";word(s,std::bit_cast<uint64_t>(v),8);}
    else if(j.is_string()){s="s";s+=j.get<std::string>();}
    else if(j.is_array()){std::vector<uint32_t> values;values.reserve(j.size());for(auto&v:j)values.push_back(encode(v));return array(values);}
    else if(j.is_object()){
      std::vector<uint32_t> pairs;for(auto it=j.begin();it!=j.end();++it)pairs.push_back(array({encode(it.key()),encode(it.value())}));
      auto id=array(pairs);s="o";word(s,id,4);
    }else throw Error(11,"TRAJECTORY_TEMPLATE","unsupported archive value");
    return intern(std::move(s));
  }
  Json decode(uint32_t id)const {size_t budget=8000000;return expand(id,0,budget);}
  void write(const std::filesystem::path&path,const std::vector<uint32_t>&roots)const {
    require(roots.size()<=100000&&24+bytes_+4*roots.size()<=capacity,11,"TRAJECTORY_LIMIT","template archive exceeds resource limit");
    std::ofstream f(path,std::ios::binary);f.exceptions(std::ios::failbit|std::ios::badbit);
    f.write("PULPOOL2",8);
    auto put=[&](uint64_t v,size_t n){std::string s;word(s,v,n);f.write(s.data(),std::streamsize(s.size()));};
    put(nodes_.size(),8);put(roots.size(),8);
    for(auto&s:nodes_){put(s.size(),4);f.write(s.data(),std::streamsize(s.size()));}
    for(auto id:roots)put(id,4);
  }
  static std::pair<TrajectoryPool,std::vector<uint32_t>> read(const std::filesystem::path&path) {
    require(std::filesystem::file_size(path)<=capacity,11,"TRAJECTORY_LIMIT","template archive exceeds resource limit");
    std::ifstream f(path,std::ios::binary);require(bool(f),11,"TRAJECTORY_IO","cannot read template archive");
    auto get=[&](size_t n){std::string s(n,'\0');f.read(s.data(),std::streamsize(n));require(size_t(f.gcount())==n,11,"TRAJECTORY_TRUNCATED","truncated template archive");size_t p=0;return read_word(s,p,n);};
    char magic[8];f.read(magic,8);require(f.gcount()==8&&std::string(magic,8)=="PULPOOL2",11,"TRAJECTORY_VERSION","invalid template archive header");
    auto count=get(8),root_count=get(8);require(count<=4000000&&root_count<=100000,11,"TRAJECTORY_LIMIT","invalid template archive counts");
    TrajectoryPool pool;std::vector<uint32_t> roots;pool.nodes_.reserve(size_t(count));
    for(size_t i=0;i<count;++i){auto size=get(4);require(size>0&&pool.bytes_+4+size<=capacity,11,"TRAJECTORY_LIMIT","invalid template block size");
      std::string s(size,'\0');f.read(s.data(),std::streamsize(size));require(uint64_t(f.gcount())==size,11,"TRAJECTORY_TRUNCATED","truncated template block");pool.bytes_+=4+size;pool.nodes_.push_back(std::move(s));}
    for(size_t i=0;i<root_count;++i){auto id=get(4);require(id<count,11,"TRAJECTORY_TEMPLATE","invalid template root");roots.push_back(uint32_t(id));}
    require(f.peek()==std::char_traits<char>::eof()&&!f.bad(),11,"TRAJECTORY_TRAILING","trailing template archive bytes");return {std::move(pool),std::move(roots)};
  }
};
}
