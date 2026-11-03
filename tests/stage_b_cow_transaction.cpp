#include "pulse/core.hpp"
#include <stdexcept>
#define CHECK(expr) do { if (!(expr)) throw std::runtime_error("COW check failed: " #expr); } while (false)
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>

// Real PULSE types, not a synthetic Mode or RunState surrogate.
int main() {
  using namespace pulse;
  Mode original;
  original.definition.edit().M = Matrix::Identity(3,3);
  original.definition.edit().constraints = Matrix::Zero(1,3);
  original.binding.edit().maps["V(X)"] = Vector::Ones(3);
  original.binding.edit().guards.push_back({Vector::Ones(3), 0, 1, "CMP"});
  original.bools["G"] = false;
  Mode candidate = original;
  CHECK(candidate.definition.shares_storage_with(original.definition));
  CHECK(candidate.binding.shares_storage_with(original.binding));
  candidate.binding.edit().maps.at("V(X)")[0] = 2;
  CHECK(original.binding.read().maps.at("V(X)")[0] == 1);
  CHECK(candidate.definition.shares_storage_with(original.definition));
  candidate.definition.edit().M(0,0) = 7;
  CHECK(original.definition.read().M(0,0) == 1);

  RunState accepted;
  accepted.mode = original;
  accepted.regs.edit()["GATE"] = 0;
  accepted.software.edit()["CTRL"].bytes = {1,2,3};
  accepted.software.edit()["CTRL"].invocation = 2;
  accepted.agenda.edit().push_back({Time{}, 1, 0, 0, "CLK", "0"});
  accepted.generations.edit()[1] = 5;
  RunState transaction = accepted;
  CHECK(transaction.mode.definition.shares_storage_with(accepted.mode.definition));
  CHECK(transaction.regs.shares_storage_with(accepted.regs));
  CHECK(transaction.software.shares_storage_with(accepted.software));
  transaction.regs.edit()["GATE"] = 1;
  transaction.software.edit().at("CTRL").bytes[0] = 9;
  transaction.software.edit().at("CTRL").invocation = 3;
  transaction.agenda.edit().clear();
  transaction.generations.edit()[1] = 6;
  transaction.mode.binding.edit().maps.at("V(X)")[0] = 4;
  // Simulate failure: discard the candidate. The last committed checkpoint
  // must retain Mode, REG, C ABI bytes, agenda and generation exactly.
  CHECK(accepted.regs.read().at("GATE") == 0);
  CHECK(accepted.software.read().at("CTRL").bytes[0] == 1);
  CHECK(accepted.software.read().at("CTRL").invocation == 2);
  CHECK(accepted.agenda.read().size() == 1);
  CHECK(accepted.generations.read().at(1) == 5);
  CHECK(accepted.mode.binding.read().maps.at("V(X)")[0] == 1);
  CHECK(!transaction.regs.shares_storage_with(accepted.regs));
  CHECK(!transaction.software.shares_storage_with(accepted.software));
  CHECK(!transaction.agenda.shares_storage_with(accepted.agenda));
  CHECK(!transaction.generations.shares_storage_with(accepted.generations));
  const RunState saved_checkpoint = accepted;
  RunState retry = accepted;
  retry.regs.edit()["GATE"] = 1;
  accepted = std::move(retry);
  CHECK(accepted.regs.read().at("GATE") == 1);
  CHECK(saved_checkpoint.regs.read().at("GATE") == 0);
  CHECK(saved_checkpoint.software.read().at("CTRL").invocation == 2);
  CHECK(saved_checkpoint.mode.binding.read().maps.at("V(X)")[0] == 1);
  std::cout << "PASS: Stage B COW ModeDefinition/ModeBinding and RunState retry isolation\n";
}
