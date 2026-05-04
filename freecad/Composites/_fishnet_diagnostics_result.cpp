#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <array>
#include <cstring>
#include <string>
#include <vector>

#include "_fishnet_algorithm_sections.hpp"
#include "_fishnet_algorithm_types.hpp"

namespace fishnet_internal {

#define static
#include "_fishnet_diagnostics_result.inc"
#undef static

}  // namespace fishnet_internal
