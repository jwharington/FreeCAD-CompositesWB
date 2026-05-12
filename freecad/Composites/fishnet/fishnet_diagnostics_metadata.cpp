#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <cstring>
#include <string>

#include "fishnet_diagnostics_api.hpp"
#include "fishnet_options_api.hpp"

namespace fishnet_internal
{

    void attach_solver_metadata(PyObject *result, PyObject *params_copy, const char *termination_reason, bool converged, PyObject *diagnostics)
    {
        if (!result || !PyDict_Check(result))
        {
            return;
        }
        std::string algorithm = solver_algorithm_from_params(params_copy);
        int iterations = solver_iterations_from_params(params_copy);

        PyObject *algorithm_obj = PyUnicode_FromString(algorithm.c_str());
        PyObject *termination_obj = PyUnicode_FromString(termination_reason ? termination_reason : "unknown");
        PyObject *converged_obj = converged ? Py_True : Py_False;
        PyObject *iterations_obj = PyLong_FromLong(iterations);
        PyObject *status_obj = PyUnicode_FromString(converged ? "ok" : "error");
        if (algorithm_obj)
        {
            PyDict_SetItemString(result, "algorithm", algorithm_obj);
            Py_DECREF(algorithm_obj);
        }
        if (termination_obj)
        {
            PyDict_SetItemString(result, "termination_reason", termination_obj);
            Py_DECREF(termination_obj);
        }
        PyDict_SetItemString(result, "converged", converged_obj);
        if (iterations_obj)
        {
            PyDict_SetItemString(result, "iterations", iterations_obj);
            Py_DECREF(iterations_obj);
        }
        if (status_obj)
        {
            PyDict_SetItemString(result, "solver_status", status_obj);
            Py_DECREF(status_obj);
        }

        PyObject *diagnostics_obj = diagnostics;
        if (!diagnostics_obj)
        {
            diagnostics_obj = PyDict_New();
        }
        else
        {
            Py_INCREF(diagnostics_obj);
        }
        if (diagnostics_obj)
        {
            if (PyDict_Check(diagnostics_obj) && !PyDict_GetItemString(diagnostics_obj, "stop_reason_detail"))
            {
                const char *detail = "unspecified";
                if (termination_reason && std::strcmp(termination_reason, "converged") == 0)
                {
                    detail = converged ? "residual_within_threshold" : "inconsistent_state";
                }
                else if (termination_reason && std::strcmp(termination_reason, "max_iterations") == 0)
                {
                    detail = "edge_length_violation_after_max_iterations";
                }
                else if (termination_reason && std::strcmp(termination_reason, "infeasible") == 0)
                {
                    detail = "input_or_geometry_infeasible";
                }
                PyObject *detail_obj = PyUnicode_FromString(detail);
                if (detail_obj)
                {
                    PyDict_SetItemString(diagnostics_obj, "stop_reason_detail", detail_obj);
                    Py_DECREF(detail_obj);
                }
            }
            emit_sweep_signature_fields(result, diagnostics_obj);
            emit_sweep_transition_event_summary_fields(result, diagnostics_obj);
            PyDict_SetItemString(result, "diagnostics", diagnostics_obj);
            Py_DECREF(diagnostics_obj);
            return;
        }

        emit_sweep_signature_fields(result, nullptr);
        emit_sweep_transition_event_summary_fields(result, nullptr);
    }

    void attach_result_diagnostics(
        PyObject *result,
        PyObject *params_copy,
        const SolverDiagnosticsInput &input)
    {
        const bool legacy_edge_converged = !(input.acp_energy_mode && input.edge_violations > 0);
        const bool strict_forced_nonconverged = input.surface_spacing_strict_force_nonconverged;
        const bool converged = legacy_edge_converged && !strict_forced_nonconverged;

        const bool strict_infeasible_reason =
            input.surface_spacing_strict_fail_reason == "insufficient_coverage" ||
            input.surface_spacing_strict_fail_reason == "infeasible_geometry";
        const char *termination_reason = "converged";
        if (!converged)
        {
            termination_reason = (strict_forced_nonconverged && strict_infeasible_reason) ? "infeasible" : "max_iterations";
        }

        PyObject *diagnostics = PyDict_New();
        if (diagnostics)
        {
            add_solver_diagnostics(
                diagnostics,
                params_copy,
                input.sample_count,
                input.point_count,
                input.triangle_count,
                input.quad_count,
                input.orientation_break_count,
                input.edge_violations,
                input.max_rel_error,
                input.rel_tol,
                input.rel_tol_from_parameter,
                input.max_iterations,
                input.residual_history,
                input.combined_objective_history,
                input.acp_energy_mode,
                input.acp_summary,
                input.objective_summary,
                input.coverage_point_count,
                input.surface_spacing_active_nodes,
                input.surface_spacing_total_nodes,
                input.surface_spacing_frontier_pops,
                input.surface_spacing_frontier_accepts,
                input.surface_spacing_candidate_quads,
                input.surface_spacing_selected_quads,
                input.per_row_active_cols_min,
                input.per_row_active_cols_max,
                input.per_row_active_cols_mean,
                input.topology_transition_count,
                input.topology_split_count,
                input.topology_merge_count,
                input.topology_transition_fail_count,
                input.per_row_counts,
                input.per_row_transitions_in_counts,
                input.per_row_transitions_out_counts,
                input.transition_event_history,
                input.surface_spacing_strict_enabled,
                input.surface_spacing_strict_fail_on_violation,
                input.surface_spacing_strict_tolerance,
                input.surface_spacing_strict_edge_count,
                input.surface_spacing_strict_violation_count,
                input.surface_spacing_strict_max_rel_error,
                input.surface_spacing_strict_pass,
                input.surface_spacing_strict_repair_passes,
                input.surface_spacing_strict_fail_reason);
            attach_solver_metadata(result, params_copy, termination_reason, converged, diagnostics);
            Py_DECREF(diagnostics);
            return;
        }

        attach_solver_metadata(result, params_copy, termination_reason, converged, nullptr);
    }

} // namespace fishnet_internal
