#pragma once
#include "pulse/core.hpp"
namespace pulse::constitutive {
Vector coordinate(const Model &, const Mode &, int part);
int direction(const Model &, const Mode &, const Mode::Guard &);
double boundary_value(const Model &, const Mode::Guard &);
bool arrived(const Mode::Guard &, const Vector &, double location_error);
Json transition(const Model &, const Mode &, const Mode &, const Vector &,
                const Mode::Guard &, int from, int to);
}
