#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <array>
#include <cstring>
#include <string>
#include <vector>

#include "_fishnet_algorithm_sections.hpp"
#include "_fishnet_algorithm_types.hpp"

namespace fishnet_internal {

std::string solver_algorithm_from_params(PyObject *params_copy) {
    if (!params_copy || !PyDict_Check(params_copy)) {
        return "legacy_fishnet";
    }
    PyObject *alg_obj = PyDict_GetItemString(params_copy, "algorithm");
    if (!alg_obj || !PyUnicode_Check(alg_obj)) {
        return "legacy_fishnet";
    }
    const char *alg_name = PyUnicode_AsUTF8(alg_obj);
    if (!alg_name || !*alg_name) {
        PyErr_Clear();
        return "legacy_fishnet";
    }
    return std::string(alg_name);
}

int solver_iterations_from_params(PyObject *params_copy) {
    if (!params_copy || !PyDict_Check(params_copy)) {
        return 0;
    }
    PyObject *steps_obj = PyDict_GetItemString(params_copy, "steps");
    if (!steps_obj) {
        return 0;
    }
    long parsed = PyLong_AsLong(steps_obj);
    if (PyErr_Occurred()) {
        PyErr_Clear();
        return 0;
    }
    if (parsed < 0) {
        return 0;
    }
    return static_cast<int>(parsed);
}

void attach_solver_metadata(PyObject *result, PyObject *params_copy, const char *termination_reason, bool converged, PyObject *diagnostics=nullptr) {
    if (!result || !PyDict_Check(result)) {
        return;
    }
    std::string algorithm = solver_algorithm_from_params(params_copy);
    int iterations = solver_iterations_from_params(params_copy);

    PyObject *algorithm_obj = PyUnicode_FromString(algorithm.c_str());
    PyObject *termination_obj = PyUnicode_FromString(termination_reason ? termination_reason : "unknown");
    PyObject *converged_obj = converged ? Py_True : Py_False;
    PyObject *iterations_obj = PyLong_FromLong(iterations);
    PyObject *status_obj = PyUnicode_FromString(converged ? "ok" : "error");
    if (algorithm_obj) {
        PyDict_SetItemString(result, "algorithm", algorithm_obj);
        Py_DECREF(algorithm_obj);
    }
    if (termination_obj) {
        PyDict_SetItemString(result, "termination_reason", termination_obj);
        Py_DECREF(termination_obj);
    }
    PyDict_SetItemString(result, "converged", converged_obj);
    if (iterations_obj) {
        PyDict_SetItemString(result, "iterations", iterations_obj);
        Py_DECREF(iterations_obj);
    }
    if (status_obj) {
        PyDict_SetItemString(result, "solver_status", status_obj);
        Py_DECREF(status_obj);
    }

    PyObject *diagnostics_obj = diagnostics;
    if (!diagnostics_obj) {
        diagnostics_obj = PyDict_New();
    } else {
        Py_INCREF(diagnostics_obj);
    }
    if (diagnostics_obj) {
        if (PyDict_Check(diagnostics_obj) && !PyDict_GetItemString(diagnostics_obj, "stop_reason_detail")) {
            const char *detail = "unspecified";
            if (termination_reason && std::strcmp(termination_reason, "converged") == 0) {
                detail = converged ? "residual_within_threshold" : "inconsistent_state";
            } else if (termination_reason && std::strcmp(termination_reason, "max_iterations") == 0) {
                detail = "edge_length_violation_after_max_iterations";
            } else if (termination_reason && std::strcmp(termination_reason, "infeasible") == 0) {
                detail = "input_or_geometry_infeasible";
            }
            PyObject *detail_obj = PyUnicode_FromString(detail);
            if (detail_obj) {
                PyDict_SetItemString(diagnostics_obj, "stop_reason_detail", detail_obj);
                Py_DECREF(detail_obj);
            }
        }
        PyDict_SetItemString(result, "diagnostics", diagnostics_obj);
        Py_DECREF(diagnostics_obj);
    }
}

void set_diag_long(PyObject *diagnostics, const char *key, long value) {
    if (!diagnostics || !PyDict_Check(diagnostics) || !key) {
        return;
    }
    PyObject *obj = PyLong_FromLong(value);
    if (obj) {
        PyDict_SetItemString(diagnostics, key, obj);
        Py_DECREF(obj);
    }
}

void set_diag_double(PyObject *diagnostics, const char *key, double value) {
    if (!diagnostics || !PyDict_Check(diagnostics) || !key) {
        return;
    }
    PyObject *obj = PyFloat_FromDouble(value);
    if (obj) {
        PyDict_SetItemString(diagnostics, key, obj);
        Py_DECREF(obj);
    }
}

void set_diag_string(PyObject *diagnostics, const char *key, const char *value) {
    if (!diagnostics || !PyDict_Check(diagnostics) || !key || !value) {
        return;
    }
    PyObject *obj = PyUnicode_FromString(value);
    if (obj) {
        PyDict_SetItemString(diagnostics, key, obj);
        Py_DECREF(obj);
    }
}

void add_solver_diagnostics(
    PyObject *diagnostics,
    PyObject *params_copy,
    long face_count,
    long point_count,
    long triangle_count,
    long quad_count,
    long orientation_break_count,
    int edge_violations,
    double max_rel_error,
    double rel_tol,
    bool rel_tol_from_parameter,
    int max_iterations,
    const std::vector<double> &residual_history,
    bool acp_energy_mode,
    const AcpPropagationSummary &acp_summary
) {
    if (!diagnostics || !PyDict_Check(diagnostics)) {
        return;
    }

    if (face_count >= 0) {
        set_diag_long(diagnostics, "face_count", face_count);
    }
    set_diag_long(diagnostics, "point_count", point_count);
    set_diag_long(diagnostics, "triangle_count", triangle_count);
    set_diag_long(diagnostics, "quad_count", quad_count);
    set_diag_long(diagnostics, "orientation_break_count", orientation_break_count);
    set_diag_long(diagnostics, "edge_violations", edge_violations);
    set_diag_double(diagnostics, "max_edge_rel_error", max_rel_error);
    set_diag_double(diagnostics, "final_residual", max_rel_error);
    set_diag_double(diagnostics, "residual_threshold", rel_tol);
    set_diag_long(diagnostics, "max_iterations", max_iterations);

    const long performed_iterations = residual_history.empty() ? 0 : static_cast<long>(residual_history.size() - 1);
    set_diag_long(diagnostics, "performed_iterations", performed_iterations);
    if (PyObject *residual_history_obj = build_double_list(residual_history)) {
        PyDict_SetItemString(diagnostics, "residual_history", residual_history_obj);
        Py_DECREF(residual_history_obj);
    }

    set_diag_string(diagnostics, "residual_metric", "max_edge_rel_error");
    set_diag_string(diagnostics, "residual_norm_type", "linf_relative_edge_length_error");
    set_diag_string(
        diagnostics,
        "stop_threshold_source",
        rel_tol_from_parameter ? "parameter:edge_length_tolerance" : "default:edge_length_tolerance"
    );

    if (acp_energy_mode) {
        set_diag_long(diagnostics, "propagation_seed_index", acp_summary.seed_index);
        set_diag_long(diagnostics, "propagation_primary_assigned", acp_summary.primary_assigned);
        set_diag_long(diagnostics, "propagation_orthogonal_assigned", acp_summary.orthogonal_assigned);
        set_diag_long(diagnostics, "propagation_fill_assigned", acp_summary.fill_assigned);
        if (PyObject *primary_axis_obj = build_vec3_tuple(acp_summary.primary_axis)) {
            PyDict_SetItemString(diagnostics, "primary_direction", primary_axis_obj);
            Py_DECREF(primary_axis_obj);
        }
        if (PyObject *orth_axis_obj = build_vec3_tuple(acp_summary.orthogonal_axis)) {
            PyDict_SetItemString(diagnostics, "orthogonal_direction", orth_axis_obj);
            Py_DECREF(orth_axis_obj);
        }
        set_diag_string(diagnostics, "objective_model", param_string(params_copy, "material_model", "woven").c_str());
        set_diag_double(diagnostics, "objective_ud_coefficient", param_double(params_copy, "ud_coefficient", 0.0));
        set_diag_long(diagnostics, "objective_thickness_correction", param_bool(params_copy, "thickness_correction", false) ? 1L : 0L);
        const std::string algorithm = solver_algorithm_from_params(params_copy);
        set_diag_long(diagnostics, "objective_surface_spacing", (algorithm == "acp_energy_v2_surface_spacing") ? 1L : 0L);
        set_diag_string(diagnostics, "propagation_stages", "primary_orthogonal_fill");
    }
}

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
    PyObject *params_copy
) {
    if (!result || !PyDict_Check(result)) {
        return;
    }

    PyDict_SetItemString(result, "valid", Py_True);
    PyDict_SetItemString(result, "error", PyUnicode_FromString(""));
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
    if (origin_obj) {
        PyDict_SetItemString(result, "origin", origin_obj);
        Py_DECREF(origin_obj);
    }
    if (normal_obj) {
        PyDict_SetItemString(result, "normal", normal_obj);
        Py_DECREF(normal_obj);
    }
    if (x_axis_obj) {
        PyDict_SetItemString(result, "x_axis", x_axis_obj);
        Py_DECREF(x_axis_obj);
    }
    if (y_axis_obj) {
        PyDict_SetItemString(result, "y_axis", y_axis_obj);
        Py_DECREF(y_axis_obj);
    }

    PyDict_SetItemString(result, "parameters", params_copy);
}

