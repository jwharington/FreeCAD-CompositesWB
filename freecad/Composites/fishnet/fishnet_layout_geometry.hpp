#pragma once

#include "fishnet_layout_geometry_api.hpp"

namespace fishnet_internal
{

    Vec3 centroid(const std::vector<Vec3> &points);
    void build_basis(
        const std::vector<Vec3> &points,
        const std::vector<std::array<int, 3>> &faces,
        Vec3 &normal,
        Vec3 &x_axis,
        Vec3 &y_axis);
    Vec3 project_point(
        const Vec3 &point,
        const Vec3 &origin,
        const Vec3 &x_axis,
        const Vec3 &y_axis,
        const Vec3 &normal);
    std::vector<std::vector<int>> boundary_loops(
        const std::vector<std::array<int, 3>> &faces);
    std::vector<std::array<double, 3>> face_strains(
        const std::vector<std::array<int, 3>> &faces,
        const std::vector<Vec3> &local_points,
        const Vec3 &normal);
    std::vector<int> order_quad_indices(
        const std::vector<int> &indices,
        const std::vector<Vec3> &points);
    std::vector<std::vector<int>> extract_quads(
        const std::vector<std::array<int, 3>> &faces,
        const std::vector<Vec3> &points);
    std::vector<Vec3> loop_to_points(
        const std::vector<int> &loop,
        const std::vector<Vec3> &fabric_points);
    std::array<std::array<double, 2>, 4> quad_poly2d(
        const std::vector<Vec3> &points,
        const std::vector<int> &quad);
    std::vector<AtlasChartBuild> split_into_non_overlapping_charts(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::vector<int>> &quads,
        int &overlap_rejections);
    double point_set_span(const std::vector<Vec3> &pts);
    void transfer_layout_between_faces(const FaceSample &prev, FaceSample &curr);
    bool ensure_part_module_loaded();

} // namespace fishnet_internal
