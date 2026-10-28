double feedback_command(double measured, double reference) {
    return 2.0 * reference - measured;
}
