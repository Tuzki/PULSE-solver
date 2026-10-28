#ifndef PULSE_SOFTWARE_H
#define PULSE_SOFTWARE_H
#include <stddef.h>
#include <stdint.h>
#if defined(_WIN32)
#define PULSE_SW_EXPORT __declspec(dllexport)
#define PULSE_SW_CALL __cdecl
#else
#define PULSE_SW_EXPORT __attribute__((visibility("default")))
#define PULSE_SW_CALL
#endif
#ifdef __cplusplus
extern "C" {
#endif
#define PULSE_SOFTWARE_ABI 2u
#define PULSE_SW_EXTERNAL 1u
#define PULSE_SW_WAKEUP 2u
#define PULSE_SW_INITIALIZE 4u
typedef struct pulse_software_info {
    uint32_t abi_version;
    uint32_t struct_size;
    size_t state_bytes;
    size_t input_count;
    size_t output_count;
    size_t parameter_count;
} pulse_software_info;
/* Instances own all persistent mutable data. No persisted pointers, writable
   process globals, or external side effects are part of this contract. */
typedef struct pulse_software_call {
    uint32_t abi_version;
    uint32_t struct_size;
    double time;
    uint64_t invocation;
    const double *inputs;
    size_t input_count;
    const double *parameters;
    size_t parameter_count;
    const void *previous_state;
    void *next_state;
    size_t state_bytes;
    double *outputs;
    size_t output_count;
    /* NaN: no self event. Positive: request a wakeup after this simulated delay.
       Any task can request a private wakeup; external clocks retain their
       exact timer deadlines. trigger_flags identifies the activation. */
    double next_delay;
    uint32_t trigger_flags;
} pulse_software_call;
typedef const pulse_software_info *(PULSE_SW_CALL *pulse_software_describe_fn)(void);
typedef int (PULSE_SW_CALL *pulse_software_entry_fn)(pulse_software_call *);
PULSE_SW_EXPORT const pulse_software_info *PULSE_SW_CALL pulse_software_describe(void);
#ifdef __cplusplus
}
#endif
#endif
