#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <array>
#include <string>
#include <vector>

#include <TopoDS_Face.hxx>

#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal
{

    struct TransitionEventSample
    {
        int sample_index{-1};
        int from_row{-1};
        int to_row{-1};
        int from_count{0};
        int to_count{0};
        int delta{0};
        std::string kind{"none"};
        bool success{true};
        std::string reason;
    };

    struct FaceSample
    {
        std::vector<Vec3> points;
        std::vector<Vec3> layout_points;
        std::vector<std::array<double, 2>> point_uv;
        std::vector<unsigned char> point_face_state;
        std::vector<std::array<int, 3>> triangles;
        std::vector<std::vector<int>> quads;
        Vec3 origin{0.0, 0.0, 0.0};
        Vec3 normal{0.0, 0.0, 1.0};
        Vec3 x_axis{1.0, 0.0, 0.0};
        Vec3 y_axis{0.0, 1.0, 0.0};
        long surface_spacing_active_nodes{0};
        long surface_spacing_total_nodes{0};
        long surface_spacing_frontier_pops{0};
        long surface_spacing_frontier_accepts{0};
        long surface_spacing_candidate_quads{0};
        long surface_spacing_selected_quads{0};
        long boundary_reference_mode_enabled{0};
        long boundary_reference_fibre_count{0};
        long boundary_reference_arm_target_count{0};
        long boundary_reference_arm_attempt_count{0};
        long boundary_reference_arm_success_count{0};
        long boundary_reference_arm_boundary_hit_count{0};
        long boundary_reference_arm_failure_count{0};
        double boundary_reference_arm_success_ratio{0.0};
        long boundary_reference_seed_commit_success_count{0};
        long boundary_reference_seed_commit_failure_count{0};
        long boundary_reference_step_attempt_count{0};
        long boundary_reference_step_success_count{0};
        long boundary_reference_step_failure_count{0};
        double boundary_reference_step_success_ratio{0.0};
        long boundary_reference_step_backtrack_count{0};
        long boundary_reference_step_candidate_attempt_count{0};
        long boundary_reference_step_candidate_outside_face_count{0};
        long boundary_reference_step_candidate_evaluation_failure_count{0};
        long boundary_reference_step_terminal_state_in_count{0};
        long boundary_reference_step_terminal_state_on_count{0};
        long boundary_reference_step_terminal_state_unknown_count{0};
        long boundary_reference_failure_geodesic_step_count{0};
        long boundary_reference_failure_degenerate_frame_count{0};
        long boundary_reference_failure_singular_metric_count{0};
        long boundary_reference_failure_stalled_count{0};
        long boundary_reference_failure_outside_face_count{0};
        long boundary_reference_failure_evaluation_count{0};
        long boundary_reference_failure_unknown_count{0};
        long boundary_reference_failure_node_commit_count{0};
        long boundary_reference_covered_node_count{0};
        long boundary_reference_total_node_count{0};
        double boundary_reference_coverage_ratio{0.0};
        long per_row_active_cols_min{0};
        long per_row_active_cols_max{0};
        double per_row_active_cols_mean{0.0};
        long topology_transition_count{0};
        long topology_split_count{0};
        long topology_merge_count{0};
        long topology_transition_fail_count{0};
        std::vector<long> per_row_counts;
        std::vector<long> per_row_transitions_in_counts;
        std::vector<long> per_row_transitions_out_counts;
        std::vector<TransitionEventSample> transition_event_history;
    };

    struct ExperimentalSolveStats
    {
        int calls{0};
        int base_failures{0};
        int seed_attempts{0};
        int seed_solved{0};
        int seed_local{0};
        int better_candidate_hits{0};
        int fallback_count{0};
        double improvement_sum{0.0};
        double best_shift_norm_sum{0.0};
        double best_shift_norm_max{0.0};
    };

    void transfer_layout_between_faces(const FaceSample &prev, FaceSample &curr);
    bool ensure_part_module_loaded();
    FaceSample sample_face(
        const TopoDS_Face &face,
        double max_length,
        CurrentNodeSolverMode solver_mode,
        double max_adjacent_normal_angle,
        double max_local_fold_ratio,
        double max_shear_angle,
        bool surface_spacing_refine,
        int surface_spacing_relax_iterations,
        bool boundary_extend,
        ExperimentalSolveStats *experimental_stats,
        bool paper_alignment_boundary_reference = false,
        bool paper_alignment_directional_reference = false,
        bool paper_alignment_has_reference_direction_request = false,
        const Vec3 &paper_alignment_reference_direction = Vec3{1.0, 0.0, 0.0});

} // namespace fishnet_internal
