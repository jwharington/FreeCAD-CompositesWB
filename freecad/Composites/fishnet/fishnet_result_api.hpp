#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal
{

    void set_result_common_fields(
        PyObject *result,
        PyObject *fabric_points,
        PyObject *warp_weft_points,
        PyObject *fabric_quads,
        PyObject *boundary_loops,
        PyObject *warp_weft_boundary_loops,
        PyObject *strains,
        PyObject *mesh_points,
        PyObject *mesh_faces,
        PyObject *face_frames,
        PyObject *orientation_breaks,
        PyObject *atlas_charts,
        const Vec3 &origin,
        const Vec3 &normal,
        const Vec3 &x_axis,
        const Vec3 &y_axis,
        PyObject *params_copy);

    PyObject *build_empty_geometry_result(const char *error, PyObject *params_copy);

} // namespace fishnet_internal
