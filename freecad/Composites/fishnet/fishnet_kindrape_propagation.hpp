#pragma once

#include <vector>

#include "fishnet_algorithm_types.hpp"
#include "fishnet_options_api.hpp"

namespace fishnet_internal
{

    void run_kindrape_scheduler_skeleton(
        const std::vector<Vec3> &local_points,
        const std::vector<std::vector<int>> &adjacency,
        int seed_index,
        double nominal_edge_length,
        const Vec3 &primary_axis,
        const Vec3 &orthogonal_axis,
        std::vector<double> &x_coord,
        std::vector<double> &y_coord,
        AcpPropagationSummary &summary);

} // namespace fishnet_internal