PyObject *build_empty_geometry_result(const char *error, PyObject *params_copy) {
    PyObject *res = PyDict_New();
    if (!res) {
        Py_DECREF(params_copy);
        return nullptr;
    }

    PyDict_SetItemString(res, "valid", Py_False);
    PyDict_SetItemString(res, "error", PyUnicode_FromString(error));
    PyDict_SetItemString(res, "fabric_points", PyList_New(0));
    PyDict_SetItemString(res, "warp_weft_points", PyList_New(0));
    PyDict_SetItemString(res, "fabric_quads", PyList_New(0));
    PyDict_SetItemString(res, "boundary_loops", PyList_New(0));
    PyDict_SetItemString(res, "warp_weft_boundary_loops", PyList_New(0));
    PyDict_SetItemString(res, "strains", PyList_New(0));
    PyDict_SetItemString(res, "mesh_points", PyList_New(0));
    PyDict_SetItemString(res, "mesh_faces", PyList_New(0));
    PyDict_SetItemString(res, "face_frames", PyList_New(0));
    PyDict_SetItemString(res, "orientation_breaks", PyList_New(0));
    PyDict_SetItemString(res, "atlas_charts", PyList_New(0));
    PyDict_SetItemString(res, "parameters", params_copy);
    attach_solver_metadata(res, params_copy, "infeasible", false);
    Py_DECREF(params_copy);
    return res;
}


}  // namespace fishnet_internal
