#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal
{

    struct SolverDiagnosticsInput;

    struct ResultCompatibilityPayload
    {
        bool valid{true};
        const char *error{""};
        PyObject *params_copy{nullptr};
        PyObject *fabric_points{nullptr};
        PyObject *warp_weft_points{nullptr};
        PyObject *fabric_quads{nullptr};
        PyObject *boundary_loops{nullptr};
        PyObject *warp_weft_boundary_loops{nullptr};
        PyObject *strains{nullptr};
        PyObject *mesh_points{nullptr};
        PyObject *mesh_faces{nullptr};
        PyObject *face_frames{nullptr};
        PyObject *orientation_breaks{nullptr};
        PyObject *atlas_charts{nullptr};
        Vec3 origin{0.0, 0.0, 0.0};
        Vec3 normal{0.0, 0.0, 1.0};
        Vec3 x_axis{1.0, 0.0, 0.0};
        Vec3 y_axis{0.0, 1.0, 0.0};
    };

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

    PyObject *build_result_from_compat_payload(
        const ResultCompatibilityPayload &payload,
        const SolverDiagnosticsInput *diagnostics_input = nullptr);

    PyObject *build_empty_geometry_result(const char *error, PyObject *params_copy);

} // namespace fishnet_internal
