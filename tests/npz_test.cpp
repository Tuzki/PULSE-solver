#include "pulse/npz.hpp"
#include <bit>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <stdexcept>
#include <string_view>
using pulse::NpzArray;
namespace {
int checks = 0;
void check(bool value, const std::string &message) {
    ++checks;
    if (!value)
        throw std::runtime_error(message);
}
void append32(std::vector<uint8_t> &out, uint32_t n) {
    for (int i = 0; i < 4; ++i)
        out.push_back(uint8_t(n >> (i * 8)));
}
void append64(std::vector<uint8_t> &out, uint64_t n) {
    for (int i = 0; i < 8; ++i)
        out.push_back(uint8_t(n >> (i * 8)));
}
uint32_t read(const std::vector<uint8_t> &b, size_t p, size_t n) {
    uint32_t v = 0;
    for (size_t i = 0; i < n; ++i)
        v |= uint32_t(b.at(p + i)) << (i * 8);
    return v;
}
uint32_t independent_crc(const std::vector<uint8_t> &b, size_t begin, size_t end) {
    uint32_t crc = ~uint32_t(0);
    for (size_t i = begin; i < end; ++i) {
        crc ^= b.at(i);
        for (int k = 0; k < 8; ++k)
            crc = (crc & 1) ? (crc >> 1) ^ 0xedb88320u : crc >> 1;
    }
    return ~crc;
}
void rejects(const std::filesystem::path &path, std::vector<NpzArray> arrays) {
    {
        std::ofstream f(path);
        f << "sentinel";
    }
    bool threw = false;
    try {
        pulse::write_npz(path, arrays);
    } catch (const std::runtime_error &) {
        threw = true;
    }
    check(threw, "expected invalid NPZ rejection");
    std::ifstream f(path);
    std::string contents((std::istreambuf_iterator<char>(f)), {});
    check(contents == "sentinel", "invalid input must not truncate existing file");
}
} // namespace
int main(int argc, char **argv) {
    try {
        std::filesystem::path output = argc > 1 ? argv[1] : "build/npz_test.npz";
        NpzArray t{"time", "<f8", {3}, {}};
        for (double d : {0., .25, 1.})
            append64(t.bytes, std::bit_cast<uint64_t>(d));
        NpzArray a{"analog", "<f4", {3, 2}, {}};
        for (float f : {1.f, -1.f, 2.f, -2.f, 3.f, -3.f})
            append32(a.bytes, std::bit_cast<uint32_t>(f));
        NpzArray d{"digital", "|u1", {3, 1}, {0, 1, 0}};
        std::string json = "{\"status\":\"COMPLETED\",\"label\":\"测量\"}";
        NpzArray meta{"metadata_json", "|u1", {json.size()}, std::vector<uint8_t>(json.begin(), json.end())};
        NpzArray empty{"empty", "<f4", {3, 0}, {}};
        NpzArray scalar{"scalar", "<f8", {}, t.bytes};
        scalar.bytes.resize(8);
        pulse::write_npz(output, {t, a, d, meta, empty, scalar});
        std::ifstream file(output, std::ios::binary);
        std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(file)), {});
        size_t pos = 0, local_entries = 0;
        while (read(bytes, pos, 4) == 0x04034b50) {
            auto crc = read(bytes, pos + 14, 4), size = read(bytes, pos + 18, 4);
            auto namelen = read(bytes, pos + 26, 2), extra = read(bytes, pos + 28, 2);
            check(read(bytes, pos + 8, 2) == 0, "uncompressed ZIP entry");
            size_t body = pos + 30 + namelen + extra;
            check(bytes.at(body) == 0x93, "NPY magic");
            check(bytes.at(body + 6) == 1 && bytes.at(body + 7) == 0, "NPY v1.0");
            check((read(bytes, body + 8, 2) + 10) % 64 == 0, "NPY header alignment");
            check(independent_crc(bytes, body, body + size) == crc, "independent CRC32");
            pos = body + size;
            ++local_entries;
        }
        check(local_entries == 6, "six arrays");
        check(read(bytes, pos, 4) == 0x02014b50, "central directory");
        check(read(bytes, bytes.size() - 22, 4) == 0x06054b50, "EOCD");
        check(read(bytes, bytes.size() - 12, 2) == 6, "EOCD entry count");
        auto badpath = output;
        badpath += ".invalid";
        rejects(badpath, {{"bad", "<f8", {2}, {0}}});
        rejects(badpath, {{"bad", ">f8", {0}, {}}});
        rejects(badpath, {{"bad", "|u2", {0}, {}}});
        rejects(badpath, {{"../bad", "|u1", {0}, {}}});
        rejects(badpath, {{std::string("a\0b", 3), "|u1", {0}, {}}});
        rejects(badpath, {{"duplicate", "|u1", {0}, {}}, {"duplicate", "|u1", {0}, {}}});
        rejects(badpath, {{"huge", "<f8", {std::numeric_limits<size_t>::max(), 2}, {}}});
        rejects(badpath, {{std::string(65535, 'x'), "|u1", {0}, {}}});
        rejects(badpath, {{"rank", "|u1", std::vector<size_t>(24000, 0), {}}});
        rejects(badpath, std::vector<NpzArray>(65535));
        std::filesystem::remove(badpath);
        auto emptyarchive = output;
        emptyarchive += ".empty";
        pulse::write_npz(emptyarchive, {});
        check(std::filesystem::file_size(emptyarchive) == 22, "empty archive");
        bool io_error = false;
        try {
            pulse::write_npz(output / "missing.npz", {});
        } catch (...) {
            io_error = true;
        }
        check(io_error, "I/O error reported");
        std::cout << "PASS NPZ " << checks << " checks; output=" << output.string() << '\n';
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "FAIL NPZ " << e.what() << '\n';
        return 1;
    }
}
