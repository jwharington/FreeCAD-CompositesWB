#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstring>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

#include "fishnet_algorithm_types.hpp"
#include "fishnet_diagnostics_api.hpp"
#include "fishnet_options_api.hpp"
#include "fishnet_python_util.hpp"
#include "fishnet_result_api.hpp"

namespace fishnet_internal
{

    void emit_sweep_signature_fields(PyObject *result, PyObject *diagnostics);
    void emit_sweep_transition_event_summary_fields(PyObject *result, PyObject *diagnostics);

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
        PyObject *params_copy)
    {
        if (!result || !PyDict_Check(result))
        {
            return;
        }

        PyDict_SetItemString(result, "valid", Py_True);
        set_dict_string(result, "error", "");
        PyDict_SetItemString(result, "fabric_points", fabric_points);
        PyDict_SetItemString(result, "warp_weft_points", warp_weft_points);
        PyDict_SetItemString(result, "fabric_quads", fabric_quads);
        PyDict_SetItemString(result, "boundary_loops", boundary_loops);
        PyDict_SetItemString(result, "warp_weft_boundary_loops", warp_weft_boundary_loops);
        PyDict_SetItemString(result, "strains", strains);
        PyDict_SetItemString(result, "mesh_points", mesh_points);
        PyDict_SetItemString(result, "mesh_faces", mesh_faces);
        PyDict_SetItemString(result, "face_frames", face_frames);
        PyDict_SetItemString(result, "orientation_breaks", orientation_breaks);
        PyDict_SetItemString(result, "atlas_charts", atlas_charts);

        PyObject *origin_obj = build_vec3_tuple(origin);
        PyObject *normal_obj = build_vec3_tuple(normal);
        PyObject *x_axis_obj = build_vec3_tuple(x_axis);
        PyObject *y_axis_obj = build_vec3_tuple(y_axis);
        if (origin_obj)
        {
            PyDict_SetItemString(result, "origin", origin_obj);
            Py_DECREF(origin_obj);
        }
        if (normal_obj)
        {
            PyDict_SetItemString(result, "normal", normal_obj);
            Py_DECREF(normal_obj);
        }
        if (x_axis_obj)
        {
            PyDict_SetItemString(result, "x_axis", x_axis_obj);
            Py_DECREF(x_axis_obj);
        }
        if (y_axis_obj)
        {
            PyDict_SetItemString(result, "y_axis", y_axis_obj);
            Py_DECREF(y_axis_obj);
        }

        PyDict_SetItemString(result, "parameters", params_copy);
    }

    PyObject *build_result_from_compat_payload(
        const ResultCompatibilityPayload &payload,
        const SolverDiagnosticsInput *diagnostics_input)
    {
        PyObject *result = PyDict_New();
        if (!result)
        {
            return nullptr;
        }

        if (payload.valid)
        {
            set_result_common_fields(
                result,
                payload.fabric_points,
                payload.warp_weft_points,
                payload.fabric_quads,
                payload.boundary_loops,
                payload.warp_weft_boundary_loops,
                payload.strains,
                payload.mesh_points,
                payload.mesh_faces,
                payload.face_frames,
                payload.orientation_breaks,
                payload.atlas_charts,
                payload.origin,
                payload.normal,
                payload.x_axis,
                payload.y_axis,
                payload.params_copy);
            if (diagnostics_input)
            {
                attach_result_diagnostics(result, payload.params_copy, *diagnostics_input);
            }
            return result;
        }

        PyDict_SetItemString(result, "valid", Py_False);
        set_dict_string(result, "error", payload.error ? payload.error : "");
        set_dict_empty_list(result, "fabric_points");
        set_dict_empty_list(result, "warp_weft_points");
        set_dict_empty_list(result, "fabric_quads");
        set_dict_empty_list(result, "boundary_loops");
        set_dict_empty_list(result, "warp_weft_boundary_loops");
        set_dict_empty_list(result, "strains");
        set_dict_empty_list(result, "mesh_points");
        set_dict_empty_list(result, "mesh_faces");
        set_dict_empty_list(result, "face_frames");
        set_dict_empty_list(result, "orientation_breaks");
        set_dict_empty_list(result, "atlas_charts");
        if (payload.params_copy)
        {
            PyDict_SetItemString(result, "parameters", payload.params_copy);
        }

        if (diagnostics_input && payload.params_copy)
        {
            attach_result_diagnostics(result, payload.params_copy, *diagnostics_input);
        }
        else if (payload.params_copy)
        {
            attach_solver_metadata(result, payload.params_copy, "infeasible", false, nullptr);
        }

        return result;
    }

    PyObject *build_empty_geometry_result(const char *error, PyObject *params_copy)
    {
        PyObject *res = PyDict_New();
        if (!res)
        {
            Py_DECREF(params_copy);
            return nullptr;
        }

        PyDict_SetItemString(res, "valid", Py_False);
        set_dict_string(res, "error", error ? error : "");
        set_dict_empty_list(res, "fabric_points");
        set_dict_empty_list(res, "warp_weft_points");
        set_dict_empty_list(res, "fabric_quads");
        set_dict_empty_list(res, "boundary_loops");
        set_dict_empty_list(res, "warp_weft_boundary_loops");
        set_dict_empty_list(res, "strains");
        set_dict_empty_list(res, "mesh_points");
        set_dict_empty_list(res, "mesh_faces");
        set_dict_empty_list(res, "face_frames");
        set_dict_empty_list(res, "orientation_breaks");
        set_dict_empty_list(res, "atlas_charts");
        PyDict_SetItemString(res, "parameters", params_copy);
        attach_solver_metadata(res, params_copy, "infeasible", false, nullptr);
        Py_DECREF(params_copy);
        return res;
    }

    // ── Domain diagnostics aggregation ────────────────────────────────────────


} // namespace fishnet_internal
