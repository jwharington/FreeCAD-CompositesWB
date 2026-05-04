#pragma once

#include <array>
#include <vector>

#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal {

struct AtlasChartBuild;
struct FaceSample;

namespace boundary_atlas {

std::vector<std::vector<int>> boundary_loops(
    const std::vector<std::array<int, 3>> &faces
);

std::vector<Vec3> loop_to_points(
    const std::vector<int> &loop,
    const std::vector<Vec3> &fabric_points
);

std::array<std::array<double, 2>, 4> quad_poly2d(
    const std::vector<Vec3> &points,
    const std::vector<int> &quad
);

std::vector<AtlasChartBuild> split_into_non_overlapping_charts(
    const std::vector<Vec3> &fabric_points,
    const std::vector<std::vector<int>> &quads,
    int &overlap_rejections
);

void transfer_layout_between_faces(const FaceSample &prev, FaceSample &curr);

}  // namespace boundary_atlas

}  // namespace fishnet_internal
