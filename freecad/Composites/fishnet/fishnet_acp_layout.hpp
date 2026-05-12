#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <string>
#include <vector>

#include "fishnet_options_api.hpp"

namespace fishnet_internal
{

    std::vector<std::vector<int>> build_vertex_adjacency(
        size_t point_count,
        const std::vector<std::pair<int, int>> &edges);
    int nearest_point_index(const std::vector<Vec3> &points, const Vec3 &target);

    struct PrimaryAxisSelectionInfo
    {
        Vec3 axis{1.0, 0.0, 0.0};
        std::string source{"default_unit_x"};
        double request_alignment_cos{0.0};
    };

    PrimaryAxisSelectionInfo choose_primary_axis_with_analysis(
        const std::vector<Vec3> &local_points,
        const Vec3 &x_axis,
        const Vec3 &y_axis,
        const NormalizedParams *params);
    Vec3 choose_primary_axis(
        const std::vector<Vec3> &local_points,
        const Vec3 &x_axis,
        const Vec3 &y_axis,
        const NormalizedParams *params);
    AcpPropagationSummary initialize_acp_layout(
        const std::vector<Vec3> &mesh_points,
        const std::vector<Vec3> &local_points,
        const std::vector<std::pair<int, int>> &edges,
        const Vec3 &x_axis,
        const Vec3 &y_axis,
        double nominal_edge_length,
        const NormalizedParams *params,
        std::vector<Vec3> &fabric_points);
    void build_acp_edge_objective(
        const std::vector<Vec3> &local_points,
        const std::vector<std::pair<int, int>> &edges,
        const std::vector<std::vector<int>> &objective_quads,
        double nominal_edge_length,
        const Vec3 &primary_axis,
        const std::string &material_model,
        double ud_coefficient,
        bool thickness_correction,
        double objective_p_norm,
        double pre_shear_deg,
        double objective_shear_weight,
        double objective_fiber_weight,
        double objective_cell_gain,
        AcpObjectiveSummary &objective_summary,
        std::vector<double> &edge_targets,
        std::vector<double> &edge_weights);

} // namespace fishnet_internal
