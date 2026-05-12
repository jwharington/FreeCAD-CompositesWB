#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

#include "fishnet_diagnostics_api.hpp"
#include "fishnet_options_api.hpp"
#include "fishnet_python_util.hpp"

namespace fishnet_internal
{

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
        const std::vector<TransitionEventSample> &transition_event_history,
        bool surface_spacing_strict_enabled,
        bool surface_spacing_strict_fail_on_violation,
        double surface_spacing_strict_tolerance,
        long surface_spacing_strict_edge_count,
        long surface_spacing_strict_violation_count,
        double surface_spacing_strict_max_rel_error,
        bool surface_spacing_strict_pass,
        long surface_spacing_strict_repair_passes,
        const std::string &surface_spacing_strict_fail_reason)
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
        const char *threshold_source = rel_tol_from_parameter ? "parameter:edge_length_tolerance" : "default:edge_length_tolerance";
        if (surface_spacing_strict_enabled)
        {
            threshold_source = rel_tol_from_parameter ? "parameter:surface_spacing_edge_tolerance" : "default:surface_spacing_edge_tolerance";
        }
        set_diag_string(diagnostics, "stop_threshold_source", threshold_source);

        PyDict_SetItemString(diagnostics, "surface_spacing_strict_enabled", surface_spacing_strict_enabled ? Py_True : Py_False);
        PyDict_SetItemString(diagnostics, "surface_spacing_strict_fail_on_violation", surface_spacing_strict_fail_on_violation ? Py_True : Py_False);
        set_diag_double(diagnostics, "surface_spacing_strict_tolerance", surface_spacing_strict_tolerance);
        set_diag_long(diagnostics, "surface_spacing_strict_edge_count", surface_spacing_strict_edge_count);
        set_diag_long(diagnostics, "surface_spacing_strict_violation_count", surface_spacing_strict_violation_count);
        set_diag_double(diagnostics, "surface_spacing_strict_max_rel_error", surface_spacing_strict_max_rel_error);
        PyDict_SetItemString(diagnostics, "surface_spacing_strict_pass", surface_spacing_strict_pass ? Py_True : Py_False);
        set_diag_long(diagnostics, "surface_spacing_strict_repair_passes", surface_spacing_strict_repair_passes);
        set_diag_string(diagnostics, "surface_spacing_strict_fail_reason", surface_spacing_strict_fail_reason.c_str());

        if (surface_spacing_strict_enabled && !surface_spacing_strict_pass)
        {
            std::string stop_reason_detail = "surface_spacing_strict_violations_after_repair";
            if (surface_spacing_strict_fail_reason == "insufficient_coverage")
            {
                stop_reason_detail = "surface_spacing_strict_insufficient_coverage";
            }
            else if (surface_spacing_strict_fail_reason == "infeasible_geometry")
            {
                stop_reason_detail = "surface_spacing_strict_infeasible_geometry";
            }
            set_diag_string(diagnostics, "stop_reason_detail", stop_reason_detail.c_str());
        }

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

} // namespace fishnet_internal
