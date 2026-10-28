#ifndef PULSE_SOLVER_C_ABI_H
#define PULSE_SOLVER_C_ABI_H
#include <stddef.h>
#include <stdint.h>
#if defined(_WIN32)
#define PULSE_CALL __cdecl
#if defined(PULSE_BUILD_SHARED)
#define PULSE_API __declspec(dllexport)
#else
#define PULSE_API __declspec(dllimport)
#endif
#else
#define PULSE_CALL
#define PULSE_API __attribute__((visibility("default")))
#endif
#ifdef __cplusplus
extern "C" {
#endif
enum pulse_error {
    PULSE_OK = 0,
    INVALID_NETLIST = 1,
    UNSUPPORTED_MODEL = 2,
    INCONSISTENT_INITIAL_STATE = 3,
    INVALID_PWA_CURVE = 4,
    PWA_OUT_OF_RANGE = 5,
    MODEL_SINGULAR = 6,
    NUMERICAL_ERROR = 7,
    EVENT_ROOT_FAILURE = 8,
    MODE_STABILIZATION_FAILURE = 9,
    PHYSICAL_CONSTRAINT_VIOLATION = 10,
    OUTPUT_ERROR = 11,
    INTERNAL_ERROR = 12
};
typedef struct pulse_handle pulse_handle;
/* v2: flags 1 T_END, 2 SAVE_DT, 4 channels. NULL channels without flag means
   default; flag 4 with "" means explicit empty selection. Strings UTF-8,
   borrowed during call. All returned strings owned until next handle call. */
typedef struct pulse_run_options {
    uint32_t struct_size, abi_version, flags;
    double t_end, save_dt;
    const char *channels;
    int32_t atom_exponent;
} pulse_run_options;
PULSE_API uint32_t PULSE_CALL pulse_abi_version(void);
PULSE_API const char *PULSE_CALL pulse_version(void);
PULSE_API int PULSE_CALL pulse_compile_markdown(const char *, size_t, pulse_handle **);
PULSE_API int PULSE_CALL pulse_simulate(pulse_handle *, const pulse_run_options *, const char *destination);
PULSE_API const char *PULSE_CALL pulse_get_last_error(pulse_handle *);
PULSE_API const char *PULSE_CALL pulse_report_json(pulse_handle *);
PULSE_API void PULSE_CALL pulse_release_model(pulse_handle *);
/* v1 symbols and error numbers retained. ABI1 request still has four inputs.
   Each call recompiles .md; old .net formats are rejected. */
typedef struct pulse_request {
    uint32_t struct_size, abi_version;
    const char *netlist_file;
    double t_end, save_dt;
    const char *output_channels;
} pulse_request;
PULSE_API int PULSE_CALL pulse_create(pulse_handle **);
PULSE_API int PULSE_CALL pulse_run(pulse_handle *, const pulse_request *);
PULSE_API const char *PULSE_CALL pulse_last_error(pulse_handle *);
PULSE_API const char *PULSE_CALL pulse_error_name(int);
PULSE_API void PULSE_CALL pulse_destroy(pulse_handle *);
#ifdef __cplusplus
}
#endif
#endif
