#pragma once

#include <array>
#include <unordered_map>
#include <utility>
#include <vector>

#include "fishnet_algorithm_types.hpp"
#include "fishnet_sampling_api.hpp"

namespace fishnet_internal
{

    struct AtlasChartBuild
    {
        std::vector<Vec3> points;
        std::vector<std::vector<int>> quads;
        std::vector<std::array<std::array<double, 2>, 4>> quad_polys;
        std::unordered_map<int, int> global_to_local;
    };

    double orient2(const std::array<double, 2> &a, const std::array<double, 2> &b, const std::array<double, 2> &c);
    bool segment_intersect_proper(
        const std::array<double, 2> &a,
        const std::array<double, 2> &b,
        const std::array<double, 2> &c,
        const std::array<double, 2> &d,
        double eps);
    bool point_in_triangle_proper(
        const std::array<double, 2> &p,
        const std::array<double, 2> &a,
        const std::array<double, 2> &b,
        const std::array<double, 2> &c,
        double eps);
    bool triangles_overlap_proper(
        const std::array<std::array<double, 2>, 3> &t1,
        const std::array<std::array<double, 2>, 3> &t2,
        double eps);
    bool quads_overlap(
        const std::array<std::array<double, 2>, 4> &qa,
        const std::array<std::array<double, 2>, 4> &qb,
        double eps);
    bool segment_triangle_intersect_3d(
        const Vec3 &p0,
        const Vec3 &p1,
        const std::array<Vec3, 3> &tri,
        double eps);
    bool triangles_overlap_3d(
        const std::array<Vec3, 3> &t1,
        const std::array<Vec3, 3> &t2,
        double eps);
    bool quads_overlap_3d(
        const std::vector<Vec3> &points,
        const std::array<int, 4> &qa,
        const std::array<int, 4> &qb,
        double eps);
    std::vector<std::pair<int, int>> perimeter_edges_from_quads(const std::vector<std::vector<int>> &quads);
    std::vector<std::pair<int, int>> edges_from_triangles(const std::vector<std::array<int, 3>> &triangles);

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
    std::array<std::array<double, 2>, 4> quad_poly2d(const std::vector<Vec3> &points, const std::vector<int> &quad);
    std::vector<AtlasChartBuild> split_into_non_overlapping_charts(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::vector<int>> &quads,
        int &overlap_rejections);
    double point_set_span(const std::vector<Vec3> &pts);

    void relax_fabric_points_with_edge_constraints(
        std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &edges,
        const std::vector<std::vector<int>> &boundary_loops,
        double requested_nominal_edge_length,
        int iterations,
        std::vector<double> *residual_history,
        std::vector<double> *combined_objective_history,
        const std::vector<double> *edge_targets,
        const std::vector<double> *edge_weights,
        double objective_p_norm);

} // namespace fishnet_internal
