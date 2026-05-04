#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <array>
#include <cstddef>
#include <vector>

#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal {

bool parse_point(PyObject *obj, Vec3 &out);
bool parse_face(PyObject *obj, std::array<int, 3> &out);
bool collect_mesh_points(PyObject *points_obj, std::vector<Vec3> &points);
bool collect_mesh_faces(PyObject *faces_obj, size_t point_count, std::vector<std::array<int, 3>> &faces);

} // namespace fishnet_internal
