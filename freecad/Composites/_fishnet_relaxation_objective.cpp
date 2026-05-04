#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <deque>
#include <limits>
#include <queue>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include "_fishnet_algorithm_types.hpp"

namespace fishnet_internal {

#define static
#include "_fishnet_relaxation_objective.inc"
#undef static

}  // namespace fishnet_internal
