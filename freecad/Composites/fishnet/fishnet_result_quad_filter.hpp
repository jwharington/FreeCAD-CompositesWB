#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <vector>

#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal
{

    std::vector<std::vector<int>> filtered_geometry_quads_for_output(
        const std::vector<std::vector<int>> &quads,
        const std::vector<Vec3> &points,
        PyObject *params_copy);

} // namespace fishnet_internal
