#pragma once
#include "pulse/core.hpp"
#include <span>
#include <functional>
namespace pulse {
Json archive_encode_mode(const Mode&);
Mode archive_decode_mode(const Json&);
class PevtArchive {
  struct Data;
  std::shared_ptr<Data> data_;
public:
  PevtArchive(const Model&,const RunState&);
  void append(const RunState&,const RunState&,const std::vector<Json>&,uint64_t);
  void write(const std::filesystem::path&,const Result&)const;
  static Result read(const std::filesystem::path&,
      const std::function<void(Result&,const RunState&,const RunState&,bool)>&);
};
}
