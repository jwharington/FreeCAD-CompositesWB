#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <vector>

#include "fishnet_algorithm_types.hpp"
#include "fishnet_options_api.hpp"
#include "fishnet_sampling_api.hpp"

namespace fishnet_internal
{

    struct SeamContinuityStats
    {
        int group_count{0};
        double mean_min_distance{0.0};
        double max_min_distance{0.0};
    };

    double mean_planar_edge_length(
        const std::vector<Vec3> &points,
        const std::vector<std::pair<int, int>> &edges);
    double infer_nominal_edge_length(
        double requested,
        const std::vector<Vec3> &fallback_points,
        const std::vector<std::pair<int, int>> &edges);
    double max_edge_relative_error_for_edges(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &edges,
        double requested_nominal_edge_length);
    double max_edge_relative_error_for_targets(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &edges,
        const std::vector<double> &edge_targets,
        double fallback_nominal_edge_length);
    std::pair<int, double> edge_length_violation_summary_for_targets(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &edges,
        const std::vector<double> &edge_targets,
        double fallback_nominal_edge_length,
        double rel_tol);
    std::pair<int, double> edge_length_violation_summary_for_edges(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &edges,
        double requested_nominal_edge_length,
        double rel_tol);
    SeamContinuityStats seam_layout_continuity_summary(
        const std::vector<Vec3> &mesh_points,
        const std::vector<Vec3> &fabric_points,
        double position_tol);

    // ── Domain diagnostics aggregation ──────────────────────────────────────
    // These are pure domain values; no Python object construction required.

    struct SolverDiagnosticsInput
    {
        long sample_count;
        long point_count;
        long triangle_count;
        long quad_count;
        long orientation_break_count;
        int edge_violations;
        double max_rel_error;
        double rel_tol;
        bool rel_tol_from_parameter;
        int max_iterations;
        const std::vector<double> &residual_history;
        const std::vector<double> &combined_objective_history;
        bool acp_energy_mode;
        const AcpPropagationSummary &acp_summary;
        const AcpObjectiveSummary &objective_summary;
        long coverage_point_count;
        long surface_spacing_active_nodes;
        long surface_spacing_total_nodes;
        long surface_spacing_frontier_pops;
        long surface_spacing_frontier_accepts;
        long surface_spacing_candidate_quads;
        long surface_spacing_selected_quads;
        long per_row_active_cols_min;
        long per_row_active_cols_max;
        double per_row_active_cols_mean;
        long topology_transition_count;
        long topology_split_count;
        long topology_merge_count;
        long topology_transition_fail_count;
        const std::vector<long> &per_row_counts;
    };

    long coverage_point_count_for_quads(const std::vector<std::vector<int>> &quad_list);

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
        std::vector<long> &per_row_counts);

    void set_diag_long(PyObject *diagnostics, const char *key, long value);
    void set_diag_double(PyObject *diagnostics, const char *key, double value);
    void set_diag_string(PyObject *diagnostics, const char *key, const char *value);
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
        const std::vector<long> &per_row_counts);

    void attach_result_diagnostics(
        PyObject *result,
        PyObject *params_copy,
        const SolverDiagnosticsInput &input);

} // namespace fishnet_internal
