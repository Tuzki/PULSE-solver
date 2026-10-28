#include "pulse/npz.hpp"
#include <array>
#include <fstream>
#include <limits>
#include <set>
#include <stdexcept>
#include <string_view>

namespace pulse {
namespace {
constexpr uint64_t zip_limit = std::numeric_limits<uint32_t>::max();
[[noreturn]] void invalid(const std::string &message) {
    throw std::runtime_error("OUTPUT_ERROR: NPZ: " + message);
}
uint64_t add(uint64_t a, uint64_t b) {
    if (a >= zip_limit || b >= zip_limit || a + b >= zip_limit)
        invalid("ZIP32 resource limit exceeded; ZIP64 is unsupported");
    return a + b;
}
size_t dtype_size(const std::string &d) {
    if (d.size() < 3 || (d[0] != '<' && d[0] != '|'))
        invalid("dtype must explicitly specify little endian (<) or byte order (|)");
    size_t width = 0;
    for (size_t i = 2; i < d.size(); ++i) {
        if (d[i] < '0' || d[i] > '9')
            invalid("invalid dtype " + d);
        const auto digit = size_t(d[i] - '0');
        if (width > (std::numeric_limits<size_t>::max() - digit) / 10)
            invalid("dtype width overflow");
        width = width * 10 + digit;
    }
    const char kind = d[1];
    if (d[0] == '|' && width != 1 && kind != 'S')
        invalid("byte-order-independent dtype requires byte-sized items");
    if (kind == 'U') {
        if (d[0] != '<' || width > std::numeric_limits<size_t>::max() / 4)
            invalid("invalid unicode dtype");
        return width * 4;
    }
    if (kind == 'S')
        return width;
    if ((kind == 'i' || kind == 'u') && (width == 1 || width == 2 || width == 4 || width == 8))
        return width;
    if (kind == 'b' && width == 1)
        return width;
    if (kind == 'f' && (width == 2 || width == 4 || width == 8 || width == 16))
        return width;
    if (kind == 'c' && (width == 8 || width == 16 || width == 32))
        return width;
    invalid("unsupported dtype " + d);
}
std::string header(const NpzArray &a) {
    const size_t item_size = dtype_size(a.descr);
    size_t count = 1;
    for (size_t n : a.shape) {
        if (count != 0 && n > std::numeric_limits<size_t>::max() / count)
            invalid("shape product overflow for " + a.name);
        count *= n;
    }
    if (count != 0 && item_size > std::numeric_limits<size_t>::max() / count)
        invalid("array byte count overflow for " + a.name);
    if (count * item_size != a.bytes.size())
        invalid("shape/dtype/data size mismatch for " + a.name);
    std::string shape = "(";
    for (size_t i = 0; i < a.shape.size(); ++i) {
        if (i)
            shape += ", ";
        shape += std::to_string(a.shape[i]);
    }
    if (a.shape.size() == 1)
        shape += ',';
    shape += ')';
    std::string dict = "{'descr': '" + a.descr + "', 'fortran_order': False, 'shape': " + shape + ", }";
    // Preamble (10 bytes), dictionary, spaces, and terminating newline align to 64.
    size_t padding = (64 - ((10 + dict.size() + 1) % 64)) % 64;
    if (dict.size() + padding + 1 > std::numeric_limits<uint16_t>::max())
        invalid("NPY v1 header length limit exceeded");
    dict.append(padding, ' ');
    dict += '\n';
    std::string out("\x93NUMPY", 6);
    out += char(1);
    out += char(0);
    out += char(dict.size() & 255);
    out += char((dict.size() >> 8) & 255);
    out += dict;
    return out;
}
uint32_t crc_update(uint32_t state, const uint8_t *bytes, size_t size) {
    static const auto table = [] {
        std::array<uint32_t, 256> values{};
        for (uint32_t i = 0; i < 256; ++i) {
            uint32_t c = i;
            for (int k = 0; k < 8; ++k)
                c = (c >> 1) ^ ((c & 1) ? 0xedb88320u : 0u);
            values[i] = c;
        }
        return values;
    }();
    for (size_t i = 0; i < size; ++i)
        state = (state >> 8) ^ table[(state ^ bytes[i]) & 255];
    return state;
}
void word(std::ostream &out, uint64_t value, int bytes) {
    for (int i = 0; i < bytes; ++i)
        out.put(char((value >> (8 * i)) & 255));
}
void raw(std::ostream &out, const void *data, size_t size) {
    if (size)
        out.write(static_cast<const char *>(data), static_cast<std::streamsize>(size));
}
struct Entry {
    const NpzArray *array;
    std::string name, npy_header;
    uint32_t size, offset, crc;
};
} // namespace

void write_npz(const std::filesystem::path &path, const std::vector<NpzArray> &arrays) {
    if (arrays.size() >= std::numeric_limits<uint16_t>::max())
        invalid("ZIP32 entry count limit exceeded");
    std::set<std::string> names;
    std::vector<Entry> entries;
    uint64_t offset = 0, central_size = 0;
    for (const auto &array : arrays) {
        if (array.name.empty() || array.name == "." || array.name == ".." ||
            array.name.find_first_of("/\\\0", 0, 3) != std::string::npos)
            invalid("array names must be nonempty plain ZIP entry names");
        if (!names.insert(array.name).second)
            invalid("duplicate array name " + array.name);
        if (array.name.size() > std::numeric_limits<uint16_t>::max() - 4)
            invalid("ZIP32 filename length limit exceeded");
        Entry e{&array, array.name + ".npy", header(array), 0, uint32_t(offset), 0};
        e.size = uint32_t(add(e.npy_header.size(), array.bytes.size()));
        uint32_t crc = crc_update(0xffffffffu, reinterpret_cast<const uint8_t *>(e.npy_header.data()),
                                  e.npy_header.size());
        e.crc = crc_update(crc, array.bytes.data(), array.bytes.size()) ^ 0xffffffffu;
        offset = add(offset, add(30 + e.name.size(), e.size));
        central_size = add(central_size, 46 + e.name.size());
        entries.push_back(std::move(e));
    }
    // Validate the entire archive's limits before opening/truncating the destination.
    add(add(offset, central_size), 22);
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out)
        invalid("cannot open " + path.string());
    for (const auto &e : entries) {
        word(out, 0x04034b50, 4); // local header
        word(out, 20, 2);
        word(out, 0x0800, 2); // version and UTF-8 filenames
        word(out, 0, 2);
        word(out, 0, 2);
        word(out, 0x0021, 2); // stored, 1980-01-01
        word(out, e.crc, 4);
        word(out, e.size, 4);
        word(out, e.size, 4);
        word(out, e.name.size(), 2);
        word(out, 0, 2);
        raw(out, e.name.data(), e.name.size());
        raw(out, e.npy_header.data(), e.npy_header.size());
        raw(out, e.array->bytes.data(), e.array->bytes.size());
    }
    for (const auto &e : entries) {
        word(out, 0x02014b50, 4); // central directory
        word(out, 20, 2);
        word(out, 20, 2);
        word(out, 0x0800, 2);
        word(out, 0, 2);
        word(out, 0, 2);
        word(out, 0x0021, 2);
        word(out, e.crc, 4);
        word(out, e.size, 4);
        word(out, e.size, 4);
        word(out, e.name.size(), 2);
        word(out, 0, 2);
        word(out, 0, 2);
        word(out, 0, 2);
        word(out, 0, 2);
        word(out, 0, 4);
        word(out, e.offset, 4);
        raw(out, e.name.data(), e.name.size());
    }
    word(out, 0x06054b50, 4); // end of central directory
    word(out, 0, 2);
    word(out, 0, 2);
    word(out, entries.size(), 2);
    word(out, entries.size(), 2);
    word(out, central_size, 4);
    word(out, offset, 4);
    word(out, 0, 2);
    out.flush();
    if (!out)
        invalid("write failed for " + path.string());
    out.close();
    if (!out)
        invalid("close failed for " + path.string());
}
} // namespace pulse
