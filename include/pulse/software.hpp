#pragma once
#include "pulse/core.hpp"
#include "pulse/software.h"
#include <memory>
#include <span>
#include <array>
namespace pulse::software {
struct Data;
struct Wakeup { int part; double delay; std::string trigger; };
class Session {
  std::unique_ptr<Data> data_;
public:
  explicit Session(const Model &);
  ~Session();
  Session(const Session &) = delete;
  void initialize(RunState &, Stats &);
  std::vector<Wakeup> execute(const RunState &snapshot, RunState &candidate,
       const std::set<std::string> &triggers, std::map<std::string,double> &writes,
       std::vector<Json> &logs, uint64_t transaction, size_t delta);
  Json identity() const;
};
std::string file_sha256(const std::string &path, size_t max_bytes=64*1024*1024);
std::array<uint8_t,32> buffer_sha256(std::span<const uint8_t>);
}
