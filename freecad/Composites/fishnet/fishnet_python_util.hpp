#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <array>
#include <vector>

#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal {

PyObject *build_vec3_tuple(const Vec3 &v);
PyObject *build_vec3_list(const std::vector<Vec3> &values);
PyObject *build_loop_list(const std::vector<std::vector<Vec3>> &loops);
PyObject *build_quad_list(const std::vector<std::vector<int>> &quads);
PyObject *build_strain_list(const std::vector<std::array<double, 3>> &strains);
PyObject *build_double_list(const std::vector<double> &values);

} // namespace fishnet_internal
