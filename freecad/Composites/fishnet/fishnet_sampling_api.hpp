#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <array>
#include <vector>

#include <TopoDS_Face.hxx>

#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal
{

    struct FaceSample
    {
        std::vector<Vec3> points;
        std::vector<Vec3> layout_points;
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
        long per_row_active_cols_min{0};
        long per_row_active_cols_max{0};
        double per_row_active_cols_mean{0.0};
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
        ExperimentalSolveStats *experimental_stats);

} // namespace fishnet_internal
