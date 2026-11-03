#pragma once
// Stage D generic, type-safe, exact-key runtime helpers.
// No circuit topology assumptions; standard C++20 only.
#include <bit>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <vector>

namespace pulse::stage_d {
constexpr std::uint64_t fnv_offset = 14695981039346656037ULL;
constexpr std::uint64_t fnv_prime = 1099511628211ULL;
inline std::uint64_t hash_bytes(const void* data, std::size_t size) noexcept {
  std::uint64_t hash = fnv_offset;
  const auto* bytes = static_cast<const unsigned char*>(data);
  for (std::size_t i = 0; i < size; ++i) {
    hash ^= bytes[i];
    hash *= fnv_prime;
  }
  return hash;
}
// All equality-sensitive deduplication must still compare FULL keys.
// A hash collision never authorizes a cache hit.
struct WordVectorHash {
  std::size_t operator()(const std::vector<std::uint64_t>& words) const noexcept {
    return static_cast<std::size_t>(hash_bytes(words.data(), words.size()*sizeof(std::uint64_t)));
  }
};
inline std::uint64_t pair_key(std::uint32_t first, std::uint32_t second) noexcept {
  return (static_cast<std::uint64_t>(first)<<32) | second;
}
inline bool bitwise_equal(const double* lhs, const double* rhs, std::size_t count) noexcept {
  return count == 0 || std::memcmp(lhs, rhs, count*sizeof(double)) == 0;
}
inline std::uint64_t double_bits(double value) noexcept {
  return std::bit_cast<std::uint64_t>(value);
}
}  // namespace pulse::stage_d
