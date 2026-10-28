#include "pulse/pulse.h"
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv) {
    const char *text =
        "# PULSE Netlist v1.1\n## Parameters\n```pulse\n```\n## Network\n```pulse\nMATH_X X = 1\n```\n## "
        "Simulation\n```pulse\n.TRAN T_END=1 SAVE_DT=.1\n```\n## Layout\n```json\n{}\n```\n";
    pulse_handle *h = NULL;
    if (pulse_abi_version() != 2 || pulse_compile_markdown(text, strlen(text), &h) != 0) {
        if (h)
            fprintf(stderr, "%s\n", pulse_get_last_error(h));
        pulse_release_model(h);
        return 1;
    }
    int code = pulse_simulate(h, NULL, argc > 1 ? argv[1] : "out-c");
    if (code)
        fprintf(stderr, "%s\n", pulse_get_last_error(h));
    pulse_release_model(h);
    return code;
}
