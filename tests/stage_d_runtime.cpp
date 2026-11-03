#include "pulse/stage_d_runtime.hpp"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <limits>
#include <unordered_map>
int main() {
  using namespace pulse::stage_d;
  const std::vector<std::uint64_t> a{0,1,2,3}, b{0,1,2,4};
  WordVectorHash h;
  assert(h(a)==h(a));
  std::unordered_map<std::vector<std::uint64_t>, unsigned, WordVectorHash> cache;
  cache[a]=17;
  assert(cache.find(a)!=cache.end() && cache.find(b)==cache.end());
  assert(pair_key(1,7)!=pair_key(2,7));
  assert(pair_key(1,7)!=pair_key(1,8));
  const double plus_zero=+0.0, minus_zero=-0.0;
  assert(!bitwise_equal(&plus_zero,&minus_zero,1));
  assert(double_bits(+0.0)!=double_bits(-0.0));
  constexpr std::uint64_t nonzero = 42;
  assert(hash_bytes(&nonzero,sizeof(nonzero)) != hash_bytes(nullptr,0));
}
