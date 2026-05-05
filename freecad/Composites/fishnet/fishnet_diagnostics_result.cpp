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

    namespace
    {

        void set_dict_string(PyObject *dict, const char *key, const char *value)
        {
            if (!dict || !PyDict_Check(dict) || !key || !value)
            {
                return;
            }
            PyObject *str_obj = PyUnicode_FromString(value);
            if (!str_obj)
            {
                return;
            }
            PyDict_SetItemString(dict, key, str_obj);
            Py_DECREF(str_obj);
        }

        void set_dict_empty_list(PyObject *dict, const char *key)
        {
            if (!dict || !PyDict_Check(dict) || !key)
            {
                return;
            }
            PyObject *list_obj = PyList_New(0);
            if (!list_obj)
            {
                return;
            }
            PyDict_SetItemString(dict, key, list_obj);
            Py_DECREF(list_obj);
        }

        std::string lowercase_copy(std::string value)
        {
            std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c)
                           { return static_cast<char>(std::tolower(c)); });
            return value;
        }

        bool is_acp_energy_algorithm_name(const std::string &algorithm)
        {
            return algorithm == "acp_energy";
        }

        std::string parse_acp_strategy_name(const std::string &raw_value)
        {
            const std::string value = lowercase_copy(raw_value);
            if (value == "surface_spacing" || value == "surface-spacing" || value == "v2")
            {
                return "surface_spacing";
            }
            if (value == "woven" || value == "v1" || value == "default")
            {
                return "woven";
            }
            return "";
        }

    } // namespace

    std::string solver_algorithm_from_params(PyObject *params_copy)
    {
        if (!params_copy || !PyDict_Check(params_copy))
        {
            return "acp_energy";
        }
        PyObject *alg_obj = PyDict_GetItemString(params_copy, "algorithm");
        if (!alg_obj || !PyUnicode_Check(alg_obj))
        {
            return "acp_energy";
        }
        const char *alg_name = PyUnicode_AsUTF8(alg_obj);
        if (!alg_name || !*alg_name)
        {
            PyErr_Clear();
            return "acp_energy";
        }
        return std::string(alg_name);
    }

    SolverAlgorithmProfile solver_algorithm_profile_from_params(PyObject *params_copy)
    {
        SolverAlgorithmProfile profile;
        profile.requested_algorithm = solver_algorithm_from_params(params_copy);

        const std::string algorithm = lowercase_copy(profile.requested_algorithm);
        profile.acp_energy_mode = is_acp_energy_algorithm_name(algorithm);
        if (!profile.acp_energy_mode)
        {
            profile.acp_strategy = "none";
            profile.surface_spacing_mode = false;
            return profile;
        }

        std::string strategy = "woven";

        const std::string explicit_strategy = parse_acp_strategy_name(
            param_string(params_copy, "acp_strategy", ""));
        if (!explicit_strategy.empty())
        {
            strategy = explicit_strategy;
        }

        if (param_bool(params_copy, "objective_surface_spacing", false))
        {
            strategy = "surface_spacing";
        }

        profile.acp_strategy = strategy;
        profile.surface_spacing_mode = (strategy == "surface_spacing");
        return profile;
    }

    int solver_iterations_from_params(PyObject *params_copy)
    {
        if (!params_copy || !PyDict_Check(params_copy))
        {
            return 0;
        }
        PyObject *steps_obj = PyDict_GetItemString(params_copy, "steps");
        if (!steps_obj)
        {
            return 0;
        }
        long parsed = PyLong_AsLong(steps_obj);
        if (PyErr_Occurred())
        {
            PyErr_Clear();
            return 0;
        }
        if (parsed < 0)
        {
            return 0;
        }
        return static_cast<int>(parsed);
    }

    void attach_solver_metadata(PyObject *result, PyObject *params_copy, const char *termination_reason, bool converged, PyObject *diagnostics = nullptr)
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
            PyDict_SetItemString(result, "diagnostics", diagnostics_obj);
            Py_DECREF(diagnostics_obj);
        }
    }

    void set_diag_long(PyObject *diagnostics, const char *key, long value)
    {
        if (!diagnostics || !PyDict_Check(diagnostics) || !key)
        {
            return;
        }
        PyObject *obj = PyLong_FromLong(value);
        if (obj)
        {
            PyDict_SetItemString(diagnostics, key, obj);
            Py_DECREF(obj);
        }
    }

    void set_diag_double(PyObject *diagnostics, const char *key, double value)
    {
        if (!diagnostics || !PyDict_Check(diagnostics) || !key)
        {
            return;
        }
        PyObject *obj = PyFloat_FromDouble(value);
        if (obj)
        {
            PyDict_SetItemString(diagnostics, key, obj);
            Py_DECREF(obj);
        }
    }

    void set_diag_string(PyObject *diagnostics, const char *key, const char *value)
    {
        if (!diagnostics || !PyDict_Check(diagnostics) || !key || !value)
        {
            return;
        }
        PyObject *obj = PyUnicode_FromString(value);
        if (obj)
        {
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
        const std::vector<double> &combined_objective_history,
        bool acp_energy_mode,
        const AcpPropagationSummary &acp_summary,
        const AcpObjectiveSummary &objective_summary,
        long coverage_point_count,
        long surface_spacing_active_nodes,
        long surface_spacing_total_nodes,
        long surface_spacing_frontier_pops,
        long surface_spacing_frontier_accepts,
        long surface_spacing_candidate_quads,
        long surface_spacing_selected_quads,
        long per_row_active_cols_min,
        long per_row_active_cols_max,
        double per_row_active_cols_mean,
        long topology_transition_count,
        long topology_split_count,
        long topology_merge_count,
        long topology_transition_fail_count,
        const std::vector<long> &per_row_counts,
        const std::vector<long> &per_row_transitions_in_counts,
        const std::vector<long> &per_row_transitions_out_counts,
        const std::vector<TransitionEventSample> &transition_event_history)
    {
        if (!diagnostics || !PyDict_Check(diagnostics))
        {
            return;
        }

        if (face_count >= 0)
        {
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

        const size_t residual_len = residual_history.size();
        const size_t combined_len = combined_objective_history.size();
        size_t synced_len = 0;
        if (residual_len > 0 && combined_len > 0)
        {
            synced_len = std::min(residual_len, combined_len);
        }
        else
        {
            synced_len = std::max(residual_len, combined_len);
        }

        std::vector<double> residual_history_synced;
        std::vector<double> combined_history_synced;
        if (synced_len > 0)
        {
            if (residual_len > 0)
            {
                residual_history_synced.assign(residual_history.begin(), residual_history.begin() + static_cast<long>(std::min(residual_len, synced_len)));
            }
            if (combined_len > 0)
            {
                combined_history_synced.assign(combined_objective_history.begin(), combined_objective_history.begin() + static_cast<long>(std::min(combined_len, synced_len)));
            }
            if (residual_history_synced.empty())
            {
                residual_history_synced.resize(synced_len, max_rel_error);
            }
            if (combined_history_synced.empty())
            {
                combined_history_synced = residual_history_synced;
            }
            if (residual_history_synced.size() < synced_len)
            {
                residual_history_synced.resize(synced_len, residual_history_synced.back());
            }
            if (combined_history_synced.size() < synced_len)
            {
                combined_history_synced.resize(synced_len, combined_history_synced.back());
            }
        }

        const long performed_iterations = residual_history_synced.empty() ? 0 : static_cast<long>(residual_history_synced.size() - 1);
        set_diag_long(diagnostics, "performed_iterations", performed_iterations);
        if (PyObject *residual_history_obj = build_double_list(residual_history_synced))
        {
            PyDict_SetItemString(diagnostics, "residual_history", residual_history_obj);
            Py_DECREF(residual_history_obj);
        }
        if (PyObject *combined_objective_history_obj = build_double_list(combined_history_synced))
        {
            PyDict_SetItemString(diagnostics, "combined_objective_history", combined_objective_history_obj);
            Py_DECREF(combined_objective_history_obj);
        }

        set_diag_string(diagnostics, "residual_metric", "max_edge_rel_error");
        set_diag_string(diagnostics, "residual_norm_type", "linf_relative_edge_length_error");
        set_diag_string(diagnostics, "combined_objective_metric", "weighted_lp_relative_edge_length_error");
        set_diag_string(
            diagnostics,
            "stop_threshold_source",
            rel_tol_from_parameter ? "parameter:edge_length_tolerance" : "default:edge_length_tolerance");

        if (coverage_point_count >= 0)
        {
            set_diag_long(diagnostics, "coverage_point_count", coverage_point_count);
            if (point_count > 0)
            {
                set_diag_double(diagnostics, "coverage_point_ratio", static_cast<double>(coverage_point_count) / static_cast<double>(point_count));
            }
        }

        if (acp_energy_mode)
        {
            set_diag_long(diagnostics, "propagation_seed_index", acp_summary.seed_index);
            set_diag_long(diagnostics, "propagation_primary_assigned", acp_summary.primary_assigned);
            set_diag_long(diagnostics, "propagation_orthogonal_assigned", acp_summary.orthogonal_assigned);
            set_diag_long(diagnostics, "propagation_fill_assigned", acp_summary.fill_assigned);
            set_diag_long(diagnostics, "propagation_step1_assigned", acp_summary.step1_assigned);
            set_diag_long(diagnostics, "propagation_step2_assigned", acp_summary.step2_assigned);
            set_diag_long(diagnostics, "propagation_step3_assigned", acp_summary.step3_assigned);
            set_diag_long(diagnostics, "propagation_step2_nr_attempts", acp_summary.step2_nr_attempts);
            set_diag_long(diagnostics, "propagation_step2_nr_converged", acp_summary.step2_nr_converged);
            set_diag_long(diagnostics, "propagation_step2_nr_fallback_count", acp_summary.step2_nr_fallback_count);
            set_diag_long(diagnostics, "propagation_step2_nr_infeasible", acp_summary.step2_nr_infeasible);
            set_diag_long(diagnostics, "propagation_step2_nr_decrease_count", acp_summary.step2_nr_decrease_count);
            set_diag_long(diagnostics, "propagation_step2_nr_iterations", acp_summary.step2_nr_iterations);
            set_diag_double(diagnostics, "propagation_pre_shear_deg", acp_summary.propagation_pre_shear_deg);
            set_diag_double(diagnostics, "propagation_pre_shear_slope", acp_summary.propagation_pre_shear_slope);
            set_diag_long(
                diagnostics,
                "propagation_pre_shear_active",
                std::abs(acp_summary.propagation_pre_shear_deg) > 1.0e-12 ? 1L : 0L);
            set_diag_long(diagnostics, "propagation_step3_pre_shear_adjust_count", acp_summary.propagation_step3_pre_shear_adjust_count);
            if (acp_summary.propagation_step3_pre_shear_adjust_count > 0)
            {
                set_diag_double(
                    diagnostics,
                    "propagation_step3_pre_shear_adjust_mean",
                    acp_summary.propagation_step3_pre_shear_adjust_sum /
                        static_cast<double>(acp_summary.propagation_step3_pre_shear_adjust_count));
            }
            else
            {
                set_diag_double(diagnostics, "propagation_step3_pre_shear_adjust_mean", 0.0);
            }
            if (acp_summary.step2_nr_signed_shear_count > 0)
            {
                set_diag_double(
                    diagnostics,
                    "propagation_step2_signed_shear_mean_deg",
                    acp_summary.step2_nr_signed_shear_sum_deg /
                        static_cast<double>(acp_summary.step2_nr_signed_shear_count));
                set_diag_double(
                    diagnostics,
                    "propagation_step2_signed_shear_target_error_mean_deg",
                    acp_summary.step2_nr_signed_shear_target_error_sum_deg /
                        static_cast<double>(acp_summary.step2_nr_signed_shear_count));
            }
            else
            {
                set_diag_double(diagnostics, "propagation_step2_signed_shear_mean_deg", 0.0);
                set_diag_double(diagnostics, "propagation_step2_signed_shear_target_error_mean_deg", 0.0);
            }
            if (acp_summary.step2_nr_attempts > 0)
            {
                const double inv_attempts = 1.0 / static_cast<double>(acp_summary.step2_nr_attempts);
                set_diag_double(
                    diagnostics,
                    "propagation_step2_nr_initial_objective_mean",
                    acp_summary.step2_nr_initial_objective_sum * inv_attempts);
                set_diag_double(
                    diagnostics,
                    "propagation_step2_nr_final_objective_mean",
                    acp_summary.step2_nr_final_objective_sum * inv_attempts);
            }
            else
            {
                set_diag_double(diagnostics, "propagation_step2_nr_initial_objective_mean", 0.0);
                set_diag_double(diagnostics, "propagation_step2_nr_final_objective_mean", 0.0);
            }
            if (PyObject *primary_axis_obj = build_vec3_tuple(acp_summary.primary_axis))
            {
                PyDict_SetItemString(diagnostics, "primary_direction", primary_axis_obj);
                Py_DECREF(primary_axis_obj);
            }
            if (PyObject *orth_axis_obj = build_vec3_tuple(acp_summary.orthogonal_axis))
            {
                PyDict_SetItemString(diagnostics, "orthogonal_direction", orth_axis_obj);
                Py_DECREF(orth_axis_obj);
            }
            set_diag_string(diagnostics, "objective_model", param_string(params_copy, "material_model", "woven").c_str());
            set_diag_double(diagnostics, "objective_ud_coefficient", param_double(params_copy, "ud_coefficient", 0.0));
            set_diag_long(diagnostics, "objective_thickness_correction", param_bool(params_copy, "thickness_correction", false) ? 1L : 0L);
            set_diag_double(diagnostics, "objective_p_norm", objective_summary.objective_p_norm);
            set_diag_double(diagnostics, "objective_pre_shear_deg", objective_summary.objective_pre_shear_deg);
            set_diag_double(diagnostics, "objective_shear_weight", objective_summary.objective_shear_weight);
            set_diag_double(diagnostics, "objective_fiber_weight", objective_summary.objective_fiber_weight);
            set_diag_double(diagnostics, "objective_cell_gain", objective_summary.objective_cell_gain);
            set_diag_long(diagnostics, "objective_edge_count", objective_summary.edge_count);
            set_diag_long(diagnostics, "objective_cell_count", objective_summary.cell_count);
            set_diag_long(diagnostics, "objective_primary_edge_count", objective_summary.primary_edge_count);
            set_diag_long(diagnostics, "objective_transverse_edge_count", objective_summary.transverse_edge_count);
            set_diag_long(diagnostics, "objective_bias_edge_count", objective_summary.bias_edge_count);
            set_diag_long(diagnostics, "objective_positive_bias_edge_count", objective_summary.positive_bias_edge_count);
            set_diag_long(diagnostics, "objective_negative_bias_edge_count", objective_summary.negative_bias_edge_count);
            set_diag_double(diagnostics, "objective_target_scale_mean", objective_summary.target_scale_mean);
            set_diag_double(diagnostics, "objective_target_scale_min", objective_summary.target_scale_min);
            set_diag_double(diagnostics, "objective_target_scale_max", objective_summary.target_scale_max);
            set_diag_double(diagnostics, "objective_weight_mean", objective_summary.weight_mean);
            set_diag_double(diagnostics, "objective_weight_min", objective_summary.weight_min);
            set_diag_double(diagnostics, "objective_weight_max", objective_summary.weight_max);
            set_diag_double(diagnostics, "objective_target_scale_primary_mean", objective_summary.primary_target_scale_mean);
            set_diag_double(diagnostics, "objective_target_scale_transverse_mean", objective_summary.transverse_target_scale_mean);
            set_diag_double(diagnostics, "objective_target_scale_bias_mean", objective_summary.bias_target_scale_mean);
            set_diag_double(diagnostics, "objective_weight_primary_mean", objective_summary.primary_weight_mean);
            set_diag_double(diagnostics, "objective_weight_transverse_mean", objective_summary.transverse_weight_mean);
            set_diag_double(diagnostics, "objective_weight_bias_mean", objective_summary.bias_weight_mean);
            set_diag_double(diagnostics, "objective_target_scale_positive_bias_mean", objective_summary.positive_bias_target_scale_mean);
            set_diag_double(diagnostics, "objective_target_scale_negative_bias_mean", objective_summary.negative_bias_target_scale_mean);
            set_diag_double(diagnostics, "objective_signed_bias_target_asymmetry", objective_summary.signed_bias_target_asymmetry);
            set_diag_double(diagnostics, "objective_signed_shear_proxy_mean", objective_summary.signed_shear_proxy_mean);
            set_diag_double(diagnostics, "objective_abs_shear_proxy_mean", objective_summary.abs_shear_proxy_mean);
            set_diag_double(diagnostics, "objective_cell_shear_abs_mean_deg", objective_summary.cell_shear_abs_mean_deg);
            set_diag_double(diagnostics, "objective_cell_shear_signed_mean_deg", objective_summary.cell_shear_signed_mean_deg);
            set_diag_double(diagnostics, "objective_cell_shear_target_error_mean_deg", objective_summary.cell_shear_target_error_mean_deg);
            set_diag_double(diagnostics, "objective_cell_fiber_angle_mean_deg", objective_summary.cell_fiber_angle_mean_deg);
            set_diag_double(diagnostics, "objective_cell_combined_objective_mean", objective_summary.cell_combined_objective_mean);
            set_diag_double(diagnostics, "objective_target_anisotropy_ratio", objective_summary.target_anisotropy_ratio);
            set_diag_double(diagnostics, "objective_weight_anisotropy_ratio", objective_summary.weight_anisotropy_ratio);
            const SolverAlgorithmProfile profile = solver_algorithm_profile_from_params(params_copy);
            set_diag_long(diagnostics, "objective_surface_spacing", profile.surface_spacing_mode ? 1L : 0L);
            set_diag_string(diagnostics, "objective_strategy", profile.acp_strategy.c_str());
            set_diag_string(diagnostics, "propagation_stages", "primary_orthogonal_fill");
            if (!acp_summary.stage_trace.empty())
            {
                PyObject *trace_obj = PyList_New(static_cast<Py_ssize_t>(acp_summary.stage_trace.size()));
                if (trace_obj)
                {
                    for (size_t i = 0; i < acp_summary.stage_trace.size(); ++i)
                    {
                        PyObject *value = PyUnicode_FromString(acp_summary.stage_trace[i].c_str());
                        if (!value)
                        {
                            Py_DECREF(trace_obj);
                            trace_obj = nullptr;
                            break;
                        }
                        PyList_SET_ITEM(trace_obj, static_cast<Py_ssize_t>(i), value);
                    }
                    if (trace_obj)
                    {
                        PyDict_SetItemString(diagnostics, "propagation_stage_trace", trace_obj);
                        Py_DECREF(trace_obj);
                    }
                }
            }
            if (PyObject *generator_objective_history_obj = build_double_list(acp_summary.generator_objective_history))
            {
                PyDict_SetItemString(diagnostics, "generator_objective_history", generator_objective_history_obj);
                Py_DECREF(generator_objective_history_obj);
            }
            if (PyObject *generator_shear_history_obj = build_double_list(acp_summary.generator_shear_history))
            {
                PyDict_SetItemString(diagnostics, "generator_shear_history", generator_shear_history_obj);
                Py_DECREF(generator_shear_history_obj);
            }
            if (profile.surface_spacing_mode)
            {
                if (point_count > 0 && surface_spacing_active_nodes > coverage_point_count)
                {
                    set_diag_long(diagnostics, "coverage_point_count", surface_spacing_active_nodes);
                    set_diag_double(
                        diagnostics,
                        "coverage_point_ratio",
                        static_cast<double>(surface_spacing_active_nodes) / static_cast<double>(point_count));
                }

                if (surface_spacing_active_nodes >= 0)
                {
                    set_diag_long(diagnostics, "surface_spacing_active_nodes", surface_spacing_active_nodes);
                }
                if (surface_spacing_total_nodes >= 0)
                {
                    set_diag_long(diagnostics, "surface_spacing_total_nodes", surface_spacing_total_nodes);
                }
                if (surface_spacing_total_nodes > 0 && surface_spacing_active_nodes >= 0)
                {
                    set_diag_double(
                        diagnostics,
                        "surface_spacing_active_ratio",
                        static_cast<double>(surface_spacing_active_nodes) / static_cast<double>(surface_spacing_total_nodes));
                }
                if (surface_spacing_frontier_pops >= 0)
                {
                    set_diag_long(diagnostics, "surface_spacing_frontier_pops", surface_spacing_frontier_pops);
                }
                if (surface_spacing_frontier_accepts >= 0)
                {
                    set_diag_long(diagnostics, "surface_spacing_frontier_accepts", surface_spacing_frontier_accepts);
                    if (surface_spacing_frontier_pops > 0)
                    {
                        set_diag_double(
                            diagnostics,
                            "surface_spacing_frontier_accept_ratio",
                            static_cast<double>(surface_spacing_frontier_accepts) / static_cast<double>(surface_spacing_frontier_pops));
                    }
                }
                if (surface_spacing_candidate_quads >= 0)
                {
                    set_diag_long(diagnostics, "surface_spacing_candidate_quads", surface_spacing_candidate_quads);
                }
                if (surface_spacing_selected_quads >= 0)
                {
                    set_diag_long(diagnostics, "surface_spacing_selected_quads", surface_spacing_selected_quads);
                    if (surface_spacing_candidate_quads > 0)
                    {
                        const double select_ratio =
                            static_cast<double>(surface_spacing_selected_quads) / static_cast<double>(surface_spacing_candidate_quads);
                        set_diag_double(diagnostics, "surface_spacing_quad_select_ratio", select_ratio);

                        std::string stall_reason = "none";
                        if (surface_spacing_selected_quads == 0 && surface_spacing_frontier_accepts > 0)
                        {
                            stall_reason = "no_valid_quad_component";
                        }
                        else if (select_ratio < 0.5)
                        {
                            stall_reason = "component_or_overlap_filtered";
                        }
                        else if (surface_spacing_frontier_pops > 0 && surface_spacing_frontier_accepts == 0)
                        {
                            stall_reason = "frontier_rejected";
                        }
                        set_diag_string(diagnostics, "surface_spacing_growth_stall_reason", stall_reason.c_str());
                    }
                }
            }
        }

        // Per-row column count diagnostics (variable cardinality / cone-adaptation).
        if (per_row_active_cols_max > 0)
        {
            set_diag_long(diagnostics, "per_row_active_cols_min", per_row_active_cols_min);
            set_diag_long(diagnostics, "per_row_active_cols_max", per_row_active_cols_max);
            set_diag_double(diagnostics, "per_row_active_cols_mean", per_row_active_cols_mean);
        }

        set_diag_long(diagnostics, "topology_transition_count", topology_transition_count);
        set_diag_long(diagnostics, "topology_split_count", topology_split_count);
        set_diag_long(diagnostics, "topology_merge_count", topology_merge_count);
        set_diag_long(diagnostics, "topology_transition_fail_count", topology_transition_fail_count);

        if (!per_row_counts.empty())
        {
            PyObject *per_row_counts_obj = PyList_New(static_cast<Py_ssize_t>(per_row_counts.size()));
            if (per_row_counts_obj)
            {
                for (size_t i = 0; i < per_row_counts.size(); ++i)
                {
                    PyObject *value = PyLong_FromLong(per_row_counts[i]);
                    if (!value)
                    {
                        Py_DECREF(per_row_counts_obj);
                        per_row_counts_obj = nullptr;
                        break;
                    }
                    PyList_SET_ITEM(per_row_counts_obj, static_cast<Py_ssize_t>(i), value);
                }
                if (per_row_counts_obj)
                {
                    PyDict_SetItemString(diagnostics, "per_row_counts", per_row_counts_obj);
                    Py_DECREF(per_row_counts_obj);
                }
            }
        }

        if (!per_row_transitions_in_counts.empty())
        {
            PyObject *in_obj = PyList_New(static_cast<Py_ssize_t>(per_row_transitions_in_counts.size()));
            if (in_obj)
            {
                for (size_t i = 0; i < per_row_transitions_in_counts.size(); ++i)
                {
                    PyObject *value = PyLong_FromLong(per_row_transitions_in_counts[i]);
                    if (!value)
                    {
                        Py_DECREF(in_obj);
                        in_obj = nullptr;
                        break;
                    }
                    PyList_SET_ITEM(in_obj, static_cast<Py_ssize_t>(i), value);
                }
                if (in_obj)
                {
                    PyDict_SetItemString(diagnostics, "per_row_transitions_in_counts", in_obj);
                    Py_DECREF(in_obj);
                }
            }
        }

        if (!per_row_transitions_out_counts.empty())
        {
            PyObject *out_obj = PyList_New(static_cast<Py_ssize_t>(per_row_transitions_out_counts.size()));
            if (out_obj)
            {
                for (size_t i = 0; i < per_row_transitions_out_counts.size(); ++i)
                {
                    PyObject *value = PyLong_FromLong(per_row_transitions_out_counts[i]);
                    if (!value)
                    {
                        Py_DECREF(out_obj);
                        out_obj = nullptr;
                        break;
                    }
                    PyList_SET_ITEM(out_obj, static_cast<Py_ssize_t>(i), value);
                }
                if (out_obj)
                {
                    PyDict_SetItemString(diagnostics, "per_row_transitions_out_counts", out_obj);
                    Py_DECREF(out_obj);
                }
            }
        }

        if (!transition_event_history.empty())
        {
            PyObject *events_obj = PyList_New(static_cast<Py_ssize_t>(transition_event_history.size()));
            if (events_obj)
            {
                bool ok = true;
                for (size_t i = 0; i < transition_event_history.size(); ++i)
                {
                    const TransitionEventSample &event = transition_event_history[i];
                    PyObject *event_obj = PyDict_New();
                    if (!event_obj)
                    {
                        ok = false;
                        break;
                    }

                    PyObject *sample_index_obj = PyLong_FromLong(event.sample_index);
                    PyObject *from_row_obj = PyLong_FromLong(event.from_row);
                    PyObject *to_row_obj = PyLong_FromLong(event.to_row);
                    PyObject *from_count_obj = PyLong_FromLong(event.from_count);
                    PyObject *to_count_obj = PyLong_FromLong(event.to_count);
                    PyObject *delta_obj = PyLong_FromLong(event.delta);
                    PyObject *kind_obj = PyUnicode_FromString(event.kind.c_str());
                    PyObject *success_obj = event.success ? Py_True : Py_False;
                    Py_INCREF(success_obj);
                    PyObject *reason_obj = PyUnicode_FromString(event.reason.c_str());

                    if (!sample_index_obj || !from_row_obj || !to_row_obj || !from_count_obj || !to_count_obj ||
                        !delta_obj || !kind_obj || !reason_obj)
                    {
                        Py_XDECREF(sample_index_obj);
                        Py_XDECREF(from_row_obj);
                        Py_XDECREF(to_row_obj);
                        Py_XDECREF(from_count_obj);
                        Py_XDECREF(to_count_obj);
                        Py_XDECREF(delta_obj);
                        Py_XDECREF(kind_obj);
                        Py_XDECREF(success_obj);
                        Py_XDECREF(reason_obj);
                        Py_DECREF(event_obj);
                        ok = false;
                        break;
                    }

                    PyDict_SetItemString(event_obj, "sample_index", sample_index_obj);
                    PyDict_SetItemString(event_obj, "from_row", from_row_obj);
                    PyDict_SetItemString(event_obj, "to_row", to_row_obj);
                    PyDict_SetItemString(event_obj, "from_count", from_count_obj);
                    PyDict_SetItemString(event_obj, "to_count", to_count_obj);
                    PyDict_SetItemString(event_obj, "delta", delta_obj);
                    PyDict_SetItemString(event_obj, "kind", kind_obj);
                    PyDict_SetItemString(event_obj, "success", success_obj);
                    PyDict_SetItemString(event_obj, "reason", reason_obj);

                    Py_DECREF(sample_index_obj);
                    Py_DECREF(from_row_obj);
                    Py_DECREF(to_row_obj);
                    Py_DECREF(from_count_obj);
                    Py_DECREF(to_count_obj);
                    Py_DECREF(delta_obj);
                    Py_DECREF(kind_obj);
                    Py_DECREF(success_obj);
                    Py_DECREF(reason_obj);

                    PyList_SET_ITEM(events_obj, static_cast<Py_ssize_t>(i), event_obj);
                }

                if (ok)
                {
                    PyDict_SetItemString(diagnostics, "transition_event_history", events_obj);
                    Py_DECREF(events_obj);
                }
                else
                {
                    Py_DECREF(events_obj);
                }
            }
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
            attach_solver_metadata(result, payload.params_copy, "infeasible", false);
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
        attach_solver_metadata(res, params_copy, "infeasible", false);
        Py_DECREF(params_copy);
        return res;
    }

    // ── Domain diagnostics aggregation ────────────────────────────────────────

    long coverage_point_count_for_quads(const std::vector<std::vector<int>> &quad_list)
    {
        std::unordered_set<int> covered;
        for (const auto &q : quad_list)
        {
            for (int idx : q)
            {
                if (idx >= 0)
                {
                    covered.insert(idx);
                }
            }
        }
        return static_cast<long>(covered.size());
    }

    void accumulate_surface_spacing_stats(
        const std::vector<FaceSample> &samples,
        long &surface_spacing_active_nodes,
        long &surface_spacing_total_nodes,
        long &surface_spacing_frontier_pops,
        long &surface_spacing_frontier_accepts,
        long &surface_spacing_candidate_quads,
        long &surface_spacing_selected_quads,
        long &per_row_active_cols_min,
        long &per_row_active_cols_max,
        double &per_row_active_cols_mean,
        long &topology_transition_count,
        long &topology_split_count,
        long &topology_merge_count,
        long &topology_transition_fail_count,
        std::vector<long> &per_row_counts,
        std::vector<long> &per_row_transitions_in_counts,
        std::vector<long> &per_row_transitions_out_counts,
        std::vector<TransitionEventSample> &transition_event_history)
    {
        surface_spacing_active_nodes = 0;
        surface_spacing_total_nodes = 0;
        surface_spacing_frontier_pops = 0;
        surface_spacing_frontier_accepts = 0;
        surface_spacing_candidate_quads = 0;
        surface_spacing_selected_quads = 0;
        per_row_active_cols_min = 0;
        per_row_active_cols_max = 0;
        per_row_active_cols_mean = 0.0;
        topology_transition_count = 0;
        topology_split_count = 0;
        topology_merge_count = 0;
        topology_transition_fail_count = 0;
        per_row_counts.clear();
        per_row_transitions_in_counts.clear();
        per_row_transitions_out_counts.clear();
        transition_event_history.clear();

        double per_row_mean_sum = 0.0;
        long sample_count = 0;
        bool first_sample = true;
        for (size_t sample_idx = 0; sample_idx < samples.size(); ++sample_idx)
        {
            const auto &sample = samples[sample_idx];
            surface_spacing_active_nodes += sample.surface_spacing_active_nodes;
            surface_spacing_total_nodes += sample.surface_spacing_total_nodes;
            surface_spacing_frontier_pops += sample.surface_spacing_frontier_pops;
            surface_spacing_frontier_accepts += sample.surface_spacing_frontier_accepts;
            surface_spacing_candidate_quads += sample.surface_spacing_candidate_quads;
            surface_spacing_selected_quads += sample.surface_spacing_selected_quads;
            topology_transition_count += sample.topology_transition_count;
            topology_split_count += sample.topology_split_count;
            topology_merge_count += sample.topology_merge_count;
            topology_transition_fail_count += sample.topology_transition_fail_count;
            for (long count : sample.per_row_counts)
            {
                if (count > 0)
                {
                    per_row_counts.push_back(count);
                }
            }
            for (long count : sample.per_row_transitions_in_counts)
            {
                per_row_transitions_in_counts.push_back(count);
            }
            for (long count : sample.per_row_transitions_out_counts)
            {
                per_row_transitions_out_counts.push_back(count);
            }
            for (const auto &event : sample.transition_event_history)
            {
                TransitionEventSample out = event;
                out.sample_index = static_cast<int>(sample_idx);
                transition_event_history.push_back(std::move(out));
            }

            if (sample.per_row_active_cols_max > 0)
            {
                if (first_sample)
                {
                    per_row_active_cols_min = sample.per_row_active_cols_min;
                    per_row_active_cols_max = sample.per_row_active_cols_max;
                    first_sample = false;
                }
                else
                {
                    if (sample.per_row_active_cols_min < per_row_active_cols_min)
                    {
                        per_row_active_cols_min = sample.per_row_active_cols_min;
                    }
                    if (sample.per_row_active_cols_max > per_row_active_cols_max)
                    {
                        per_row_active_cols_max = sample.per_row_active_cols_max;
                    }
                }
                per_row_mean_sum += sample.per_row_active_cols_mean;
                sample_count++;
            }
        }
        if (sample_count > 0)
        {
            per_row_active_cols_mean = per_row_mean_sum / static_cast<double>(sample_count);
        }
    }

    void attach_result_diagnostics(
        PyObject *result,
        PyObject *params_copy,
        const SolverDiagnosticsInput &input)
    {
        const bool converged = !(input.acp_energy_mode && input.edge_violations > 0);
        const char *termination_reason = converged ? "converged" : "max_iterations";

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
                input.transition_event_history);
            attach_solver_metadata(result, params_copy, termination_reason, converged, diagnostics);
            Py_DECREF(diagnostics);
            return;
        }

        attach_solver_metadata(result, params_copy, termination_reason, converged, nullptr);
    }

} // namespace fishnet_internal
