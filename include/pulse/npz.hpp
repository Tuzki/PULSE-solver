#pragma once
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>
namespace pulse {
// bytes contains C-order data already encoded in the specified little-endian dtype.
// metadata_json uses descr="|u1", shape={UTF-8 byte count}.
struct NpzArray {
    std::string name, descr;
    std::vector<size_t> shape;
    std::vector<uint8_t> bytes;
};
// Writes uncompressed ZIP32 entries containing NPY v1.0 arrays. Invalid inputs,
// ZIP64-sized resources, and I/O failures throw std::runtime_error.
void write_npz(const std::filesystem::path &, const std::vector<NpzArray> &);
} // namespace pulse
