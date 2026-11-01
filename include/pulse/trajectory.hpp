#pragma once
#include "pulse/engineering.hpp"
#include <functional>
#include "pulse/trajectory_pool.hpp"
namespace pulse {
// Version 1: JSON numerical templates plus explicit little-endian records.
// Derived floating-point caches are rebuilt by the unchanged Flow constructor.
class Trajectory {
  TrajectoryPool pool_;
  std::map<uint32_t,uint32_t> ids_;
  std::vector<uint32_t> templates_;
  std::vector<uint8_t> bytes_;
  uint64_t records_=0;
  size_t dimension_=0;
  uint32_t mode(const Mode &);
  void state(const RunState &);
public:
  void initial(const RunState &);
  void append(const RunState &,const RunState &);
  void write(const std::filesystem::path &,const Result &) const;
  static Result read(const std::filesystem::path &,
                     const std::function<void(Result &,const RunState &,const RunState &,bool)> &);
};
}
