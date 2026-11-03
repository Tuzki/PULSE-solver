#include "pulse/cow_value.hpp"
#include <stdexcept>
#define CHECK(expr) do { if (!(expr)) throw std::runtime_error("COW check failed: " #expr); } while (false)
#include <map>
#include <string>
#include <vector>
#include <stdexcept>

struct MockModeDefinition {
  std::vector<double> matrix;
  std::map<std::string,std::vector<double>> maps;
};
struct MockRunState {
  pulse::CowValue<MockModeDefinition> mode;
  pulse::CowValue<std::map<std::string,double>> regs;
  pulse::CowValue<std::vector<unsigned char>> software;
};
static void fail_after_update(MockRunState& candidate) {
  candidate.mode.edit().matrix[0] = 99;
  candidate.regs.edit()["gate"] = 1;
  candidate.software.edit()[0] = 5;
  throw std::runtime_error("transaction failed");
}
int main() {
  MockRunState original;
  original.mode.edit().matrix = {1,2,3};
  original.mode.edit().maps["V"] = {1,0};
  original.regs.edit()["gate"] = 0;
  original.software.edit().push_back(0);
  MockRunState candidate = original;
  CHECK(candidate.mode.shares_storage_with(original.mode));
  CHECK(candidate.regs.shares_storage_with(original.regs));
  bool threw = false;
  try { fail_after_update(candidate); } catch (const std::runtime_error&) { threw = true; }
  CHECK(threw);
  CHECK(original.mode.read().matrix[0]==1);
  CHECK(original.regs.read().at("gate")==0);
  CHECK(original.software.read()[0]==0);
  CHECK(!candidate.mode.shares_storage_with(original.mode));
  CHECK(!candidate.regs.shares_storage_with(original.regs));
  CHECK(!candidate.software.shares_storage_with(original.software));
  MockRunState accepted = original;
  accepted.regs.edit()["gate"] = 1;
  original = std::move(accepted);
  CHECK(original.regs.read().at("gate")==1);
  // Shallow snapshots copy no payload; only the first shared edit detaches.
  struct Counted {
    int* copies;
    explicit Counted(int& n) : copies(&n) {}
    Counted(const Counted& other) : copies(other.copies) { ++*copies; }
  };
  int copies = 0;
  pulse::CowValue<Counted> owner{Counted(copies)};
  copies = 0;
  auto snapshot = owner;
  CHECK(copies == 0);
  (void)owner.read();
  CHECK(copies == 0 && owner.shares_storage_with(snapshot));
  (void)owner.edit();
  CHECK(copies == 1 && !owner.shares_storage_with(snapshot));
  (void)owner.edit();
  CHECK(copies == 1);
  return 0;
}
