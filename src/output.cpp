#include "pulse/core.hpp"
#include "pulse/npz.hpp"
#include "pulse/trajectory.hpp"
#include <algorithm>
#include <bit>
#include <fstream>
#include <iomanip>
#include <sstream>
namespace pulse {
namespace {
template <class T>
NpzArray array(std::string name, std::string descr, std::vector<size_t> shape,
               const std::vector<T> &data) {
  NpzArray a{std::move(name), std::move(descr), std::move(shape), {}};
  for (auto v : data) {
    auto bytes = std::bit_cast<std::array<uint8_t, sizeof(T)>>(v);
    if constexpr (std::endian::native == std::endian::big)
      std::reverse(bytes.begin(), bytes.end());
    a.bytes.insert(a.bytes.end(), bytes.begin(), bytes.end());
  }
  return a;
}
void write(const std::filesystem::path &p, const std::string &s) {
  std::ofstream f(p, std::ios::binary);
  f.exceptions(std::ios::failbit | std::ios::badbit);
  f << s;
}
std::string signal_id(size_t i) {
  std::ostringstream s;
  s << 's' << std::setw(4) << std::setfill('0') << i;
  return s.str();
}
struct SignalInfo {
  std::string unit, kind, axis, dtype;
};
SignalInfo signal_info(const std::string &name, bool digital) {
  if (digital)
    return {"", "logic", "digital", "uint8"};
  if (name.rfind("V(", 0) == 0 || name.find("/VD") != std::string::npos ||
      name.find("_VOLTAGE") != std::string::npos)
    return {"V", "voltage", "left", "float32"};
  if (name.rfind("I(", 0) == 0 || name.find("CURRENT") != std::string::npos ||
      name.find("/OFFSET") != std::string::npos ||
      name.find("/BIAS") != std::string::npos)
    return {"A", "current", "right", "float32"};
  return {"", "analog", "left", "float32"};
}
NpzArray unicode_scalar(const std::string &name, const std::string &text) {
  std::vector<uint32_t> cp;
  for (size_t i = 0; i < text.size();) {
    unsigned char c = static_cast<unsigned char>(text[i]);
    uint32_t v = 0;
    size_t n = 0;
    if (c < 0x80) {
      v = c;
      n = 1;
    } else if ((c & 0xe0) == 0xc0) {
      v = c & 0x1f;
      n = 2;
    } else if ((c & 0xf0) == 0xe0) {
      v = c & 0x0f;
      n = 3;
    } else if ((c & 0xf8) == 0xf0) {
      v = c & 0x07;
      n = 4;
    } else {
      v = 0xfffd;
      n = 1;
    }
    if (i + n > text.size()) {
      v = 0xfffd;
      n = 1;
    } else
      for (size_t j = 1; j < n; ++j) {
        unsigned char cc = static_cast<unsigned char>(text[i + j]);
        if ((cc & 0xc0) != 0x80) {
          v = 0xfffd;
          n = 1;
          break;
        }
        v = (v << 6) | (cc & 0x3f);
      }
    cp.push_back(v);
    i += n;
  }
  if (cp.empty())
    cp.push_back(0);
  std::vector<uint8_t> bytes;
  for (uint32_t v : cp)
    for (int j = 0; j < 4; ++j)
      bytes.push_back(uint8_t((v >> (8 * j)) & 255));
  return {name, "<U" + std::to_string(cp.size()), {}, std::move(bytes)};
}
} // namespace
void write_result(const Model &m, const Result &r,
                  const std::filesystem::path &destination) {
  try {
    std::filesystem::create_directories(destination);
    if(r.trajectory){r.trajectory->write(destination,r);return;}
    Json metadata;
    metadata["format"] = "PEWave";
    metadata["version"] = 1;
    metadata["case"] = m.parts.empty() ? "" : m.parts.front().raw.source.file;
    metadata["simulator"] = "pe-sim";
    metadata["time"] = {
        {"array", "time"},
        {"unit", "s"},
        {"is_uniform",
         [&] {
           if (r.times.size() < 2)
             return true;
           for (size_t i = 1; i < r.times.size(); ++i)
             if (std::abs((r.times[i] - r.times[i - 1]) - r.save_dt) >
                 8 * std::numeric_limits<double>::epsilon() *
                     std::max(1.0, std::abs(r.save_dt)))
               return false;
           return true;
         }()},
        {"t_start", r.times.empty() ? 0.0 : r.times.front()},
        {"t_end", r.times.empty() ? 0.0 : r.times.back()},
        {"save_dt", r.save_dt},
        {"count", r.times.size()}};
    metadata["signals"] = Json::array();
    std::vector<NpzArray> arrays;
    arrays.push_back(array("time", "<f8", {r.times.size()}, r.times));
    size_t id = 0;
    for (size_t c = 0; c < r.analog_names.size(); ++c, ++id) {
      auto info = signal_info(r.analog_names[c], false);
      metadata["signals"].push_back({{"id", signal_id(id)},
                                     {"name", r.analog_names[c]},
                                     {"unit", info.unit},
                                     {"kind", info.kind},
                                     {"axis", info.axis},
                                     {"dtype", info.dtype}});
      std::vector<float> values;
      values.reserve(r.times.size());
      for (size_t row = 0; row < r.times.size(); ++row)
        values.push_back(r.analog[row * r.analog_names.size() + c]);
      arrays.push_back(array(signal_id(id), "<f4", {values.size()}, values));
    }
    for (size_t c = 0; c < r.digital_names.size(); ++c, ++id) {
      auto info = signal_info(r.digital_names[c], true);
      metadata["signals"].push_back({{"id", signal_id(id)},
                                     {"name", r.digital_names[c]},
                                     {"unit", info.unit},
                                     {"kind", info.kind},
                                     {"axis", info.axis},
                                     {"dtype", info.dtype}});
      std::vector<uint8_t> values;
      values.reserve(r.times.size());
      for (size_t row = 0; row < r.times.size(); ++row)
        values.push_back(r.digital[row * r.digital_names.size() + c]);
      arrays.push_back(array(signal_id(id), "|u1", {values.size()}, values));
    }
    metadata["events"] = {{"count", r.events.size()}};
    metadata["available_signal_count"] = id;
    metadata["exported_signal_count"] = id;
    metadata["state_space_exact_export"] = false;
    metadata["state_space_export_segments"] = 0;
    metadata["state_space_time_varying_source"] = false;
    metadata["state_space_augmented_sources"] = 0;
    std::string text = metadata.dump();
    arrays.push_back(unicode_scalar("metadata_json", text));
    write_npz(destination / "out.pewave.npz.tmp", arrays);
    std::string log;
    for (auto &e : r.events)
      log += e.dump() + "\n";
    write(destination / "event_log.jsonl.tmp", log);
    write(destination / "simulation_report.json.tmp", r.report.dump(2) + "\n");
    std::string md = "# PULSE Solver V1.2pre run\n\nStatus: **" + r.status +
                     "**\n\nEvidence: " + r.evidence +
                     "\n\nEffective SAVE_DT: " + std::to_string(r.save_dt) +
                     " s. T_atom is recorded without rounding in "
                     "JSON.\n\nCommitted prefix: `" +
                     r.committed.at.canonical() + "`\n\n";
    if (!r.diagnostic.empty())
      md += "Diagnostic: `" + r.diagnostic.dump() + "`\n\n";
    md += "Engineering event traces use numerical point trajectories and "
          "explicit atomic grouping. They "
          "do not certify the complete trajectory.\n";
    write(destination / "simulation_report.md.tmp", md);
    for (auto name : {"out.pewave.npz", "event_log.jsonl",
                      "simulation_report.json", "simulation_report.md"}) {
      auto target = destination / name;
      std::error_code error;
      std::filesystem::rename(target.string() + ".tmp", target, error);
      if (error) {
        std::filesystem::remove(target);
        std::filesystem::rename(target.string() + ".tmp", target);
      }
    }
  } catch (const std::exception &e) {
    throw Error(11, "OUTPUT_ERROR", e.what());
  }
}
} // namespace pulse
