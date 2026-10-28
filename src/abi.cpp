#include "pulse/core.hpp"
#include "pulse/pulse.h"
#include <fstream>
#include <sstream>
struct pulse_handle {
  std::optional<pulse::Model> model;
  std::string error = "{}", report = "{}";
};
namespace {
std::vector<std::string> channels(const char *s) {
  std::vector<std::string> v;
  std::stringstream in(s ? s : "");
  std::string n;
  while (std::getline(in, n, ','))
    if (!n.empty())
      v.push_back(n);
  return v;
}
int save_error(pulse_handle *h, const std::exception &e) {
  if (h) {
    auto diag = pulse::diagnostic(e);
    h->error = diag.dump();
    h->report = pulse::Json{
        {"version", "1.2.0-pre"},
        {"status", diag.value("unresolved", false) ? "STOPPED_UNRESOLVED"
                                                   : "STOPPED_ERROR"},
        {"diagnostic",
         diag}}.dump();
  }
  if (auto p = dynamic_cast<const pulse::Error *>(&e))
    return p->code;
  return INVALID_NETLIST;
}
} // namespace
extern "C" {
uint32_t PULSE_CALL pulse_abi_version() { return 2; }
const char *PULSE_CALL pulse_version() { return "1.2.0-pre"; }
int PULSE_CALL pulse_create(pulse_handle **out) {
  if (!out)
    return INVALID_NETLIST;
  try {
    *out = new pulse_handle;
    return 0;
  } catch (...) {
    *out = nullptr;
    return INTERNAL_ERROR;
  }
}
int PULSE_CALL pulse_compile_markdown(const char *data, size_t len,
                                      pulse_handle **out) {
  if (!out)
    return INVALID_NETLIST;
  *out = nullptr;
  int code = pulse_create(out);
  if (code)
    return code;
  try {
    pulse::require(data && len > 0 && len < 64 * 1024 * 1024, 1,
                   "INVALID_INPUT", "invalid Markdown buffer");
    (*out)->model =
        pulse::compile(pulse::parse_markdown(std::string(data, len)));
    return 0;
  } catch (const std::exception &e) {
    return save_error(*out, e);
  } catch (...) {
    return INTERNAL_ERROR;
  }
}
int PULSE_CALL pulse_simulate(pulse_handle *h, const pulse_run_options *o,
                              const char *dest) {
  if (!h)
    return INVALID_NETLIST;
  try {
    pulse::require(h->model.has_value(), 1, "INVALID_HANDLE",
                   "model not compiled");
    pulse::Options options;options.retain_history=false;
    if (o) {
      pulse::require(o->struct_size == sizeof(*o) && o->abi_version == 2 &&
                         (o->flags & ~7u) == 0,
                     1, "ABI_VERSION", "run options ABI mismatch");
      if (o->flags & 1)
        options.t_end = o->t_end;
      if (o->flags & 2)
        options.save_dt = o->save_dt;
      if (o->flags & 4)
        options.channels = channels(o->channels);
      options.atom_exponent = o->atom_exponent;
    }
    auto result = pulse::simulate(*h->model, options);
    pulse::write_result(*h->model, result, dest ? dest : ".");
    h->report = result.report.dump();
    h->error = result.diagnostic.dump();
    return result.status == "COMPLETED"
               ? 0
               : result.diagnostic.value("code", INTERNAL_ERROR);
  } catch (const std::exception &e) {
    return save_error(h, e);
  } catch (...) {
    return INTERNAL_ERROR;
  }
}
const char *PULSE_CALL pulse_get_last_error(pulse_handle *h) {
  return h ? h->error.c_str() : "{\"code\":1,\"subcode\":\"INVALID_HANDLE\"}";
}
const char *PULSE_CALL pulse_last_error(pulse_handle *h) {
  return pulse_get_last_error(h);
}
const char *PULSE_CALL pulse_report_json(pulse_handle *h) {
  return h ? h->report.c_str() : "{}";
}
void PULSE_CALL pulse_release_model(pulse_handle *h) { delete h; }
void PULSE_CALL pulse_destroy(pulse_handle *h) { pulse_release_model(h); }
const char *PULSE_CALL pulse_error_name(int i) {
  static const char *names[] = {"OK",
                                "INVALID_NETLIST",
                                "UNSUPPORTED_MODEL",
                                "INCONSISTENT_INITIAL_STATE",
                                "INVALID_PWA_CURVE",
                                "PWA_OUT_OF_RANGE",
                                "MODEL_SINGULAR",
                                "NUMERICAL_ERROR",
                                "EVENT_ROOT_FAILURE",
                                "MODE_STABILIZATION_FAILURE",
                                "PHYSICAL_CONSTRAINT_VIOLATION",
                                "OUTPUT_ERROR",
                                "INTERNAL_ERROR"};
  return i >= 0 && i <= 12 ? names[i] : "UNKNOWN_ERROR";
}
int PULSE_CALL pulse_run(pulse_handle *h, const pulse_request *r) {
  if (!h)
    return INVALID_NETLIST;
  try {
    pulse::require(r && r->struct_size == sizeof(*r) && r->abi_version == 1 &&
                       r->netlist_file,
                   1, "ABI_VERSION", "invalid ABI1 request");
    std::ifstream f(r->netlist_file);
    pulse::require(bool(f), 1, "INPUT_IO", "cannot open netlist");
    std::string data((std::istreambuf_iterator<char>(f)), {});
    h->model = pulse::compile(pulse::parse_markdown(data, r->netlist_file));
    pulse_run_options options{
        sizeof(pulse_run_options), 2, 3, r->t_end, r->save_dt,
        r->output_channels,        9};
    if (r->output_channels)
      options.flags |= 4;
    return pulse_simulate(h, &options, ".");
  } catch (const std::exception &e) {
    return save_error(h, e);
  } catch (...) {
    return INTERNAL_ERROR;
  }
}
}
